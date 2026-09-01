## Checks run, latest verdict per claim

| Suite | Pass | Fail | Error | Skip | Total |
|---|---|---|---|---|---|
| `area-a-concurrency-live` | 10 | 0 | 0 | 0 | 10 |
| `area-a-delegation-live` | 4 | 0 | 0 | 0 | 4 |
| `area-a-fingerprint` | 1 | 2 | 0 | 0 | 3 |
| `area-a-graph-mechanics` | 8 | 2 | 0 | 0 | 10 |
| `area-a-heldback` | 1 | 0 | 0 | 0 | 1 |
| `area-a-replay-is-real` | 1 | 0 | 0 | 0 | 1 |
| `area-c-tools-builtins` | 34 | 0 | 0 | 0 | 34 |
| `area-c-tools-consult` | 17 | 1 | 0 | 0 | 18 |
| `area-c-tools-contract` | 29 | 1 | 0 | 0 | 30 |
| `area-c-tools-live` | 5 | 1 | 0 | 0 | 6 |
| `area-c-tools-policy` | 25 | 3 | 0 | 0 | 28 |
| `area-c-tools-replay` | 8 | 0 | 0 | 0 | 8 |
| `area-d-extra` | 2 | 1 | 0 | 0 | 3 |
| `area-d-hybrid` | 2 | 2 | 0 | 0 | 4 |
| `area-d-identifiers` | 7 | 0 | 0 | 0 | 7 |
| `area-d-retrieval` | 35 | 1 | 0 | 0 | 36 |
| `area-d-semantic` | 11 | 1 | 0 | 0 | 12 |
| `area-de-live` | 5 | 0 | 0 | 0 | 5 |
| `area-e-eval` | 6 | 0 | 0 | 0 | 6 |
| `area-e-memory` | 19 | 0 | 0 | 0 | 19 |
| `area-e-rollouts` | 7 | 0 | 0 | 0 | 7 |
| `area-f-evaluation` | 182 | 0 | 0 | 0 | 182 |
| `area-g-model-clients` | 117 | 2 | 1 | 5 | 125 |
| `area-hb-suspension-envelope` | 90 | 11 | 0 | 1 | 102 |
| `area-i-conformance-cli` | 165 | 15 | 0 | 1 | 181 |
| `composite-vllm` | 4 | 0 | 0 | 0 | 4 |
| `lead-verify-suspension-loss` | 0 | 1 | 0 | 0 | 1 |
| `verify-flagged-contradictions` | 1 | 6 | 0 | 0 | 7 |
| `vllm-reasoning-overflow` | 5 | 0 | 0 | 0 | 5 |
| **Total** | **801** | **50** | **1** | **7** | **859** |

58 superseded rows were dropped: a check re-run after its own harness bug was fixed appears more than once in the append-only result files.


## Every check not passing, latest verdict


### `area-a-fingerprint`

- **FAIL `PIPE-FP-1`** changing a container's tools= moves the graph_fingerprint
  - a container whose tools= changed from [alpha] to [beta] produced the same graph_fingerprint; pipeline.md line 297 says a change to any of it moves it
- **FAIL `PIPE-FP-2`** changing a container's budget moves the graph_fingerprint
  - a container whose budget changed from max_steps=5 to max_steps=9 produced the same graph_fingerprint

### `area-a-graph-mechanics`

- **FAIL `RATE-1`** a fan-out that trips the free tier's ceiling recovers through the adapter's retry
  - 13 of 14 fan-out items failed against the free tier despite the adapter's six-attempt retry
- **FAIL `GRAPH-JOIN-3`** a Join placed in the node list is refused rather than failing at run time
  - a Join in the node list constructed without complaint and then failed at run time with AttributeError: 'Join' object has no attribute 'node_kind'. Join is exported from simple_agents and takes node_id

### `area-c-tools-consult`

- **FAIL `CONS-017`** resume continues from the same point, and the answer is a second record
  - resume did not deliver the answer to a `consult` call in a Deterministic node: the channel was called 2 times, the run suspended again (RunSuspended), and the trajectory holds ['pending', 'pending']

