# Build log — What a store is for, and the two lifetimes on the memory store

`plan.md` §1 `P3-44`. Built 2026-08-27. Carries `DF5-I18`, `DF5-I20` and `DF5-I21`.

## 1. Before any design

**The naming was checked against the alternatives before anything was written.** The sitting's
`memory_scope=` was mine at the sitting rather than measured, so four candidates were weighed:
`scope=` (rejected at the sitting, and rightly: a bare one on `run()` reads as scoping the run or
the tools), `end_user=` (taken, and by something else:
[`RunEnvelope.with_end_user`](../../src/simple_agents/envelope.py#L940) is the consultation
channel), `memory=` (taken by the envelope's store), and `remembers_for=` (a verb where every
other keyword is a noun, connecting to none of `scope`, `scope_digest` or
[`docs/shipping.md` §5](../../docs/shipping.md#L104)'s "a memory store is declared once and read
under a scope"). `memory_scope=` stands.

**What actually reaches the store, read out of the code.** `MemoryStore` is reached from four
places: [`RunContext.memory`](../../src/simple_agents/context.py#L376),
[`_memory_handle`](../../src/simple_agents/runtime/handles.py#L200),
[`_refuse_unreachable_memory`](../../src/simple_agents/pipeline/preflight.py#L403) and
[`_scoped_for_rollout`](../../src/simple_agents/evaluation/runner.py#L2556)'s `rebound`. Small
blast radius, and no conformance check, no report and no view page reads the manifest's `memory`
block.

**Three ways a run starts, and the item covered one.** `Pipeline.run`, `Pipeline.resume` and
[`Pipeline.answer_shelved`](../../src/simple_agents/pipeline/core.py#L968) each build a `RunContext`
carrying `memory=envelope.memory`. The item settled `run()` and said nothing about the other two.
`resume` is the one that forks, since the manifest records the scope as a digest and cannot hand
it back.

## 2. Design

**Settled at dogfood #5's sitting 4**, and the item record carried it:

> The memory store holds what the agent learns and writes. What the end user tells the product is
> the project's data model, and it reaches the run as inputs.

**The shape, decided in the build on the conversation precedent.** `ConversationStore` holds the
directory and `.thread(id)` produces a `Thread`; `MemoryStore` holds the directory and
`.scoped(scope)` produces a `ScopedMemory`. **Two classes rather than one**: leaving the read and
write methods on `MemoryStore` and adding a `scoped()` beside them would leave one object in two
states, which is the fusion this item exists to remove wearing a different hat.

**`resume` takes the scope again, and refuses another end user's. Thilina's call, 2026-08-27**,
on the two options put to him. Rejected: recording the scope in `suspension.json` so a resume
needs no argument. It would have matched `P3-39`'s "a resume continues the turn it stopped in",
and it costs the promise `docs/memory.md` makes that the scope is written down nowhere. A
suspended run waits hours or days with that file on disk, and no redaction rule matches an
identifier of that shape. What the argument buys instead is a check the other option cannot
offer: the manifest holds `scope_digest`, so a scope whose digest differs from the run's is
refused rather than silently writing one person's facts into another's memory.

**`answer_shelved` takes it with no fork**, since the caller is filing a person's answer and
knows whose it is. The item names this case as the store's: a `remember` inside the pipeline that
call triggers is the agent writing down what it learned from a reply.

**The manifest keeps recording the scope digest in the same place**, which is what the item left
to the build. Same three fields, same digest of the same string, sourced from the run's scope
rather than the store's. No format moves.

**Every rollout names one scope, `ROLLOUT_SCOPE`**, on `ROLLOUT_THREAD`'s precedent: each rollout
has a store to itself, so one name serves them all.

## 3. Build

**The signature.** `MemoryStore(directory)`, `pipeline.run(..., memory_scope=)`,
`pipeline.resume(..., memory_scope=)`, `Pipeline.answer_shelved(..., memory_scope=)`.
[`ScopedMemory`](../../src/simple_agents/memory.py#L181) carries what `MemoryStore` carried:
`get`, `entries`, `keys`, `put`, `write`, `forget`, `scope_digest`, `root`, `to_manifest`.
`scope_digest_of` is the one implementation of the digest, and `refuse_unreachable` and
`refuse_another_scope` live in `memory.py` rather than in `Pipeline`.

**Two ways to be unreachable, and they are separate messages.** No store on the envelope names
the store to declare and the argument to pass; a store with no scope names the argument alone.
Both fire before the run directory exists.

**What the build found that the design did not know.**
[`Manifest.restore`](../../src/simple_agents/records/manifest.py#L463) **drops three fields the run
recorded**, found when the digest check read `manifest.memory` on a resume and got `None`.
Measured rather than reasoned: a run making one model call, suspending and resuming leaves a
manifest whose `schemas` map is empty while its own trajectory record names a block by digest, so
**a shipped artifact carried a dangling reference `docs/trajectory-format.md` §4.1.5 promises
resolves**. `mcp` goes the same way, and nothing recomputes it on a resume, so a project whose
agent uses MCP tools and stops for a person loses which server it read and the drift FT-43 is
about. `memory` was masked, because `_close_manifest` rewrote it from the envelope at the end.
All three are read back now, and `restore`'s docstring says why the list has to stay complete.
This is `P3-39`'s `role` defect for the third time in the same function.

**Surfaces touched.** `memory.py`, `pipeline.py`, `manifest.py`, `context.py`, `nodes.py`,
`envelope.py`, `builtins/memory.py`, `evaluation/runner.py`, `__init__.py`. **3,591 tests pass**,
nine of them new. No format moves.

**`scripts/shape_baseline.json` was raised eleven times, by one to thirteen lines each.** What
was decomposed first is what belonged elsewhere: the two refusals, about 45 lines, out of
`Pipeline` and into `memory.py`, and `_scoped_memory` replacing the same four-line conditional in
two places. What is recorded is a keyword threading through four call sites: `pipeline.py`
+13 lines, `Pipeline` +6, `resume` 80 to 83, `_start_run` 56 to 58, `_new_manifest` 56 to 57,
`answer_shelved` newly over at 52, and one line each on `context.py`, `RunContext`, `nodes.py`,
`runner.py` and `EvalSuite`. Thilina's standing call of 2026-08-27 at `P3-39`: decompose where it
is not a big job, record where it is.

**Three docstrings were at the 20-line ceiling and each new argument evicts prose.** `run`,
`resume` and `answer_shelved` all sat exactly at it, so documenting one keyword meant rewriting
four paragraphs shorter. Nothing was lost; it is worth noticing that the three entry points a
builder reads first cannot gain a sentence without losing one.

## 4. Verification

**Live, against Gemini** (`gemini-3.1-flash-lite`), three probes.

**One envelope, two end users.** An `AgentNode` told a fact about the reader stored it under
`preferred_book_length` for `user-ada` ("only reads books under 300 pages") and for `user-bo`
("epics that are at least 900 pages long"), through one `RunEnvelope` built once. Same key,
different memories, different digests (`4aecfa1562eb`, `97dbab41ce25`), and `user-ada` appears
nowhere in either manifest. A later run under `user-ada` read it back.

**A run that stopped, and the three ways a resume goes.** A run suspended before its writing node
under `user-ada`. `memory_scope="user-bo"` was refused naming both digests and neither scope; no
scope at all was refused naming `Pipeline.resume(..., memory_scope=)`; and the correct scope
completed the run, wrote `taste_summary` into `user-ada` alone, and **kept the `schemas` map its
own trajectory references**, which is §3's defect confirmed fixed on a live run.

**A shelved question answered.** A background run's channel returned `Shelved`,
`Pipeline.shelved` listed it, and `Pipeline.answer_shelved(..., memory_scope="user-ada")` ran a
pipeline that wrote `format_preference` into that person's memory and nobody else's.

**An evaluation, two examples, seeded.** Both rollouts read their own seeded
`preferred_length` and answered correctly. Every rollout's manifest carried the digest of
`rollout`, and the project's declared store directory was never created.

**3,591 tests pass.** `prose_check`, `shape_check`, `check_docs` and `check_citations` clean.

**Eight reverification cycles were run over `P3-44` to `P3-47` together**, each one reading the
docs, reading the code, cross-verifying the two, testing the pieces, the full suite and a live
run. **Cycles 1 to 7 each found something and cycle 8 found nothing.** What they found about this
item: `docs/product.md` claimed the library reads "no configuration of its own", which is false
since `GeminiClient` and `MistralClient` read their keys from the process environment; the
opening sentence of `docs/memory.md` parsed two ways; a `plan.md` §2.2 destination in §6 below
resolved to nothing; and "constructed in six places" was eight when it was written. The resume
claim's release on a refused scope was read out of the code and is asserted by a test now.
Cycle 8 mutated nine behaviours these four items introduced and every one was caught by a test.

## 5. Doc consequences

`docs/memory.md`'s opening states what a store is for and what the test is, its §1 is the store
and the scope apart, and a new §1.1 is the resumed run. `docs/product.md` §3's scoping sentence
is replaced: it read as *per-person state goes in the memory store* and is what sent two projects
to name the store in their design and build their own. §3 gains the credentials sentence
(`DF5-I21`) and §4.3 states that a shelved answer reaches the next run through
`Pipeline.answer_shelved` and its records. `docs/shipping.md` §5 and `docs/tools.md` §3.2's table
follow the signature. `docs/run-envelope.md`'s `memory` row says where the digest comes from.

`docs/tools.md` §3.3 says what a run loses when a node body does its own I/O and
`docs/failure-taxonomy.md` §10 carries it as uncheckable (`DF5-I20`).

`CHANGELOG.md` records the signature and what a project on disk has to do. **It also gains the
manifest `0.35` to `0.36` entry that `P3-39` never wrote**, and its header now counts seven
versioned artifacts rather than six, the conversation file having been left out
(`DF5-X14`).

**`check_citations` was not clean at `923cdf8`** and was reported here as clean at the start of
this build, which was wrong. It had 12 problems, 11 symbol-drift and one unresolvable. `--fix`
took those and the drift this build caused; the five blank-line anchors left over are corrected
by hand, one of which pointed a `pipeline.md` citation at `pipeline.py`.

## 6. Left open

**`thread=` had the fault `scope=` was rejected for, and it moved.** A bare `thread=` on
`run()` does not say thread of what, and `threading` is a live meaning in Python: `run()`'s own
docstring documents `stop_when` with `paused = threading.Event()` two paragraphs below it, with
`concurrency=8` four lines above. **Taken 2026-08-28 on Thilina's call**, after the surface was
measured: the identifier moves to `conversation_id` and the classes keep their names, since
`Conversation` the handle and `Thread` the object on disk are the shape `Memory` and
`ScopedMemory` already have. `Pipeline.run(conversation_id=)`, `ConversationStore.threads()` to
`conversation_ids()`, `ROLLOUT_THREAD` to `ROLLOUT_CONVERSATION`, manifest `0.36` to `0.37` and
conversation `0.1` to `0.2`. **`Pipeline.resume` reads both manifest keys**, since a run that
stopped mid-conversation would otherwise finish outside it with nothing reporting that.

**A worker sweeping `Pipeline.suspensions(run_dir)` holds a run id and no person.** Under the
decision above it maps run id to person itself, which it already does to deliver the result. If a
project appears that cannot, that is the evidence for reopening the suspension-state option.
Nothing queued.
