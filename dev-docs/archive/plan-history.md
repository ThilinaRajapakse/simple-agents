# Plan history — the record of items already built

**Moved verbatim out of `plan.md` on 2026-08-06**, when §3.1 had grown to roughly 380 lines of
history against 60 lines of plan. Nothing here was rewritten; each section is the item's entry
as `plan.md` carried it.

**This file is for one question: was this already decided, and why.** It is not read
top to bottom. `plan.md` carries what is still to build; a build log carries how an item was
actually built and what it found; the shipped documents in `docs/` are authoritative on what
the library does today.

**Where the fuller record is.** Items 8c, 8d, 8e, 8f, 9, 8a, 8g and 8b each have a build log under
`build-logs/`, written while building rather than reconstructed, and it supersedes the entry
here wherever the two differ. Items 5 and 7 also have `runs/checkpoint-item5/findings.md` and
`runs/checkpoint-item7/findings.md`.

The sections are in build order: 1 → 8, 8c → 8f, 9, 8a, 8g, 8b.

---

## Item 1 — `docs/failure-taxonomy.md`

1. **`docs/failure-taxonomy.md`** — written first, before any code. Seed list in `simple-agents.md` §7. Each entry maps to a conformance check, or is explicitly marked as one that cannot be checked. **Written; 27 entries.** The seed list of 14 grew for two reasons, both recorded per entry in the document: eight failures were named in `simple-agents.md` as requirements without a corresponding seed entry (offline eval, seed control, secret redaction, context truncation, tool docstrings and contract tests, per-node metrics, ablation, elicitation), and four seed entries were each carrying two distinct failures that need different fixes. Taxonomy size is not v0 build scope — see item 9.

---

## Item 2 — `docs/trajectory-format.md`

2. **`docs/trajectory-format.md`** — written second, before anything reads it. Summary in `simple-agents.md` §6. **Written; now at version `0.8`.** Not "frozen" — per the amended §9.7 it is versioned and pre-adoption, so a breaking change is allowed while no project depends on it, provided it bumps the version and lands in the changelog. Phase 1 is exactly when such a change is most likely and least costly.
   - **Rewritten at the document review, 2026-07-30**, and the version history moved out to `design/trajectory-format-changelog.md`, which is now where a format bump's reasoning goes. `CHANGELOG.md` at the repository root is new and carries what a builder needs; this plan's §3.1 and that file are the two places a bump is recorded.
   - **What the document owns, settled with Thilina:** the record on disk, its fields, their types, and how to read them without getting wrong numbers. It does not own the mechanism that produces a field's value, and it does not own a concept that exists in the library outside the record. That rule moved cost to `docs/run-envelope.md` §4 (which already owned the bases, and where the compute formula was being stated twice), the OpenTelemetry argument to `simple-agents.md` §6, the `error` concept to `docs/tools.md` §1.3, and `unknown` to the new `docs/pipeline.md` §4.

---

## Item 3 — Agent shape

3. **Agent shape** — three node kinds, pipeline as a list of callables plus a run context. No graph engine. *(That last clause is superseded by item 8c, 2026-08-03: the pipeline becomes a directed graph over the same three node kinds. Everything else in this entry stands, including the fan-out precedent it records, which is the argument routing was decided on.)* **Built 2026-07-26** (`src/simple_agents/`, 65 tests). **Amended 2026-07-27 by the item 5 checkpoint** (`runs/checkpoint-item5/findings.md`): `LLMNode` records its own failure, `max_steps` is charged per model call under every kind rather than only inside the agent loop, duplicate `node_id`s are refused, `RunResult` lost a field that could never be set and gained the manifest accessors two sessions hand-rolled, and `LLMNode` gained `over=` for fan-out. Fan-out is a property of a node and not a fourth kind, which leaves do-not-change #8 and #12 intact; the rule that came out of it is that a pipeline covers a variable number of *calls* and a graph covers a variable set of *nodes*. The governing principle, which the code enforces rather than documents: *the node kind is a promise the library keeps, not a label the builder applies.* `Deterministic` is never handed a model client; `LLMNode` takes a prompt builder and the library makes the single call; `AgentNode` is the only kind that owns a loop. If a node kind could be wrong, `node_kind` would be a field that lies and FT-11, per-node metrics and ablation would all be reading it.

---

## Item 4 — Run envelope

4. **Run envelope** — manifest, seeds, trajectory log, cassette record/replay. **Built 2026-07-26.** Shipped as `docs/run-envelope.md`, which is authoritative on detail; this entry records only the decisions and why they were taken. Five decisions, in the order they were made:
   - **The envelope is split by lifetime, with no overlap.** `RunEnvelope` holds what is constant across runs of a project (run directory, cost basis, redaction, cassette); `Pipeline.run` holds what varies (inputs, model, seed, run id). The alternative considered was the Simple Transformers shape — a config object plus per-call overrides — and it was rejected because two ways to set one value is exactly the ambiguity that makes a coding agent pick one at random, and the docs are a prompt surface. The split is forced by item 8 in any case: the eval runner does k×n runs sharing a cost basis and a cassette, varying only the seed.
   - **Cassettes are keyed by a strict content hash**, over model identity, messages, params, tools and seed, and a miss reports what differs from the nearest recorded request in that node. This closes `simple-agents.md` §11 open question 4 and `docs/trajectory-format.md` open question 1. The rejected alternative was an ordinal fallback, which survives a prompt edit by replaying the response recorded against the *old* prompt: the eval then runs green, offline, and reports a number the current code never produced. That is FT-14 and FT-15's failure arriving through the replay layer, and it is silent. Red CI on a prompt edit is the correct behaviour, and re-recording is the fix.

     *Amended at item 8:* re-recording is no longer the only fix, and the three modes became four. `Cassette.update` serves what is on file and calls live for what is not, so an edited prompt costs one call rather than the whole run. **It does not reopen what this entry refused.** The ordinal fallback served the *old* response for a *new* request; an edited request here has no entry, so it is answered live and filed under the new key, and the old entry is never served for it. Item 8's own entry carries the measurement that motivated it.
   - **Cassettes cover tool calls as well as model calls.** FT-20 routes non-`read_only` tools through the cassette and FT-21 needs every external call replayable, so a model-only cassette would have to be rebuilt at item 8.
   - **Seeds are generated when absent, recorded once, and derived per call** from `(run_seed, node_id, call_index)`. Reproducibility does not depend on the builder remembering to ask for it, and one integer in the manifest reconstructs every call in the run. A run-level refusal was considered and rejected: it fails the cheapest possible first run on something the library can decide correctly itself, which is the over-refusal that gets suites disabled.
   - **`max_cost` is enforced against the derived figure, including an upper bound**, reversing the position recorded in item 3's code. The argument is in `simple-agents.md` §2.3. A pipeline setting `max_cost` with no declared basis is refused before it runs.

---

## Item 5 — Model client seam

5. **Model client seam** — thin, with pinning recorded. **Built 2026-07-26** (`src/simple_agents/adapters/`, 250 tests in total). Amended 2026-07-26: the seam is two methods, `complete` and `identity`, not one. Item 4's cassette key must include the model identity and must be computable before the call is made, and no other source can supply it. An adapter therefore reports `ModelIdentity(backend, request_model, model_revision)` from its own configuration. This satisfies the rule in `simple-agents.md` §2.5 that every field in the common surface is one the library itself reads: the key reads it, and so does the manifest. **Dual backend from v0** (decided 2026-07-26): a hosted API and self-hosted open-weight models served by vLLM, behind one interface. Both from the start rather than one now and one later, because an interface designed against a single backend encodes that backend's assumptions without anyone noticing — and the two differ in ways that reach the trajectory format: cost basis, revision pinning, and cache semantics all fork on the backend (`docs/trajectory-format.md` §4.1, and `docs/run-envelope.md` §4). Constrained decoding (outlines / xgrammar / vLLM guided decoding) is available if the `unknown` branch proves unreliable on open weights; it is not committed for v0.

   **The kickoff decisions held.** Mistral on the free tier as the hosted backend; the adapter records an alias faithfully rather than refusing it, so FT-14's judgement stays in one check instead of spreading across every adapter; the cost basis is the published paid rates, so FT-27 and the two-basis machinery are exercised rather than sitting at `0.00`; and the contract tests run with no key and no network. The suite is runnable by someone who has never held a Mistral key, and `MistralClient(api_key="not-used-in-replay")` is what the replay tests construct.

   **What the probe measured, before any adapter was written.** The kickoff note said to verify the lineup rather than trust a description, and that was right. A throwaway script made one call per question against both backends and dumped the raw JSON, which cost twenty minutes and corrected three assumptions:
   - **Mistral's ids are `YYMM`-dated** (`mistral-small-2603`, `mistral-large-2512`), not the marketing names on the models page. `-latest` aliases exist alongside them, so the FT-14 reasoning above is unchanged.
   - **`GET /v1/models` publishes aliases symmetrically and marks no canonical form.** `mistral-small-2603` lists `mistral-small-latest` as its alias and the reverse also holds. The provider does not say which is the pin, which is independent support for keeping that judgement in FT-14: string shape is the only available signal, and it is ours to interpret.
   - **A response echoes back the identifier that was sent**, so on this backend `models.observed` cannot reveal a substitution and adds nothing over `configured`. Worth knowing before FT-14 is written against it.
   - **Prompt caching is opt-in on Mistral and automatic on vLLM.** The open question closed cleanly: `prompt_tokens` includes `prompt_tokens_details.cached_tokens`, so `input_uncached` is the difference, and with no `prompt_cache_key` sent the reported `0` is a measurement rather than a guess.
   - **The free tier is 50 requests and 50,000 tokens per minute**, published on every response header rather than in the documentation.

   **Four decisions taken while building, in the order they were made:**
   - **`httpx` is the one new dependency.** Both backends are JSON over HTTPS, so one client serves both adapters, and `MockTransport` gives the offline tests a seam that needs no monkeypatching. The alternatives were stdlib `urllib` (hand-rolled timeouts and retries, and a worse test seam) and the vendor SDKs (two dependencies that churn monthly, in a library whose architecture exists to absorb churn in adapters).
   - **The trajectory format went to `0.4`.** vLLM reports the cache split only when its server carries `--enable-prompt-tokens-details`; without the flag it reports the prompt size alone. `0.4` states that the three input counts are disjoint, and that where only the total is available it goes in `input_uncached` with the two cache counts `unknown`. A `0.3` reader cannot tell which convention wrote a record, which is what the bump exists to say.
   - **A server missing that flag is warned about, not refused.** Refusing would block a builder pointed at a shared server they cannot restart, and recording `0` would be a claim about something nobody measured. The adapter warns once per client, names the flag, and records the reason on the record itself, so a trajectory read later says what the warning said.
   - **Tests are layered, because a cassette cannot test an adapter.** The cassette stores a decoded `ModelResponse`, so replaying one never re-enters the adapter and proves nothing about how the wire format was read. Wire-level fixtures captured from the real backends test the translation; recorded cassettes test the envelope over real data. The kickoff note conflated the two, and this is the correction.

   **The layering paid for itself immediately.** A placeholder revision in the replay test produced a `CassetteMiss` naming `model_revision (recorded '70d244cc…', now '0000…')`. That is FT-14's failure arriving through the replay layer, refused rather than served, which is what item 4's strict content hash was chosen to do.

   **Two bugs in items 3 and 4 surfaced the moment an `AgentNode` met a real model, and both were invisible to 236 passing tests.** `FakeModelClient` returns scripted responses without reading the request, so the loop's own output had never been seen by anything that validates it. This is the general lesson and it applies to every item still to come: a fake that ignores its input tests the caller and nothing else.
   - **`@tool` never derived a parameter schema from the signature.** It defaulted to an empty object schema, so a tool taking arguments was advertised to the model as taking none, the model called it with `{}`, and the run died inside the library. Schemas are now derived from the annotations. This is `simple-agents.md` §8.2's "typed signature" clause landing early, at item 5 rather than item 7, because without it an `AgentNode` could not be used with any tool that takes an argument.
   - **The conversation an `AgentNode` builds is not what a backend accepts.** It records a tool call as `{id, name, arguments}` with the arguments as a dict; both backends want it nested under `function` with the arguments serialized, and Mistral answers anything else with a 422. Translating the conversation is the adapter's job for the same reason translating tool declarations is, so `messages_to_wire` sits beside `tools_to_wire`.

   **`tests/cassettes/agent.jsonl` now covers the multi-turn path**, recorded from a real run: three model calls, four tool calls including two issued in one turn, terminating on `finish`. Nothing else exercises it, and nothing else would have caught either bug.

   **The docs ship inside the wheel** (2026-07-26). The package carried only `simple_agents/*.py` while nine docstrings cited `docs/*.md` by path, so every one of those references dangled for anyone installing from PyPI, and `prose_check` could not see it because it resolves those paths against the repository. `force-include` maps `docs/` to `simple_agents/docs/`, so the same relative path resolves in both places with no reference rewritten, and `docs_path()` returns the directory. This is a partial answer to `simple-agents.md` §11 open question 7: the documentation's distribution is settled, the skill's is not.

---

## Item 6 — Context builder

6. **Context builder** — pluggable, trivial default. **Built 2026-07-27** (`src/simple_agents/context_builder.py`, 304 tests in total). Shipped as `docs/context.md`, the fifth document in the wheel; `simple-agents.md` §2.4 carries the rationale. Six decisions, in the order they were made:
   - **One interface, one call site.** `build(messages, ctx)` plugged into `_call_model`, so every model call under every node kind builds once. The second application of the item 5 checkpoint's rule that one step is one model call everywhere. Set per node, no envelope-level default.
   - **The estimate is unavoidable, and the first design that denied it was circular.** The probe measured what is knowable: the window is published in tokens on `GET /v1/models`, the previous call's prompt size is exact, and the next unsent prompt is countable by nothing. Checking a measured previous size against a limit only fires after that call already exceeded, so it never predicts the next one. Overflow is therefore answered in two layers, the backend's refusal always and an optional pre-flight estimate whose *ratio* is measured from the previous call in the node.
   - **Only the error shape that was observed is matched.** Both backends answer 400 carrying `maximum context length`; the bodies are committed as wire fixtures. Neither carries a `usage` block or, on Mistral, the rate-limit headers, so **whether a rejected request consumes anything is unmeasured and nothing claims otherwise**. This is item 5's lesson applied before writing the classifier rather than after.
   - **The guard does not bind a single-call `LLMNode`**, because the ratio needs a previous call in the same run. Accepted rather than refused at construction: a single call has no earlier turns to waste, so the no-op costs nothing, unlike `max_steps` not binding. Refusing would need a node to introspect a separate object's configuration. Documented where the limit is set and pinned by a test.
   - **A `ContextOverflow` inside a fan-out is collected, not fatal.** One oversized document says nothing about the next, so it behaves like every other per-item failure. This is why the refusal cannot claim the run stops unconditionally, and why one helper decorates both overflow paths with what actually happened.
   - **The trajectory went to `0.5` and the manifest to `0.2`.** `model_call` gains a required `context` object, because FT-17 requires a truncation policy to record a truncation event and there was nowhere to record one. An empty `dropped` is a statement rather than an absence. `nodes[].context_builder` in the manifest is what lets a reader of an old run tell which builder produced it: a swapped builder changes the request without changing the prompt function's source hash, which is FT-15's failure by another route.

   **The live recording is what made the estimate worth anything.** A fan-out over three documents against Mistral: estimated 36 prompt tokens where the backend reported 40, then 40 where it reported 36. `FakeModelClient` returns a scripted token count without reading the request, so a fake run only measures a ratio the test chose. `tests/cassettes/context.jsonl` replays it offline. The existing three cassettes replayed unchanged, which is the evidence that `AppendAll` leaves every key identical.

---

## Item 7 — Tool registry and the minimal tool set

7. **Tool registry and the minimal tool set** — `simple-agents.md` §8.1, with the full contract §8.2. **Built 2026-07-27** (`src/simple_agents/builtins/`, 401 tests in total). Shipped as `docs/tools.md`, the sixth document in the wheel. Trajectory `0.6` and manifest `0.3`. Five decisions, in the order they were made:
   - **The registry is an explicit object the project constructs**, with no global default and no auto-registration from the decorator. A global mutable is a second source for one value, it makes test order significant, and two projects in one process would share a namespace, which is the ambiguity item 4 split the envelope to avoid. Having no registry at all was live, since `Tool` already refuses a missing side-effect class and `Pipeline` already writes every tool to the manifest; it was rejected because FT-19's and FT-23's static checks and item 8's runner all need to enumerate *every declared tool*, including one no node uses, and a list on a node is not that.
   - **`DeclaredCost` is typed and required only on a `spends_money` tool.** Requiring it everywhere would refuse `now`, whose cost is zero and whose declaration says nothing, which is the over-refusal that gets suites disabled. Requiring it where the figure is the point is what an evaluation needs before it multiplies it by k×n.
   - **A tool call's cassette key gained an occurrence count**, and this is the decision the item turned on. `runs/checkpoint-item5/findings.md` §6 had recorded the rule as "tools cannot see run state"; that is broader than its reason, which is only that the key must identify the answer. The count makes any *intra-run* impurity replay correctly, because within a run any two calls are ordered. It is not the ordinal fallback rejected at item 4: content hash **plus** ordinal is strictly more specific, so a changed argument still misses and still misses loudly. It also brings tool calls level with model calls, whose seed already derives from the call index and is in the key. **Every committed cassette holding tool calls was invalidated and re-recorded live.**
   - **Two handles, `ModelHandle` and `Workspace`, read off the signature rather than declared.** A tool taking either is not stored and runs again on replay. The alternative was a `re_executed` flag, rejected because a mode a coding agent has to classify into is a mode it will sometimes classify wrongly; deriving it from an annotation the tool needed anyway costs the author nothing. The rule such a tool must satisfy, carried into the docstring and the refusal, is that **it may reach the outside world only through the handles it was given**, and a handle beside `spends_money` or `irreversible` is refused. `parent_id` was redefined so a nested `model_call` hangs off its `tool_call`, which is the `0.6` bump.
   - **Extraction was nearly answered by "use an `LLMNode`", and the counter-argument is the one to keep.** The first proposal was to cut §8.1's extract-to-schema row on the grounds that `LLMNode(output_schema=...)`, or `over=` for many documents, already is LLM-backed typed extraction, and that a model call inside a tool has nowhere correct to be recorded. The first half is right at build time and wrong at run time: **an agent that decides mid-run it needs typed facts cannot add a node.** The second half was a real problem and is what the handle solves, since a stored tool is not run on replay and its nested call would leave no record, so a replay would write fewer records than the run it reproduces. No key expansion reaches that, because the fault is in record shape rather than in key selection.

   **Both live recordings paid, and differently.** `tests/cassettes/tools.jsonl` (Mistral) and `tools-vllm.jsonl` (Qwen3-1.7B) show the same record shape from two backends: a nested `model_call` parented to its `tool_call` and written before it, a stored `document_search`, and `extract_facts` and `workspace_write` re-run with no key. The replay test reads the offered tool schema out of the *recorded request*, so it asserts what a server accepted rather than what the library meant to send. The vLLM run also produced a wrong answer, because Qwen issued all four tool calls in one turn and so wrote `extract_facts`'s arguments before the search returned. That is model behaviour rather than a defect, a turn may legitimately carry several tool calls, and it is the kind of thing a `FakeModelClient` cannot produce.
   - **Two clauses of the contract landed early, at item 5, and this item inherits a smaller job.** The typed signature (§8.2 clause 1) now produces the JSON schema the model is shown, derived from the annotations, with `*args`, `**kwargs` and an unannotated parameter refused. Arguments are validated against it before the call, so a malformed call returns to the model as a `ModelFacingError` rather than ending the run, which is what `finish` already did. Neither was scope creep: an `AgentNode` could not be used with any tool taking an argument until the first was fixed, and the second is the same failure one turn later. What item 7 still owns is the registry, the built-in tools, their contract tests, and `declared_cost`.
   - **A limitation worth knowing before writing the built-in tools:** annotations resolve against the module the function was defined in, so a tool whose signature names a type declared inside a function is refused with a message naming `parameters=` as the way round it. Module-level types are the normal case and the shipped tools will all be module-level, so this is a boundary rather than a problem, but a builder writing a tool factory will meet it.
   - **The tool contract takes `pydantic.SecretStr` for credentials, and the HTTP fetch tool is its first caller** (decided 2026-07-26, at item 5). Redaction as built is detection-based: it matches known credential formats, sensitive field names, and values declared in `secret_env`. A secret in none of those categories was undetectable, which `docs/run-envelope.md` §6 admitted in as many words. A secret-carrying type closes that by matching on the type rather than the content. The writer half landed at item 5, because it was a live leak rather than new scope: `_fallback` unwrapped any object's `__dict__` after redaction had already run, so a credential one field inside a dataclass was written in full while the same credential in a dict was replaced. Normalizing before redaction fixed the ordering, and `docs/run-envelope.md` §6 now documents the type as a second declaration route. What is left for this item is the tool-facing half: the contract, the shipped tools that carry credentials, and the guidance. **Adopt pydantic's type rather than inventing one** — the docs are a prompt surface and a coding agent already knows `SecretStr`, so a bespoke equivalent would add a glossary term and buy nothing.
   - **Two limits to state wherever the type is documented, or it becomes the FT-16 ceiling problem in new clothes.** Python has no taint tracking, so `f"Bearer {token.get_secret_value()}"` is an ordinary string again and only the pattern rules see it: the type reduces accidents and guarantees nothing. And a cassette key is computed with `default=str`, so a `SecretStr` hashes as `**********` and two calls differing only in a typed secret collide onto one key, with the second replaying the first's response. Narrow, but it sits behind a type we are about to recommend.
   - **Every shipped tool lands with a contract test over handcrafted fixture data**, and the item is not done until they all have one. FT-23 requires this of a builder's tools, and a library that shipped `document_search` without one would be asking for a discipline it had not kept. The fixture is a handful of documents written for the test, with known content, so the assertion is on behaviour the test author fixed rather than on whatever a real corpus happens to contain. Contract tests exist to catch the docstring drifting from the code, and a docstring is prompt text the model reads to decide how to call the tool, so drift there surfaces as a reasoning failure and sends debugging to the wrong place.

---

## Item 8 — Eval machinery

8. **Eval machinery** — labeled sets with split tracking, k rollouts with seed control, bootstrap CIs, per-node metrics, false-confidence separated from recall. **Built 2026-07-29** (`src/simple_agents/evaluation/`, 565 tests in total). Shipped as `docs/evaluation.md`, the seventh document in the wheel. The results file is versioned on its own, at `eval_format_version` `0.1`; the trajectory format and the manifest are unchanged, which is the first item since 4 that needed neither.
   - ~~**Not done until the FT-20 promise is verified end to end.**~~ **Done, and it is the test session B ran by hand** (`runs/checkpoint-item5/findings.md` §5.4, S3): a rollout over a tool declared `spends_money`, refused before anything runs, naming the tool, the class and the k×n count. Two decisions inside it. The refusal covers the tools the pipeline can *reach* rather than everything in a registry, because refusing a project for a tool this evaluation never touches is the over-refusal that gets suites disabled. And replay is exempt, since a filed tool's body never executes there, which is what FT-20's own failure message tells the reader to do about it.
   - **The resampling unit is the example, and the signature is what enforces it.** Two rollouts of one question move together, so treating k×n rollouts as k×n independent observations narrows the interval by roughly √k with nothing in the reported number saying so. `bootstrap_ci` takes the rollouts grouped by example and cannot be handed a flat list by accident. **The test that proves the method rather than the code** is twenty examples each answered the same way five times, against a deliberately naive bootstrap written in the test file, asserting the clustered interval comes out at least 1.8× wider. A second test over data where rollouts vary as much as examples do asserts the two agree closely, because the correction is a property of the data rather than a constant the library adds.
   - ~~**k rollouts are how the determinism finding gets used rather than only recorded.**~~ **Measured, and the live recording is what produced it.** Example `e1` of the recorded evaluation, at a fixed seed and `temperature=0.0`, came back correct on rollouts 0 and 1 and reported absence on rollout 2. A single rollout of it would have reported 1.0 or 0.0 and looked equally authoritative either way. That is session 2's 15-calls-against-4-calls variance, arriving as a measurement.
   - **`cassette.diverged` turned out to be the wrong instrument, and this is worth recording.** The plan said this item would turn that counter into an interval. It cannot: a rollout's seed is in its cassette key, so two rollouts of one example are two different requests and never collide, and `diverged` only ever fires when the *identical* request is recorded twice. The two measure different things. `diverged` measures whether a backend reproduces itself at a fixed request; the interval measures whether the agent reproduces itself across seeds. Both are real and the second is what an evaluation needs.
   - **k=1 runs and is recorded rather than refused.** A refusal here would be stronger than FT-05, which item 9 deliberately dropped from the v0 seven because k=1 can be legitimate at temperature 0 over fixed documents. It would also fire on the cheapest possible first run, which is the pattern that got seeds generated rather than demanded at item 4. The results file carries `k` beside an interval that is wide at k=1, so the number carries its own qualification.
   - **A fourth cassette mode, `Cassette.update`, and it is not the ordinal fallback item 4 rejected.** Session 1 changed one node's prompt and re-paid for every earlier call: about two thirds of ~100 minutes and $0.37 of ~$0.55, its own estimate. Under k×n rollouts that is 15–30 minutes of wall clock per prompt edit at the measured 1.4–1.7s median call latency. The mode serves what is on file and calls live for what is not. What item 4 refused was serving the response recorded against the **old** prompt; here an edited request hashes to a key with no entry and is answered live and filed under the new key, so the silent-wrong-number failure is untouched. **An evaluation refuses the mode**, so a reported number never comes from a mixture.
   - **`concurrent_requests` is filled under vLLM, opt in, and the probe came before the code.** §3.1's watch list parked this here. `scripts/probe_vllm_concurrency.py` fired 1, 2, 4 and 8 requests at once at the local server: `vllm:num_requests_running` tracked what was issued exactly, with nothing queued. **The first implementation was then wrong in exactly the condition the flag exists for.** It scraped before sending, so six calls issued together each saw an idle server, every one recorded 1, and under a compute basis that charges each the whole device and reports six times the real cost. The reading moved to a moment *after* the send, from a short-lived thread, and six concurrent calls report 6. The runner never writes its own in-flight count into that field: it means what the server had open, and ours is a lower bound on it.
   - **Pacing ships as a wrapper rather than as an envelope hook.** H4 landed `rate_limit` on the response against the argument that item 8's runner would be its library reader, and this is that reader. Both item 7 sessions wrote this shape by hand and both estimated a figure the backend published on every response, over a per-question spend ranging from 4,700 to 122,000 tokens. A hook on `RunEnvelope` would be the more general answer and would need its firing contract settled now, before/after/on-failure/may-it-raise, against one known use. The wrapper needs none of that, because the seam is already a Protocol, and it composes. If something later needs the node id, the hook can be added then.
   - **Tested against handcrafted example sets with known properties, never against a real dataset.** Held. Every set in `tests/` is written for its test: a known proportion for the interval to cover, a copied example and a near-duplicate either side of the threshold for the contamination check, a set where rollouts within an example are perfectly correlated for the clustering. `ExampleSet` also refuses a repeated identifier at construction, so FT-03's first clause is enforced rather than checked, and what `contamination` is left with is the same example under two identifiers.
   - **What item 8 changed in the shipped documents, and what it deliberately did not.** `docs/evaluation.md` is new. `docs/run-envelope.md` §3.4 documents the fourth cassette mode; the concurrency flag and the paced client were documented in `docs/model-clients.md` §5 and §6, which the 2026-08-05 split moved to `docs/model-clients/vllm.md` §5 and `docs/model-clients.md` §4. Three sentences that item 8 made false were corrected: `tools.py`'s module docstring, `docs/tools.md` §1.4's "No evaluation runner ships yet", and FT-20's "Not yet built". The README gained an `evaluation.md` row. **Nothing else in the documents Thilina is reviewing was touched**, and the three corrections above are the minimum needed to stop the shipped documents asserting something untrue; they are flagged for him because they land in files he is editing.
   - **The recording paid for itself twice, and the first time was a defect in my own pipeline.** The two-node recording had `verify` checking an answer against notes it had never been given, because a node receives only the previous node's output. It reported that it could not verify, which was correct behaviour and an incorrect pipeline. That is the same shape as the checkpoint's D1 and it was invisible until a real model ran it. The file also shows 20 tool calls storing 4 entries: a tool call is keyed on name, version, arguments and occurrence, and the seed is not in it, so two rollouts searching the same words are one call. That is FT-20's mechanism visible in the file rather than argued for.