### `area-c-tools-contract`

- **FAIL `TOOL-005`** Field(description=...) on a parameter reaches the schema
  - Field(description=...) did not reach the schema: None. Annotated metadata is stripped, so a constraint is lost too (top_k=400 accepted: True).

### `area-c-tools-live`

- **FAIL `LIVE-006`** the Reply docstring's own example against the shipped matcher
  - `Reply`'s docstring shows reply='Yes, go ahead' with chose='yes' against options ['yes', 'no']; the shipped default matcher returns None, so that answer is `unmatched` and an `on_reply` route sends it

### `area-c-tools-policy`

- **FAIL `POL-008`** a URL naming an explicit port is judged against the bare host
  - a URL on a configured host with an explicit port is out of scope, and the refusal names the same host on both sides: This agent may not fetch from 'docs.example.com:8443'. Permitted hosts: docs.exampl
- **FAIL `POL-009`** admit given a whole URL rather than a bare host
  - a whole URL was accepted as a host, spending the run's one admission on an entry that matches nothing: admitted ['https://brand.example/listing']
- **FAIL `GROUND-002`** contains_normalised folds case, accents and punctuation
  - contains_normalised('Beyoncé sang', 'Beyonce') is False, expected True; contains_normalised('The café is closed', 'cafe') is False, expected True; contains_normalised('Müller GmbH', 'Muller') is False

### `area-d-extra`

- **FAIL `RETR-057`** a one-node run whose search overspends max_steps is not stopped
  - the run completed after making 8 model calls under max_steps=1

### `area-d-hybrid`

- **FAIL `RETR-091`** the default ranking against six paraphrase queries, small corpus
  - over 6 queries the shipped default returned the answer in the top five 1 times against 5 for Semantic() alone; ranks were [None, None, 5, None, None, None] against [1, 1, 2, None, 4, 3]
- **FAIL `RETR-092`** the default ranking against the same six queries, 319 documents
  - over 6 queries at 318 documents the default returned the answer in the top five 2 times against 4 for Semantic() alone; ranks were [2, None, 3, None, None, None] against [1, 1, 2, None, None, 3]

### `area-d-retrieval`

- **FAIL `RETR-051`** the embedding model_call is parented to the tool call that made it
  - docs/retrieval.md says the model_call is parented to the tool call. From a Deterministic node its parent is {'rec_441241892499'}, the tool call is rec_67ea59d17a4b and the node execution is rec_441241

### `area-d-semantic`

- **FAIL `RETR-009`** the default hybrid returns the answer the semantic search ranked first
  - the default Hybrid(fuse=RRF(k=5)) did not return the answer in the top five at all: ['library-hours', 'extension-form', 'coffee', 'invoice-terms', 'bearing']. Semantic() alone ranked it first.

### `area-g-model-clients`

- **FAIL `VLLM-29/30/31`** two concurrent calls each read 2
  - [3, 3]
- **FAIL `VLLM-08/MC-59`** a real tool-calling turn over the wire
  - 
- **ERROR `MC-05b`** one basis over a two-backend run prices only what it names
  - ConfigurationError: This run calls both a hosted and a self-hosted backend (cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit, gemini-3.1-flash-lite) and declares one PriceBasis. A hosted call is priced on

### `area-hb-suspension-envelope`

- **FAIL `H-03b`** the refused resume left the suspension claimable again
  - the refusal consumed the suspension; the run can no longer be resumed
- **FAIL `H-09b`** the manifest records one suspension entry per stopped node
  - the run stopped in left and right; the manifest records ['left']. The second stop's node and question are not recorded anywhere in the manifest.
- **FAIL `H-03d`** a typo in answers= leaves the run resumable
  - a mistyped node id in answers= destroyed the suspension. The refusal is raised after discard_claim has unlinked the state, so the run cannot be resumed with the corrected key.
- **FAIL `H-03e`** an unreadable value tag refusal leaves the run resumable
  - the refusal deleted the state. codec.decode(state.inputs) is evaluated at pipeline.py:606, after discard_claim at pipeline.py:594.
