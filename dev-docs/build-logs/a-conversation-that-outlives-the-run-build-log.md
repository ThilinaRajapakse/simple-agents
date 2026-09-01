# A conversation that outlives the run — build log

`P3-39`, designed and built 2026-08-27. Seven decisions, four steps, six verification cycles.

## 1. Before any design

Four measurements, taken before any option was written down.

**A project carries a conversation across runs today, in twelve lines.** A JSONL file, a prompt
function that reads it, an append after the run.
[`_as_messages`](../../src/simple_agents/runtime/calls.py#L427) accepts a message list from any prompt
function. The probe's turn 2 put system, user, assistant and user on the wire and the trajectory
recorded all four. **So the item was never "make it possible"**: it is a shape a coding agent
reaches for, a record that says a run was turn 2, and an answer for what an evaluation does.

**Run directory depth was a load-bearing data field.** Twelve globs across six modules selected
by exact depth. Measured: a run one folder deeper was silently invisible to
[`Pipeline.shelved`](../../src/simple_agents/pipeline/core.py#L1130), so a project that tidied its runs
into folders lost its question inbox and its suspension inbox with nothing raised.

**A rollout did not record that it was a rollout.** On the frozen dogfood #5 copy a rollout's
manifest read `role: "agent"`, `live: false` and named no evaluation. What separated it from a
run made while building was that it sat two directories down.

**The scale.** 2,393 top-level runs, 276 rollouts, 2,669 from `runs(nested=True)` with nothing
telling them apart. `DF5-I08` is the same defect from the checks' side.

## 2. Design

[`design/conversations.md`](../design/conversations.md#L1)
carries the seven decisions and what decided each. **Three of the seven overturned the proposal**,
each on evidence rather than preference: a stored turn is the node's wire messages rather than a
said/answered pair; messages go on as they are produced rather than in one write at the end;
compaction is a real summariser rather than a read-side limit.

**Three settled positions were defeated in writing**, and the arguments are in the item record and
in [`simple-agents.md` §2.4](../simple-agents.md#L224): the clause placing a message store behind a
tool, the clause ruling out summarisation anywhere, and `docs/memory.md` §3's sentence that a task
depending on a sequence of sessions is a fixture.

## 3. Build

Four steps, in order, each landing before the next was started.

**Step 1, the run directory.** A run is filed by what it is: `runs/live/<date>/`, `runs/dev/<date>/`,
`runs/eval/<eval_id>/`, `runs/<role>/<date>/`. The real change is that **no reader counts slashes
any more**: every one walks the tree and reads the manifest. `EvaluationRef` on the envelope and in
the manifest is what a rollout says about itself. `find_run`, `manifest_paths`, `is_a_rollout`,
`evaluation_dir` and `rollouts_under` are the published readers. `RunEnvelope` refuses `role` in
`{live, dev, eval}`. **A project on the old flat layout needs no migration**, which falls out of
step 1 rather than being written: nothing depends on where a file sits.

**Step 2, the conversation.** [`conversation.py`](../../src/simple_agents/records/conversation.py#L1) holds
the store, the thread, the per-node view and the writer. The store is on the envelope and the thread
id is on `run()`. A node takes part by continuing the conversation, and the library appends what it
produces as it produces it. `compact_conversation` is a built-in that takes the summary as an
argument and makes no model call of its own.

**Step 3, the evaluation.** `Example.conversation` seeds what was already said;
`Example.turns` is a conversation the rollout runs through in order, one run per turn, scored on
the last. Each rollout gets its own store, the way each gets its own memory.

**Step 4, the record.** The manifest carries `conversation` with the thread, the turn, `carried_in`
and the node that read it. Manifest `0.34` to `0.36`.

## 4. Verification

Six cycles of read the docs, read the code, cross-verify, test the pieces, full suite, live.
**Cycles 1 to 4 found nine defects; cycles 5 and 6 found none.**

| Found by | What |
|---|---|
| Running the code | The compaction tool held a `ModelHandle`, which a `Deterministic` node refuses. Redesigned to take the summary as an argument, which is better: no hidden second model call |
| Running the code | `messages()` applied the compaction watermark as it read, so every message written before a compaction survived it |
| Running the code | The summary landed in the middle of the conversation rather than at the head |
| Cross-checking the doc | **Redaction was documented and never wired.** The store wrote raw model messages, and it outlives every run |
| Cross-checking the doc | `ctx.conversation` was `None` outside a conversation, so the documented splat crashed a pipeline serving both |
| Reading the code back | The message sequence was a read-modify-write, so two worker processes on one chat would assign duplicates and break the watermark. Removed |
| Executing the doc | §5's two-node pattern did not run: the schema needed `allow_unknown=False` |
| **Live** | **The summarising node enrolled itself**, because it read the conversation to build its prompt, so its own prompt and answer were appended to the conversation it was about to summarise. Enrolment is now continuing the conversation rather than looking at it |
| Reading the code back | `rescore` parsed `<example>-<index>` out of the directory name, which a multi-turn rollout broke. It reads the manifest now, which is step 1's lesson applied again |
| Reading the code back | `Pipeline.resume` never wired the conversation, and a resumed turn was left open forever. A resume now continues the turn it stopped in, on both node kinds |

**Live, against Gemini.** A four-turn chat where the model tracked constraints across turns; a real
compaction from 8 messages to 3 where the agent still knew all four constraints afterwards; a
three-turn evaluation whose last turn answered out of the second's; `rescore` reproducing the
number with no model calls; and a run that suspended mid-turn to ask the reader, resumed, closed
its own turn, and answered turn 2 out of what the consultation had said.

**3,582 tests pass.** `prose_check`, `shape_check`, `check_citations` and `check_docs` clean.

## 5. Doc consequences

`docs/conversation.md` is new and is the whole surface. `docs/evaluation.md` §13 is the evaluation
shapes. `docs/memory.md` §3's sentence is reversed. `docs/tools.md` §3.2 gains the `Conversation`
handle and §4's table gains the built-in. `docs/run-envelope.md` carries `evaluation` and
`conversation` at manifest `0.36`. `docs/index.md` and `README.md` carry the new document and the
new run layout. `CHANGELOG.md` records both format moves.

## 6. Left open

**A conversation is unbounded.** A run is bounded by its budget; forty turns is forty budgets.
`thread.turn_count` and `thread.run_ids()` are what a product reads to decide, and the library
refuses nothing. Decided at the sitting.

**Two turns of one conversation at once are not serialised across processes.** Appends need no
read, so nothing is lost or renumbered, and a line longer than the operating system's atomic write
can interleave. `docs/conversation.md` §9 states it; a product that needs the order holds its own
lock.

**`MemoryStore(scope=...)` fuses two lifetimes**, which this item's D2 settled the other way for
conversations. Recorded against `DF5-I18` for dogfood #5's sitting 4.

**`scripts/shape_baseline.json` was raised three times**, against `plan.md` §2.2's rule that it
only shrinks. What was decomposed first is what belonged elsewhere: `evaluation_dir` and
`rollouts_under` out of `runner.py` and `ThreadWriter` out of `nodes.py`, about 120 lines into the
modules that own those subjects. What was recorded rather than decomposed is 1 to 7 lines each on
`Manifest`, `Manifest.to_json`, `Manifest.restore`, `Pipeline`, `EvalSuite`, `EvalSuite.record`,
`EvalSuite._rollout` and their modules, all of which were already over a threshold and are on the
pre-release refactor's worklist. `to_json` is a flat dict literal that splitting fragments, and
`EvalSuite` is a session's work. **Thilina's call, 2026-08-27**, on being shown the numbers:
decompose where it is not a big job, record where it is.