---

## Item 8c — Branching

#### Item 8c — Branching

`Pipeline` becomes a directed graph over the same three node kinds (`simple-agents.md` §2.2, amended 2026-08-03). **Built 2026-08-04**, as deliverables 1 to 7 and 10 plus the executor half of 9. Deliverables 8 and 9 were split out as items 8d and 8e at the top of the build sitting; the argument and what was decided while building are in `build-logs/item8c-build-log.md`. **691 tests**, trajectory `0.11`, manifest `0.5`, results `0.2`.

**Numbered 8c rather than 9, on the precedent item 8a sets.** Existing citations resolve against these identifiers, and a Markdown ordered list renumbers itself whatever the source says, so a heading keeps source and render agreeing. Unlike 8a, this one is built *before* item 9.

**Deliverables, in build order.** Each is a graph feature and each changes the edge model, so they land together rather than as later patches on a shipped format.

1. **Edges.** `successors=` on a node, defaulting to the next node in the list, so every pipeline that exists today keeps its exact meaning. `route=`, plain Python over the node's validated output.
2. **Branch and skip.** A route selecting one successor. A node whose in-edges all resolved absent does not run and emits a `node_execution` record with `termination: "skipped"`.
3. **Parallel branches.** A route may select **more than one** successor, and both arms run. Sequentially, in topological order: concurrency is §3.2.1, and nothing here depends on it. Without this a join can only ever merge alternative paths, and merging work done on two arms is the more common reason to want one.
4. **Join.** A node with more than one in-edge receives a `Join` mapping keyed by source `node_id`, with `Unknown` carrying a reason for each edge that did not fire. The input shape is a function of the declared graph and never of what ran.
5. **Bounded cycles.** `loop=Loop(max_iterations=, then=)` on the node that closes a cycle, counting **per entry to the loop**: the counter resets when the cycle is entered from outside it. The final iteration's record carries `termination: "max_iterations"`.
6. **Error edges and per-node retry.** `on_error=` naming a successor, and a retry policy on the node. Today a node that raises ends the run, and the only retries in the library are transport-level inside the HTTP adapter, invisible to the pipeline. A flaky tool or a model returning unparseable output is the first thing a real project hits, and an error edge is the natural graph answer to it. An exhausted retry follows `on_error=` where one is declared and propagates where none is.
7. **Composition.** A `Pipeline` usable as a node inside another. Node ids are namespaced by the containing node so per-node metrics and ablation stay keyed on something unique.
8. ~~**Suspend and resume.**~~ **Split out as item 8d, 2026-08-04.** The reasoning is under that heading.
9. **Streaming.** ~~Token streaming through the `ModelClient` seam~~ **split out as item 8e, 2026-08-04**, and node-progress events from the executor, which shipped here as `Pipeline.run(on_progress=)` and a `NodeEvent`.
10. **Rendering.** The declared graph as a diagram. Nearly free once edges exist, and it is how a builder checks the shape matches what they meant. **Built** as `Pipeline.to_mermaid()`.

**Per-node accuracy ships with this item**, decided 2026-08-03. The library already records what reached each node and what it produced; only the label was ever missing. `Example.expected_by_node` and `EvalSuite(node_matches=...)` close it, and the denominator is the rollouts that reached the node and carry a label for it, which is why it could not have been done correctly before reach existed. Not enforced: a label is ground truth about the task, and refusing an evaluation for want of one refuses most legitimate projects. Elicitation asks which nodes have their own ground truth (item 12).

**Decisions settled at the sitting, not to be reopened without new evidence:**

- **The problem the sitting had to solve.** "Per-node evaluation rests on a node's input being determined by its predecessor" names two properties and only one is threatened. **A node's input is a recorded value** (`node_execution.inputs`, attribution on `parent_id`) survives a join and does not change a line of `per_node.py`, provided every value arrives on a declared edge. **Every node runs exactly once per run**, so all per-node numbers share the denominator n × k, is what is given up. `NodeMetrics` gains `runs`, `reached` and `reach`, the last a `Metric` with an interval from the existing `bootstrap_ci`; a node with `reached == 0` reports a `reason` rather than zeros, the convention `_metric` already uses. `compare()` reports a moved reach beside every moved node number, so a metric that moved because routing moved is a named fact rather than an inference.
- **Shared state is rejected**, and it is what "solve the join" usually means. A mutable bag breaks the recorded-input property three ways: `inputs` becomes a pointer into ambient state so a node is no longer replayable from its record; a change in node A reaches node C with no edge between them, so `compare()._changed` has nothing to key a cause on; and reachability and successor checks become undecidable because the data dependency is not in the graph.
- **Routing is a property of a node, not a fourth node kind**, on the argument that kept fan-out from being one (item 3).
- **The model's choice of edge is mediated by the output schema.** It may choose freely by filling a schema field a route reads, which keeps the decision validated and recorded and costs no extra call. It may not choose outside the schema, because a node that picks its own next step is an `AgentNode` by definition and the alternative would put the graph's shape into the prompt.
- **A cycle with no `loop=` is refused at construction.** No runtime axis binds one: `max_steps` counts model calls and a `Deterministic` cycle makes none, tokens and cost likewise, and `max_wall_clock_ms` is a time bound that may be `None`. That is the FT-18 shape, a limit that looks set and stops nothing. The graph is static so cycle detection is complete, and a refusal names the cycle at author time. **No fifth budget axis.**
- **`max_iterations` counts per entry, not per run**, corrected 2026-08-03. Per run makes the arithmetic simpler and starves a nested loop: bounded at 3 inside one bounded at 10, the first outer pass consumes all three and the remaining nine get none with nothing marking it. Per entry is what "at most 3 revisions" means, and the run stays finite by the product over nesting depth.

**Construction refusals**, added to the four `Pipeline` already has: a successor naming a node not in the pipeline; a node unreachable from the first; more than one node with no successors; more than one successor with no `route`; a `route` with fewer than two successors; a cycle with no `loop=`; a `Loop(then=)` naming a node inside the cycle or outside `successors`. At run time, a route returning an id outside its declared successors raises `CallerFacingError`.