- **FAIL `H-05a`** the stop names the id the trajectory records that node under
  - the stop names 'ask_inner', which is not the id the manifest, the trajectory and every other surface record this node under ('research.ask_inner')
- **FAIL `H-05b`** the nested run resumes with answer= and the answer arrives
  - the answer 'slim' was recorded as 'declined' with response None. resume(answer=) is dropped on the way into a pipeline used as a node, and the node is told the end user declined.
- **FAIL `H-06b`** a refused version mismatch leaves the state readable
  - the version refusal happened after the claim and the file was left renamed to suspension.claimed.json, so the run reads as not suspended
- **FAIL `H-07c`** to_mermaid draws the planned stop
  - nothing in the diagram marks the declared stop
- **FAIL `H-08d`** wait=True blocks and then continues the run
  - a Deterministic node whose tool suspended is never handed the answer: it runs again from the beginning, calls the tool again, and suspends again. The run cannot be continued at all.
- **FAIL `B-06b2`** nothing adds device-seconds to a figure in money
  - charged_cost is 0.397, which is 0.387 device-seconds added to 0.01 USD
- **FAIL `B-07c`** a redacted cassette still replays
  - a run that redacted a tool result cannot replay its own recording past that tool call

### `area-i-conformance-cli`

- **FAIL `INIT-004`** a committed symlink does not survive being cloned elsewhere
  - cli.py `_place` says the relative symlink means 'a project that commits it survives being cloned elsewhere'. The link is '../../../../../qa-venv/lib/python3.12/site-packages/simple_agents/.agents/skil
- **FAIL `INIT-006`** AGENTS.md names the path the skill was actually installed at
  - init --claude wrote AGENTS.md pointing at `.agents/skills/simple-agents/SKILL.md`, which that layout does not have. The coding agent reads AGENTS.md and follows a path with nothing at it.
- **FAIL `INIT-013`** an AGENTS.md that merely names the package is left without the pointer
  - init tests for the substring 'simple-agents' anywhere in AGENTS.md, so a file carrying the README's own install line (`uv add simple-agents`) is treated as already carrying the note and the pointer to
- **FAIL `COUNT-006`** the README's '28 characteristic failures'
  - README.md says the taxonomy holds 28 characteristic failures; it holds 30.
- **FAIL `COUNT-007`** the README's 'four record types'
  - README.md says four record types; the library ships ('node_execution', 'model_call', 'tool_call', 'consultation', 'delegation').
- **FAIL `COUNT-008`** FT-13's message on a bad record_type names the right number
  - checks.py's FT-13 reason says 'and the four are' and then lists 5 record types.
- **FAIL `BRIEF-003`** a deferral to something that is not a stage is refused
  - the refusal says 'the three stages are' and then lists four (brief.py `_entry`). A reader counting on the number is told the wrong one.
- **FAIL `README-001`** `pip install simple-agents` resolves on PyPI
  - the README's first quick-start line is `uv add simple-agents` / `pip install simple-agents`, and PyPI answers 404 for that name. A builder following the quick start literally stops on line one.
- **FAIL `README-009`** the README carries no unresolved editorial comments
  - 6 unresolved review comments are in the shipped README, including an empty `## Cassettes and Replays` section and `<what does this provide?>` left in the prose.
- **FAIL `README-010`** the README's empty sections
  - headings with nothing under them: ['## Cassettes and Replays']
- **FAIL `SCRIPT-002`** scripts/check_citations.py over the whole repository
  - check_citations exits 1: check_citations: 65 problem(s) — 1 blank-line, 64 symbol-drift. Every problem is in files this test checkpoint wrote today, not in the library's own documents: ['dev-docs/f
