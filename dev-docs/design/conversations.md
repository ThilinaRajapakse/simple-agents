# A conversation that outlives the run

`P3-39`'s design of record, built 2026-08-27. The build is
[`build-logs/a-conversation-that-outlives-the-run-build-log.md`](../build-logs/a-conversation-that-outlives-the-run-build-log.md#L1).

## Where it came from

Dogfood #5's sitting 3, 2026-08-26, from the same survey that produced
[`an-mcp-server.md`](../build-logs/an-mcp-server-build-log.md#L1). Thilina scheduled it in two words: *"We need this."* It
is not a dogfood finding and has no candidate in
[`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L1).

## What the problem is

**Nothing carries a conversation from one run to the next.** An `AgentNode` keeps one inside a
single node execution ([`docs/context.md`](../../docs/context.md#L17), the context table);
`MemoryStore` keeps facts about a person across runs
([`docs/memory.md`](../../docs/memory.md#L1)). A second turn of a chat starts from nothing unless
the project stores and re-feeds the history itself.

**The library invites this and does not carry it.** `used_through`
([`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L103), `used_through`) offers
a chat as one of the surfaces a builder may name, and
[`docs/product.md`](../../docs/product.md#L1) classifies the interactions a surface offers.

**What the comparison ships.** The OpenAI Agents SDK's `Session` is passed to each run and carries
prior turns, with compaction when the history outgrows the window.

## What the sitting measured

Four measurements, all taken 2026-08-27 before any decision was made.

**1. A project carries a conversation across runs today, in twelve lines.** A JSONL file, a prompt
function that reads it and returns a message list, an append after the run.
[`_as_messages`](../../src/simple_agents/runtime/calls.py#L427) accepts a message list from any prompt
function and [`AgentNode`](../../src/simple_agents/nodes/agent.py#L138) seeds its conversation from it.
The probe's turn 2 put system, user, assistant and user on the wire, and the trajectory recorded
all four. **So the item is not "make it possible"**: it is a shape a coding agent reaches for, a
record that says a run was turn 2, and an answer for what an evaluation does with five turns.

**2. Run directory depth is a load-bearing data field.** Twelve globs across six modules select by
exact depth. [`Pipeline.shelved`](../../src/simple_agents/pipeline/core.py#L1130) and
[`Pipeline.suspensions`](../../src/simple_agents/pipeline/core.py#L950) read `*/<file>` with no
`nested=` escape. Measured: a run one folder deeper is **silently invisible** to
`Pipeline.shelved`, so a project that tidies its runs into folders loses its question inbox and
its suspension inbox with no error.

**3. A rollout does not record that it is a rollout.** Read off the frozen dogfood #5 copy, a
rollout's manifest says `run_id: judge-2024-09-23-0`, `role: "agent"`, `live: false`, and names no
evaluation, example or k. It is indistinguishable from a dev run except by sitting two directories
down instead of one.

**4. The scale that makes it bite.** On the same copy: 2,393 top-level runs, 276 rollouts, 2,669
returned by `runs(nested=True)` with nothing separating them. 2,342 of the top-level runs declare
`role="agent", live=False`. The only structure is what the project invented in its own run names,
which covered 94 of 2,313. `DF5-I08` is the same defect from the checks' side: nineteen distinct
pipelines ran under `role=agent` and five checks certified a two-node summariser.

## What has to be decided

**All seven are settled, 2026-08-27**, and each is recorded here with what decided it. Where a
recommendation was overturned the reason is recorded, because each one was overturned on evidence
rather than on preference.

**D1. A stored turn is the node's wire messages, with a compact read beside it.** Proposed as
turns alone, on a provider-expiry argument. **Overturned by Thilina**: the expectation that no
context is lost outweighs it, and the expiry problem is smaller than the proposal claimed. Three
readings confirm that. [`_assistant_turn`](../../src/simple_agents/runtime/calls.py#L398) builds messages
in *the library's own shape* and each adapter translates at the boundary;
[`_refuse_provider_state`](../../src/simple_agents/adapters/_openai_wire.py#L245) refuses a tool
call carrying provider state a dialect cannot express, so a Gemini thread read back through
Mistral fails loudly rather than corrupting; and the suspension file already writes this exact
message list to disk and reads it back. **His framing also collapsed the objection to storing
both**: it is one stored format with two reads, not two formats. So `ctx.conversation` gives every
message, `.compact()` gives said/answered pairs, `.without_provider_state()` survives a backend
swap.

**D2. The store is on the envelope; the thread id is on `run()`.** Taken fresh on Thilina's
instruction to ignore what was written down. `ConversationStore("conversations/")` is project
configuration set once; `pipeline.run(..., thread="chat-8817")` is the per-request identity,
beside `run_id`, which is already exactly that. Copying `MemoryStore(directory, scope=...)` would
have fused two lifetimes and forced an envelope rebuild per request.

**The node reads it explicitly and the library writes it structurally.** The prompt function
splats `*ctx.conversation` where it wants the history. Considered and rejected: the library
prepending automatically, because a system message then either duplicates or needs a dedupe rule,
and a system prompt that has to change has no clean way in. Explicit read costs one splat and has
neither problem; `carried_in` (D7) is what catches a builder who forgets it.

**D3. Messages are appended as they are produced, not batched at the end of the run.** Proposed as
end-of-run. **Overturned by Thilina's question, "Why append at the end of the run instead of node
by node?"** Four reasons, and the proposal had none against them. The trajectory streams and the
manifest is written whether or not the run completes, so a batched conversation would be the only
artifact that is not. A hard kill loses the whole turn. A run suspended for a consultation may
resume days later, and the thread stays empty across the gap. And more than one node may talk, so
"the node's messages at the end" is ambiguous where "each message as it is produced" is not.
Cost: about 25 small appends for a 12-turn `AgentNode`, against a trajectory that already writes a
record per model call. Adds a turn boundary marker so a reader can say "turn 4".

**D4. Compaction is a built-in tool, not a store-side rule.** Proposed as a read-side limit with no
summarisation anywhere. **Thilina asked for proper compaction, as a tool so it is recorded when it
runs**, which dissolves the objection: the objection was that a model call inside a store write is
unrecorded, unbudgeted, unpriced and outside any node, and a tool call is none of those. It
re-runs on replay with its inner model call served from the cassette, which is
[`docs/memory.md` §5](../../docs/memory.md#L1)'s rule for a tool that writes state. A compaction is
itself a turn record, so the thread says what was replaced, by which model, on which run. The
documented caller is a `Deterministic` node at the head of the pipeline. **No ceiling**:
`thread.turns` and `thread.spend()` report, and the product decides.

**D5. An evaluation may resample a whole conversation.** Proposed as a fixture now with the real
thing deferred. **Thilina folded it in**: deferring it is cognitive overhead and delay. This
reverses a shipped sentence in [`docs/memory.md` §3](../../docs/memory.md#L191). Scored on the last
turn by default, which is what `answer=` already reads; ended by the script running out or by
`max_turns`. [`SimulatedEndUser`](../../src/simple_agents/evaluation/stand_in.py#L102) already
plays a person, is seeded, is stored in the cassette, keeps what that person said earlier in front
of it, and spends outside the agent's budget: what it gains is taking a turn rather than only
answering one.

**D6. The run directory says what a run is, and no reader counts slashes.** Scheduled as its own
item; **Thilina made it step one of this one** and asked for the layout to be worked out properly.
Two halves, and the first is the real one. Every run records what it is in its manifest, so a
rollout names its evaluation, its example and its k; then every reader globs `**/manifest.json`
and reads the run rather than its depth. **That removes the migration problem**: a project on
today's flat layout keeps working, because nothing depends on where the file sits. The layout is
then free:

```
runs/
  live/2026-08-27/<run_id>/       a person used it
  dev/2026-08-27/<run_id>/        made while building
  eval/<eval_id>/<example>-<k>/   an evaluation and its rollouts
  <role>/2026-08-27/<run_id>/     labelling, judge, variant
```

Day shard, on Thilina's call. Three reserved names and `RunEnvelope` refuses `role` in
`{live, dev, eval}`, which avoids inventing a category noun for the fourth.

**D7. The manifest records `thread`, `turn` and `carried_in`.** Proposed with the thread id
digested, on the memory precedent, and **agreed in that form before Thilina asked the question
that undid it**: *"doesn't that beg the question of whether we should be using it as the thread
id?"* It does. `MemoryStore`'s scope is a person by design; a conversation is not a person, and a
person has many. So a thread id names a conversation the project minted, and digesting an
identifier that is definitionally not a person's buys nothing while costing the ability to read a
manifest and see which conversation it was. **Recorded in the clear**, as `run_id` and a
consultation's `about` already are, with one sentence where the builder sets it saying what
happens if they choose to put a person's identifier there. The store's filenames are still
digested, for filesystem safety rather than privacy. **The thread is not a directory**: a
conversation spans days and would fight the day shard, and it would restore the depth-as-data
field D6 removes. Grouping is `runs("runs/", thread=...)`.

`carried_in` is how many earlier messages the agent was shown. It exists to catch the failure
where the thread fills up correctly and nobody wired the read: every run says turn 4 and shows
zero.

## What it defeats

Three, each argued rather than worked around.

- [`simple-agents.md` §2.4](../simple-agents.md#L224)'s *"a message store is a tool rather than a
  context builder"*. A tool is keyed in the cassette by its arguments, so a tool reading a thread
  that moved on replays whichever content was recorded first, silently. A prompt function's output
  **is** the keyed material, so the same drift is a `CassetteMiss`. That is §2.4's own reasoning
  about context builders, one level out, and it points the other way from the clause.
- The same paragraph's *"Nothing truncates. No policy, no summarisation, no sliding window, no
  tokenizer."* The context-builder half stands. Summarisation moves to a recorded tool, where the
  objections do not reach.
- [`docs/memory.md` §3](../../docs/memory.md#L191)'s *"It does not measure a sequence of
  sessions"*, reversed by D5.

## How it was built

Four steps, in order. All before `P3-31`, since each moves a format a project holds.

| | | Why here |
|---|---|---|
| 1 | Runs say what they are; readers stop counting slashes; the layout above | Fixes a live defect, and steps 2 to 4 write onto it |
| 2 | The conversation store: D1, D2, D3, D4 | The item as scheduled |
| 3 | Evaluation over conversations: D5 | Needs step 1 for where a conversation's rollouts land |
| 4 | The record: D7 | One more manifest field, on a settled layout |

## What it waits on

Nothing blocks it. **Dogfood #5's sitting 4 waits on it**, because `DF5-I18` and this item are
both about what the memory store is for, and this item's D2 and D7 are the evidence that sitting
reads. The `DF5-I18` row carries both notes.