**Formats.** Trajectory `0.10` → `0.11` (`route` and `visit` on `node_execution`, `termination` gains `skipped` and `max_iterations`, `outputs` null on a skip as well as an error, a join's `inputs` keyed by source node). Manifest `0.4` → `0.5` (`successors`, `loop`, `on_error`, retry policy). Results `0.1` → `0.2` (`runs`, `reached`, `reach`, `accuracy`; `config.nodes[]` gains `successors`, which makes a routing change appear in `comparison.changed` through the walk that already exists, so FT-15 costs nothing). `expected_by_node` on the example set is additive.

**Doc consequences, written after the build and not before it.** `pipeline.md` §1, §1.1, §1.2 (rewritten, retitled "Branching, joining and looping", opening with the flattest shape that expresses the work being the one to reach for) and §3; `trajectory-format.md` §3; `evaluation.md` §1 and §5; `failure-taxonomy.md` FT-08, FT-12 and FT-18; `CHANGELOG.md`; the `index.md` and README one-liners. The design is settled and the wording is not, on Thilina's instruction: **document what was actually built, once it exists.** Same call item 8b made about FT-13.

**Two alternatives were on file and are closed.** A conditional skip answers the item 7 session and nothing else: no join, no bounded loop. Routing without joins was the standing recommendation, on the ground that it preserved a node's input coming from one predecessor; that property turned out not to be the one per-node evaluation rests on.

---

## Item 8d — Suspend and resume

#### Item 8d — Suspend and resume

A run that can stop at a declared point, persist what it needs, and be resumed in another
process. **Not built. Split out of item 8c on 2026-08-04**, at the top of the build sitting,
with Thilina's agreement.

**Why it left 8c.** It is the only one of the ten deliverables whose cost driver is not the
edge model. An edge value in flight is an arbitrary Python object, and the library's one
serializer is `to_record_data` (`src/simple_agents/records/trajectory.py`), which flattens types: a
resumed run would hand a downstream node a `dict` where the live run handed it an `Answer`.
Settling that is a design sitting with real alternatives, and it needs a second capture for an
`AgentNode` stopped mid-loop, which is the case consultation actually has.

**The argument it had to beat, and how.** Item 8c held it on the ground that retrofitting it
onto a shipped scheduler and a shipped trajectory format costs a third format bump.
`CHANGELOG.md` says nothing is released, so a third bump costs re-recorded cassettes and doc
edits rather than a migration for anyone. That is a real cost and a small one against
designing the state contract under the pressure of an already large item.

**Held 2026-08-04.** The entry previously listed four open questions. Six were settled, because
two were open and unnamed: what a suspend point actually is, and what a suspension waiting on a
clock does. `build-logs/item8d-build-log.md` §1 records the sitting and §4 what it found.

**Three triggers, one capture, one resume.** They were first costed as three designs to choose
between, with a recommendation to build one and defer the rest. That was wrong: the expensive
part is the state capture and all three share it, so the second and third are the same check in
the same place in `_walk` and cost a handful of lines each.

| Trigger | Where it stops | Case it serves |
|---|---|---|
| `Suspend` raised from a tool, a node function or a `ModelClient` | anywhere, including mid-agent-loop | an agent discovering mid-search that it must ask; waiting out a token quota |
| `suspend_before=` declared on a node | node boundary | a planned human review, visible in `to_mermaid()` |
| `stop_when=` on `run()` | node boundary | an end user pressing pause; parking work before a redeploy |

`Suspend` unwinds like `CassetteMiss` and `BudgetExceeded` already do: never retried, never
diverted along `on_error`, because none of the three is the node's failure. `run()` raises
`RunSuspended`, on `BudgetExceeded`'s precedent, so a caller who did not plan for suspension gets
a loud stop rather than a `RunResult` whose `output` is `None`. The model gets no `suspend` tool
beside `finish`: a model calling `consult` already is the model choosing to stop, schema-validated
and recorded.

**Decisions settled at the sitting, not to be reopened without new evidence:**

- **A value crossing a suspend point is decoded from the producing node's declared
  `output_schema`.** No type names in the file, no import by string, no registry: the
  reconstructed pipeline supplies the type, so a class rename is invisible and a schema that
  actually changed fails loudly in `model_validate` rather than quietly handing a `dict`
  downstream. An `LLMNode` or `AgentNode` output is `output_schema`, `None`, or a `FanOutResult`
  of it, and nothing else is reachable. `Unknown`, `Join`, `NodeFailure` and `FanOutResult` are
  tagged library types. **`Deterministic` gains an optional `output_schema=`**, so the cheapest
  node kind is usable across a suspend without being rewritten to return dicts. Anything else
  must be plain JSON data, refused at the suspend point rather than at construction, because
  whether a value serializes is a fact about data and not about shape.
- **Pickle was rejected**, and the deciding reason is not security. Every artifact this library
  writes is readable JSON, and an opaque blob in a run directory would be the only thing in it
  that cannot be checked by reading.
- **Re-executing the run from the start against the cassette was rejected.** It dodges the
  serialization question entirely and reuses built machinery, and it makes correctness depend on
  `Deterministic` being a property rather than a name the builder chose. A node reading the clock
  or a file that changed returns something else on resume and nothing says so, which is the
  silent-wrong-number class item 4 refused when it refused serving an old response to an edited
  request. It also requires a cassette on in production, which is what item 8b exists to avoid.
- **State goes to a versioned `suspension.json` in the run directory, not into the trajectory.**
  Item 8b is about to make trajectory payloads sampled and droppable, and a run that could not
  resume because its trajectory was sampled at 1% is a collision that would be found late. It
  carries the conversation verbatim, so it goes through the same `Redaction`, and it is deleted
  once a resume succeeds.
- **A resume is verified in two tiers.** Structural differences, which are node ids, kinds,
  edges, loop bounds, `on_error` and output schemas, are refused outright, because the stored
  state is keyed on node ids and a changed graph makes it meaningless rather than stale. Version
  differences, which are prompts, routes, tool versions, the model pin, the cost basis and the
  redaction rules, are refused by default and waivable through `accept_changed=`, recorded in the
  manifest in the shape `allow_unknown=False` already uses. A `graph_fingerprint` compares in one
  string and a mismatch reports the field-by-field diff, which is item 4's cassette rule one level
  up.
- **A consultation across a process boundary is two records**, joined by a new `answers` field,
  with `resolution` gaining `pending`. One record written on resume would leave a never-resumed
  run showing no sign that anything was asked; amending a record in place would give up the
  append-only property that makes a crashed run leave a readable prefix.
- **The resume writes the delivered answer into the cassette** under the pending call's key.
  Without it a suspended run is unreplayable, because the tool raised rather than returned and
  nothing was stored, and `docs/tools.md`'s promise that a consultation replays instead of asking
  k times would be false for exactly the runs this item creates. It settles a second question
  free: **an evaluation never suspends**, because every consultation it meets is on file.
- **`resume_not_before` is data and a refusal, not a timer.** `resume()` refuses before the time
  and says when; `resume(wait=True)` blocks in the caller's own process, which is the caller's
  explicit choice with its duration visible. `Pipeline.suspensions(run_dir)` lists what is waiting
  and what is ready, so a project's cron job or queue worker drives it. Same posture as `consult`:
  the library owns no terminal, the project supplies the channel. `simple-agents.md` §2.1 carries
  the invariant this rests on.
- **Wall clock does not charge the time spent suspended.** It is stored as elapsed and the clock
  restarts on resume, or a consultation answered a day later would trip `max_wall_clock_ms` on the
  first check after resume, on every pipeline that sets one. The suspended interval is recorded in
  the manifest so it stays auditable rather than invisible.
- **A fan-out captures its finished items and continues from the next index.** An `LLMNode` was
  assumed atomic on the ground that only an `AgentNode` calls tools; a `Suspend` raised from a
  `ModelClient` wrapper defeats that, and re-paying for three of ten items is worst in the case
  that suspended, where the quota was the reason.

**Formats.** Trajectory `0.11` → `0.12` (`termination` gains `suspended`, `resolution` gains
`pending`, `answers` and `resumed_from` added). Manifest `0.5` → `0.6` (`outcome` gains
`suspended`, a `suspensions[]` array, `graph_fingerprint`, the resume waivers). A new
`suspension.json` at `0.1`. Results stays `0.2`: `terminations` is an open dict and `reached` and
`runs` are untouched.

**Doc consequences, written after the build and not before it**, on the same instruction item 8c
followed. `build-logs/item8d-build-log.md` §5 carries the table.


---

## Item 8e — Streaming

#### Item 8e — Streaming

Token streaming through the `ModelClient` seam. **Built 2026-08-04**, the last of the ten
deliverables item 8c named. Split out of 8c at the top of that build sitting, because it
changes the Protocol §2.5 settled, both adapters and what a cassette replay does, while
touching none of the edge model. **The half that landed in 8c** is node-progress events, which
needed no seam change: `Pipeline.run(on_progress=)` and a `NodeEvent`.

**Held 2026-08-04.** The entry listed three open questions and the three things 8d left it.
Seven decisions came out, because the framing question was not among them and had to go first:
**the library's own control flow cannot use a partial response**, since a node validates an
output schema, dispatches a tool call and charges a budget only against an assembled one. So
streaming is an additional delivery channel for bytes the call was going to produce anyway, and
every option was judged on how little it disturbs what exists. `build-logs/item8e-build-log.md`
§1 records the sitting and §4 what the build found.

**Decisions settled at the sitting, not to be reopened without new evidence:**

- **A second Protocol, not an amendment to the first.** `ModelClient` stays two methods;
  `StreamingModelClient` adds `stream(request, on_chunk) -> ModelResponse`. The reasoning is in
  `simple-agents.md` §2.5 as amended. Presence of the method is the capability declaration,
  which is what lets a client that cannot stream be refused by name rather than emulated.
- **The node declares, the run supplies the sink.** `stream=True` on an `LLMNode` or
  `AgentNode`; `on_token=` on `run()` and `resume()`. A run given no sink makes ordinary calls
  whatever a node declares, so an evaluation of a streaming pipeline sends what a non-streaming
  one sends and their recordings are interchangeable.
- **A token event is a second callback, and the relationship is stated rather than the channel
  merged.** A `TokenEvent` always falls between the `started` and the `completed` or `failed`
  `NodeEvent` of the node that produced it and carries the same `node_id`. They are separate
  because `on_progress` describes what the executor did and fires about four times per node,
  while tokens describe what the backend sent and fire thousands of times.
- **Streaming is not in the cassette key, and the chunk boundaries are stored.** The key covers
  what determines the answer; transport does not. The entry gains cut offsets into the content
  plus `first_chunk_ms`, beside `duration_ms` and on the same reasoning, so a replay re-emits
  the pieces the recording delivered with no simulated timing. Serving one lump instead was
  rejected: it is observably not the run that was recorded, and it leaves a builder's streaming
  path unexercised by any evaluation. An entry recorded without streaming replays as one piece
  and records `stream: null`, since nothing is invented.
- **`model_call` gains `stream`**, carrying `chunks` and `first_chunk_ms`. **Time to first token
  is the reason streaming is adopted and is derivable from no other field.** A bare boolean was
  rejected for costing the same bump and recording the one thing already inferable elsewhere.
- **A streamed response with no token counts is refused, and the refusal is waivable on the
  adapter.** Thilina rejected the first version, which shipped no `stream` at all on a backend
  that never reports usage: a backend that never does and one that sometimes fails to are the
  same trade, and it is the builder's. `stream_without_usage=True` accepts the loss, the
  manifest records which client, and every count on those calls is `unknown`. **The message is
  built from the run**, so only consequences the run actually has appear; `Budget` permits any
  axis to be `None`, and a pipeline with no token limit and no cost basis is told what is true
  of it instead.
- **A `Suspend` mid-stream leaves the delivered tokens with the end user**, and the resumed run
  makes the call again from the start. Neither backend resumes a partial generation, and the
  library cannot recall text without owning the display. The record says how far it got.

**Formats.** Trajectory `0.12` → `0.13` (`model_call.stream`; `error.class` gains `suspended`).
Manifest `0.6` → `0.7` (`stream` on a node entry, `stream_waivers`). Suspension stays `0.1` and
results `0.2`. Cassette entries gain an optional `stream`, so every committed cassette replays
untouched.

**A defect item 8d left, fixed here.** `_call_model` catches `Exception` and emits a failed-call
record, so a `Suspend` raised from a `ModelClient` was recorded as `error.class: caller_facing`
while 8d had deliberately decided the opposite for the tool path. Anything counting caller-facing
failures over a trajectory over-counted every suspension. `error.class` gains `suspended`.

**Doc consequences, written after the build and not before it**, on the same instruction items
8c and 8d followed. `build-logs/item8e-build-log.md` §5 carries the table.


---

## Item 8f — Reasoning output

#### Item 8f — Reasoning output

Recording the chain of thought a model emits separately from its answer. **Built 2026-08-05**,
after item 8e and before item 9. Promoted from §3.2.1 the same day, at the model-clients review,
because a builder-facing document says what the library is at release and so cannot describe a
gap that is scheduled to close.

**Held 2026-08-05.** Seven questions went to the sitting, five of them named in the brief and two
found while preparing it. Three turn on what the backends do, so they were measured first, on the
rule the item 8e log recorded at its §1.3. `build-logs/item8f-build-log.md` §1 is the measurement,
§2 the sitting, and §5 what the build found.

**Two claims in the entry as scheduled were false, and measuring is what found them.** The entry
said the OpenAI dialect carries reasoning as `reasoning_content` on the message and the delta, and
marked it an assertion needing a measurement. vLLM 0.26 calls it `reasoning` and treats
`reasoning_content` as a deprecated request-side spelling; the repository already held a fixture
showing this, captured at item 5, and nobody had read it. And **no Mistral model this account can
reach reports a chain of thought at all** — all twelve return `content` as a string and refuse
`prompt_mode: "reasoning"` — so the entry's premise that both adapters would fill the field was
wrong.

**Decisions settled at the sitting, not to be reopened without new evidence:**

- **`Reasoning(text, blocks)`, not a string.** `text` serves the record and the reader; `blocks`
  carries what a backend needs returned verbatim. The string was rejected on the published SDK
  types of the two adapters named next in §3.2.1: Anthropic's thinking block carries a `signature`
  and has a `redacted_thinking` variant with no text at all, and OpenAI's Responses item carries an
  `id` and `encrypted_content`. **`blocks` ships filled by nothing**, which is an exception to the
  rule against fields no adapter can fill, granted by Thilina on the argument that the alternative
  is a second bump and a second re-recording. It is measured when those adapters land.
- **An `AgentNode` keeps reasoning on the assistant turn, and the adapter decides the wire form.**
  Exact precedent: tool calls already travel in the library's own shape and each adapter
  translates. `messages_to_wire(..., reasoning_field=)` is where it is decided; vLLM sends it and
  Mistral drops it. **This is not cosmetic.** Measured, a Qwen3 conversation carrying reasoning
  back within the turn renders 100 prompt tokens against 58 without, so the library had been
  removing the model's own reasoning from the turn it was still working on whenever a server ran a
  reasoning parser.
- **The field goes inside `outputs`.** Item 8b samples `inputs` and `outputs` and nothing else, so
  the largest payload the record carries is covered without amending 8b's design.
- **A second sink, keyword-only, passed only where the signature accepts it.** Either sink turns
  streaming on. A run given `on_reasoning=` against a client that takes none is refused by name,
  which is item 8e's refusal one level down. `first_chunk_ms` stays measuring content, on Thilina's
  call, because changing its meaning would make recordings either side of this incomparable.
- **`reasoning=False` on an adapter suppresses generation**, and an adapter whose backend offers no
  such setting refuses it at construction. That is the general form of the construction-time check
  Thilina asked for: **the adapter knows whether it has a mechanism at all, and only a response
  knows whether the mechanism bound.** vLLM 0.26 publishes nothing about its parsers on any
  endpoint, so the parser case is a warning on the first response that shows it.
- **The library never sets `include_reasoning: false`.** Measured, that setting still generates and
  bills the chain of thought and only withholds it, which is the failure this item exists to end.
- **The library does not split `<think>` out of `content`.** Raised by Thilina and settled against:
  it reverses the never-emulated rule, the markers are model-specific, and a false positive
  rewrites the string an output schema is validated against.
- **No reasoning token count.** Neither shipped backend reports one, and a field no adapter can
  fill is the rule `blocks` is already the exception to.

**Formats.** Trajectory `0.13` → `0.14` (`outputs.reasoning`; `stream.reasoning_chunks`). Manifest
stays `0.7`, suspension `0.1`, results `0.2`.

**Every committed cassette was re-recorded**, all fifteen, the vLLM ones against a server started
with `--reasoning-parser qwen3`. The format did not force it and the recording configuration did:
every vLLM cassette had been recorded without a parser, so its chains of thought sat inside
`content` and the fix was invisible under that setup. Five recorded figures in the evaluation
integration tests moved with the new recording, and each was checked against the property its test
demonstrates before the number was updated.

**Doc consequences, written after the build and not before it**, on the same instruction items 8c,
8d and 8e followed. `build-logs/item8f-build-log.md` §6 carries the table.


---

## Item 9 — The conformance checks

9. **Five to eight conformance checks**, derived from the taxonomy, runnable as one command, graded by tier. This is a **v0 implementation budget, not a cap on the taxonomy** — the taxonomy is the full spec and v0 builds a subset of it. Pick the subset against what dogfood #1 will actually exercise, after the trajectory format exists, since several checks read fields that are not yet defined. **Built 2026-08-06** (`src/simple_agents/conformance/`, `src/simple_agents/cli/main.py`, **899 tests**). Six of the seven, with FT-24 at item 12; results file `0.3`, and no other format touched. Shipped as `docs/conformance.md`, the tenth document in the wheel. The build log is `build-logs/item9-build-log.md`, and the decisions taken at the sitting are below.
   - **The runner is one command over a project directory**, `simple-agents check [path]`, which is the first console script the package declares. It reads the brief, the most recent run under `runs/`, and the most recent results file under `evals/results/`, and the report names which of each it read. `--brief`, `--run` and `--results` override. Exit 0 when nothing failed, 1 when a check did, and **2 when the suite could not run**, which is a missing or unreadable brief and is not a check failure.
   - **A check reads raw JSON and never the library's own typed readers.** `EvalResults.read` refuses a file whose format version this library does not write, and a file it did not write is what several of these checks exist to catch, so a malformed artifact has to arrive at the check that reads it rather than raising on the way in.
   - **A missing artifact fails once.** A project claiming `evaluated` with no evaluation gets one failure from FT-01 and three checks reported `blocked` naming it, rather than four failures for one cause. Nothing a project declares changes that, so it is not the suppression mechanism the taxonomy refuses.
   - **A project with no brief is refused rather than defaulted to `prototype`.** Defaulting would make deleting `brief.toml` silence the four `evaluated` gates.
   - **Three amendments to signed-off taxonomy entries, each because the check and its message disagreed.** FT-07 said every trajectory record carries a seed, which is false of `tool_call` and `consultation` on every trajectory this library has written, and its second clause was a `runtime` measurement inside an `artifact` entry. FT-13's check asked for conformance to the trajectory format and its message could only report absence, so the message took a `<reason>` placeholder rather than the entry gaining a second message. FT-02 gained one for the same reason. FT-14's sampling-parameter clause moved out of the check entirely, since the message is about an alias and can say nothing about a missing `params`.
   - **Two library changes fell out of making a check real**, both small and both raised at the sitting rather than found later. `ExampleSet` takes `held_out=`, because nothing in any artifact marked which split may not be inspected and FT-02 would otherwise be guessing from a name the project chose. And `config` records the version of `matches`, because a change to what counts as a correct answer moves every rate and `compare()` reported it in `changed` as nothing at all.
   - **Chosen for v0 (2026-07-26): FT-01, FT-02, FT-06, FT-07, FT-13, FT-14, FT-24.** Graded at `prototype` + `evaluated`, the tiers dogfood #1 claims. Four are the eval-honesty spine — evaluation exists, a held-out split exists, the metric carries an interval, seeds are controlled — which is the failure class `handoff.md` argues the library exists to prevent. FT-13 gates every other artifact check and is the first real test of `docs/trajectory-format.md`. FT-14 is near-free once FT-13's reader exists. FT-24 is the only one testing elicitation, which is the thesis.
   - **All seven are `artifact` surface, and that is a deliberate implementation constraint.** The v0 check runner is then one mechanism: read the project's files, its trajectory, and its brief. No AST analysis, no runtime harness observing a live run. Static- and runtime-surface checks arrive in v0.1, once dogfooding says which earn their cost.
   - **Amended 2026-08-05, at the item 9 sitting: six are built here and FT-24 is built at item 12.** The subset is unchanged; what changed is where the seventh lands. FT-24's check is "for each question required at the project's current stage", and neither half of that exists: no stage vocabulary appears anywhere in `docs/` or `dev-docs/`, and the required-question set is item 12, whose material is `plan.md` item 12's seed four plus the thirteen banked in `runs/checkpoint-item5/findings.md` §7 and `runs/checkpoint-item7/findings.md` §8. Built here it would pass on any brief that parses, which is the "a check that has never been shown to fire proves nothing" rule arriving before the code. Building it at item 12 costs one registration in a runner that is a registry either way. **It is still in the v0 seven and still ships before v0**, since item 12 precedes the ship criterion; the letters-are-not-an-order rule at the top of §3.1 applies to this the same way.
   - **The brief's tier declaration lands at item 9 rather than item 11**, and this is the sitting's other scope decision. It is not FT-24's dependency alone. Four of the six built here are `evaluated`-tier gates, `docs/failure-taxonomy.md` §1.2 fires a gate only when the project claims the tier or higher, and **the claim cannot be inferred from the artifacts**: FT-01 fires exactly when a project claims `evaluated` and has no evaluation, so reading the claim off the presence of an evaluation makes FT-01 unfirable by construction. Nine shipped failure messages already name where the declaration lives, in identical words — *"declare tier `prototype` in the brief and this gate will not fire"* — so a runner reading the tier from anywhere else ships nine messages pointing at a file the library does not define. Item 9 therefore defines the brief file itself: `tier`, `stage`, and `entries` with a status each. **Item 11 inherits the smaller job**, which is the elicitation half: what goes in the entries, how the coding agent fills them, and what a stage means. The precedent is item 7's, where two clauses of the tool contract landed at item 5 because an `AgentNode` could not be used without them.
   - **Dropped, with reasons:** FT-03 (needs set comparison; low risk on a hand-built doc set), FT-05 (k=1 may be legitimate at temperature 0 over fixed documents, and a false failure would teach the coding agent to distrust the suite), FT-16 (redaction belongs in the logger by construction, not in a check), FT-11 and FT-12 (nothing to ablate in a one- or two-node agent), FT-23 (one tool), FT-27 (nothing reports cost in v0 yet), FT-17 and FT-22 (static surface, would drag AST work into v0).
   - **Two of the dropped checks got cheaper at item 4, and stay dropped.** FT-20 (non-replayable tools in rollouts) and FT-21 (evaluation cannot run offline) both need a cassette covering tool calls, which now exists. Neither enters the v0 seven: FT-20 and FT-21 are `runtime` surface and the v0 runner is `artifact`-only by construction, which is the constraint above and not something to spend on a check that dogfood #1 (one read-only tool, no live network) cannot exercise. Revisit at v0.1 with the rest of the runtime surface. FT-16 also stays dropped for its original reason, redaction being enforced in the writer rather than checked afterwards, and item 4 built exactly that.
   - **Enforcement is not a check and does not count against the budget.** FT-09 (schema admits `unknown`), FT-18 (loop refuses to run without a budget), and FT-19 (registration refuses a tool with no side-effect class) are enforced by construction in the core — the library has to implement them regardless of which checks ship. See `simple-agents.md` §2.3, §2.6, §8.2.

---

## Item 8a — Ablation, built as variant comparison

#### Item 8a — Ablation, built as variant comparison

`oracle → ablate` as a first-class operation (`simple-agents.md` §4.3). **Built 2026-08-06.** The
record is `build-logs/item8a-build-log.md`; §2 carries the sitting, which reframed the item twice
and is what `simple-agents.md` §4.3 was amended to match.

**What shipped is `compare_variants()`, of which ablation is one direction.** A variant is another
`Pipeline`, so a node kind, a node added or removed, a tool added or removed, a reworded prompt, a
moved temperature and a rewired graph are all one operation, and a per-node model swap needs no
amendment when it lands. `ablate()` generates the standard downgrades. Both arms run in one
session, `plan_variant()` says which calls the baseline recording answers before any are made, and
`max_live_calls` refuses a sweep before the first call. Manifest `0.8`, results `0.4`, a fifth
versioned artifact at `0.1`. 928 tests. Shipped as `docs/evaluation.md` §10.

**Two things it found that were nobody's design**, both recorded in the build log §5 and §4.1:
`compare().moved` reported `True` from a single example, because a percentile bootstrap over
examples that all move the same way returns an interval of zero width; and nothing in the library
checks that a successor accepts its predecessor's declared type, which is item 8g.

The scheduling record follows.

**It is numbered 8a rather than 9 on purpose.** `handoff.md` and `simple-agents.md` both cite these item numbers, and renumbering would invalidate every existing citation including the ones in commit messages and the checkpoint findings. It sits outside the numbered list for a second reason: a Markdown ordered list renumbers its items sequentially whatever digits the source carries, so an inserted `9.` would silently shift every later item in the rendered output while the source still said otherwise. A heading keeps source and render agreeing.

**The name no longer matches the position, and the name wins.** It is built after item 9, not after item 8. The `8a` is an identifier that existing citations resolve against, not a claim about sequence.

*Corrected 2026-08-04, at item 8e.* This paragraph previously said "the heading sits here because that is the build order", which was false: the headings run 8c, item 9, 8d, 8e, 8a, 8b, so item 9's entry sits in the middle of the lettered ones and the order in this document is neither build order nor alphabetical. **The build order is 8 → 8c → 8d → 8e → 8f → 9 → 8a → 8b → 10 onward**, and it is stated at the top of §3.1 so a reader does not have to infer it from where a heading landed. Thilina read the letters as a sequence and asked whether part of item 8 had been skipped, which is what found this.

- **Why it needed an entry at all.** §4.3 commits to shipping it in v0 and calls it the most defensible feature in the library, and §3.1 never allocated it one. That was a gap in this plan rather than a decision, and it was found while building item 8.
- **Item 8 built the half it needs.** `compare()` takes two results files and reports whether each metric moved, on an interval over the paired per-example difference. Ablation is that plus constructing the ablated pipeline and reading which decisions the oracle made identically every time.
- **Why it is scheduled here, decided at the document review (2026-07-30).** Three things forced it. §4.3 already commits to shipping it in v0, so "unscheduled" was a gap rather than a decision. §4.2's dogfood #1 expects the missing-measurement hunt to be the one `AgentNode` that survives ablation and everything else to collapse into `LLMNode`s, which is a measurement that cannot happen without the operation. And `docs/failure-taxonomy.md` FT-12 describes it in the present tense, which a builder-facing document may do only for something that ships. **After item 9** because the v0 seven do not include FT-12 and do not need it, so the checks stay next; **before item 10** because item 10's gates can then invoke ablation from the start rather than being retrofitted.


---

## Item 15 — `docs/pipeline.md`

15. **`docs/pipeline.md`** — the eighth shipped document. **Written 2026-07-30, at the document review.** Not a planned item; it was forced by applying the rule in item 2 above. Cutting the definition of `unknown` out of the trajectory format left the concept with no owner in `docs/`, because the agent shape itself had none: seven documents covered the envelope side, and the node kinds, budgets and output schemas lived only in the README and in docstrings. It covers the pipeline, the three node kinds, what a node receives, the output schema with `unknown`, and budgets, and it points out to the other seven.
    - **The name.** `agent-shape.md` was proposed and rejected by Thilina: "agent shape" is our term, and to a builder it promises a document about agents or `AgentNode`. Every other shipped document is named after the library object it documents, so `pipeline.md` is the consistent name and the one that promises what it delivers.
    - **Every example in it was executed against the library** rather than written from memory, including all seven `RunResult` accessors, the eight `NodeContext` fields, `FanOutResult`, the `unknown` refusal and `Budget.narrowed_by`. Thilina reviews it in detail in a later sitting.

---

## Item 16 — `prose_check.py` resolves `§n`

16. **`scripts/prose_check.py` resolves `§n` references.** **Landed 2026-07-30**, the follow-up agreed at the taxonomy review. A reference following a `docs/*.md` path resolves against that document; a bare one inside a shipped document resolves against the document it sits in; a bare one in a `.py` file is left alone, since those files state their referent once at the top. It found nothing on the first clean run, which was a bug in the check rather than a clean repository: the heading pattern was anchored without `re.MULTILINE`, so it matched no headings and passed everything. **A check that has never been shown to fail is not evidence.**


---

## The item 5 checkpoint, as actually run (2026-07-26)

*Moved out of `plan.md` §3.5 on 2026-08-06. The checkpoint ran; `runs/checkpoint-item5/findings.md` is its result, and this is how it was set up.*

#### The item 5 checkpoint, as actually run (2026-07-26)

**It is two sessions, and the second uses a tool.** The plan originally put the first checkpoint at "no tool", on the grounds that the tool surface arrives at item 7. Two things changed that. The narrow question is a line longer than the README quickstart, so on its own it measures almost nothing. And the tool *contract* is usable from item 5: `@tool` derives its schema, and `AgentNode` runs, so only the registry and the built-in set are missing. A tool-using task is therefore posable now, and the after-item-7 checkpoint keeps its distinct purpose because by then the tools are ours rather than the builder's.

**Session A, the narrow one.** A fresh environment holding only the installed wheel, and the question as written above. Reads: whether the installed documents are found at all, whether `Budget` is constructed with all four axes rather than worked around, whether the output schema gets an `unknown` branch or `allow_unknown=False`, whether a dated model is pinned, and whether arguments that do not exist are invented.

**Session B, shape unprescribed.** A folder of ten synthetic news articles, at `/home/thilina/Projects/search-agent/data`, with fifteen questions in `questions.md`. Nine need facts from two or three articles, so the number of lookups cannot be planned; two are single-hop controls; four have no answer in the corpus. Expected answers **must not be in that directory while a session runs**, since a coding agent working there will read them and anything measured afterwards means nothing. They are held at `~/checkpoint-answers/search-agent-answers.md`, outside `Projects/` so that neither session can stumble on them, and the corpus README still describes them as belonging at `data/answers.md`, where they go back once scoring is done.

The task is given without a shape: build an agent that answers questions about these articles. **Whether the session reaches for an `AgentNode`, and whether it can say what the model decides that fixed control flow could not, is the most valuable thing either session produces**, because it is the library's central claim. Prescribing the node kinds throws that away.

**Three gaps are known and are not findings.** There is no tool-authoring guide (item 13), so tool-writing friction is expected. There is no procedure, no gates and no brief (items 9 to 12). There is no context builder (item 6). Friction in those places goes in a different column from anything the docs caused, and so does anything environmental, such as an interpreter that is not the one the library was installed into.

---

#### Item 8g — What a node accepts

Created 2026-08-06 at item 8a, and scheduled immediately after it. **Built 2026-08-06.** The
record is `build-logs/item8g-build-log.md`; §2 carries the sitting.

**What shipped is a declaration read off the node's own function** rather than the `input_schema=`
below, on item 7's precedent that a mode a coding agent classifies into is one it will classify
wrongly. The first parameter's annotation is what a node accepts; `output_schema`, or a
`Deterministic` function's return annotation, is what the node before it produces. A disagreement
is refused at construction and again when the value is handed over, and only where both sides are
declared and no value could satisfy both, so a pipeline that annotates nothing is refused nothing.
`over=` gained two construction refusals of its own, the first node now receives the run's inputs
even where a cycle returns to it, and an exception raised inside a node carries a note naming it.
Manifest `0.9`, FT-28, 978 tests. Shipped as `docs/pipeline.md` §3.1.

**Of the six cases below, one is wrong and four were missing.** A node inside a loop has two
in-edges and receives a `Join`, so it is the join case rather than a case of its own; the build
log §5.1 carries the four the list does not have. The scheduling record follows.

- **The gap.** A node declares `output_schema`, what it produces. **Nothing anywhere declares what
  a node accepts.** `Graph` validates node ids, edges, loops, retries and reachability, and never
  compares a node's declared output with what its successors expect.
- **Why it is not a nuisance.** A mistyped input does not reliably fail. The shape every shipped
  example uses, and the one `scripts/record_backend_cassettes.py::eval_verify` uses, interpolates
  whatever arrived: `f"Check this: {inputs}"`. Measured at item 8a: inserting a node between two
  others left the run at `outcome: "completed"` with the downstream node silently building its
  prompt from a different value. There is no error to locate, so a run-time message naming the
  edge does not cover it.
- **The design.** `input_schema=` on a node, optional, checked at construction against each
  predecessor's `output_schema`. Item 8a's `_refuse_reshaped_inputs` is the relative form of the
  same check and is the precedent for the message.
- **Six cases where a naive check refuses a correct pipeline**, and the reason this needs a
  design pass rather than a bolt-on: the entry node, which receives run inputs and has no
  predecessor; a node with several in-edges, which receives a `Join` keyed by source rather than
  any one schema; a fan-out successor, which receives a `FanOutResult`; a node inside a loop,
  whose predecessor can be a later node; a predecessor declaring no `output_schema` at all; and
  an `on_error` handler, which receives the failure rather than an output. Getting any of them
  wrong is the over-refusal item 8 named as how a suite gets switched off.
- **What it touches.** All three node kinds, `graph.py`, `docs/pipeline.md`, and the manifest node
  entry if the declaration is recorded.

---

---

## `plan.md` §6, as it stood before 2026-08-06

*The watch list and the struck-through action list. Kept because two of the watch items are still live and are restated in `plan.md` §6 today.*

## 6. Immediate next actions

Phase 0 is complete, and so is every decision that was blocking Phase 1. ~~Write `docs/failure-taxonomy.md`~~ · ~~Write `docs/trajectory-format.md`~~ · ~~Confirm open question 2 (OpenTelemetry alignment)~~ · ~~Choose the v0 conformance-check subset~~ · ~~Settle naming, packaging, and the Python floor~~ · ~~Set up the repository~~ — all done 2026-07-26.

**Phase 1 is under way.** Items 3 to 8 and 8c to 8f are built. ~~agent shape~~ · ~~run envelope~~ · ~~model client seam (dual backend)~~ · ~~context builder~~ · ~~tool registry and tools~~ · ~~the §3.5 cold-read checkpoint~~ (done 2026-07-28, `runs/checkpoint-item7/findings.md`) · ~~eval machinery~~ (done 2026-07-29) · the shipped-document review with Thilina, seven of nine documents done · ~~the branching sitting~~ (done 2026-08-03) · ~~branching (item 8c)~~ (done 2026-08-04) · ~~suspend and resume (item 8d)~~ (done 2026-08-04) · ~~streaming (item 8e)~~ (done 2026-08-04) · ~~reasoning output (item 8f)~~ (done 2026-08-05) · ~~the six checks (item 9)~~ (done 2026-08-06) · ~~ablation as variant comparison (item 8a)~~ (done 2026-08-06) · **what a node accepts (item 8g), which is next, then trajectory sampling (item 8b)** · then the skill, the brief and the elicitation sets, with FT-24 built alongside them. Three ordering constraints inside that: FT-24 needs the required-question set and the stage vocabulary, so it moved to item 12 on 2026-08-05 while the brief file it reads is defined at item 9; items 8a and 8b sit between 9 and 10 by a decision taken at the document review on 2026-07-30; and item 8c preceded item 9 by a decision taken at the branching sitting on 2026-08-03.

**The document review comes before item 9, and it is not a code task.** Thilina is part-way through a pass over `docs/`, with comments left in the files as HTML comments and standing instructions under "Thilina's Corner" in `random-thoughts-questions.md`. `handoff.md` carries what he has named so far and a prompt to start the session. The reason it goes first: item 9's seven checks are derived from `docs/failure-taxonomy.md`, and that is the document he says needs the most work. Writing seven checks against a spec about to be rewritten is work done twice.

**Watch during Phase 1:**

- The trajectory format is version `0.11` and pre-adoption. The first four bumps: at item 4 `model_call` gained a required `replayed`, at item 5 §5.1 gained the disjointness rule and the convention for a backend that reports a prompt size without its split, at item 6 `model_call` gained a required `context`, and at item 7 `parent_id` was redefined so a model call made inside a tool hangs off that tool's record and `tool_call` gained `re_executed`. Five more followed, at items 7 and 8c and at three document reviews; `design/trajectory-format-changelog.md` carries the table and what each one settled. Every bump came from building or writing against the format, which is what the pre-adoption clause is for, and Phase 1 is the cheapest moment any of them will ever happen. If another field turns out wrong or missing, change it and bump again.
- ~~**Two things in the format are asserted rather than measured.**~~ **Both measured 2026-07-26, at item 5, against a local server.** vLLM *does* report cached prefix tokens, in `prompt_tokens_details`, when started with `--enable-prompt-tokens-details`, and it reports newly cached tokens as `created_cache_tokens` besides. The two counts and the uncached remainder are disjoint and sum exactly to `prompt_tokens`, verified on a call that both read a cached prefix and extended it. Without the flag the field is absent entirely, which is the case `0.4` now specifies. In-flight counts are exposed on `/metrics` as `vllm:num_requests_running`, so `concurrent_requests` is populatable and compute cost is an upper bound **by choice rather than permanently**: the adapter does not scrape it, because that costs a request per call and samples an instant rather than the call's lifetime. ~~Revisit at item 8, where the eval runner is the first thing to issue calls in parallel.~~

  **Revisited and closed at item 8.** `scripts/probe_vllm_concurrency.py` fired 1, 2, 4 and 8 requests at once at the local server, and `vllm:num_requests_running` tracked what was issued exactly, with nothing queued. `VLLMClient(report_concurrency=True)` now fills the field, default off, at the cost of one request per call. **The instant it is sampled at is the whole decision**: read before the send, a batch issued together each see an idle server and every one records 1, which under a compute basis charges each the whole device and reports several times the real cost. The reading is taken a moment after the send instead. Item 8's entry carries the rest.
- **A documented bug is not a measurement.** The first pass at item 5 cited an open vLLM issue reporting `prompt_tokens_details` as always null, and recommended a format change on that basis. Running the server disproved it in one call. The measurement was cheap and available the whole time.
- **Docstring usage examples are unverified and will drift.** Every public name carries one, written as a literal block rather than a doctest, so an API change leaves the example wrong with the suite still green. `scripts/prose_check.py` records this among its own limitations. Closing it means running the runnable subset under `--doctest-modules`; the examples that need a model client or a document index cannot run as written and would need fixtures or a split. Worth doing once the API settles after dogfood #1 — doing it now would pin examples to an API the first dogfood is expected to change.

---

#### Item 8b — Trajectory volume in production

**Built 2026-08-06. `build-logs/item8b-build-log.md` supersedes this entry and disagrees with
it in five places**, each measured: the payload fields are 91% of the bytes on a production
shape and 22% on the library's own recordings, 1% sampling cuts volume by about 10x rather
than by two orders of magnitude, the sizing below is low by a factor of four, the
`{"type": "unknown"}` convention cannot carry a dropped payload, and per-node metrics do read
payloads. The entry as it stood follows.

**Not built. Scheduled 2026-07-30, in the same slot as item 8a.** Decided at the document review; the design below is settled and the build is not.

- **The problem, raised by Thilina.** `RunEnvelope.prepare` always writes `trajectory.jsonl` and there is no way to turn it off. A `model_call` record embeds the rendered request and the response verbatim, and an agent node re-sends its growing context every turn, so a five-turn node over a 4,000-token context writes on the order of 100KB per run, more with retrieved documents in context. Nothing bounds it. A project in production accumulates linearly with traffic. Cassettes are not part of this: `Cassette.off()` is already the default, so a production project that never passes `cassette=` records none.
- **Storage is the smaller half.** Production trajectories carry end-user text. `Redaction` matches declared credential patterns and built-in high-confidence ones; it does not detect arbitrary personal data, and `consultation` records are end-user answers by definition. **Whether `consultation` records should carry stricter redaction defaults than other records is an open question this item owns**, moved here on 2026-07-30 from the shipped document, which no longer carries open questions. It is decided once the shopping agent produces real ones. "Always record everything, forever" is a data-protection position the library currently takes on the builder's behalf without saying so.
- **A second question moved here from the same place**, and it belongs to this item for the same reason: does `inputs` on a `model_call` store the fully rendered request or a reference to one? A full render is correct for training data and expensive for long contexts, and the levels-plus-sampling design below is the first thing that makes the cost measurable. Decide it with real trajectory sizes from dogfood #1 rather than by argument.
- **The tension it had to be argued against.** FT-13's design is record-by-construction, and an off switch is the remembering-to that FT-13 exists to prevent. The resolution is that FT-13 was argued about the *development* project, at `prototype` tier. Production is a different context and the library had no concept of it, which was the actual gap.
- **Rejected: change nothing.** Builders who hit scale stop using the envelope in production or fork it, which loses the production trajectory stream that §4's training-data chain depends on. It loses it quietly, which makes it the worst of the three.
- **Rejected: a boolean off switch.** Honest and trivial, but it forces a choice between unbounded volume and no observability, and it hands the coding agent a one-line way to make FT-13 unenforceable.
- **Chosen: levels plus sampling.** `RunEnvelope(trajectory=Trajectory.sampled(0.01))`. Every run still writes a trajectory, so FT-13 stays literally true and per-node metrics, cost derivation and budgets are unaffected, because none of them read payloads. Sampling governs `inputs` and `outputs` only, which are nearly all of the bytes and all of the personal data, so 1% cuts volume by roughly two orders of magnitude with every number intact. A run that errored keeps full payloads whatever the rate, which is ordinary tail-based sampling and is the case a builder actually needs. Thilina accepted it on the ground that the rate can be set to 0 where a project needs that.
- **What it costs.** An envelope option amending item 4, payload fields becoming nullable with a reason in the trajectory format (the existing `{"type": "unknown"}` convention already covers the shape), a manifest field recording the rate so a reader knows what they are looking at, and a format bump on both.
- **The document consequence, already handled.** `docs/failure-taxonomy.md` FT-13 currently says recording is not a setting, which is true today. It takes a two-line edit when this lands. Writing it before the build would have been describing an unreleased feature as released.

---

# The plan as run — sections moved out of `plan.md` on 2026-08-09

**Moved when v0 was met and `plan.md` was cut back to what is live.** Nothing here was
rewritten; each block is the text `plan.md` carried, under its old section number, so a
citation such as `plan.md §4.2` resolves here when the summary left behind is not enough. The
findings records and build logs supersede these wherever they overlap.

## §1 (part) — Phase 0, and what was decided before Phase 1

**Phase 0 delivered:** `docs/failure-taxonomy.md` (27 entries) and `docs/trajectory-format.md` (version `0.2` at the time, `0.5` since items 4, 5 and 6). Three decisions were closed along the way that Phase 1 depends on — the elicitation/consultation split (`simple-agents.md` §2.8–2.9), the four trajectory record types (§6), and OpenTelemetry alignment rejected (§11 open question 2).

**Decided 2026-07-26, before Phase 1 code:** the v0 conformance-check subset and its tier bar (§3.1 item 9), a dual-backend model seam (item 5), and the packaging questions that land in the first commit — distribution `simple-agents`, import `simple_agents`, one CLI `simple-agents`, Python ≥ 3.11, Apache-2.0, and a bespoke check runner rather than a pytest plugin. The runner is the load-bearing one: `docs/failure-taxonomy.md`'s failure messages are a prompt surface, and pytest's assertion output would fight that design at every step.

## §2 — The ordering decision, and why it was reversed

**Decision: build Simple Agents v0 first, then build the shopping agent with it.**

An earlier plan had the opposite order — build the shopping agent by hand, log the friction, extract the library from it. That was rejected, and the reason matters:

> Hand-building the shopping agent surfaces the friction a **human** hits typing code. The product is a procedure a **coding agent** follows. Those are different failure surfaces, and translating one into the other loses exactly the information we need.

**The risk this takes on**, stated honestly: designing an abstraction before having a working instance of what it abstracts. Rails came out of Basecamp, Django out of a newsroom, Simple Transformers out of Thilina's own repeated notebooks. Extraction beats invention for API design almost every time.

**Two mitigations, both mandatory:**

1. **v0 is thin and explicitly disposable.** Nothing in v0 is defended. If dogfooding says an abstraction is wrong, it gets deleted, not patched.
2. **The dogfood loop is tight enough that reality corrects the design within days, not months.** Hence the hard cap in Phase 1 and the trivial-task-first rule in Phase 2.

## §3.1 (part) — the built items' closing entries

10. ~~**The procedure as a skill**~~, ~~**the brief's elicitation half**~~ and ~~**the staged
    elicitation sets**~~. **Built 2026-08-06 as one item**, on Thilina's ruling at the sitting:
    thirteen earned questions is smaller than it sounds, and with all three built the dogfood
    can run. `build-logs/item10-build-log.md` is the record. **Items 11 and 12 keep their rows
    in the table above**, because about 290 citations across the repository resolve against the
    identifiers.

    What shipped: `docs/procedure.md`, the twelfth shipped document and the skill, force-included
    into the wheel a second time at the path a skill installer reads; `simple-agents init`, which
    links it into the project's skills directory; three stages, `shape`, `build` and `measure`,
    validated on the brief and read by the gate; sixteen elicitation questions with a scaffold
    each, eleven of them required, printed by `simple-agents questions`; and FT-24, the seventh
    conformance check.

13. ~~**Tool-authoring guide.**~~ **Built 2026-08-07.** The entry's framing did not survive the
    measurement and the item did. `docs/tools.md` was already the tool-authoring guide, and the
    two cold-read sessions of `runs/checkpoint-item7/findings.md` had both written good tools and
    contract tests against it, so no thirteenth document was written.

    What §1 found instead: a tool whose body changed replayed its old answer silently, with
    `version` `null` on all 13 tool entries anywhere on this machine and the resume guard that
    compares it therefore unable to fire; the whole tool contract reachable only from inside an
    `AgentNode`, so a `spends_money` tool called at a fixed point left no record at all; FT-23's
    declared `static` surface reading the wrong name for all eight shipped tools; and no
    elicitation question reaching a tool.

    What shipped: `Deterministic(fn, tools=[...])` with `ctx.call_tool`, recorded and replayed
    as an `AgentNode`'s calls are; a tool version derived from the function's source where the
    author declares none; `Pipeline(tools=registry)` putting the whole declared tool surface in
    the manifest, at manifest format `0.11`; `tool_effects`, a seventeenth elicitation question
    required at `build`; FT-23 narrowed to the half the library enforces; and four edits to
    `docs/tools.md`. `build-logs/item13-build-log.md` is the record.

14. ~~**Project-supplied metrics.**~~ **Built 2026-08-07.** `ProjectMetric` reports a figure the
    project computes from the answer, beside the six rates and per node, at results format `0.5`.
    Two of the entry's four checkable claims did not survive being measured;
    `build-logs/item14-build-log.md` is the record.

## §3.3 (part) — the ship criterion's record

*Amended 2026-08-06, at the item 10 sitting.* The criterion said "conformance-passing" and named no tier, which was written before any check existed. **At tier `prototype` the bar is a brief and one run**, and item 10 §1.2 measured that three hand-written files pass it with the library never called. §4.2 already requires `evaluated` in substance, since it asks for splits, labels and a proportion of unanswerable examples. Naming the tier states what was already meant.

**"Cold start" means informational, not social.** The coding agent begins with no context from this design work and no prior session — it has the library and its docs, nothing else. It is *expected* to elicit from the builder, and doing so is the criterion being met, not a violation of it. See §4.1 for how this is handled during dogfooding.

**Met on 2026-08-07, by dogfood #1, twice.** Run 1: 9 of 9 at tier `evaluated`, exit 0, on 470 envelope-written runs, an `EvalSuite.run` results file, and 12 elicited brief entries. Run 2, against the wheel carrying run 1's fixes: 9 of 9, exit 0, on 635 envelope-written runs, 782 tool calls through the built-in registry, a recorded cassette replayed, and 16 brief entries with no deferrals. Neither is item 10 §1.2's three hand-written files. `runs/dogfood-1/findings.md` §2 and `runs/dogfood-1/run2-findings.md` §2 record what each passed on.

**The bar rose between them and the second run cleared the higher one.** FT-03 and FT-04 became checks off run 1, so a project that would have passed at seven could fail at nine. Run 2 passed FT-03 on a split drawn by whole source before any example existed, which is the failure run 1 paid 150 rollouts to discover.

**Hard cap: two weeks.** If the criterion isn't met by then, cut scope — do not extend. Scope creep at this stage compounds into a framework nobody dogfooded.

## §3.5 — Checkpoints during Phase 1

Two measurements taken while building, distinct from dogfood #1 and not logged against it. Both are the §5 meta-eval technique aimed at one component, and both cost a single session and no elicitation, since at these points there is no procedure to elicit with.

**The cold-read test.** A fresh coding-agent session, given only the library and its docs, asked something narrow: *"using this library, write a two-node pipeline that runs and records a trajectory."* What is under test is whether the docstrings and `docs/` are readable by something that has never seen this design work. A cold agent writing `Pipeline.run(trajectory_path=...)` from habit is a documentation bug, and it is cheap now and expensive once six more items sit on top of the misreading.

- **After item 5**, two sessions rather than one. See below.
- **After item 7**, with the registry and the built-in tools in play. Same shape, more surface: what has to be read correctly now includes a tool set the builder did not write. **Shape the task so a context decision is forced** (decided at item 6): a corpus large enough that the session has to choose between fanning out, packing one prompt, or writing a builder. One session then tests the tool surface and the context surface together, which is why no separate checkpoint was inserted after item 6 — two sessions a week apart over an overlapping surface mostly measure the same thing twice, and item 7 changes the node constructors again anyway. What it reads on the context side: whether `docs/context.md` is found at all, and whether a session meeting a long conversation reaches for the seam or hand-rolls truncation inside a prompt function.

**Neither is a dogfood.** There is no procedure, no gates, and no conformance to pass at these points, so a session that flounders for want of a procedure is telling us nothing. Read only whether the API was used correctly.

## §4 (preamble) — the entry condition

**Entry condition: every item in §3.1 is built.** Dogfood #1 is not a step that follows Phase 1, it is the measurement that decides whether Phase 1 met its criterion, so running it against a partial build measures the gaps rather than the handshake. Items 9 through 12 are the ones that make it meaningful at all: without the checks there is nothing to pass, and without the skill, the brief, and the elicitation sets there is no procedure under test. A failure sends the work to Phase 3, not back to the start; the intervention log is the v0.1 changelog. For measurements worth taking before that point, see §3.5.

## §4.1 (part) — how the protocol's three runs went

*Run twice on 2026-08-07. `runs/dogfood-1/findings.md` and `runs/dogfood-1/run2-findings.md` are the logs.* **All three categories came back empty on both runs**: no forced intervention, no question the library should have answered itself, nothing Thilina wanted to volunteer. Run 2 asked 18 questions against run 1's 14 brief entries and he read none of them as over-asking. Its prompt also asked for interactions recorded verbatim so the log could be checked against him rather than trusted, and it checked.

**Step 5's three categories are not the instrument they were expected to be**, and two empty runs is the evidence for that rather than against it. **Every finding in both records came from reading the artifacts**, which is why item 8b's and item 13's §1 precedent is in the protocol. Dogfood #2 is the last chance for the categories on a task whose shape they were designed for.

*Measured 2026-08-08, on dogfood #2, which was that last chance.* **One entry, in category 2, and the artifacts settled it rather than the instrument.** Thilina raised it with an explicit "I don't remember if I was offered more balanced options", and the build log showed he was not: `absence_vs_error` was put as three options spanning both poles and a midpoint the coding agent had pre-committed to arguing against, he took the nearest, and corrected it unprompted 24 minutes later. `runs/dogfood-2/findings.md` §7.1 has it, and traces the library's share to the scaffold asking "which is worse" for a question whose answer the code consumes as a magnitude. Categories 1 and 3 were empty for the third time. **Three runs, one entry, and it needed the artifacts to confirm.**

**What the artifacts cannot answer, and the log has to.** Reading the run directories gives the wall clock, the cost, the calls and what the agent did. It cannot give the time the coding agent spent blocked on the builder, which is the one figure separating how long a build took from how long a builder took to answer. Run 2 was 189 minutes with 26 of them holding a model call, and how much of the remaining 163 was waiting on Thilina is not on disk.

*Amended 2026-08-06, at the item 10 sitting.* **Dogfood #1 runs once**, and dogfood #2 keeps the two or three. Thilina's position was that the trivial task is too simple to be worth running at all; what was conceded is the cost rather than the order. The argument that kept it is §4.2's, that a failure in the shopping agent is ambiguous between "the library misled the coding agent" and "this task is hard", and item 10 §1.10 and §1.11 gave it evidence: building a three-document toy with full context on this library, four budget numbers were invented and one node's constructor was written from a prior about other libraries without opening the six-line section showing the right call. Neither would be visible on a hard task. Do-not-change #13 is untouched.

## §4.2 — Dogfood #1 must be a trivial task

**Decision: the first dogfood is NOT the shopping agent.**

Use something with cheap, unambiguous ground truth — question answering over a small fixed document set with checkable answers.

**Decided 2026-07-26: a subset of SQuAD 2.0, around 60 examples, with the passages pooled into one collection and the agent given a search tool over it.** It satisfies every clause of that sentence: extractive short answers scored by exact match, so no judge model sits inside the thing under test; the pooled passages as the document collection; and unanswerable questions by design, which is the absent-data case FT-04 asks for and the reason false confidence can be measured separately from recall. Fix the proportion of unanswerable examples deliberately rather than taking whatever the sample gives.

**The pooling is what makes it a document set rather than a reading comprehension exercise, and it is not optional.** Handing the agent the question alongside its own passage collapses the pipeline to a single `LLMNode` and the dogfood then exercises no tool at all: the tool registry and minimal tool set of item 7 ship undogfooded, no `side_effect_class` is ever declared, and the tool-call half of the cassette is never replayed. Retrieval over sixty short passages stays trivial in the sense this section requires, and it is the shape the library is built around.

**Wrinkle to handle when building the set.** SQuAD 2.0's unanswerable questions are unanswerable relative to their own paragraph. Once paragraphs are pooled, a question labelled unanswerable may become answerable from a different one, which is label noise pointing in the worst direction: it scores a correct answer as false confidence. Draw the pool from unrelated articles, or verify each unanswerable against the whole pool at build time.

**StrategyQA and MS MARCO were considered and rejected.** StrategyQA is smaller and boolean-scored, which makes the harness trivial, but the *task* is not trivial: its questions are constructed so the reasoning steps are implicit, which is exactly the ambiguity between "the library misled the coding agent" and "this task is hard" that this section exists to exclude. It also has no absent-data case at all, so `unknown` would never legitimately fire and the discipline in §2.6 of `simple-agents.md` would go untested. MS MARCO has unanswerable queries but free-text answers, and scoring them needs fuzzy matching or a judge, which adds a confounding component to the handshake under test.

**Every candidate was contaminated, and SQuAD 2.0 is no exception.** It is a public benchmark and is almost certainly in the pretraining data of any model worth pointing at it, so the agent can answer from memory rather than from the passage. This is survivable here because dogfood #1 measures the handshake and not the agent, and the ship criterion in §3.3 is "conformance-passing", not "good". It is recorded so that nobody later cites the number as evidence that the library produces accurate agents. It is not evidence of that.

**The dataset is the builder's answer, held until asked. It is not handed over.** Building the subset in advance and giving it to the dogfood session pre-answers "what is your ground truth", which is one of the four seed elicitation questions (§3.1 item 12) and is covered by FT-24, the only one of the seven v0 checks that tests elicitation at all. Arriving with a finished labelled set and its splits already drawn is the unsolicited help that §4.1 step 3 forbids, and it removes the thing the run exists to measure. When the coding agent elicits ground truth, answer it fully: SQuAD 2.0, passages pooled, unanswerables verified against the pool. If it never asks, that is the highest-value entry in the intervention log.

**One consequence of item 4 that changes the trade-off:** dataset size no longer drives iteration speed. The first recording costs network and time; every replay after it is a disk read, so running the protocol two or three times per §4.1 costs the same whichever set was chosen.

*Measured 2026-08-07, twice.* **The pooling argument above did not hold on run 1 and held on run 2.** Run 1 pooled the passages and wrote BM25 by hand rather than reaching for `document_search`, so no tool was declared and `manifest.tools` was `[]` on all 470 runs (`runs/dogfood-1/findings.md` D4). Run 2 used `document_search` from the built-ins, declared it `read_only`, made 782 tool calls and replayed 173 of them from a cassette. The change between them is one sentence: `docs/procedure.md` stage 2 names the built-in set before a node is written. **What decided it was routing rather than the task**, which is worth carrying into §4.3: a shipped component a coding agent has no reason to open is one it reimplements.

**Why:** the shopping agent's extraction problem is genuinely hard. Failures would be ambiguous between "the library misled the agent" and "this task is difficult," and the time would go into debugging retailer HTML instead of the library. Get a clean signal on the handshake first.

This is in the do-not-change list (`simple-agents.md` §9.13). It is a methodological requirement.

## §4.3 — Dogfood #2 — the clothes shopping agent

The real motivating case, run second, once the handshake is clean.

**Task:** find t-shirts that fit, from online retailers, where the garment measurement that decides fit is often not published. Returns suggestions with direct links. *Amended 2026-08-07: trousers to t-shirts, on Thilina's instruction. The problem shape is unchanged and the conflict is sharper — a t-shirt has to be long enough in the body without being too wide in the shoulders and chest, so going up a size to buy length is the failure the agent exists to avoid, and one garment can pass on one measurement and fail on another.*

**What makes it a good second dogfood:** the builder is also the end user here, is the ground truth, and will know immediately whether it works; it's genuinely multi-step; and the hard part — extracting a specific fact from heterogeneous pages where it is sometimes absent — is exactly the narrow skill where a small trained model could later beat a prompted frontier model. It becomes the library's first real `Task`.

**What was agreed for it, split three ways.** *Amended 2026-08-07, at the run 2 sitting, on Thilina's instruction that the original list was overzealous.* It read "carry these in; they are not open for rediscovery" and was one list of seven bullets. Read against what the two runs of dogfood #1 actually measured, the seven are three different kinds of thing, and only one kind belongs in the prompt.

**(a) Answers to give when asked, and not before.** These are elicitation answers, and handing them over pre-answers `ground_truth`, `answer_form`, `agency_boundary` and `budget`. §4.2 already ruled on this shape for the dataset: arriving with the answer "removes the thing the run exists to measure".

- **Scope for the first pass:** one garment type (t-shirts for men), three retailers, no browser automation, hardcoded personal profile rather than a generic preference model. Brands publishing full per-size garment measurements are dramatically easier targets; start there. **Fit is more than one measurement and they trade against each other**: body length has to reach, and shoulder and chest have to not be too wide, so a garment is a fit only where every measurement passes. This is the builder's answer to `answer_form` and to `ground_truth`, and it stays out of the prompt.
- **Normalize the measurement schema up front.** Retailers report body length as length from high point of shoulder, as total length, or as back length, measure chest flat or as a circumference, and quote shoulder width across the seams or across the back, sometimes only for the sample size. Define the target schema first; extraction fills *that*, with explicit `unknown` per measurement rather than a guess, so a garment missing one measurement is distinguishable from one that fails on it.
- **Hand-label 40–50 product URLs before writing the agent**, including pages where the measurement is genuinely absent, so false-confidence rate is measurable separately from recall.

**The labelling is the one that has to be settled before the run rather than during it**, because it is hours of the builder's work rather than a sentence, and §4.1 step 3 says to answer fully. A builder who will not label when asked leaves the run stalled at stage 3, and "it stalled because the builder would not label" is a different finding from "the library failed".

*Measured 2026-08-08.* **It was never asked for as 40 to 50, and the builder labelled everything he was asked for, immediately.** The elicitation fired off a builder question rather than off the procedure, and the project's own `label.py` capped a sitting at 5 by default, so the run's one number rests on n=4 and its interval is 51% to 100%. The clause above anticipated a builder who would not label and the failure mode was the opposite: **the tool's default decided the sample size and nothing surfaced that it had.** What the clause got right is that the labelling had to be settled in advance; what it did not anticipate is a project reaching a number without reaching stage 3 at all (`runs/dogfood-2/findings.md` §10 and §11.3).

**(b) Predictions, scored afterwards.** These are claims about what a cold agent does next, which is the shape that gave run 2 its value: four predictions written down in advance, three of them passes. These four are about the library's own design opinion rather than about a doc fix, which makes them worth more.

- **Structured data first, LLM last.** Many retail pages embed `schema.org/Product` JSON-LD, and size charts are real HTML tables. **Prediction:** a cold agent reaches for LLM extraction on the whole page rather than parsing those deterministically and using a model on the residue.
- **Where agency earns its cost:** the missing-measurement hunt (size guide subpage, brand site, review mentioning it, size chart embedded as an image — the path is discovered, not planned); constraint relaxation when zero products pass; possibly cross-retailer strategy. **Prediction:** exactly these become `AgentNode`s and nothing else does.
- **Everything else collapses into `LLMNode`s under ablation.** **Prediction:** the ablation is run at all, and it agrees.
- **The built-in tools are found.** Run 1 reimplemented `document_search` line for line and run 2 used it, and what changed was one sentence of routing. This task reaches `http_fetch` and `extract_to_schema`, which no dogfood has touched. **Prediction:** both are found, on the strength of the same routing fix.

*Scored 2026-08-08, from `runs/dogfood-2/findings.md` §3.* **One pass, two halves, one unreachable.**

- **Structured data first, LLM last. Held**, and the shape is more than the prediction claimed:
  the project *did* parse JSON-LD deterministically and then rendered the parse back into text
  for the model, so `product_name`, `brand` and `price` came from the model on a page where the
  parse already held all three. The deterministic work made the model's input smaller rather
  than its job smaller.
- **Where agency earns its cost. Half.** `chase` is the only `AgentNode` and nothing else is, so
  the "nothing else" half holds and holds under pressure: when the builder asked for *more*
  agency the coding agent made it an `LLMNode` and argued FT-11 explicitly. Constraint
  relaxation was never built at all, and cross-retailer strategy is not a node.
- **The ablation is run at all. Not reached**, and §10 of that record is why: the project never
  left stage `build`, so there was no ablation to agree or disagree.
- **The built-in tools are found. Half.** `http_fetch` was found and *extended* rather than
  reimplemented, which is D4's routing fix holding on a second cold run and on a harder case.
  `extract_to_schema` was never reached for, and the docs told it not to: that tool's own
  docstring says extraction at a fixed point is an `LLMNode(over=...)`, which is what the
  project wrote. The case the tool exists for — an `AgentNode` deciding mid-run that it needs
  typed facts — was present and went unnoticed.

**(c) Constraints on the world, which go in the prompt.** These are not about the library or the measurement. A cold agent pointed at retail sites may crawl hard, and that is a real-world harm rather than a finding.

- **Search via API with `site:` filters, not crawling.** Crawling category pages means fighting bot protection, infinite scroll, and JS-rendered SPAs. Respect `robots.txt` and ToS, keep concurrency low.
- **Cache everything** — pages and extractions — into a local store. This turns a fragile live agent into an accumulating dataset, and it is also the eval set and the future training data.

**Method, and it is ours rather than the coding agent's:** build the fully agentic oracle first, then ablate (`simple-agents.md` §4.3). This is a prediction in group (b) rather than an instruction.

---

# Phase 3 as run — sections moved out of `plan.md` on 2026-08-15

**§1 had reached 740 lines against a four-item queue, two-thirds of the file.** This is the same
cut as "The plan as run" above, applied to Phase 3. Nothing here was rewritten; each section is
the entry as `plan.md` carried it, and `plan.md` §1.3 to §1.13 are the tombstones that point
here. Where an item has a build log, that log was written while building and supersedes the
brief here wherever the two differ.

### 1.3 ~~Per-node model selection~~ — built 2026-08-10

**`build-logs/per-node-model-build-log.md`**

### 1.4 ~~A pipeline exposed to a model as a tool~~ — built 2026-08-10

**`build-logs/pipeline-as-tool-build-log.md` is the record.** It ships as
`AgentNode(delegates=[Delegation(pipeline, description=...)])`, a declaration rather than a
`Tool`, because `Tool` requires a side-effect class a pipeline cannot honestly declare and
because a declaration is what `declared_nodes()` can descend into. §1.7 has the outcome. This
section held the brief until the item was built; it is collapsed rather than deleted so
citations against §1.4 keep resolving.

**One claim in the brief did not survive being checked.** It said `simple-agents.md` §8.2
already settles replay because "a pipeline-as-tool is that case exactly". It is not: `re_executed`
is derived from a handle in the signature, and a delegation has no handle, so nothing would have
put it on that side of the line. What is true is that it belongs there **for the same reason**,
which is what the brief was reaching for. No new rule was needed; a mechanism was.

### 1.5 ~~Memory~~ — built 2026-08-10

**`build-logs/memory-build-log.md` is the record.** It ships as a store declared on the envelope
and reached through recorded tool calls, which is neither of the two things this section asked a
design to choose between: both are intra-run, and memory's writer and reader are in different
runs. It amends §3.2, and §1.7 has the outcome. This section held the brief until the item was
built; it is collapsed rather than deleted so citations against §1.5 keep resolving.

**Two of its scope claims did not survive being checked**, and §2 of the build log is where that
is recorded: redaction and the cassette were already wrong for a store the library does not own,
and the cassette fix that shipped is not the one that was approved.

### 1.6 ~~`ablate()` is broken on any pipeline it did not generate~~ — built 2026-08-10

**`build-logs/ablate-build-log.md` is the record.** The two failures this section named were
symptoms of a third thing: `Pipeline` as a container was read only for its leaves, so
`declared_nodes()` and `manifest_nodes()` handed every reader downstream a flat list that is not
a graph. Ten defects in all, eight of them not in this brief. §1.7 has the outcome. This
section held the brief until the item was built; it is collapsed rather than deleted so
citations against §1.6 keep resolving.

### 1.7 What has closed in Phase 3

Newest first, so §1.2 stays a queue rather than a history.

- **The `ship` stage**, 2026-08-15, designed and built the same day.
  **`build-logs/ship-stage-build-log.md` is the record**: §2 is the five decisions, **§3 is what
  it does not close**, §6 is the build. A fifth stage after `measure`, for the point where
  somebody other than the builder uses the agent. **The tier now decides which stages a project
  has**: `prototype` has no `measure`, so its questions stop being required in the same report
  that says its checks do not apply, and a brief declaring both is refused. That collision was in
  the shipped suite before this item and in four of our own fixtures (§1.1, §6.3). A run says
  whether an end user was on the other end, `RunEnvelope(live=True)` and `runs(live=True)`; the
  checks read the runs that are not live; an evaluation's rollouts never are. Four questions at
  `ship`, three required. **FT-31**, `Shipped on a development channel`, fails a shipped project
  whose consultations reach `coding_agent`, `simulated`, `canned` or `builder`, and is the first
  check gated on a stage rather than on a tier alone. `docs/shipping.md` is new. Manifest `0.23`
  to `0.24`; the trajectory did not move. **2230 tests.** Verified live against Gemini and vLLM,
  both arms separating the two runs and FT-31 firing on the stub (§6.4).
- **Dogfood #4's cheap fixes**, 2026-08-15, one short pass off
  `build-logs/consultation-build-log.md` §5.1. Four surfaces that read as working and were not: a
  routed-around node no longer fails FT-07, which is what cost 1,584 model calls in one evaluation
  arm; a fan-out declaring a `retry=` that collecting makes inert is refused at construction; a
  `consult` tool's version stops covering the library's own body, so a library upgrade no longer
  makes every recorded consultation miss; and `progress_of` reaches the top-level namespace the
  full-test pass ruled it into. **2193 tests.** No format moved.
  `build-logs/dogfood-4-fixes-build-log.md` is the record, and §5 is what the pass did not change. **`progress_of` also produced a check**: every name a package `__init__` imports from inside the library has to be in its `__all__`, which holds everywhere with no exemption and is two tests rather than a sitting.
  `runs/dogfood-4/inventory.md` §F carries the dispositions; F-3 to F-7 are open.
- **Consultation: who answers, and what the record says**, 2026-08-15, both halves.
  A channel declares `answered_by` and is refused without one; a coding agent answering declares
  the builder's `permission` beside it; both reach the manifest's tool entry, which is the marker
  FT-25's check and the `ship` gate need. `Unavailable(reason=...)` and `unattended()` for a run
  with nobody to ask, with its own resolution, its own required `on_reply` branch, and the model
  told once and answered from that afterwards. `timed_out` and `defaulted` are gone.
  `RunEnvelope(end_user=...)` says who a run asks without the pipeline being rebuilt, and
  `EvalSuite.run(end_user=SimulatedEndUser(model=...))` answers an evaluation's consultations
  with a model playing the person `Example.end_user` describes, bound per rollout, recorded with
  its model and cost, and inside the evaluation's identity. Trajectory `0.21` to `0.22`, manifest
  `0.22` to `0.23`, results file `0.12` to `0.13`. **2176 tests.**
  `build-logs/consultation-build-log.md` is the sitting and §7 is the build. **Four things the
  sitting did not settle and two defects the build found are §7.2 and §7.3**, including a
  `answered_by` that named the wrong answerer whenever a run supplied its own channel, and a
  `Cost` reaching a record as the string its `repr` produces. **The hosted suspend fixture is
  Gemini now**: Mistral is out of credits, and `tests/cassettes/suspend.jsonl` became
  `suspend-gemini.jsonl`.
- **The full-test QA pass**, 2026-08-13, run outside this queue against `2f4db4c`. Five blockers
  and every other finding are fixed, merged and pushed; results file `0.11` to `0.12` and
  manifest `0.21` to `0.22`. `build-logs/full-test-checkpoint-build-log.md` is the entry point
  and `runs/full-test-2026-08-13/` is everything it produced.
- **Concurrency: independent branches, and a fan-out that runs together**, 2026-08-13. Three
  things overlap where they are declared to: `concurrent_nodes` groups on the pipeline,
  `concurrent_items` on a fan-out, `concurrent_tools` on an `AgentNode`, under
  `Pipeline.run(concurrency=N)` which is the most calls in flight and defaults to 1. A stop
  drains, `max_steps` reserves, `max_wall_clock_ms` becomes elapsed, `DeviceBasis` reports
  device-seconds with no rate, and a suspended run becomes a tree so two arms can stop at once
  and resume with `answers=`. Suspension `0.3` to `0.4`; trajectory and manifest unchanged.
  **1879 tests.** §1.12 is the design of record and
  `build-logs/concurrency-build-log.md` is the build. **What the testing found is most of the
  value**: seven defects, three of which predate the item and one of which shipped a wrong
  instruction to builders. The manifest lost counts under any concurrency, including an
  evaluation's; a trajectory could be written out of `sequence` order; `VectorScan` could file a
  vector under another document's identifier; `MemoryStore.write` and `UrlCache.put` shared a
  scratch file per key; `ablate` dropped the concurrency groups, putting a second difference into
  a comparison meant to hold one; and `warn_unpaced_wait` told a builder to wrap a client in a
  `PacedClient` against a backend that publishes no allowance to pace against, measured doing
  nothing on Gemini's free tier. **Measured live**: 7.5x at width 60 on Gemini, and vLLM
  reporting six requests in flight for a fan-out of six.

- **A consultation answer the library can read**, 2026-08-12. `consult` returns a `Reply`
  carrying which option the answer was, `on_reply` routes on it with a branch required for an
  unmatched answer and a refusal, and `resolution` gains `unmatched`. Trajectory `0.21`, manifest
  `0.21`, 1827 tests. `build-logs/typed-consultation-build-log.md`. **What it nearly shipped
  with**: a replayed evaluation recording `answered` where the live run recorded `unmatched`,
  because a `Reply` is a string and a cassette stores the text. **What it found beside the
  item**: `source_version` digests a closure's source, so any route built by a factory records a
  version that two different mappings share. **Measured live against Gemini and vLLM**, three
  outcomes each and a replay of each agreeing with its recording.

- **A Gemini adapter**, 2026-08-12. `build-logs/gemini-adapter-build-log.md`.

- **A design decision the coding agent proposes rather than makes**, 2026-08-11. Six decision
  kinds, `[decisions]` in the brief, **FT-30** as an eleventh check, and three elicitation
  questions: `how_far` and `involvement` at `brainstorm`, `presentation` at `shape`. 33
  questions. 1737 tests. `build-logs/decision-surface-build-log.md`. **The measurement**: dogfood #3 passed
  10 of 10 and fails 2 of 11 against this, on FT-24 and FT-30, which are exactly what its
  findings were about.

  **§1.11's lean on where the record lives did not survive.** It goes in the brief rather than
  `idea.md`, because a gate reads a per-decision status and `idea.md` is prose. That widens what
  the brief holds, and `CLAUDE.md`'s glossary still calls it the record of elicited answers.

  **Left open**: the build-log instruction, folded into this item at the sitting and not built;
  and whether asking the `measurement` kind is enough to close `DF3-D1`, which dogfood #4 is
  what measures.

- **The dogfood #3 fixes, and an evaluation that can be watched and re-entered**, 2026-08-11,
  in one sitting straight off the one that decided them. `DF3-D2`, `D4`, `D5`, `D6`, `D7` and
  `P1`, plus `EvalSuite.run(resume_from=...)` for `D3` and the `watch_eval.py` absorption as
  `on_rollout=` and `progress_of()`. Results file `0.10`. 1721 tests.
  `build-logs/dogfood-3-fixes-build-log.md`.

  **Verified live** against a local Qwen3-30B-A3B with tool calling: a model invented
  `find_book(year=...)`, exactly the argument that ended a dogfood #3 run, was refused
  model-facing, and **corrected itself on the next step with the run completing**.

  **Two things the build found that the sitting did not.** `per_node` was double-counting a
  consultation answered in a later process, which `docs/trajectory-format.md` §4.3 has always
  said not to do. And the obvious fix for `DF3-D2`, `extra='forbid'` on the validation model,
  would have shipped the wire-level change the sitting explicitly declined, because pydantic
  emits `additionalProperties: false` into the schema the backend is sent; the check is in
  `Tool.call` instead and a test holds the wire schema unchanged.

  **Left open**: the hosted arm, since Mistral is out of credits, and the strict tool schema,
  which still has no measurement against any backend.

- **Dogfood #3's findings record**, 2026-08-11. `runs/dogfood-3/findings.md`, ten findings over the
  book-recommendation task `items/example-projects.md` §17 named. **The run met the ship
  criterion at 10 of 10 and `DF3-D1` is what that is worth**: it passed with an evaluation whose
  chance rate was about 0.5%, and the replacement design's whole confidence interval sits below
  the chance rate the project computed for itself. §9.1 is the two items already built off the
  run, including `config.incomplete` absorbed verbatim; §9.3 is eight open items, unscheduled.

  **Two things the record could produce and earlier ones could not.** The project's git object
  store held 639 unreachable objects, which is how three deleted evaluations, an overwritten
  results file and seven versions of `idea.md` were recovered; they are files now, at
  `runs/dogfood-3/recovered/`. And **FT-29 has its first evidence**: `idea.md` grew by one section
  per stage across those seven versions. **What is gone**: no build log was asked for, so §4.1's
  waiting time is not recoverable for this run and is not reconstructed.

- **Semantic recall**, 2026-08-11. `DocumentIndex(embeddings=)` and `memory_search(embeddings=)`,
  with the ranking, the fusion, the reranker and the vector store each settable. A fourteenth
  document, `docs/retrieval.md`. 1683 tests. `build-logs/semantic-recall-build-log.md`.

- **A run records by default**, 2026-08-11. `RunEnvelope.cassette` defaults to
  `Cassette.into_run()`, and a run's recording is kept or dropped with its trajectory payloads
  on the one decision `Trajectory.keeps(run_id)` makes. Manifest `0.20`, gaining
  `cassette.dropped`. 30 elicitation questions, the new one required at `build`. 1635 tests.
  `build-logs/recording-default-build-log.md`. **Found rather than argued**: flipping the
  default alone moved 3 of 1619 tests and wrote nothing, because `Cassette.store` was a silent
  no-op with no path; and the conformance fixture generator has been broken since the
  `brainstorm` stage shipped, so the fixtures were being hand-edited. Both are repaired, and
  every fixture is now generated, including the two a copy-and-edit cannot produce.
  **Left open**: a hosted-backend recording, not run because Mistral is out of credits.

- **Scoring rollouts that already ran**, 2026-08-10, straight off dogfood #3. A project metric
  that raised ended an evaluation after every rollout was paid for. It now fails on the first
  rollout and cancels the rest, `EvalSuite.run` records its rollouts by default, and
  `EvalSuite.rescore(run_dir=...)` scores what is on disk with nothing executed. Results file
  `0.9`. 1619 tests. `build-logs/rescore-build-log.md`. **What it left open closed the next
  day**, as the entry above.

- **Evaluating an agent that spends money**, 2026-08-10. `EvalSuite.run(max_spend=...)` and
  `EvalSuite.record(...)`. **Do-not-change #5 moved**: `irreversible` refused outright,
  `spends_money` under a ceiling checked before the first rollout. Results file `0.8`. 1595
  tests. `build-logs/paid-eval-build-log.md`. **Left open**: a tool metering above its own
  `DeclaredCost`, unrefused on Thilina's ruling, and `max_spend` under a `ComputeBasis`, not run
  because vLLM was unavailable.

- **Memory**, 2026-08-10. `RunEnvelope(memory=MemoryStore(directory, scope=...))`, reached
  through a `Memory` handle and `remember`, `recall` and `memory_search`. Neither of the two
  things §1.5 posed: both are intra-run, and memory's writer and reader are in different runs.
  Manifest `0.19`. 1574 tests. `build-logs/memory-build-log.md`. **Left open**: an evaluation
  whose unit is a sequence of sessions, and a store the library does not own, which FT-20
  states.

- **A pipeline exposed to a model as a tool**, 2026-08-10. Ships as
  `AgentNode(delegates=[Delegation(...)])`. The trajectory gains a fifth record type,
  `delegation`, and goes to `0.19`; `node_execution` gains a `parent_id` naming it, so the n
  invocations of one worker are separable while its node ids stay the node's. `containers`
  gains `reached_by`, which is what joins a delegate to a graph it declares no edges in.
  Suspension goes to `0.3`: `node_state` moved onto `_Frame`, because a delegation puts two
  agent nodes mid-execution at once and the state held one. The delegate's own budget and
  `max_calls` are model-facing; the run's budget still ends the run. 1544 tests.
  `build-logs/pipeline-as-tool-build-log.md`.

  **Two things were measured rather than argued.** §1.4's claim that `simple-agents.md` §8.2
  already settled replay was checked and is right for a different reason than the brief gave.
  And **the item found a defect that predates it**: a tool whose body calls `Pipeline.run` is
  outside `declared_nodes()`, so a `spends_money` tool inside it escapes §4.4's refusal and an
  evaluation would run it k×n times with nothing declaring it. A declared delegate is inside
  the walk; the hand-rolled body cannot be detected and is stated as a rule in FT-20 instead.

  **Found by the live run**, against a local Qwen3-1.7B: `to_mermaid()` drew a delegate
  nowhere, so an orchestrator rendered as a single box. Fixed.

  **Left open**: `Example.expected_by_node` on a node inside a delegate is not meaningful, since
  `_node_outputs` keys by node id and the last invocation wins. That is already true of a
  bounded cycle and a delegation makes it worse, because the subtasks differ. The fix is a
  per-invocation expectation surface, which is a larger design than this item.

- **`ablate()` on a pipeline it did not generate**, 2026-08-10. The two failures §1.6 named,
  plus eight more with one cause: a container was read only for its leaves. The manifest gains
  `containers` and goes to `0.18`; `graph_fingerprint` covers it, so a suspension no longer
  resumes against a rewired sub-pipeline; a nested `tools=` registry now reaches the
  mixed-currency refusal it escaped; `on_error` and `loop.then` are prefixed the way
  `successors` already was; a `node_id` with a dot is refused. `ablate()` splices the edges that
  named a removed node, keeps nesting, and reports what it did not generate as
  `Ablations.skipped` rather than raising and losing the whole set. The results file gained
  `config.containers` for the same reason and went to `0.7`. 1503 tests.
  `build-logs/ablate-build-log.md`. **Left open**: nothing.
- **Per-node model selection**, 2026-08-10. `LLMNode(model=)` and `AgentNode(model=)`, resolving
  node-first then run. The manifest gained `nodes[].model` and went to `0.17`; FT-14 checks every
  identity that could serve a call rather than one; streaming is refused per node; a calling node
  with no client is refused before the run rather than when it is reached. **Two consequences the
  §1.3 brief did not name were found by reading the code**: a run spanning two models priced every
  call under one basis and reported a figure nothing said was wrong, which is why `cost_basis` now
  takes one basis per model with two pre-flight refusals; and `variants.py` claimed a model swap it
  could not express, which is now true. Recorded live against Mistral and a local Qwen3-1.7B in one
  run. `build-logs/per-node-model-build-log.md`. **Left open**: a single-backend basis mismatch,
  where a `VLLMClient` under a `PriceBasis` still prices device time at token rates, and an
  elicitation question asking which model each node uses, held back because dogfood #3 is
  measuring the question set.
- **The `brainstorm` stage and FT-29**, 2026-08-10. A fourth stage before `shape`, eleven
  questions of which six are required, and `idea.md`. `design/brainstorm-stage.md` is the design of
  record; `simple-agents.md` §2.8 carries the amendment.
- **The three sittings**, 2026-08-09: DF2-D2 measured tool spend, DF2-D1 the loop accumulator,
  and the ground-truth sitting the labelling machinery with DF2-D8. Their build logs are
  `build-logs/tool-spend-`, `loop-accumulator-` and `ground-truth-build-log.md`. DF2-D2 reopened
  `simple-agents.md` §2.3; DF2-D1 closed §3.2.1's shared-state entry and opened the per-edge one.
- **Nine absorption build items**, 2026-08-09, with `load_env` dropped as outside the library.
  `archive/dogfood-absorption.md` carries the dispositions.
- **Ten library-analysis fixes**, 2026-08-08. `archive/library-analysis-2026-08-08.md`.
- **Five prose findings, DF2-D6 and the §10 protocol amendment**, 2026-08-09.
  `runs/dogfood-2/findings.md` §9.2 says how each closed.

**What is left open from the dogfoods:** `runs/dogfood-2/findings.md` §1.1, on timestamps.

### 1.8 ~~Semantic recall over memory~~ — built 2026-08-11

**`build-logs/semantic-recall-build-log.md`**

### 1.9 ~~Evaluating an agent that spends money~~ — built 2026-08-10

**`build-logs/paid-eval-build-log.md` is the record.** It ships as
`EvalSuite.run(max_spend=...)` and `EvalSuite.record(...)`, and **do-not-change #5 moved**:
`simple-agents.md` §4.4 carries the argument and §9 item 5 the reworded rule. §1.7 has the
outcome. This section held the brief until the item was built; it is collapsed rather than
deleted so citations against §1.9 keep resolving.

**Two of its claims did not survive being checked**, and the build log's §1 and §2 are where
that is recorded: the pre-flight arithmetic it proposed counts rollouts rather than calls, and
its headline measurement holds only for a pipeline that calls no model.

### 1.10 ~~A run records by default, and cassettes sample with trajectories~~ — built 2026-08-11

**`build-logs/recording-default-build-log.md` is the record.** It completes `simple-agents.md`
§2.1 rather than changing it: two of the three artifacts that section's diagram names were
written by construction and the cassette was not. §2.1 gains the linkage as a second decision,
which it did not carry. §1.7 has the outcome. This section held the brief until the item was
built; it is collapsed rather than deleted so citations against §1.10 keep resolving.

**One of its claims did not survive being checked.** The brief had the cassette decided at run
start, which would have left a run that errored under sampling holding its payloads with no
recording, and that is the run most worth replaying. The deletion matches the trajectory's own
moment instead, in the same branch of `_close_manifest`.

### 1.11 ~~A design decision the coding agent proposes rather than makes~~ — built 2026-08-11

**`build-logs/decision-surface-build-log.md` is the record.** It ships in `brief.toml` under
`[decisions]` rather than in `idea.md`, which is the one thing below that did not survive being
built: a gate has to read a per-decision status and `idea.md` is prose. §1.7 has the outcome.
This section held the brief until the item was built; it is collapsed rather than deleted so
citations against §1.11 keep resolving. **The build log left the build-log instruction unbuilt**
and says why.

**Scheduled 2026-08-11, at the dogfood #3 sitting**, as §1.2 item 3. `runs/dogfood-3/findings.md`
`DF3-D8` is the evidence and this section is not a summary of it.

**What the run found.** Every one of the 30 questions asks the builder about their own world:
their data, their end users, whether a wrong answer beats no answer, what they would act on.
Those worked. **None asks the coding agent to put its own decision in front of the builder**, so
six decisions in dogfood #3 were made alone — the external catalogue the whole project rests
on, the pipeline's shape, a limit on how much of the library is read, prompt text stating a
requirement the builder never gave, whether the measurement could move, and a 174KB page.

**Why more questions cannot fix it.** The decisions that hurt were project-specific: no shipped
question can ask "which catalogue API" of a project with no catalogue. What generalises is the
**kinds**, and all six fall into six of them: an external dependency the project will rest on;
the shape of the machine; a number written into code that changes behaviour; prompt text
stating a requirement; how results are presented; whether the measurement can move.

**What ships**, decided at the sitting: a recorded surface for decisions the coding agent made
and the builder did not — what was chosen, what else was considered, why, and the builder's
response — gated so a stage cannot close while one is unreviewed, driven by that taxonomy. Plus
**a question asked before any of it about how involved the builder wants to be**.

**Four things a design has to answer**, listed so they are not discovered late.

- **Where the record lives.** `idea.md` grew a section per stage in dogfood #3 and is the
  artifact that worked, which argues for putting it there rather than shipping a fifth artifact
  a project can forget.
- **What a gate can check, and what it cannot.** It can check that an entry exists, names
  alternatives, and is not still `proposed`. It cannot check that the decision was real or that
  the builder read it. That is FT-29's limit one level over, and the design has to state it
  rather than be read as guaranteeing more.
- **How the six kinds are expressed.** Prose in the procedure, or a typed field a check can
  read. Only the second makes "which kinds have no entry" a question a gate can ask.
- **What the involvement dial moves.** The number of decisions surfaced, or only the timing. A
  builder wanting low involvement arguably still needs all six kinds, as a list at the gate
  rather than as six interruptions.

**Two decisions fold in here rather than being scheduled separately**, because all three edit
the elicitation and procedure surface and `docs/procedure.md` is also the shipped skill, held to
a word budget by `tests/test_procedure.py`:

- **Presentation is elicited, not shipped.** The builder is asked what the output has to look
  like and who reads it. Dogfood #3's output schema was shaped by that decision at `shape`,
  before any page existed, which is why the library cares about the decision and not the
  rendering.
- **The procedure asks for a build log.** Not the library writing one: the library cannot see
  the conversation, and the conversation is the only thing a log holds that the artifacts do
  not. It is nearly free once a decision record with statuses exists.

**What decides whether it worked: dogfood #4, and it partly did.** The surface works — 16
decisions, all six kinds, six of them `changed` by the builder, none a formality. Two still
reached him late and one elicited capability left the graph with its entry still `answered`.
`runs/dogfood-4/findings.md` §3 and `DF4-D2`, `DF4-D6`, `DF4-D9`; `runs/dogfood-4/inventory.md` S-3 is what
is open. *(This section's original text read "What decides whether it worked: dogfood #4, §1.2's
dogfood row, on a task whose decisions are not already known.")* *(This named "item 4" until 2026-08-12, when adding one row above it made the
reference resolve to Phase 5. A queue position renumbers by design, so nothing cites one.)*

### 1.12 ~~Concurrency: independent branches, and a fan-out that runs together~~ — built 2026-08-13

**`build-logs/concurrency-build-log.md` is the record**, and §1.7 has the outcome. This section
kept the brief before the sitting and keeps the six decisions after it, because they are the
design of record rather than a plan: what may overlap, where it is declared, what a stop does,
what the wall-clock axis measures, what replaces the reproducibility guarantee, and how tool
calls inside a turn behave. **Two of the six are amended by what the build measured**, marked in
place at Decision 2.

**Scheduled 2026-08-12**, on Thilina's instruction, promoted from §3.2.1 where it had been
deferred since the branching sitting of 2026-08-03. It was scheduled because the alternative on
the table was correcting a shipped sentence to match the implementation, and the ruling was that
the implementation is the defect. **That sentence is now true**: a route returning a list of ids
sends the output down every arm named, and listing those arms in `concurrent_nodes` overlaps
them.

**What is true today.** Nothing in a run overlaps anything. `LLMNode(over=...)` is a `for` loop
over the items ([fanout.py:216](../../src/simple_agents/nodes/fanout.py#L216), `_fan_out`), and the graph
walk is a single loop taking ready nodes in list order
([core.py:1327](../../src/simple_agents/pipeline/core.py#L1327), `_walk`). The only thing in the
library that runs anything at the same time as anything else is an evaluation, which overlaps
**rollouts** at `concurrency=4` ([runner.py:63](../../src/simple_agents/evaluation/runner.py#L63),
`DEFAULT_CONCURRENCY`). So a fan-out over 40 documents is 40 sequential calls inside one run, and
an evaluation of many runs overlaps them. *(`items/example-projects.md` §15.1 stated the first half
as a flat "nothing runs concurrently" and §16.0 corrected it; both halves are stated here so the
next reader does not have to hold two sections at once.)*

**The sentence this makes true, and where it actually lives.** It is not in a document. It is the
last line of the **refusal a builder gets** when a node declares two successors and no route
([graph.py:447](../../src/simple_agents/graph.py#L447), `_refuse_undecided_routes`): after telling
them to pass `route=`, it adds "Returning a list of ids runs those arms in parallel." So the claim
is made at the moment a builder is deciding how to branch, which is the worst place for it to be
wrong. It means parallel in the graph; a reader takes it to mean concurrent. **It was not corrected in the
meantime**, on Thilina's ruling of 2026-08-12: a wording change hides the gap rather than closing
it. The cost of that ruling was that a false sentence shipped in an error message for a day, and
what closed it was making the claim true rather than editing it.

**Three things a design had to answer**, carried from §3.2.1 so they were not rediscovered. Two
of the three were wrong about where the difficulty is, and the sitting below says why:

- **Cassette keys** are content hashes and are already order-independent. True, and it is not
  the whole answer: a model call's key carries its seed, and the seed is derived from a counter
  that arrival order moves. Decision 5.
- **`sequence` on a trajectory record is a total order** and would have to express a partial one.
  It does not have to. `sequence` is allocated at emission
  ([context.py:522](../../src/simple_agents/context.py#L522), `next_sequence`) and stays monotonic in write
  order, a parent record still emits after its children, and everything downstream resolves a
  record to its node through `parent_id` rather than through order
  ([per_node.py:839](../../src/simple_agents/evaluation/per_node.py#L839), `_owners`). What changes
  is that the order is no longer reproducible, which is Decision 5 and not a format problem.
- **`Spend` is accumulated per call** and would need to be safe under simultaneous charges. True,
  and Decision 4 changes one of its four axes at the same time.

**What item 8c was required not to foreclose, and did not:** execution order is derived from the
declared graph rather than from the list, so a concurrent executor changes how the graph is
walked and not the node API or any format.

---

## The sitting of 2026-08-13

**Six decisions, and this is the design of record.** `build-logs/concurrency-build-log.md` is what
building it found. Three questions were open coming in; three more were opened by reading the
code, and two of those are defects that exist today with no concurrency involved.

### Decision 1 — One executor, both units, built together

A fan-out item and a branch arm are not alike, and the difference is what the design has to
absorb rather than what it should split on:

| | fan-out item | branch arm |
|---|---|---|
| what it is | one model call | an arbitrary subgraph |
| calls tools, delegates to a pipeline | no | yes |
| touches `ctx.workspace` | no | yes |
| its resume state | `{done, next_index}` | a `_Frame` with a single `in_progress` |
| two of them can be the same node | yes, always | no |

**Building the fan-out first was the safer plan and was rejected on what it leaves standing.**
The false sentence is about arms, not items, so shipping the fan-out alone leaves the defect that
put this item on the schedule exactly where it was. What makes both tractable at once is Decision
3: draining is a single rule for every way work stops, so the branch case does not need a special
case per stopping reason.

**What it costs.** The suspension file's shape changes, since `_Frame.in_progress` becomes a list
of nodes rather than one node, each with its own held state and its own stack of frames below, and
a fan-out's `done` becomes a set of indices rather than a prefix. **A suspended run is therefore a
tree rather than a stack**, because a level where two arms stopped has one frame and two ways down
from it. The file is versioned and refuses a mismatch
([suspension.py:92](../../src/simple_agents/records/suspension.py#L92)), so the cost is a version number and
any run currently suspended, which is none.

### Decision 2 — Declared per node, bounded per run, and not per client

**`Pipeline(concurrent_nodes=[[...], ...])` says which nodes may overlap each other**, as a list
of groups: two nodes may run at the same time when a group lists both. Any number of groups, any
size, and a node may appear in several. **A node says what inside it overlaps**:
`concurrent_items=8` on an `LLMNode` with `over=`, and `concurrent_tools=[search, fetch]` on an
`AgentNode`. **`Pipeline.run(concurrency=N)` bounds the total in flight**, and defaults to 1, so
every pipeline that exists today behaves exactly as it does now until someone asks.

**Why the pair lives on the pipeline and the rest on the node.** Whether two nodes can overlap is
a claim about a pair, and the pipeline is the only place a pair is in view; on a node it is a
claim about everything else in the graph, made somewhere that cannot see it. What a node can
speak for is what happens inside it. The cost of that split, stated rather than discovered: a
node that must never overlap carries no such mark itself, so someone has to leave it out of a
group once per pipeline that uses it.

**A bare `concurrent=True` was proposed and rejected on Thilina's reading**: it names no subject,
so it reads as a switch that turns concurrency on rather than as an assertion about what may
overlap. Every keyword here names what it governs.

**The run ceiling bounds the total, not what reaches one backend, and the first argument for it
was wrong.** *(A second amendment, 2026-08-13: the ceiling was built and then enforced by
nothing, which every single-region test passed over. `build-logs/concurrency-build-log.md` §3.6.)* Per-node model selection ships (§1.3), so a run has as many clients as its nodes
declare and `_clients_of` already enumerates them, pacing each separately
([runner.py:2846](../../src/simple_agents/evaluation/runner.py#L2846)). What a run-level number
bounds is the drain overshoot of Decision 3. *(Amended at the build, 2026-08-13: it was written
here as bounding units of work and thread count, and it bounds **calls** in flight. A unit
waiting for the units below it would hold a slot while they waited for one, so a run whose arms
each held a fan-out would wait on itself. `build-logs/concurrency-build-log.md` §3.2.)* What
bounds a backend is a
`PacedClient` given the run ceiling through `expect_callers`
([pacing.py:224](../../src/simple_agents/pacing.py#L224)), which over-declares and therefore paces
early rather than late. **A ceiling per
client is deferred to §3.2.1**, on Thilina's decision: `concurrent_items` bounds what reaches an
expensive backend from the node that names it, and the case it does not cover is several nodes
sharing one client and overlapping each other.

**One composition fix falls out.** `_pace_for` passes an evaluation's `concurrency` as the caller
count. An evaluation of a concurrent pipeline has rollouts times pipeline concurrency callers on
each client, and passing anything less leaves the pacing floor wrong by that factor.

### Decision 3 — A budget refusal drains, and `max_steps` reserves

**Drain**: stop starting new work, let what is running finish, be recorded and be charged, then
raise. **Reserve on `max_steps`**: one call is one step and a step is known before the call, so a
unit does not start unless a step remains.

**The same rule answers all three ways work stops** — a budget exceeded, a suspension raised
inside one arm, and an exception — which is what makes Decision 1 affordable.

**Why not abandoning in-flight work.** The money is already spent, so dropping the results leaves
spend that no record accounts for, against the containment decision at `simple-agents.md` §2.1.
A request already sent also cannot be cancelled cheaply, so the call happens whether or not it is
recorded.

**The cost, which goes in `docs/pipeline.md` §5 rather than being discovered.** A budget already
overshoots by one call: `Budget`'s docstring says a single node can overrun the run budget by
whatever one of its calls consumes ([budget.py:129](../../src/simple_agents/budget.py#L129)). Under
concurrency N it overshoots by up to N−1 calls on the token and cost axes, and not at all on
`max_steps`. **The precedent is the eval runner's**, which answers this question one level up:
the rollouts not yet started are not worth paying for, and those already running finish
([runner.py:525](../../src/simple_agents/evaluation/runner.py#L525), `unstarted`).

### Decision 4 — `max_wall_clock_ms` becomes elapsed, and a device can be measured without money

**The axis is elapsed time while the run is executing**, not the sum of what each call took.
Wall clock is wall clock. Time spent suspended stays uncharged, which is what
[nodes.py `_one`](../../src/simple_agents/nodes/agent.py#L375) already promises.

**The argument that summing is more reproducible does not hold.** `elapsed_ms` is measured around
`run.call_model`, which on a replay returns from the file immediately, so a replayed run already
charges roughly zero to this axis while `recorded_duration_ms` sits unused on the record. This is
already the one axis that does not bind on a replay, under either reading.

**Two consequences to agree to rather than find later.** It changes sequential runs too: pacing
waits and retry backoff are excluded today as `held_back_ms`, and under elapsed they count, so a
run that waits 40 seconds for a quota window is charged those 40 seconds. And the run total stops
being the sum of the per-node `wall_clock_ms` figures once calls overlap; those stay per-node
durations, which is what per-node metrics read
([per_node.py:158](../../src/simple_agents/evaluation/per_node.py#L158)).

**And the library is what forces an invented hourly rate.** `Budget` takes all four axes with no
defaults, so a coding agent writes a number for `max_cost` rather than `None`. That number reaches
`_refuse_unauditable_cost` ([preflight.py:211](../../src/simple_agents/pipeline/preflight.py#L211)), whose
message says to pass `PriceBasis` or `ComputeBasis` and buries `max_cost=None` third, and
`ComputeBasis` requires an `hourly_rate` ([cost.py:254](../../src/simple_agents/cost.py#L254)). The
correct guidance exists only in a document, `docs/run-envelope.md` §4: a device the project owns
has no hourly rate to read off an invoice, and `max_wall_clock_ms` bounds such a run exactly.
**This is the same failure shape as the sentence that put this item on the schedule**, with the
guidance in a document and something else landing where the decision is made. Measured on the
dogfoods: coding agents declare a rate that is imaginary and then report costs derived from it.

**Two fixes, both in this item on Thilina's instruction.**

- **A.** `_refuse_unauditable_cost` leads with `max_cost=None` and `max_wall_clock_ms`, and the
  `prices` elicitation question ([elicitation.py:496](../../src/simple_agents/conformance/elicitation.py#L496))
  asks whether the run is billed to anyone before it asks where the prices came from.
- **B.** A **`DeviceBasis(device=..., device_count=...)`**, with no rate and no currency, under
  which a run reports **device-seconds** as a measured total. A separate type rather than an
  optional `hourly_rate`, because `ComputeBasis` means money and a half-filled one reads as a
  mistake. The figure does not travel through `Cost`, which carries a `currency`
  ([cost.py:52](../../src/simple_agents/cost.py#L52)) that device-seconds would falsify. `max_cost`
  still cannot bind under it, and no fifth budget axis appears: device-seconds is roughly elapsed
  times the device count on a saturated device, so the ceiling is the one Decision 4 already
  fixed. **What B is for:** a run with no basis reports `cost: null`, and a null is what a coding
  agent fills in. Giving it a real measured number is what stops the invention.

### Decision 5 — What replaces "a run is reproducible"

`_walk`'s docstring says order among ready nodes is by position in the list "so a run is
reproducible" ([core.py:1327](../../src/simple_agents/pipeline/core.py#L1327)). **It is protecting
something list order never provided.** A model call's cassette key carries its seed, the seed is
`derive_seed(run_seed, node_id, call_index)`
([context.py:81](../../src/simple_agents/context.py#L81)), and `call_index` comes from a counter
kept **per node** ([context.py:717](../../src/simple_agents/context.py#L717), `next_model_call`). Two
arms could already have run in either order with every request hashing the same. The replacement:

> A run makes the same set of requests whatever order they run in, and the cassette answers every
> one of them the same way. What varies is the order records were written, and therefore
> `sequence` and the timestamps.

**The rule that makes it true, and it covers all three units:** identity is assigned from declared
position before dispatch, never from arrival order. A fan-out item takes its item index, which
reproduces today's sequential seeds exactly and re-records nothing. A tool call inside a turn
takes its position in the turn, which the model supplied as an ordered list. A branch arm needs
nothing, because two threads never run one node. The precedent is `docs/evaluation.md` §6.2,
where a rollout's seed comes from the example and the index rather than from the order it started
in.

**One hole, and it is a defect that ships today with no concurrency involved.**
`_note_tool_occurrence` counts by `(name, version, arguments)` across the whole run
([context.py:1227](../../src/simple_agents/context.py#L1227)) and the count is in the key
([cassette.py:594](../../src/simple_agents/records/cassette.py#L594), `tool_call_key`). So node `hunt`
calling `search(q)` takes occurrence 0 and node `verify` calling the same takes occurrence 1, and
adding one more `search(q)` to `hunt` invalidates `verify`'s recorded entry through an edit in a
node it has nothing to do with. **`node_id` joins the key and occurrences count per node**, which
closes the race and the coupling together.

**The cassettes this invalidates do not need re-recording**, which matters because four of them
are Mistral and Mistral is out of credits. Every entry stores `node_id` and the full keyed
request, so a script recomputes the keys with no backend call. The exception is an entry whose
arguments were redacted before storage but hashed before redaction; those are detectable and
there are none.

### Decision 6 — Tool calls inside one turn, named per tool, with `WRITES` refused

A turn can carry several tool calls — the item 7 vLLM recording showed a 1.7B model issuing four
— and they run one after another under an order the loop imposes
([agent.py:297](../../src/simple_agents/nodes/agent.py#L297) `execute`). `AgentNode(concurrent_tools=[...])` names
the ones that overlap. What stays sequential is what the loop already orders for reasons that
were never about safety: `finish` last, because a finish check has to see the reads made in the
turn it is judging, and delegations and anything that can suspend last, so a stop lands on a turn
boundary.

**Restricting this to `READ_ONLY` tools was proposed and rejected on Thilina's ruling.** The
library refuses `irreversible` tools **in evaluation rollouts** (`simple-agents.md` §9 item 5),
because k rollouts multiply real actions with nobody having said so, and there is no such refusal
in `Pipeline.run` because a live run is the builder doing the thing on purpose. Extending an
evaluation-scoped refusal into a live run because concurrency is involved is the library taking a
decision that is the builder's.

**`WRITES` is refused, on a narrower ground.** Not that a race is certain: two writes to separate
paths do not collide. The workspace is the library's own, created at `root / "workspace"` and
handed to every node as the same `Path` ([`envelope.py`, `RunPaths`](../../src/simple_agents/envelope.py#L699)),
so refusing concurrent writes into it is the library defending a resource it owns, which is the
rule that refuses shared mutable state on edges everywhere else. **What it costs:** a turn whose
calls each write their own file, which has to return content from the tool and write it in a
later node instead.

**The refusal cannot reach one level up.** A `Deterministic` node writing to `ctx.workspace`
directly is plain Python the library never sees, and `concurrent_nodes` is exactly where two of
those would be listed together. That is a sentence in `docs/pipeline.md` saying what listing two
nodes asserts, on the same footing as a tool declaring its own side-effect class: the library
states the contract and cannot verify it.

### What the build has to touch

A run-owned bounded pool; a lock on `TrajectoryWriter.write`
([trajectory.py:704](../../src/simple_agents/records/trajectory.py#L704), `TrajectoryWriter.write`) and an atomic `Spend`;
`call_index` from the item index in `_fan_out`; tool occurrence from turn position; `node_id` in
`tool_call_key` with an offline re-key script; `done` as an index set and `in_progress` as a set,
with the suspension format bumped; drain and the `max_steps` reservation in `_charge_or_stop`
([core.py:1679](../../src/simple_agents/pipeline/core.py#L1679)) and in `_fan_out`; the run clock
replacing summed wall clock; `DeviceBasis` and device-seconds; the `_refuse_unauditable_cost` and
`prices` rewrites; `concurrent_nodes`, `concurrent_items` and `concurrent_tools` with their four
construction refusals; the manifest and the results file carrying the ceiling; `_pace_for` given
the product; and `_refuse_undecided_routes`
([graph.py:447](../../src/simple_agents/graph.py#L447)) becoming true. Then a live run against vLLM
and Gemini rather than a green suite, with the vLLM arm timed around dogfood #4 so an overlap
does not corrupt its cost basis.

### 1.13 ~~A consultation answer the library can read~~ — built 2026-08-12

**`build-logs/typed-consultation-build-log.md` is the record.** It ships as `consult` returning a
`Reply` and `on_reply` routing on it, trajectory `0.21` and manifest `0.21`. §1.7 has the outcome.
This section held the brief until the item was built; it is collapsed rather than deleted so
citations against §1.13 keep resolving.

**Three things the brief did not know**, and §2 of the build log is where they are recorded: a
`Reply` had to be a `str` subclass or every agentic consultation would change what the model
sees; deriving the match inside the tool alone made a replayed evaluation record `answered`
where the live run recorded `unmatched`; and a route helper returning a closure would have
defeated FT-15, because `source_version` digests a closure's source and two different mappings
hash the same. **Both live arms ran**, and §3 of the log records how the vLLM one was taken
without disturbing dogfood #4, which was using the only GPU.

**The brief, as approved.** *Scheduled 2026-08-12, and the design below is settled with Thilina the same day.* It came out
of the agent-shapes verification pass as the one candidate-adjacent gap with external precedent
behind it (`items/example-projects.md` §19.7).

**What is wrong today.** The channel a project supplies is
`Callable[[str, Sequence[str] | None], str | None]`
([consult.py:51](../../src/simple_agents/builtins/consult.py#L51), `ConsultChannel`), so a
consultation comes back as free text or `None`, and
[tools.py:1042](../../src/simple_agents/tools.py#L1042), `ConsultTool.resolve`, maps only `None` to
`declined`. Three consequences:

- **`options` is a hint nothing enforces.** A reply outside the offered list is recorded as
  `answered` exactly like one inside it.
- **Every project parses the reply itself.** An approve / reject / amend outcome is a string, so
  each project writes the same mapping from text to branch. That is machinery, and §3.4 says the
  library holds machinery.
- **Nothing downstream can read the decision.** The trajectory holds the string, so an evaluation
  cannot score whether the agent escalated when it should have without the project re-parsing.

**That this is real rather than tidy-up.** Consultation is used by two of the three completed
dogfood projects, and dogfood #3's records show `resolution: "declined"` on a question offering
`["yes","no"]`. Three 2026 benchmarks score this gate mechanically — HiL-Bench's `Ask-F1`,
τ²-bench's policy-compliance check against the action trace, PhoneHarness's
`CONFIRM_FIRST`/`SAFE_COMPLETE`/`NEVER_AUTO` labels — and they can because the approval decision
is a typed value in their trace. Ours is prose. `items/example-projects.md` §19.6.

**The design, and what decided it.**

- **The reply carries both a chosen option and its raw text.** Not one or the other. **The
  argument that settles it is that strict enforcement makes the amend branch unreachable**: an
  amendment is by definition a reply that is neither offered choice, so a design refusing those
  cannot express the flow it exists for. Filing such a reply as `declined` is also a lie, since
  `declined` means the end user refused to answer.
- **`options` binds interpretation, not the reply.** A matching reply records the choice; a
  non-matching one records answered-and-unmatched with the text kept.
- **Enforcement belongs to the channel, not to the library.** A channel rendering buttons
  constrains the reply by construction and the project knows it; the library receives whatever
  project code returns and cannot constrain it, so validating afterwards adds nothing there and
  breaks the text case everywhere else.
- **Matching reuses `normalise_text`** ([grounding.py:27](../../src/simple_agents/grounding.py#L27)),
  which already ships and is documented with an example, so "Yes." matches `yes` under a rule
  nobody has to learn twice.
- **A route over a consultation must have a branch for unmatched and for declined, unless the
  project waives it explicitly.** Required by default, with an opt-out for the case where the
  offered options really are the only possibilities. Thilina, 2026-08-12: *"By default, it's
  required, but we provide an explicit opt-out if the project really only needs yes/no or for
  scenarios where yes/no are the only real possibilities."* This is `allow_unknown=False`'s shape,
  which is the library's settled answer to the same question one layer up: the branch is required,
  the waiver is available, and **the waiver is recorded** so a reader can see it was taken
  deliberately rather than by omission. It is also FT-25 stated as a refusal, since being made to
  say what happens when the end user says something unexpected is the design.
- **The route helper follows `route=`'s existing idiom**, including its refusals: a mapping
  covering two of three options is refused, as is one naming an undeclared successor. The project
  supplies the mapping and may supply its own matcher; the library supplies the shape and the
  refusals.
- **The simple case stays simple.** No route means no branches, and the result is a typed value
  the project reads. Unmatched and declined may share one branch.

**Two precedents this rests on, both already in the library.** `Maybe[T] = T | Unknown` with
`require_unknown_branch` is the settled position that a value which might not be what was expected
gets a type saying so and a branch that must exist. And `resolution` on the consultation record is
already a five-state vocabulary, `pending` / `answered` / `declined` / `timed_out` / `defaulted`
([trajectory.py:456](../../src/simple_agents/records/trajectory.py#L456), `ConsultationRecord`), so
distinguishing an answer that matched an option from one that did not extends a state machine
rather than inventing one.

**What it touches.** `ConsultChannel` and `consult`; `ConsultTool.resolve`; the three sites in
`nodes.py` that write a `ConsultationRecord`; `ConsultationRecord` itself; a route helper, new;
and **`Pipeline.resume(run_id, answer=...)`, which takes `answer: Any`** and is the same seam for
an answer arriving in a later process. Folding resume in is what stops the suspend path
re-opening the untyped hole, and it is one item rather than two.

**The cost, stated rather than discovered.** This is a **trajectory format bump** from `0.20`: the
consultation record gains a field and `resolution` gains a state.
`design/trajectory-format-changelog.md` takes the entry and `CHANGELOG.md` says what a project does. §6
says a bump is cheap now and stops being cheap at the first release, which is also the argument
for doing it before six committed example projects exist and have to be re-recorded. `docs/`
surfaces to update: `tools.md`, `trajectory-format.md`, `pipeline.md`, `evaluation.md`, FT-25 and
`index.md`.

**What was separable and is now settled**: the refusal when a route has no unmatched or declined
branch stays, with the opt-out above.

---

## Where an old `plan.md` section number went

**`plan.md` was chaptered by phase until 2026-08-15**, so every other kind of content had been
filed under whichever phase was current when it was written. It holds items only now: §1
scheduled, §2.1 accepted, §2.2 deferred, §3 out of scope, §4 done.

This table is here rather than in `plan.md` because everyone who needs it is already reading
history. No live document cites a retired number, and `check_docs.py` fails on one that does. What
still carries the old numbers is 15 references inside this archive and the frozen full-test record,
and 25 git commit messages.

| Was | Is now |
|---|---|
| §1, §1.1 | `plan.md`'s header |
| §1.2 | `plan.md` §1 |
| §1.3 to §1.6, §1.8 to §1.13 | this file, under "Phase 3 as run" |
| §1.7 | `plan.md` §4 |
| §2, §3.1, §3.5, §4.2 to §4.4 | this file, below |
| §3.2 | `plan.md` §3 |
| §3.2.1 | `plan.md` §2.2 |
| §3.3 | this file; the ship criterion itself is in `plan.md`'s header |
| §3.4 | [`simple-agents.md` §1.6](../simple-agents.md#L46) |
| §4, §4.1 | [`runs/dogfood-protocol.md`](../runs/dogfood-protocol.md#L1) |
| §5 | [`items/meta-eval.md`](../items/meta-eval.md#L1) |
| §6 | `CLAUDE.md` |
| §7 | a stub, deleted |

# The rest of `plan.md`, moved out on 2026-08-15

**`plan.md` was reorganised on 2026-08-15 to hold items and nothing else.** It had been chaptered
by phase, so every other kind of content had been filed under whichever phase was current when it
was written: §3, headed "Phase 1 — v0, met", carried four things that were still live. Phases are
gone as chapters; what survives of them is the milestone line in `plan.md`'s header.

The sections below are what left, verbatim. The phase table, the ordering decision, the v0 item
table and its 581 item-number citations, the ship criterion's record, the Phase 1 checkpoints and
the run-by-run dogfood summaries. The protocol went to `runs/dogfood-protocol.md`, §3.4 to
`simple-agents.md` §1.6, §5 to `items/meta-eval.md` and §6 to `CLAUDE.md`.

## The phase table, as it stood

```
Phase 0   Write the two spec documents          DONE 2026-07-26
Phase 1   Build v0                              DONE 2026-08-07 — ship criterion met
Phase 2   Dogfood #1, the trivial task          DONE 2026-08-07 — ran twice, 9 of 9 both
Phase 4   Dogfood #2, the t-shirt fit finder    DONE 2026-08-08 — ran before Phase 3
Phase 3   v0.1                                  CURRENT until 2026-08-15
Phase 5   Meta-eval of the docs                 pending, `items/meta-eval.md`
```

**The numbers were out of order because Phase 4 ran before Phase 3**, deliberately: dogfood #2 was
the measurement that decided what v0.1 is.

## 2. The ordering decision

v0 was built first and the agents were built with it, reversing an earlier plan to hand-build
the shopping agent and extract the library from the friction. The reason: the product is a
procedure a coding agent follows, and hand-building surfaces the friction a human hits, which
is a different failure surface. The full argument, the risk it took on and the two mitigations
are in the archive under §2.

## 3. Phase 1 — v0, met

### 3.1 What was built

**The identifiers are not a sequence**: 8a and 8b were created on 2026-07-30 after item 8 was
built, 8c to 8e were split out of 8c later, 8f was promoted from §3.2.1 on 2026-08-05, and 8g
was created on 2026-08-06 at item 8a. **The letters stay because about 290 citations across 28
files resolve against them**, including four commit messages.

| # | Item | Status | The record |
|---|---|---|---|
| 1 | `docs/failure-taxonomy.md`, 29 entries | written | `docs/failure-taxonomy.md` |
| 2 | `docs/trajectory-format.md` | written | `docs/trajectory-format.md`, `design/trajectory-format-changelog.md` |
| 3 | Agent shape: three node kinds, `Pipeline`, `RunContext`, budgets | built 2026-07-26 | `docs/pipeline.md` |
| 4 | Run envelope: manifest, seeds, trajectory, cassette | built 2026-07-26 | `docs/run-envelope.md` |
| 5 | Model client seam, both adapters | built 2026-07-26 | `docs/model-clients.md` and its two pages |
| 6 | Context builder | built 2026-07-27 | `docs/context.md` |
| 7 | Tool registry and the minimal tool set | built 2026-07-27 | `docs/tools.md`, `runs/checkpoint-item7/findings.md` |
| 8 | Eval machinery | built 2026-07-29 | `docs/evaluation.md` |
| 8c | Branching: `Pipeline` as a directed graph | built 2026-08-04 | `build-logs/item8c-build-log.md` |
| 8d | Suspend and resume | built 2026-08-04 | `build-logs/item8d-build-log.md` |
| 8e | Token streaming | built 2026-08-04 | `build-logs/item8e-build-log.md` |
| 8f | Reasoning output | built 2026-08-05 | `build-logs/item8f-build-log.md` |
| 9 | Six conformance checks and `simple-agents check` | built 2026-08-06 | `docs/conformance.md`, `build-logs/item9-build-log.md` |
| 8a | Variant comparison, of which ablation is one direction | built 2026-08-06 | `docs/evaluation.md` §10, `build-logs/item8a-build-log.md` |
| 8g | What a node accepts | built 2026-08-06 | `build-logs/item8g-build-log.md` |
| 8b | Trajectory volume in production | built 2026-08-06 | `build-logs/item8b-build-log.md` |
| 10 | The procedure as a skill, the brief's elicitation half, and the staged elicitation sets | built 2026-08-06 | `build-logs/item10-build-log.md` |
| 11 | *Folded into item 10.* The brief, elicitation half | built | `build-logs/item10-build-log.md` §2.2 |
| 12 | *Folded into item 10.* Staged elicitation sets, with FT-24 | built | `build-logs/item10-build-log.md` §2.2 |
| 13 | Tool-authoring guide, and a tool called at a fixed point | built 2026-08-07 | `build-logs/item13-build-log.md` |
| 14 | Project-supplied metrics | built 2026-08-07 | `build-logs/item14-build-log.md` |
| 15 | `docs/pipeline.md` | written 2026-07-30 | `docs/pipeline.md` |
| 16 | `prose_check.py` resolves `§n` | landed 2026-07-30 | `scripts/prose_check.py` |

**Where the detail lives.** Each item's design entry is in `archive/plan-history.md`, verbatim;
where an item has a build log, that log was written while building and supersedes the archived
entry. The closing entries this section used to carry for items 10, 13 and 14 are in the
archive under §3.1.

### 3.3 Ship criterion — met

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

Not a *good* agent. Passing, from cold. That was the whole bar, and **dogfood #1 met it twice
on 2026-08-07**: 9 of 9 at tier `evaluated`, exit 0, on both runs, with the bar rising between
them because FT-03 and FT-04 became checks off run 1. "Cold start" means informational, not
social: the coding agent has the library and its docs, no context from this design work, and
eliciting from the builder is the criterion being met rather than a violation of it. The
criterion's amendments, what each run passed on, and the two-week hard cap are in the archive
under §3.3.

### 3.5 Checkpoints during Phase 1 — done

Two cold-read checkpoints ran while building, after items 5 and 7: a fresh session, only the
library and its docs, a narrow task, reading whether the API was used correctly.
`runs/checkpoint-item5/findings.md` and `runs/checkpoint-item7/findings.md` are the records; the
checkpoint design is in the archive under §3.5.

### 4.2 Dogfood #1 — run, criterion met

A subset of SQuAD 2.0 with the passages pooled into one collection and a search tool over it:
extractive answers scored by exact match, unanswerables by design so false confidence is
measurable apart from recall, and the pooling is what forces a tool at all. Ran twice on
2026-08-07 and met the ship criterion both times. The dataset rationale, the rejected
alternatives, the contamination caveat and what each run measured are in the archive under
§4.2. The trivial-task-first rule is do-not-change #13 (`simple-agents.md` §9.13).

### 4.3 Dogfood #2 — run, ended on the builder's verdict

Find t-shirts that fit, from online retailers, where the deciding garment measurement is often
not published. Ran 2026-08-07 to 2026-08-08 at tier `prototype` and ended on the builder's
verdict: the agent measures correctly and the market does not publish the data, so the finding
is about the task rather than the library — and it opened the question of what the headline
project should be instead (`archive/library-analysis-2026-08-08.md` carries the open proposal).
`runs/dogfood-2/findings.md` is the record: 26 project defects, five library fixes landed at the
sitting, and §9.2 is what remains open. The agreed scope, the four scored predictions and the
labelling record are in the archive under §4.3.

### 4.4 Dogfood #3 — run, criterion met, and the criterion is what it questions

A book recommendation agent over the builder's own Goodreads export, `items/example-projects.md`
§17's worked candidate. Ran 2026-08-10 to 11 at tier `evaluated` and **met the ship criterion at
10 of 10**, which is the first time the raised bar including FT-29 has been met. **The run's
central finding is that the criterion was met by a project whose measurement could not detect
its own effect**, twice over, on two successive designs.

**The first project ever to meet the `brainstorm` stage.** What that stage produced is
`runs/dogfood-3/findings.md` §3 and §6: a real input file read before any node was designed, an
`idea.md` that grew a section per stage across seven versions, and the project's main dependency
correctly named as open at `brainstorm` and then closed by the coding agent alone, because no
later stage has a question that reaches it.

**187 run directories, 8 evaluations of which 3 were deleted, $5.4624 of Mistral spend.**
`runs/dogfood-3/findings.md` is the record: ten findings, two items already built off the run, and
§9.3 is what remains open.


---

# The §4 Done entries, as they stood before 2026-08-29

Moved out of `plan.md` on 2026-08-29, verbatim, when §4 was trimmed back to one line per item.
The convention at the top of §4 ("one line each: what shipped, what it cost, and a link to the
build log") had held for none of the entries written after 2026-08-15. What follows is the text
as it stood; the build log each one links is the record of what the item found.

- **P3-32 — working through dogfood #5's findings.** Done 2026-08-28. **40 candidates over eight sittings**, every one disposed of: `P3-33`, `P3-34`, `P3-36`, `P3-37`, `P3-44` to `P3-48`, `P3-50`, `P3-52`, `P3-53` and `P3-54` were built out of them, `P3-29` had its open question answered by two, and the last folded into going public. The sittings also produced `P3-35`, `P3-38`, `P3-39` and the results visualiser, none of them a candidate. **Twenty-one statements were found false and corrected on sight** (`DF5-X1` to `DF5-X21`), and **entries closed out of both §2.1 and §2.2** with the items that carried them. A sitting's work was built before the next was taken, agreed 2026-08-25, which is what kept the queue from filling with hypothetical plans. [`runs/dogfood-5/inventory.md`](../../dev-docs/runs/dogfood-5/inventory.md#L1) is the record
- **P3-51 — the results visualiser, and the fixtures it draws against.** Done 2026-08-29, in three stages under their own ids: `P3-58` the fixtures, `P3-59` the stage-page shell, `P3-60` the measure page. The sitting's eleven decisions and the stage-page architecture are the design of record at [`design/results-visualiser.md`](../../dev-docs/design/results-visualiser.md#L1). What it found on the way is in the three build logs; what it left is one §2.1 entry (`progress_of` reading the file the runner now writes) and the three view items scheduled behind it.
- **P3-60 — the measure page.** Built 2026-08-29, the results visualiser item's third stage under its own id. The page answers how good it is, where it loses it, and whether the last change helped: every figure opens to its numbers; an example browser sorted wrong-first is the hub that every outcome segment, criterion row and group cell opens into, and every rollout opens into the walk; the evaluation's cost sits beside its quality; a written variant comparison is drawn as deltas around zero with the library's verdict and its reason, the candidate cause beside it; the headline figure over time joins only comparable points and breaks where the behaviour moved; a ladder of rungs reads the loss across rows and shades the drawing to a rung's node set; a project that measured nothing says what it will. **The runner keeps `progress.json` beside an evaluation's rollouts**, and the served page follows an evaluation with the runner's own denominator, share-right-so-far marked provisional, spend and time left. **`compare_variants` takes `max_spend`**: a project with a paid tool could not sweep at all. The branching fixture gained a rung and a variant arm, recorded live. **3,951 tests**, no format moves. [`build-logs/the-measure-page-build-log.md`](../../dev-docs/build-logs/the-measure-page-build-log.md#L1)
- **P3-59 — the stage-page shell.** Built 2026-08-28, the results visualiser item's second stage under its own id. `view.html` is one file holding a page per stage: a strip under the header switches freely, the homepage is the stage `brief.toml` records, `#stage/<name>` deep-links one, the page set derives from the tier (a `prototype` project has no measure page), and every section files on one stage's page (questions and answers under the stage that asks them, decisions by their `kind`, the run record on `ship` until the operations page is built). A page without the drawing keeps the writing panel, addressed to the project. **The live-watch half of decision 10 shipped to what the record can honestly fill**: the full record behind any walked step on request (`/record/<run>/<sequence>`, served raw and never parsed), and the evaluation a live rollout belongs to with rollouts-finished and no invented total; live figures and a remaining-time estimate need the runner to write scored state mid-evaluation and moved to the measure-page stage. **The comments loop is verified end to end** over a real socket, both directions, closing the Corner entry folded in at the sitting. **3,933 tests**, no format moves. [`build-logs/the-stage-page-shell-build-log.md`](../../dev-docs/build-logs/the-stage-page-shell-build-log.md#L1)
- **P3-58 — the view fixtures, and what keeps them current.** Built 2026-08-28, the results visualiser item's first stage under its own id. `scripts/build_view_fixtures.py` re-records the three runs-holding view fixtures live (`--record`, ~0.005 USD) and its offline default verifies the committed cassettes still serve; `tests/test_view_fixtures.py` fails on format drift, exempts `many-pipelines`' frozen run by name (its staleness is what `code_moved_since` is tested against) and fails if that run ever stops being stale; and the `DF5-X20` fixture exists: `t-nonsense` scores `correct_abstention` through `branching`'s own semantics, with the page's counts held against the report on the same data. **The committed records are live recordings, deliberately**: a served call spends nothing, so replay-regenerated records cannot carry a tool spend, and the money surfaces would be tested by nothing. All records at manifest `0.39`, trajectory `0.29`, results `0.29`; found and fixed `view_at_stage.py` keeping a whole evaluation in a stage that subtracts it, under the role-filed runs layout. **3,923 tests**, no format moves. [`build-logs/the-view-fixtures-build-log.md`](../../dev-docs/build-logs/the-view-fixtures-build-log.md#L1)
- **P3-54 — four surfaces that read as working.** Built 2026-08-28, dogfood #5's sitting 7 over `DF5-I32` to `DF5-I35`. **A fan-out raises where every item failed with one exception type and one message**, which is separate from `max_failures` and says the node produced nothing rather than how many items may fail; **a `ConfigurationError`, `StreamUsageMissing` or `LeftTheSlice` inside an item ends the run** rather than being collected, joining the cassette miss and the exhausted budget that always did, so an evaluation over a misconfigured fanned-out node stops on the first rollout rather than scoring k×n; the fan-out bar shows failures and counts a resumed set from where it left off; **a run warns where its `concurrency` cuts a node's `concurrent_items`**; `value_or` reads the encoded absence as well as the object and `str(Unknown)` renders `unknown (reason)`; **a `Maybe` field is always told how to send an absence**, the library completing a description that replaced the one `Maybe` carries; and **a throttled source is waited out** through a new `Throttled`, which `http_fetch` raises on 408, 429 and 503 where it used to tell the model the URL would answer the same way. Carried `plan.md` §2.1's `ConfigurationError`-in-a-fan-out entry and §2.2's resumed-fan-out-bar entry, both closed. **No format moves**, and two changes invalidate a recorded artifact without moving one. **The `graph` Mistral arm retired** and `graph-gemini` replaced it, checked first against the live backend. **Our own suite carried the finding's own defect**: a fan-out test read the item under the wrong key, both items raised `KeyError`, and it passed because it asserted the node added nothing. **3,911 tests**, five defects the design did not know and four false statements in the documents describing it, over reverification cycles run until one found nothing. [`build-logs/dogfood-5-fixes-build-log.md`](../../dev-docs/build-logs/dogfood-5-fixes-build-log.md#L1)
- **P3-53 — evaluating back to front.** Built 2026-08-28. `Pipeline.slice(start=, end=, nodes=)` returns part of a graph as a real `Pipeline`, so a project scores the last step alone on ideal inputs, then the last two, and the rung where the number falls is the step that lost it. An edge whose other end is outside the slice stays declared: a node that took a `Join` still receives one with the cut arm in `absent`, and a route may still select an arm the slice does not hold, which ends the run at the boundary and leaves that rollout out of every figure under `left_the_slice` rather than failing it. `ExampleSet.entering` builds what a rung is run on out of `expected_by_node`. A `ProjectRatio` is reportable per node, and `refuse_a_ratio_per_node` is gone. `EVAL_FORMAT_FLOOR` stops an additive results-file bump destroying a held file. FT-08 gains a note where no node carries a current figure of its own. Manifest `0.39`, results file `0.29`. Seven reverification cycles found five defects, two of them `P3-48`'s. [`build-logs/evaluating-back-to-front-build-log.md`](../../dev-docs/build-logs/evaluating-back-to-front-build-log.md#L1)
- **P3-52 — the floor a do-nothing agent sets.** Built 2026-08-28, dogfood #5's sitting 6, closing `DF5-I27`. A `baseline=` returning `None` is refused, because `None` is what a rollout produces when the pipeline returned nothing: an agent that cannot fail was setting `failure_rate`'s floor at **100%**. The baseline is asked once per example **before the first rollout**, so that refusal and the existing raising one cost no rollouts. `baseline_unscored` names the project figures whose own function no baseline answer reached, since `over` decides a non-asserting rollout without it and a do-nothing baseline asserts nothing: dogfood #5 met that and got it right on one of its two suites. **And the floor is over the examples that ran rather than the split**, which a part-scored rescore had reporting `n=4` on the figure and a floor over 10. Results file `0.27` to `0.28`. **`evaluation/baseline.py` is new**, extracted rather than grown, which took `runner.py` and `EvalSuite` below their recorded sizes. **Seven defects found by ten reverification cycles and none by the suite**, including [`DF5-X20`](../../dev-docs/runs/dogfood-5/inventory.md#L79): the view counted every right report of absence as wrong, so a report saying accuracy 100% showed as 1 of 3 on the page, with 3,796 tests green over it. **3,800 tests.** [`build-logs/the-do-nothing-floor-build-log.md`](../../dev-docs/build-logs/the-do-nothing-floor-build-log.md#L1)
- **P3-50 — what a run says it cost, and what it says it is doing.** Built 2026-08-28. `Cost` carries `measured`, `priced_calls` and `unpriced_calls`, accumulated per call, so a total that is `null` still says what was spent: an evaluation that cost **$5.5024** reported nothing on three surfaces and **$0** on a fourth. `value` stays `null` where one call was unmeasured, because the floor sits beside the total and never in place of it. **A 429 whose message says the allowance does not reset inside a retry window raises `Suspend` instead of climbing the ladder**, which is all 1,674 seconds of the 28 minutes dogfood #5 spent; a resumed run continues once the allowance is back, measured. `Retry-After` is capped at `max_backoff_s`. `RunHandle.liveness` says `running`, `abandoned` or `unknown` about a run with no outcome, derived from the run's own declared wall clock because a killed process writes nothing. **Trajectory `0.29` adds `run_start`**, carrying what the run was given, and `Pipeline.rerun` replays a dead run from its own cassette: a process actually `SIGKILL`ed was rerun from its directory alone in 3 ms. Manifest `0.38`, results file `0.27`. Carried `plan.md` §2.1's `Cassette.update` entry, and the results visualiser was scoped out of it into §1. **Ten defects found by the seven reverification cycles, four of them by running the code rather than by the suite, including one that made the whole rerun feature inert.** **3,749 tests.** [`build-logs/what-a-run-says-it-cost-build-log.md`](../../dev-docs/build-logs/what-a-run-says-it-cost-build-log.md#L1)
- **P3-48 — a figure that is not a mean over examples, and a win rate.** Built 2026-08-28. `ProjectRatio` reports one total over another for a figure whose unit is not the rollout, with the interval resampling examples and summing both sides inside each resample; `Pair` and `paired_figure` do the same over judged pairs, which is a shape with no answer key at all. **The sitting found the two halves are one aggregation**: a win rate is that ratio with the unit being a pair, and the four figures four dogfoods built by hand are the same ratio over candidates, pages, picks and citations. **The library fixes no pairing and names no verdict set**, on Thilina's call, so a bracket and a four-verdict scheme both express themselves. **A count over one run now goes on file** with a declared reason instead of a print statement, and **FT-06 got stricter while admitting it**, reading a declared state rather than free text. `Metric.denominator` renamed `population` and the freed name holds a number. **All four remaining answer shapes closed**: B2 and G2 came out expressible, F2 needed `Scoring.verdict` and H1 needed `read_every_label`. Carried `plan.md` §2.1's arm-fingerprint entry and `DF5-I30`. Results file `0.25` to `0.26`, variant comparison `0.2` to `0.3`, and the written comparison gains a version of its own. **Seven defects found by running it that a green suite could not see**, four of them in six reverification cycles, and the prose check's own guidance recommended a workaround. **3,701 tests, after six reverification cycles.** [`build-logs/a-figure-that-is-not-a-mean-build-log.md`](../../dev-docs/build-logs/a-figure-that-is-not-a-mean-build-log.md#L1)
- **P3-49 — which conversation a run is a turn of is `conversation_id`.** Built 2026-08-28. A bare `thread=` on `run()` reads as the thread the run executes on, beside `concurrency=` and a `stop_when` documented with `threading.Event()`, which is the fault `memory_scope=` was named to avoid the day before. **The identifier moves and the classes do not**: `Conversation` the handle and `Thread` the object on disk are what `Memory` and `ScopedMemory` already are. Manifest `0.36` to `0.37`, conversation `0.1` to `0.2`, and `resume` reads both manifest keys. Raised at `P3-44` and taken on Thilina's call. **3,622 tests.** [`build-logs/what-a-store-is-for-build-log.md`](../../dev-docs/build-logs/what-a-store-is-for-build-log.md#L1) §6
- **P3-47 — when a decision was made.** Built 2026-08-27. `recorded_at` on every answered brief entry and every decision, an ISO 8601 timestamp with a zone, written off the coding agent's system clock. The brief carried `asked_at` and `stage`, both holding a stage name, and no clock, so whether something had changed since a decision had nothing to anchor against. **The brief format moves**: a brief without it is refused when read, naming the entry and the line to write. The dogfood protocol's build-log timestamp leaves with it. **3,607 tests.** [`build-logs/when-a-decision-was-made-build-log.md`](../../dev-docs/build-logs/when-a-decision-was-made-build-log.md#L1)
- **P3-46 — absence declared where it is enforced.** Built 2026-08-27. FT-04's waiver narrows from every model-calling node to the node producing the scored answer, read out of the recorded graph, so a pipeline whose lookup can genuinely find nothing can still say its answer never is. **Measured on dogfood #5**: the waiver went unused in all 2,669 manifests and twenty invented absence examples were written instead. FT-04's message names the node and quotes the brief's `absence_vs_error`. Moves no format. **3,599 tests.** [`build-logs/absence-declared-where-it-is-enforced-build-log.md`](../../dev-docs/build-logs/absence-declared-where-it-is-enforced-build-log.md#L1)
- **P3-45 — what a stored result is stamped with.** Built 2026-08-27. The consultation channel comes out of `behaviour_fingerprint`, so a product asking whoever is on the site and shelving the question when nobody is stamps one value rather than two. **Measured on dogfood #5**: every slate built from a click reported itself stale the instant it was written. The channel still keys the cassette and is still compared on a resume, which the build separated from the stamp. `docs/shipping.md` §6.1 is the artifact with no pipeline behind it. **Every stamp moves once.** **3,595 tests.** [`build-logs/what-a-stored-result-is-stamped-with-build-log.md`](../../dev-docs/build-logs/what-a-stored-result-is-stamped-with-build-log.md#L1)
- **P3-44 — what a store is for, and the two lifetimes on the memory store.** Built 2026-08-27. `MemoryStore(directory)` on the envelope and `memory_scope=` on `run`, `resume` and `answer_shelved`, with `ScopedMemory` for one end user's memory; a resume under another scope refused against the manifest's digest. The documents say the store holds what the agent learns and writes, which `docs/product.md` §3's scoping sentence had steered two projects away from. Carried `DF5-I20` and `DF5-I21`. **Found by building: `Manifest.restore` dropped `schemas`, `mcp` and `memory`**, so a resumed run's manifest carried a dangling schema reference. No format moves. **3,591 tests at the build and 3,622 after eight reverification cycles over the four items together, which found seven defects and a shipped instruction that produced a refused brief.** [`build-logs/what-a-store-is-for-build-log.md`](../../dev-docs/build-logs/what-a-store-is-for-build-log.md#L1)
- **P3-39 — a conversation that outlives the run.** Built 2026-08-27. A conversation carried across runs, a node taking part by continuing it, compaction as a built-in that makes no model call of its own, and an evaluation whose example is either what was already said or the turns a rollout goes through. **Runs are filed by what they are and no reader counts slashes**, which fixed a live defect: a run one folder deeper was invisible to `Pipeline.shelved`. Manifest `0.34` to `0.36`, conversation format `0.1`, `docs/conversation.md` new. **3,582 tests.** Six verification cycles found nine defects, four of them only by running it. [`build-logs/a-conversation-that-outlives-the-run-build-log.md`](../../dev-docs/build-logs/a-conversation-that-outlives-the-run-build-log.md#L1)
- **P3-38 — connecting to an MCP server.** Built 2026-08-27. The `mcp` SDK as an optional extra, both transports, a connection the builder constructs and holds, tools declared in Python with the hint mapping proposed in the refusal, and a replay that reads its schemas from the cassette. Manifest `0.33` to `0.34`, and a new `FT-43`. [`build-logs/an-mcp-server-build-log.md`](../../dev-docs/build-logs/an-mcp-server-build-log.md#L1)
- **What a decision produced** (P3-29), 2026-08-27. `produces` on a `dependency`, `shape`,
  `constant` or `prompt_rule` decision names what it became, and FT-42 reads it against the node
  ids, tool names and constants of every run under `runs/`: a note at every stage, a failure from
  `ship`. Manifest `0.32` to `0.33` for a `constants` array, the module-level numbers of the
  project's own modules the run reaches, outside `behaviour_fingerprint`. The other direction is
  a report that never fails, on Thilina's call, because the reverse would have demanded 71 names
  of dogfood #5 at `ship` and which numbers are the builder's is a judgement the library cannot
  make. **Re-measuring first is what shaped it**: the recorded module rule reached 17 of 56
  constants and the recorded join surface read one pipeline of seven. Six defects came out of the
  read-back cycles, including a module reached only by importing data from it and a project
  upgrading from `0.32` failing for constants it has. 3487 tests.
  [`build-logs/what-a-decision-produced-build-log.md`](../../dev-docs/build-logs/what-a-decision-produced-build-log.md#L1)
- **The build is a conversation** (P3-37), 2026-08-27. Four candidates from dogfood #5's
  sitting 3. The rule for how a question is put now sits in the three places a question is
  composed, because the measurement said a scaffold is not enough: `answer_form`'s scaffold
  already read "offer the five against one of the builder's own inputs" at that run's freeze,
  and the coding agent took the five library type-names out of it and asked against an invented
  example. Five `ask` strings rewritten to name what goes in front of the builder, and a ratchet
  that none cites a document or a taxonomy entry. `consultation`'s scaffold reads which of the
  three modes a project needs off `used_through`, one stage earlier. **FT-41** is new, the
  twenty-fourth check: a run stopped to ask and nothing continued it, counted at every stage and
  a failure from `ship`, with the stage 4 step that produces the state. FT-25's pass note widens
  from the run to the newest results file, where a rollout answers with a stand-in by
  construction. 3415 tests.
  [`build-logs/the-build-is-a-conversation-build-log.md`](../../dev-docs/build-logs/the-build-is-a-conversation-build-log.md#L1)
- **Refining the view** (P3-42), 2026-08-28. Five named threads, four built and one rejected.
  A project at `shape` is viewable, as `view_projects/skeleton` pinned to `branching`, and
  reading it found `FT-40` reporting `pass` at `ship` on a project whose every one of thirteen
  steps was a placeholder: the check reads `agent.py` now, counts at every stage and fails from
  `ship`, which is the one check that reads a project's code. The system level gains the
  pipeline level's encoding, with a link's width read per run and the totals on the store's
  card. A design nobody has agreed to says so, which is what the page was silent about at the
  gate it was built for. Every question is named for the builder rather than by its brief key,
  on Thilina's call. A trigger declared on `Pipeline` was proposed and rejected: a trigger that
  can change is not a value to freeze in a constructor. The page's own script is executed by
  the suite now, under `node`, against every fixture: nothing ran those 3,000 lines before, and
  a control that hid the one measure a project had shipped under a green run. **A readability
  audit in a real browser closed the pass**: the drawing was scaled to 0.78 on a 1440 screen so
  its labels rendered at 7.4px, labels overlapped, and the lines a reader follows sat at 1.3:1
  where 3:1 is the floor. The page now holds 11px in its drawings, 4.5:1 for text and 3:1 for a
  line, across five palettes a reader picks from. 3398 tests, from 3308; no format moved.
  [`build-logs/refining-the-view-build-log.md`](../../dev-docs/build-logs/refining-the-view-build-log.md#L1)
- **What the picture cannot say** (P3-41), 2026-08-28, sitting taken and built the same day.
  Seven strands, six of them Thilina's decisions. A node records what its own code did to a
  store (`ctx.record_access`, trajectory `0.28`, `touches=` on all three node kinds), so a store
  is explorable whichever way a step reaches it. Every run is read rather than the newest, for
  per-step cost per basis, how often each edge is taken and every access: 4.3 seconds over
  2,393 runs and 2.54 GB. The drawing gains a glyph per kind, an outline that says status, edge
  widths that are traversal counts, a selectable measure bar and a key; a run walks step by step
  in the page, on the served endpoint and under `report --walk`; every function the project
  declares is on the page from its own source; and `shape_confirmed` dates the picture the
  builder agreed to. Results `0.25`. 3,308 tests.
  [`build-logs/what-the-picture-cannot-say-build-log.md`](../../dev-docs/build-logs/what-the-picture-cannot-say-build-log.md#L1)
- **The data in the view** (P3-40), 2026-08-27, built the same day it was taken. The view
  answers what each step is handed from the steps whose edges reach it, and carries one real
  value per step from the newest run; a step the run skipped is no longer counted as one that
  ran. The reported evaluation lands on the page: every figure with its definition,
  denominator, interval and left-out counts, per-node figures on the steps, the do-nothing
  floor as counts, and what was never reached, never scored or never measured. A "where the
  data goes" section, a graph that opens a step in place and draws cycles, nested pipelines and
  error edges, and a sixth fixture carrying all of them with a live Gemini run and a live
  evaluation. `assemble.py` split into `cards.py`, `findings.py` and itself; the shape baseline
  lost nine entries and the two view prototypes were deleted. **Rejected once and taken
  further the same day**: the first pass showed a slice of a payload, and what a builder needs
  is how much moved, so every step now counts what it was handed and handed on
  (`survey 2,000 · pool 40` in, `items 40` out), the example set became a section, and a
  resource gained a card. **Then read from a builder's perspective**, which put four more in:
  the brief checked against the code (`DF5-D7` caught by the page), what each step's executions
  ended as with the failure paths that fired, every question the run put to a person, and what
  moved between the last two runs. The four it did not take are §1's next item, what the picture cannot say. 3,230 tests.
  [`build-logs/the-data-in-the-view-build-log.md`](../../dev-docs/build-logs/the-data-in-the-view-build-log.md#L1)
- **The common language** (P3-35), 2026-08-26, reframed twice in one day and built overnight,
  carrying `DF5-I22`. `simple-agents view` writes one builder-facing page of the project as it
  stands, rewritten at every gate: what is declared, built, planned (`NotBuilt` in a node's
  callable slot), what changed since the last run, and what flows between pipelines
  (`touches=` on tools and `Deterministic`). `comments.toml` records what the builder said
  about a part of the system, FT-39 reports it open and `comments_block_gates` makes it
  refuse; FT-40 fails `ship` on a surviving placeholder; `@pipeline_factory` names a
  project's pipelines. Manifest `0.31` to `0.32`. **Made live the next morning on Thilina's
  call**: `--serve` takes comments on any element, answers on open questions and amendments
  on recorded ones as threads with replies both ways; `simple-agents comments` is the
  agent's inbox; the page follows the project as it changes, **including a run in
  progress**, step by step as records land. 3,186 tests, a live Gemini run in the fixtures,
  the builder loop and the run watching driven end to end in a real browser.
  [`build-logs/the-common-language-build-log.md`](../../dev-docs/build-logs/the-common-language-build-log.md#L1)
- **What an agent may do alone** (P3-36), 2026-08-26, designed and built the same day, carrying
  dogfood #5's `DF5-I14` and `DF5-I15`. `NodeInput` is a seventh handle and the first written as
  annotation metadata: a tool takes `Annotated[list[dict], NodeInput("pool")]` and is filled with
  the node's own input, hidden from the model's schema and re-run rather than served from the
  cassette, which is what an `AgentNode` whose tools need per-run state had no way to do.
  `anything_else` is a forty-seventh question, required and put again at every stage, dated by
  `asked_at` on its entry and refused a deferral; `agency_boundary` is asked as a want and put
  together with `consultation`. No format moved. 3132 tests, and `docs/pipeline.md` §2.3 now says
  when a bounded cycle is the right shape and when an `AgentNode` is. Ten verification cycles,
  the tenth clean, found twenty-nine defects the suite could not see, one of them a shipped
  example that never built and one a shipped promise a fan-out breaks; what the code does moved
  in the first alone. A twenty-six assertion live probe on vLLM ran in every cycle.
  [`build-logs/what-an-agent-may-do-alone-build-log.md`](../../dev-docs/build-logs/what-an-agent-may-do-alone-build-log.md#L1)
- **What the checks read** (P3-34), 2026-08-25, designed and built the same day, closing dogfood
  #5's sitting 2. Five checks passed over the thing they are for. FT-37 fails a reported number
  produced by a pipeline the project no longer has and FT-38 a brief nobody read against the code
  again, both from stage `ship`, which is where `DF4-D7`'s question about the road after the last
  gate is answered: a `ship`-stage check goes on firing, so a check whose subject is a change
  governs that road and no seventh stage is added. The report's header names the run the
  run-reading checks read by its nodes, a variant sweep's arms declare `role="variant"`, FT-03
  reports `n/a` where it made no check, and the results file records `behaviour_fingerprint`.
  Results file `0.24`, twenty-one checks, thirty-eight taxonomy entries, 3086 tests. Fifteen
  full verification cycles, the fifteenth clean, found forty-six defects the suite could not
  see; the code stopped moving after the second, and everything the rest found was a statement
  about it. A thirty-two assertion live probe on vLLM ran in every cycle.
  [`build-logs/what-the-checks-read-build-log.md`](../../dev-docs/build-logs/what-the-checks-read-build-log.md#L1)
- **Consultation met a product** (P3-33), 2026-08-25, designed and built the same day, closing dogfood #5's sitting 1. The once-per-run memo is the model's alone, a channel may return `Shelved` and an answer filed later starts its own run, a consultation takes an identity, `Suspend` leaves `Exception`, and an evaluation is refused over a channel that reaches a person. Trajectory `0.27`, shelf `0.1`, the channel contract broken to three arguments across 77 definitions, two cassettes re-recorded, 106 tests. Six verification cycles found nineteen defects the suite and the checks could not see. [`build-logs/consultation-met-a-product-build-log.md`](../../dev-docs/build-logs/consultation-met-a-product-build-log.md#L1)
- **The product** (P3-30), 2026-08-20, designed and built the same day, closing dogfood #4's
  sitting 7 and with it `DF4-I06` and `DF4-I38`. "The product" is a glossary term and
  `docs/product.md` the seventeenth document; `used_through` is required at brainstorm;
  `design.md` gains the product section, its interactions classified four ways, and FT-34
  reads it; stage 4 builds the product beside the pipeline. The before-any-design readings
  fixed two defects on the way: a generated run id carries eight characters, and `HostPolicy`
  binds per run as the sixth handle type, live-verified with overlapping runs against Gemini,
  as was the closing suspend-behind-a-surface, resume-in-another-process run. **The brief and
  `design.md` move for every project on disk**; no server, store or scheduler ships. The
  procedure was reviewed whole and trimmed to fit its unchanged budget. 2933 tests.
  [`build-logs/the-product-build-log.md`](../../dev-docs/build-logs/the-product-build-log.md#L1)
- **Dogfood #4 worked through** (P3-1), 2026-08-20, opened 2026-08-15 and slid twice. 41
  candidates over seven sittings: 36 built, as `P3-6` to `P3-9`, `P3-15` to `P3-28` and the
  fixes and consultation logs; 3 declined with the reason on the row; and sitting 7's two
  scheduled into §1's top row, [`build-logs/the-product-build-log.md`](../../dev-docs/build-logs/the-product-build-log.md#L1).
  [`runs/dogfood-4/inventory.md`](../../dev-docs/runs/dogfood-4/inventory.md#L1) §3 holds every disposition
  and [`findings.md`](../../dev-docs/runs/dogfood-4/findings.md#L1) the evidence.
- **The research stage** (P3-28), 2026-08-20, dogfood #4's sitting 6, closing `DF4-I14`,
  `DF4-I28`, `DF4-I29`, `DF4-I37` and `DF4-I41`. A sixth stage between `brainstorm` and
  `shape`: five questions, `research.md` in four sections, and **FT-36**, which fails a survey
  row whose `Outcome` is blank. A brief entry carries `source`, and a required one answered
  `coding_agent` fails FT-24. `ExampleSet.nearest_cross_split(n=)`, so `too_similar` can ask a
  builder to judge pairs. `simple-agents report runs/` prints each tool's registration against
  its use. **The brief's shape moved and every project past `research` gains six keys.** 2927
  tests. [`build-logs/research-stage-build-log.md`](../../dev-docs/build-logs/research-stage-build-log.md#L1)
- **What a figure is reported against** (P3-27), 2026-08-20, dogfood #4's sitting 5, closing
  `DF4-I17` and `DF4-I18` in five stages and pulling in §2.2's `required`-condition entry as the
  fifth. Any figure grouped by a property of the example, `Metric.rollout_noise` and a `compare()`
  verdict that withholds inside it, `EvalSuite(baseline=...)` reporting what doing nothing would
  have scored, and `asserted` reading the verdict rather than the outcome alone. Results file
  `0.22` to `0.23`, 2880 tests.
  [`build-logs/what-a-figure-is-reported-against-build-log.md`](../../dev-docs/build-logs/what-a-figure-is-reported-against-build-log.md#L1)

- **A gate on a loop that spent its budget without acting** (P3-26), 2026-08-19, the fourth and
  last stage of *Spend that produced nothing*. **FT-35**, the first check to read more than one
  run: it reads the `unfinished` block of every run the pipeline as it now stands has made, by
  the `behaviour_fingerprint` each recorded, so a project that fixes the node is measured on the
  runs since the fix and never has to delete the ones that prompted it. `allow_unfinished=True`
  on an `AgentNode` waives it. Eighteen checks and thirty-five taxonomy entries now.
  **Manifest `0.30` to `0.31`, results file `0.21` to `0.22`**; 2817 tests to 2831.
  [`build-logs/unfinished-work-build-log.md`](../../dev-docs/build-logs/unfinished-work-build-log.md#L1) §3.7
- **What every run did, without writing code** (P3-25), 2026-08-19, the third stage of
  *Spend that produced nothing*, which is where the figures become something a builder reads.
  `simple-agents report <path>` over a directory of runs, one run, an evaluation's rollouts or a
  results file; the same lines under each node in `results.report()`; the wider figure as a note
  under `simple-agents check`; and the `measure` stage of the procedure saying to run it.
  `basis_from_manifest` and `runs(since=, last=)` are what let a reader price runs they did not
  make. No format moved; 2776 tests to 2817.
  [`build-logs/unfinished-work-build-log.md`](../../dev-docs/build-logs/unfinished-work-build-log.md#L1) §3.6
- **What a rate is over, and what leaves it** (P3-24), 2026-08-19, the second stage of
  *Spend that produced nothing*, closing §2.1's *An outcome for a run that consulted and got no
  answer*. A rollout is inside a denominator when what it returned is attributable to the agent,
  which is the rule `no_response` already followed: a question to a channel meant to answer it
  and an item the backend never reached now leave every rate, and a question to `unattended()`
  does not. Both figures print, the narrower over the wider. **Results file `0.19` to `0.20`**;
  2741 tests to 2750.
  [`build-logs/unfinished-work-build-log.md`](../../dev-docs/build-logs/unfinished-work-build-log.md#L1)
- **What a run spent and produced nothing with** (P3-23), 2026-08-19, the first stage of
  *Spend that produced nothing*, whose three remaining stages are §1's.
  An `AgentNode` produces its output from a `finish` call, so an execution that stops on a budget
  axis returns `None` and the run completes with no error, which nothing reported: one project
  spent 24.4% of its model calls that way. Four figures per node, `node_metrics(run_dir)` over
  any directory of runs, and each run's manifest carrying its own. **Trajectory `0.25` to `0.26`**
  for `item_index` on three more record types, **manifest `0.29` to `0.30`**, **results file
  `0.18` to `0.19`**; 2713 tests to 2741.
  [`build-logs/unfinished-work-build-log.md`](../../dev-docs/build-logs/unfinished-work-build-log.md#L1)
- **A version is taken when the thing is declared, and FT-15 has a check** (P3-21), 2026-08-19,
  owed to `P3-20`'s Left open. A prompt or route closing over state it mutated changed version
  while the run ran, so the stamp a project joins its stored results on moved on its own. Versions
  are taken at declaration now, for tools as well, so two tools one factory built no longer share
  a cassette key. `ft_15` is registered seventeenth. **The Mistral `tools` arm retired** rather
  than being re-recorded against a backend out of credits. No format move; 2716 tests to 2713.
  [`build-logs/a-version-when-it-is-declared-build-log.md`](../../dev-docs/build-logs/a-version-when-it-is-declared-build-log.md#L1)
- **What an evaluation is filed under, and what the prompts show** (P3-20), 2026-08-19, closing
  dogfood #4's sitting 3. Three things changed what an evaluation measured and left its directory
  name where it was: an edited tool body, an edited `Deterministic` body, and data a node reads.
  The second moved nothing at all, `behaviour_fingerprint` included. `Deterministic` records and
  declares a version, a declared version keeps the source hash beside it, and
  `prompt_differences()` reads the prompts back out of the trajectories. **Manifest `0.28` to
  `0.29`, and every evaluation directory is renamed**; 2682 tests to 2711.
  [`build-logs/evaluation-identity-build-log.md`](../../dev-docs/build-logs/evaluation-identity-build-log.md#L1)
- **Progress a builder can see** (P3-19), 2026-08-18, closing dogfood #4's sitting 2. Three
  channels reported what was running and one rendered, and `P3-16`'s `item` phase carried an index
  with no denominator. `ProgressBar` takes either callback, `NodeEvent` gains `item_total`, and
  `simple-agents watch` follows an evaluation from another terminal. `tqdm` is a new dependency;
  2670 tests to 2682.
  [`build-logs/progress-display-build-log.md`](../../dev-docs/build-logs/progress-display-build-log.md#L1)
- **What `behaviour_fingerprint` leaves out** (P3-18), 2026-08-18, dogfood #4's sitting 2. The
  stamp a project writes beside a stored result missed three things that decide what the pipeline
  produces and are all recorded in the manifest: the client passed to `run(model=)`, every tool's
  version, and a consultation reader's model and prompt. It takes `model=` and refuses a stamp it
  knows is partial. **Manifest `0.27` to `0.28`**, 134 fixtures regenerated; 2663 tests to 2670.
  [`build-logs/what-the-stamp-covers-build-log.md`](../../dev-docs/build-logs/what-the-stamp-covers-build-log.md#L1)
- **An adapter's backend state, and the helper that drops it** (P3-17), 2026-08-18, dogfood #4's
  sitting 2. Gemini attaches a thought signature to every tool call and refuses the following
  request without it; the library carries it on `ToolCallRequest.provider` and returns it by its
  native path, and the shared OpenAI-dialect helper discarded it while `docs/model-clients.md` §7
  pointed adapter authors at that helper. `messages_to_wire` now refuses a call carrying state it
  cannot express. No format moved; 2659 tests to 2663.
  [`build-logs/adapter-backend-state-build-log.md`](../../dev-docs/build-logs/adapter-backend-state-build-log.md#L1)
- **The two defects in the fan-out mechanism** (P3-16), 2026-08-18, closing dogfood #4's first
  sitting. A transport failure inside a fan-out was invisible to an evaluation, because a fan-out
  collects a failed item rather than raising and the classification is only reached by a run that
  raised: `RolloutOutcome.unreached_items` counts the items that died on a call the backend never
  answered, and reclassifies nothing. And a fan-out handed its whole result on at the end, so
  `NodeEvent` gains an `item` phase a project writes each item on. **Results file `0.18`**, 2659
  tests. [`build-logs/fan-out-defects-build-log.md`](../../dev-docs/build-logs/fan-out-defects-build-log.md#L1)
- **`over=` on every node kind, and tools on `LLMNode`** (P3-15), 2026-08-18, out of dogfood #4's
  first sitting. Fan-out was on `LLMNode` alone, so an agentic step once per item could not be one node,
  and a fixed model call needing a tool had to be split across two. `over=`, `keep=`,
  `max_failures=` and `concurrent_items=` are on all three kinds; a fanned-out `AgentNode`
  declares `budget_per_item=` beside `budget=`, and one of the two alone is a warning naming the
  axis left open; `LLMNode` takes `tools=`; `ItemOutcome` carries `termination`; a `model_call`
  records its `item_index` and seeds from it, which is what makes an overlapping fan-out replay;
  and a stopped fan-out keeps what each item was holding. **Trajectory `0.25`, manifest `0.27`,
  suspension `0.5`**, 2650 tests.
  [`build-logs/fan-out-and-node-shape-build-log.md`](../../dev-docs/build-logs/fan-out-and-node-shape-build-log.md#L1)
- **A judgement the scoring code did not compute** (P3-12), 2026-08-18, the run-time stage and
  what closed the item. A model reads what an end user answered into the option they meant, at
  the seam where whole-answer equality read an option out of **0 of 24** measured prose answers
  and routed every one to `unmatched`. `consult(read=ModelReader(model=cheap))` ships the reader
  and takes the project's own prompt, client and retry; `read=` also takes a bare function of
  `(reading, answer, options)`. The reading happens wherever an answer arrives, live and on the
  resume path, and each of its calls is emitted as a `model_call` parented to the
  `consultation`, charged to the run because a reader ships with the agent, and served from the
  cassette on replay, so k rollouts pay for one reading. The reader is out of the tool's `version` and on its manifest entry
  instead, so an edited prompt misses on the reading and leaves every recorded answer where it
  is. A reading that cannot be made ends the run and the consultation is still recorded, with
  `resolution: "answered"` rather than `unmatched`, because a broken reader is not a claim about
  what the end user said. **Decision 8's stated mechanism could not be built**: a `ModelHandle`
  on the consult tool would ask the person again on every replay, measured. **§9 item 8 is
  narrowed rather than defeated**: a `Deterministic` node can carry this one library-owned call,
  and its function is still handed nothing that can make one. Trajectory `0.24`, one shipped
  statement corrected, fourteen fixtures regenerated. **2614 tests.**
  [`build-logs/consultation-reading-build-log.md`](../../dev-docs/build-logs/consultation-reading-build-log.md#L1),
  and **§3 is the five things the build found**, three of them only from a live run or a
  mutation pass. The item's record while it was open is at
  [`archive/a-recorded-judgement.md`](../../dev-docs/archive/a-recorded-judgement.md#L1).

- **A judgement the scoring code did not compute** (P3-13), 2026-08-18, the scoring-time
  stage of P3-12. A
  condition a model or a person decides, read at scoring time and never called from one.
  `Judged()` and `Scoring.judgement(question, over=...)` at every scoring seam; a judging pass
  given the **whole** worklist and returning a `Label` each, through `suite.judge`,
  `suite.unjudged`, `run(judge=)` and `compare_variants(judge=)`; a judgement keyed on a digest
  of the example, the question and the material, so k rollouts of one answer are judged once and
  an answer that changed has no judgement rather than an older one's; `evals/judgements.jsonl`
  as the store with a copy per evaluation that is written once, so a correction never moves what
  an earlier run reported; and a gate between the rollouts and the numbers naming every answer
  waiting, carried on `UnjudgedAnswers` with the worklist and the directory. **§9 is untouched
  and §10 gained a constraint**: scoring makes no model calls. Results file `0.17`,
  `_stable_text` corrected ahead of it, five shipped statements corrected. **2571 tests.**
  [`build-logs/recorded-judgement-build-log.md`](../../dev-docs/build-logs/recorded-judgement-build-log.md#L1),
  and **§3 is the eight things the build and the verification found**, four of them only from a
  live run. **The consultation reading shipped as P3-12 above.**

- **What a correct answer can be** (P3-5), closed 2026-08-17. The survey of twenty-four answer
  shapes, built in two blocks: `P3-10` for a typed answer key, criteria, a seventh outcome and
  eight rates, and **stage 3 under this id for per-field absence**. A criterion's check may
  return `Unknown` where the answer asserted nothing about that condition, an answer that met
  none of its key that way is `missed` rather than `false_confidence`, and
  `Criterion(expects_absence=True)` declares that silence is the right answer there and is what
  **FT-04** reads where the absent case lives in one field of a record. Measured on twelve real
  rollouts: an agent that invented nothing was reported as asserting a confident wrong value on
  25% of them. `node_matches` refuses a non-bool return as `matches` already did. Results file
  `0.16`, and `Criterion` gaining a field moves `content_hash` for any set carrying criteria.
  **2528 tests.**
  [`build-logs/per-field-absence-build-log.md`](../../dev-docs/build-logs/per-field-absence-build-log.md#L1),
  and **§4.5 is the nine defects its verification pass found after the suite was green**. The
  survey is design of record at
  [`design/answer-shapes.md`](../../dev-docs/design/answer-shapes.md#L1), and its stage 4 is §1's top row.

- **The end user an evaluation answers with** (P3-9), 2026-08-17, decided and built the same day.
  A stand-in was handed a description and nothing else, so an example whose answer depends on a
  value that person holds was unreachable in every rollout. **`EndUser` carries what they know**
  as a `Fact` per thing, with `disclose` of `volunteer`, `on_ask` or `hidden`; a `hidden` fact is
  never put in front of the model and reaches a run through the answer key. The stand-in answers
  with what it already said in that rollout in front of it, which took a fabricated choice from
  3-of-3 ratified to 3-of-3 refused; `instructions=` replaces the prompt; `consult(reaches=)` and
  a channel per name make a requester-and-approver pipeline expressible;
  `per_node.consultation_misreadings` reports a `match=` rule that reads none of the answers;
  `unanswered_consultations` counts the questions nobody answered; and a consult tool may overlap
  where its channel declares `may_suspend = False`. **Two of the record's six assumptions did not
  survive being checked**, and **`example.end_user` is an `EndUser` after construction**, which
  breaks code comparing it to a string. Trajectory `0.23`, manifest `0.26`, results file `0.15`.
  **2403 tests.**
  [`build-logs/end-user-in-an-evaluation-build-log.md`](../../dev-docs/build-logs/end-user-in-an-evaluation-build-log.md#L1),
  and **§4.1 is the six defects the verification pass found after the suite was green**.

- **What elicitation asks about the answer** (P3-11), 2026-08-17, decided and built the same day.
  `P3-10` shipped four answer keys and no question a builder is asked reached them. `answer_form`
  is the answer key question now and `presentation` keeps the output form; `ground_truth` asks
  which answers are acceptable rather than what the answer is; `absence_vs_error` weighs three
  states. **Two questions are new**, `judged_steps` and `judged_path`, because the narrowness went
  past the answer: **49 results files over four dogfoods carry a per-node section and not one
  carries a label**. `shape` goes from 6 questions to 8, all required, and a project on disk fails
  FT-24 until it answers the two. The rule that a scaffold may reach one answer through several
  exchanges is stated, in the `Question` docstring, `docs/procedure.md` and the CLI header, which
  all three left it ambiguous. No format moved. **2361 tests.**
  [`build-logs/eliciting-the-answer-shape-build-log.md`](../../dev-docs/build-logs/eliciting-the-answer-shape-build-log.md#L1).

- **An answer key that says what it is** (P3-10), 2026-08-17, decided and built the same day.
  The first two stages of *What a correct answer can be*, as one block. Four answer keys in the
  `expected` position, encoded as
  tagged objects so a JSONL file and `content_hash` both hold them; `Criteria`, a list of
  conditions each judged yes or no, carrying a weight and whether it is `required`, with the
  criterion as data and its check as code registered on the suite and versioned beside `matches`;
  **`Outcome.PARTIALLY_CORRECT`**, reachable only from a key whose parts can be met separately;
  **eight rates**, adding `graded_accuracy` and `partially_correct_rate`; a figure per criterion in
  `results.criteria` and `comparison.criteria`; and one `Scoring` at every scoring seam, which
  breaks `matches(predicted, expected)` and `score(predicted, expected, rollout)` for every project
  on disk. Results file `0.14`, FT-10's written definition moved, 2348 tests.
  [`build-logs/answer-key-build-log.md`](../../dev-docs/build-logs/answer-key-build-log.md#L1).

- **The design the builder agreed to** (P3-8), 2026-08-16, designed and built the same day. How the
  agent will be built becomes an artifact rather than a conversation. **`design.md`** at stage
  `shape`, three sections, the third carrying the builder's own words; **FT-34** reads it; a
  `shape` or `presentation` decision records `from`, and the report prints the answers about
  what the builder wants that no decision rests on. `docs/procedure.md` says the question set
  is a floor rather than the script, at 1722 words against a budget moved to 1750. Sixteen
  checks, 34 entries. **2276 tests**, no format moved.
  [`build-logs/agreed-design-build-log.md`](../../dev-docs/build-logs/agreed-design-build-log.md#L1), and
  **§3 carries two defects it found in the fixture generator**.
- **The brief against the code** (P3-7), 2026-08-16, designed and built the same day. Three checks
  that read a brief answer against what a run recorded, and the library's first enforcement
  that fires on a **change** rather than on a project reaching a gate. **FT-25's check is
  registered** after being specified since the first draft; **FT-32** reads `tool_effects`
  against the manifest's tools; **FT-33** reads a build log that stopped before the runs did;
  and `confirmed_against` in the brief makes the report name the entries due for re-reading
  when the pipeline moves under them. Fifteen checks, 33 taxonomy entries. **2262 tests**, no
  format moved.
  [`build-logs/brief-against-code-build-log.md`](../../dev-docs/build-logs/brief-against-code-build-log.md#L1),
  and **§3 carries the three false positives the fixtures and the live run found**.
- **What the end user sees** (P3-6), 2026-08-16, designed and built the same day. A project that
  accumulates its own output has a third artifact, and no check opens it.
  **`Pipeline.behaviour_fingerprint()`** is what a project stamps a stored result with, and it
  moves on a prompt edit where `graph_fingerprint()` does not; the manifest records it; a
  required `ship` question, `stored_output`, asks what the end user reads and what refreshes a
  result an older pipeline wrote. `docs/shipping.md` §6 is new and `docs/failure-taxonomy.md`
  §10 records that the suite does not open the artifact. Manifest `0.25`. **2241 tests.**
  [`build-logs/end-user-artifact-build-log.md`](../../dev-docs/build-logs/end-user-artifact-build-log.md#L1),
  and §6 is what it leaves open.
- **The `ship` stage**, 2026-08-15, designed and built the same day. A fifth stage after
  `measure`, for the point where somebody other than the builder uses the agent. **The tier
  decides which stages a project has**, which repairs a report that contradicted itself at
  `measure` in the shipped suite and in four of our own fixtures. `RunEnvelope(live=True)` and
  `runs(live=True)` say whether an end user was on the other end; four questions at `ship`, three
  required; **FT-31** is the first check gated on a stage rather than on a tier alone;
  `docs/shipping.md` is new. Manifest `0.24`. **2230 tests.**
  [`build-logs/ship-stage-build-log.md`](../../dev-docs/build-logs/ship-stage-build-log.md#L1), and **§3 is what it does not close**.
- **Dogfood #4's cheap fixes**, 2026-08-15. Four surfaces that read as working and were not, plus
  a check that a package `__init__` exports what it imports. **2193 tests**, no format moved.
  [`build-logs/dogfood-4-fixes-build-log.md`](../../dev-docs/build-logs/dogfood-4-fixes-build-log.md#L1); [`runs/dogfood-4/inventory.md`](../../dev-docs/runs/dogfood-4/inventory.md#L1) §F carries the dispositions
  and DF4-I10 to DF4-I14 are open.
- **Consultation: who answers, and what the record says**, 2026-08-15, both halves. A channel
  declares `answered_by` and is refused without one; `Unavailable(reason=...)` and `unattended()`
  for a run with nobody to ask; `RunEnvelope(end_user=...)` and
  `EvalSuite.run(end_user=SimulatedEndUser(model=...))`. Trajectory `0.22`, manifest `0.23`,
  results file `0.13`. **2176 tests.** [`build-logs/consultation-build-log.md`](../../dev-docs/build-logs/consultation-build-log.md#L1), and §7.2 and §7.3
  are what the sitting did not settle and what the build found. **The hosted suspend fixture is
  Gemini now.**
- **The full-test QA pass**, 2026-08-13, run outside this queue against `2f4db4c`. Five blockers
  and every other finding fixed, merged and pushed. Results file `0.12`, manifest `0.22`.
  [`build-logs/full-test-checkpoint-build-log.md`](../../dev-docs/build-logs/full-test-checkpoint-build-log.md#L1) is the entry point and
  `runs/full-test-2026-08-13/` is everything it produced.
- **Concurrency: independent branches, and a fan-out that runs together**, 2026-08-13.
  `concurrent_nodes` on the pipeline, `concurrent_items` on a fan-out, `concurrent_tools` on an
  `AgentNode`, under `Pipeline.run(concurrency=N)` which defaults to 1. Drain on stop,
  `max_wall_clock_ms` becomes elapsed, `DeviceBasis`, and a suspended run becomes a tree.
  Suspension `0.4`. **1879 tests.** §1.12 for the design of record, and
  [`build-logs/concurrency-build-log.md`](../../dev-docs/build-logs/concurrency-build-log.md#L1) for the build and the seven defects the testing found,
  three of which predate the item. Measured live at 7.5x on width 60.
- **A consultation answer the library can read**, 2026-08-12. `consult` returns a `Reply`,
  `on_reply` routes on it with a required branch for an unmatched answer, and `resolution` gains
  `unmatched`. Trajectory `0.21`, manifest `0.21`. **1827 tests.**
  [`build-logs/typed-consultation-build-log.md`](../../dev-docs/build-logs/typed-consultation-build-log.md#L1).
- **A Gemini adapter**, 2026-08-12. [`build-logs/gemini-adapter-build-log.md`](../../dev-docs/build-logs/gemini-adapter-build-log.md#L1).
- **A design decision the coding agent proposes rather than makes**, 2026-08-11. Six decision
  kinds, `[decisions]` in the brief, **FT-30**, and three elicitation questions. 33 questions.
  **1737 tests.** [`build-logs/decision-surface-build-log.md`](../../dev-docs/build-logs/decision-surface-build-log.md#L1). §1.11 records what dogfood #4 then
  measured against it.
- **The dogfood #3 fixes, and an evaluation that can be watched and re-entered**, 2026-08-11.
  `DF3-D2`, `D4` to `D7` and `P1`, plus `EvalSuite.run(resume_from=...)`, `on_rollout=` and
  `progress_of()`. Results file `0.10`. **1721 tests.**
  [`build-logs/dogfood-3-fixes-build-log.md`](../../dev-docs/build-logs/dogfood-3-fixes-build-log.md#L1).
- **Dogfood #3's findings record**, 2026-08-11. Ten findings over the book-recommendation task.
  **`DF3-D1` is what meeting the criterion at 10 of 10 was worth.** [`runs/dogfood-3/findings.md`](../../dev-docs/runs/dogfood-3/findings.md#L1), and
  §9.3 is the eight open items.
- **Semantic recall**, 2026-08-11. `DocumentIndex(embeddings=)` and `memory_search(embeddings=)`,
  and a fourteenth document, `docs/retrieval.md`. **1683 tests.**
  [`build-logs/semantic-recall-build-log.md`](../../dev-docs/build-logs/semantic-recall-build-log.md#L1).
- **A run records by default**, 2026-08-11. `RunEnvelope.cassette` defaults to
  `Cassette.into_run()`, kept or dropped with the trajectory's payloads. Manifest `0.20`. 30
  questions. **1635 tests.** [`build-logs/recording-default-build-log.md`](../../dev-docs/build-logs/recording-default-build-log.md#L1).
- **Scoring rollouts that already ran**, 2026-08-10. A raising project metric fails on the first
  rollout and cancels the rest, and `EvalSuite.rescore(run_dir=...)` scores what is on disk.
  Results file `0.9`. **1619 tests.** [`build-logs/rescore-build-log.md`](../../dev-docs/build-logs/rescore-build-log.md#L1).
- **Evaluating an agent that spends money**, 2026-08-10. `EvalSuite.run(max_spend=...)` and
  `EvalSuite.record(...)`. **Do-not-change #5 moved.** Results file `0.8`. **1595 tests.**
  [`build-logs/paid-eval-build-log.md`](../../dev-docs/build-logs/paid-eval-build-log.md#L1).
- **Memory**, 2026-08-10. `RunEnvelope(memory=MemoryStore(directory, scope=...))`, reached through
  recorded tool calls. Manifest `0.19`. **1574 tests.** [`build-logs/memory-build-log.md`](../../dev-docs/build-logs/memory-build-log.md#L1).
- **A pipeline exposed to a model as a tool**, 2026-08-10.
  `AgentNode(delegates=[Delegation(...)])`. The trajectory gains a fifth record type and goes to
  `0.19`; suspension `0.3`. **1544 tests.** [`build-logs/pipeline-as-tool-build-log.md`](../../dev-docs/build-logs/pipeline-as-tool-build-log.md#L1).
- **`ablate()` on a pipeline it did not generate**, 2026-08-10. Ten defects with one cause, a
  container read only for its leaves. Manifest `0.18`, results file `0.7`. **1503 tests.**
  [`build-logs/ablate-build-log.md`](../../dev-docs/build-logs/ablate-build-log.md#L1).
- **Per-node model selection**, 2026-08-10. `LLMNode(model=)` and `AgentNode(model=)`, resolving
  node-first then run, with a cost basis per model behind it. Manifest `0.17`.
  [`build-logs/per-node-model-build-log.md`](../../dev-docs/build-logs/per-node-model-build-log.md#L1).
- **The `brainstorm` stage and FT-29**, 2026-08-10. A fourth stage before `shape`, eleven
  questions of which six are required, and `idea.md`. [`design/brainstorm-stage.md`](../../dev-docs/design/brainstorm-stage.md#L1) is the design of
  record; `simple-agents.md` §2.8 carries the amendment.
- **The three sittings**, 2026-08-09. DF2-D2 measured tool spend, DF2-D1 the loop accumulator, and
  the ground-truth sitting the labelling machinery with DF2-D8.
  [`build-logs/tool-spend-build-log.md`](../../dev-docs/build-logs/tool-spend-build-log.md#L1),
  [`build-logs/loop-accumulator-build-log.md`](../../dev-docs/build-logs/loop-accumulator-build-log.md#L1) and
  [`build-logs/ground-truth-build-log.md`](../../dev-docs/build-logs/ground-truth-build-log.md#L1).
- **Nine absorption build items**, 2026-08-09, with `load_env` dropped as outside the library.
  [`archive/dogfood-absorption.md`](../../dev-docs/archive/dogfood-absorption.md#L1) carries the dispositions, and
  the builds are [`build-logs/absorption-item1-build-log.md`](../../dev-docs/build-logs/absorption-item1-build-log.md#L1),
  [`-item2-`](../../dev-docs/build-logs/absorption-item2-build-log.md#L1),
  [`-item3-`](../../dev-docs/build-logs/absorption-item3-build-log.md#L1),
  [`-items4-7-`](../../dev-docs/build-logs/absorption-items4-7-build-log.md#L1) and
  [`-items8-9-`](../../dev-docs/build-logs/absorption-items8-9-build-log.md#L1).
- **Ten library-analysis fixes**, 2026-08-08. [`archive/library-analysis-2026-08-08.md`](../../dev-docs/archive/library-analysis-2026-08-08.md#L1).
- **Five prose findings, DF2-D6 and the §10 protocol amendment**, 2026-08-09.
  [`runs/dogfood-2/findings.md`](../../dev-docs/runs/dogfood-2/findings.md#L1) §9.2 says how each closed.