- **FAIL `TAX-006`** conformance.md §4's count of what the library enforces
  - docs/conformance.md §4 says five entries are enforced by construction and lists FT-09, FT-18, FT-19, FT-28 and FT-20. 6 taxonomy entries say they are enforced: ['FT-09', 'FT-28', 'FT-18', 'FT-19', 'FT
- **FAIL `CLI-020`** `questions --stage` help names all four stages
  - the --stage help reads 'shape, build or measure. Earlier stages are included' and omits `brainstorm`, which is a stage, is what a project with nothing produced is at, and is what docs/conformance.md §
- **FAIL `CLI-021`** the refusal on an unknown stage names the four
  - the refusal is "'bogus' is not a stage." and names no stage, so a coding agent that guessed wrong is not told what to pass. Every other refusal in the suite lists the values it accepts.
- **FAIL `README-011`** the README's `result.cost  # derived against the declared basis`
  - run verbatim (README-005b, with VLLMClient in place of the unusable Mistral key) the snippet declares no cost basis, so result.cost carries value=None and the reason 'no cost basis declared in the man

### `lead-verify-suspension-loss`

- **FAIL `L-5`** a resume refused for a bad answers= key leaves the run resumable
  - after a refused resume the corrected resume also failed: CallerFacingError: There is no suspended run in /tmp/claude-1000/-home-thilina-Projects-simple-agents/a7094dd8-3465-41e8-9d46-9e5a4f7e4836/scra

### `verify-flagged-contradictions`

- **FAIL `VERIFY-consult-version`** consult() derives a version from its source when version= is unset
  - consult() produced a tool whose version is None, while a decorated tool carries a derived one; its cassette key therefore carries a null version
- **FAIL `VERIFY-websearch-cache-spend`** a web_search answered from the cache is not charged the declared price
  - web_search takes no SpendMeter, so a cache hit cannot report spent=0 and the call is charged the full declared DeclaredCost(currency='USD', per_call=0.005, latency_ms=None, max_per_call=None)
- **FAIL `VERIFY-mermaid-suspend-before`** to_mermaid() draws a node declaring suspend_before
  - to_mermaid() output contains no marking for the node declaring suspend_before
- **FAIL `EVAL-F02`** a rollout that suspends raises RunSuspended rather than scoring as a failure
  - expected RunSuspended to reach the caller, got AssertionError
- **FAIL `EVAL-F02b`** a rollout that suspends raises RunSuspended rather than being scored a failure
  - the evaluation returned normally and scored the suspended rollout ?, so a consultation is counted as an agent failure rather than reaching the caller
- **FAIL `VERIFY-maxsteps-concurrent`** max_steps is exact under concurrency: calls never exceed the limit
  - max_steps=3 at concurrency=4 but 8 model calls were made


## Checks skipped, with the reason

- **`VLLM-12/14-live`** a chain of thought inside content warns once
  - the model did not open with <think>, so the warning path was not reached; the adapter's own condition is covered by the fixture check VLLM-14
- **`MC-116`** an AgentNode returns the model's own reasoning on the next turn
  - this server runs without --reasoning-parser, so no response carries a reasoning field to send back. messages_to_wire(reasoning_field='reasoning') is covered without a backend by MC-129; the live half 
- **`VLLM-07/09`** the adapter raises the server's tool refusal as it stands
  - this server runs with --enable-auto-tool-choice and --tool-call-parser, and testing the refusal needs a restart without them, which is not available on a shared server. The library-side half (no text-
- **`GEM-06`** FT-14 passes the pin and fails the alias
  - FT-14 over a manifest belongs to area I. The halves this area owns are recorded as GEM-05 (an alias is echoed back rather than resolved) and MC-21/22/23 (what each adapter reports as model_revision).
- **`GEM-19/20/MC-25/MC-43`** caching needs no opt-in, and the hit is recorded
  - the provider reported no cache hit on the repeat of a 4631-token prompt; caching is provider-side and this is not a library behaviour to assert against
- **`B-08g`** a live model reporting absence records the tagged object
  - this model answered with the string 'absence' rather than the tagged absence, so the read-back path is not exercised here
- **`README-005`** the README's first agent, run verbatim against Mistral
  - the Mistral account behind the repository's key answers 401 to a bare completion, so the README's own backend cannot be exercised. README-005b runs the same snippet with VLLMClient substituted.
