---
name: simple-agents
description: The staged procedure for building an agent with Simple Agents. Use it from the first message of a build, and at every gate. Covers what to settle with the builder before writing code, the project layout the checks read, and the six gates that run `simple-agents check`.
---

# The procedure

Simple Agents is built in six stages, `brainstorm`, `research`, `shape`, `build`, `measure`
and `ship`. Each ends at a gate, which is the checks `simple-agents check` runs at that point. The project records
the stage it is at in `brief.toml`.

**A project declares a tier in `brief.toml`, and the tier decides which of the six stages that
project has.** `how_far` is the answer that settles it.

| Tier | What it claims | Stages |
|---|---|---|
| `prototype` | no number about how well the agent works | all but `measure` |
| `evaluated` | a measured number, with an interval | all six |
| `trained` | the same, and training on its own runs | all six |

A tier's stages are the only ones whose questions are asked and whose checks run, and each gate
includes the stages before it. `ship` is a stage every tier has, so a project at any tier can go
live (`docs/conformance.md` §1).

`simple-agents init`, run once in the project root, registers this file as a skill and writes
`AGENTS.md`. `docs/index.md` is the reference documents and when to open each. Every
`docs/*.md` name in this file is a file installed with the package:
`python -c "import simple_agents; print(simple_agents.docs_path())"` prints the directory
holding them.

---

## The Layout

```
idea.md                 what this is, who it is for, and where it is going
research.md             the parts, and what was found against each
design.md               how it is built, and what the builder said about it
brief.toml              what the project claims, and what the builder was asked
comments.toml           the builder's comments (docs/view.md)
agent.py                the pipeline
view.html               the page every gate rewrites
evals/examples.jsonl    the labeled example set
evals/labels.jsonl      what a labelling pass or a review decided
evals/results/          one file per evaluation
runs/                   one directory per run, written by the run envelope
```

`idea.md`, `research.md`, `design.md`, `brief.toml`, `runs/` and `evals/results/` are what
`simple-agents check` looks at. A run written somewhere else is reported as a run that does not
exist.

Keep a `BUILD-LOG.md` alongside them, recording each exchange with the builder as it happens.

**A project writes more than this, and the rest has three homes.** Code the pipeline imports
sits beside `agent.py`, anything run once goes in `scripts/`, and anything the project reads
goes in `data/`. A genre this does not name takes a directory of its own. Nothing checks it, and
a project that puts every file at the root is unreadable later.

---

## What to settle first, and what to keep doing

**Ask `how_far` and `involvement` first.** The first says which stage this project stops at and,
separately, which tier it claims; the second, how much of what follows the builder is shown and
when. Both govern every exchange after them.

**How to ask a question.**

- Involve something of the builder's own: one of their inputs, one of their rows, one
  run's output, written into the question.
- Look up any number the question turns on before asking, and say where the number came from.
- Name the options, and say which one is recommended and why.
- Explain every term the builder has not used themselves, the project's own code names included.
- One question per exchange, through the session's question mechanism where it has one. A
  question left in prose beside another that got answered goes unanswered, and silence is
  recorded as nothing rather than as agreement.

`ask` is the question and `scaffold` is what makes it answerable. Use the `scaffold` to formulate a clear, answerable question.

**Record what the entries were read against.** `confirmed_against` holds
`pipeline.behaviour_fingerprint(model=client)` from when the pipeline answers were last read
against the code; `simple-agents check` names the ones due when the two differ, and FT-38 fails
on it from stage `ship`. Those entries describe the pipeline rather than what the builder wants,
so each is agreement to something the code may no longer do.

**Then, at every stage, record what was decided without asking.**

```
simple-agents questions --decisions
```

Six kinds. Each entry names what was chosen, what else was weighed and why:

```toml
[decisions.source_documents]
kind = "dependency"
status = "agreed"
recorded_at = "2026-08-27T09:14:02Z"
chose = "the export the builder already has"
considered = ["scraping the internal wiki", "an API the vendor charges for"]
produces = ["load_export", "read_row"]
because = "the export is complete and needs no credential"
```

**Present each to the builder with a recommendation before writing the code that depends on it**,
then record `agreed`, or `changed` with what they wanted instead. A decision that is irrelevant to this project  is written as `not_applicable`. Every gate refuses while one is `proposed` (FT-30).

**`produces` names what the decision became**, on a `dependency`, `shape`, `constant` or
`prompt_rule`. `check` fails from `ship` on a name no run recorded, and lists what the runs
hold that no decision names (`docs/conformance.md` §2.2).

**Serve the view, and read what comes back.** `simple-agents view --serve` is the live
page (`docs/view.md`): the builder comments on any element, answers open questions and
amends recorded answers in place, each landing as a thread in `comments.toml`. Read them
with `simple-agents comments` before each session, do what each asks, reply in the thread,
and record an `answer` or `amendment` into the brief before addressing it (FT-39).

**And at every stage, ask `anything_else`.** After that stage's own questions and before the
gate. Every other question is the library's; this one is the builder's, and what comes back is
what nothing asked about. Add it under the stage it was asked at, keep what the earlier stages
recorded, and write `asked_at` naming the stage. *Nothing* is an answer, and the gate refuses
while `asked_at` names an earlier stage than the project is at (FT-24).

---

## Stage 1: `brainstorm`

Find out what the builder wants, before deciding anything about how.

```
simple-agents questions --stage brainstorm
```

Fifteen questions, ten required.

**Start with `what_it_does`.** An answer naming what the agent receives, what it produces and
who receives it is a developed idea, and the rest of the stage records it. An answer missing any
of the three is where the optional questions apply. Then `used_through`, the product: what
the end user opens, and what makes a run happen (`docs/product.md`). Then `how_far` and
`involvement`.

**Answer `one_real_input` by obtaining one and reading it**, before any node is designed.

Then write `idea.md`, the project's own account of itself, in five sections: what this is, who
it is for, what it works on, where this is going and where it is not, and what is still open.
Record `understanding_confirmed_at = "brainstorm"`, and set it to the new stage at each later
gate after reading the file again (FT-29).

**Gate.** Ask `anything_else` and record it. `simple-agents check` passes every check this
stage runs. Set `stage = "research"` and go to stage 2.

---

## Stage 2: `research`

Find out what is already known about the problem, before deciding anything about how.

```
simple-agents questions --stage research
```

Twenty questions, fifteen required: this stage's five, and every one before them.

**Break the system into parts first.** `parts` is the decomposition, answered before anything is
looked up. A part is a problem the system has to solve, so it is neither the pipeline nor a node
list. The other four questions are asked against each part in turn.

**Then go and look, part by part.** `approaches` is what already does it and how it is built when
it is built; `available_material` is what it could draw on; `what_goes_wrong` is the failure modes
people report. Fetch a real response from a source before recording it as reachable. Answer
`what_this_turns_on` last, from what was found.

Then write `research.md` in four sections: the parts, and what each has to do; what was found
against each part; what this turns on, having looked; and what the builder said about it. **The
second is a table, one row per candidate, whose `Outcome` column is never blank**: `adopted`,
`rejected, because ...` or `not investigated, because ...` (FT-36). Put the survey to the builder,
record their words verbatim under the fourth, and record `research_confirmed_at = "research"`, set
at each later gate after re-reading.

A `dependency` decision at any later stage names the research it rests on:
`from = ["approaches", "available_material"]`.

**Gate.** Ask `anything_else` and record it. `simple-agents check` passes every check this
stage runs. Set `stage = "shape"` and go to stage 3.

---

## Stage 3: `shape`

Settle what the agent is for before writing a node.

```
simple-agents questions --stage shape
```

Put each to the builder in the terms of their own work, follow the scaffold where it asks for
more than one exchange, and never answer one for them (FT-24). Record it
under its `brief.toml` key as `answered`, `deferred` naming the stage it moves to, or
`unanswered`, which the gate refuses.

**An answer naming a figure goes stale when the code needs a different one.** The new figure
goes to the builder. **`answer_form` decides what an example's `expected` holds and
`presentation` the output schema**, and they are different answers (`docs/evaluation.md` §1.6).

**An evaluation puts no question to a person.** A rollout is refused over a channel that
reaches one, so its consultations are answered by a stand-in or by `Unavailable`
(`docs/evaluation.md` §5.4). Stage 5 is the only repeated execution this procedure asks for,
and every run in it is unattended. Settle `consultation` against a run somebody is in, and
exercise it at stage 4.

Write the pipeline as a skeleton as soon as the steps have names, with
`NotBuilt("what it will do")` standing in for missing code, so the design conversation
happens over the view's drawing (`docs/view.md` §3).

Then write `design.md` in four sections: what it does step by step, what it holds on to
between runs, the product, and what the builder said about it. **The product section
classifies every interaction the end user can take: starts a run, answers a waiting run,
reads the artifact, or records a judgement** (`docs/product.md`), and, where an artifact
outlives the run, what writes, refreshes and triggers it. **Put the first three to the
builder before writing code, record their words verbatim under the fourth, and iterate until
they agree** (FT-34). Record `design_confirmed_at = "shape"` and `shape_confirmed`
(`docs/conformance.md` §3), re-set at each later gate. A
`shape` or `presentation` decision names the answers it rests on: `from = ["finished_version"]`.

Declare the tier `how_far` settled. Declaring a lower one is the only way to turn a gate off
(`docs/conformance.md` §1).

**Gate.** Ask `anything_else` and record it. Every check this stage runs passes; those
reading a run cannot yet. Set
`stage = "build"` in `brief.toml` and continue to stage 4.

---

## Stage 4: `build`

**Agree how it will be built before writing it.** Stage 2 agreed what the agent does; this,
how. Take the nodes, which decide for themselves, which model each uses, and every number and
prompt rule changing what the agent does, to the builder as `shape`, `constant` and
`prompt_rule` decisions. A rule invented while testing reads as the builder's own once it is
in a file, and `check` lists the numbers no decision names.

**Read `design.md` and say where the build departs.** A node that cannot do what the
design promised is a change to it: tell the builder and re-record `design_confirmed_at` (FT-34).

Then write the pipeline and the product: the surface `used_through` names, each interaction
doing what the design's product section says (`docs/product.md`).

```
simple-agents questions --stage build
```

Read `docs/pipeline.md` first. The node kind follows from `agency_boundary`: only a step
that decides what happens next from what the last one returned is an `AgentNode` (FT-11). One
that calls a tool but chooses nothing is `Deterministic(fn, tools=[...])`.
Read `docs/tools.md` §4 before writing a tool: fourteen tools come with it, §7 an MCP
server's. `docs/model-clients.md` covers backends, `docs/retrieval.md` search by meaning.
Before designing any capability, check the feature index at the end of this file: what it
names, the library ships.

**A pass the project runs for itself declares its own role.** A corpus build, labelling pass,
judge or one-off probe writes into `runs/` beside the agent's runs, and every check that
reads a run reads the newest whose role is `agent`. `RunEnvelope(role="corpus")` keeps it out
(`docs/run-envelope.md` §2.1). The report's `reading` line names the pipeline the checks read.

**Import the module that builds the pipeline before the gate**, which fires the library's
construction refusals (FT-09, FT-18), each naming its fix. Answer `budget` from what one
example consumed.

**Run against `FakeModelClient` before paying for a backend** (`docs/pipeline.md` §6), then once
on real input inside the envelope. Every prompt and response is recorded, and `keep_payloads`
is what the builder says no to that with.

**Then run the consultation for real, once.** Register the channel the builder answers
through and declare who that is, `consult(ask, answered_by="builder")`, and make one run
reach it. A blocking channel such as `ask_on_stdin` prints the question and waits, so the
run never stops and one exercises the whole path.

**Where the design has the run stop and wait, continue it too.** A channel that raises
`Suspend` ends the run with its state on disk, and `Pipeline.resume` picks it up
(`docs/pipeline.md` §1.8). Read what it waits for, take the builder's answer, pass it in:

```python
from simple_agents import RunSuspended

try:
    result = pipeline.run(inputs, envelope=env, model=client)
except RunSuspended as stopped:
    answer = ask_the_builder(stopped.waiting_for, stopped.options)
    result = pipeline.resume(stopped.run_id, envelope=env, model=client, answer=answer)
```

The coding agent is that `ask_the_builder` while the project is built: it carries the answer
in, and the builder is who gave it. Building the stopping half alone leaves a run on disk that
nothing continues, and an answer that reaches nothing. FT-41 reads that.

**Gate.**

```
python -c "import agent; agent.build_pipeline()"     # or however the project builds it
simple-agents check
```

Ask `anything_else` and record it. Every check this tier runs before `ship` passes. Set
`stage = "measure"` and continue to stage 5, or go to stage 6 at a tier with no `measure`.

**A green suite here says only that the run was recorded.**

---

## Stage 5: `measure`

A project claiming tier `evaluated` reports a number, and this stage is what produces it.

```
simple-agents questions --stage measure
```

`docs/evaluation.md` covers it. Four things the library will not decide, each going to the
builder as a `measurement` decision: what counts as a correct answer, where the split falls
(FT-02), how similar is too similar (FT-03), and how many rollouts (FT-05). Ask what an agent
that did nothing would score, and choose a measure that separates the agent from that baseline. Include examples
whose correct answer is absence, and where the answer never is, declare that on the node
producing it with `allow_unknown=False` rather than inventing them (FT-04).

**Assign whole sources to a split**: two questions from one document go on one side (FT-03).

**An evaluation records its rollouts**: `suite.rescore` re-scores runs already paid for,
`resume_from=` finishes one, `on_rollout=` watches (`docs/evaluation.md` §6).

**Report a figure per step as well as end to end** (FT-08): a labelled step (`node_matches`), a
figure declared for one (`node_metrics`), or the step evaluated on its own. **Evaluate a step on
its own where the pipeline scores badly and every step looks fine**: per-node accuracy scores
each on the inputs it got, which is the thing under suspicion. `pipeline.slice(start=...)` is the
last step as a pipeline, then the last two (`docs/evaluation.md` §5.6). `simple-agents check`
reports a project whose every figure is end to end.

**Read what the runs spent and what they produced**, with `simple-agents report runs/` and
`print(results.report())`. A node can spend its whole allowance and return nothing, which no
rate reports; the gate fails one that never called a tool (FT-35). **The gate reads less than
the report**: it covers the runs one pipeline made, and its pass line says what that left out.

**Gate.** Ask `anything_else` and record it. `simple-agents check` reports every check this
tier runs passing, and exits 0. Set `stage = "ship"` if anyone else is going to use it, and continue to stage 6.

---

## Stage 6: `ship`

Somebody other than the builder is about to use this. `docs/shipping.md` covers it.

```
simple-agents questions --stage ship --tier <the project's>
```

**Mark the runs a person makes**, with `RunEnvelope(live=True)` or `env.with_live()`; nothing
infers it (`docs/shipping.md` §1, §2).

**Swap the channel the agent asks through.** A channel declaring `coding_agent`, `simulated`,
`canned` or `builder` is a stand-in used while building, and FT-31 fails a shipped project on
each. Where the run is meant to be unattended, `unattended()` says so and passes.

**Settle what a live run keeps** before one is made, since the rate is decided as each run
starts and the material is now the end user's.

**Name what the end user reads.** Where the project stores the result for later reading, each
stored result carries `pipeline.behaviour_fingerprint(model=client)` and something re-runs
what an older pipeline wrote.

**Gate.** Ask `anything_else` and record it. `simple-agents check` reports FT-31 passing
alongside the rest, and exits 0.

**This gate does not close.** `stage = "ship"` stays in the brief, so what it adds runs every
later time the suite does. FT-37 fails once the pipeline behind the reported number is gone and
FT-38 once the entries describing it were read against something else, both reading a change
rather than an arrival. A project keeps building here, and re-running the check covers it.

**What the library cannot see.** The surface around the agent, a web app, a queue worker, a
scheduled job, produces no artifact it reads, and the runs a person makes through it are
reported rather than certified.

---

## When a gate fails

The report prints one block per check: what failed, why it matters, and the next action. Act on
the message printed under a `FAIL`; it is `docs/failure-taxonomy.md`'s own text. `blocked` means
the artifact it reads is missing and another check says why, and `n/a` means the check does not
apply: at this tier, at a stage the project has not reached, or to what the project declared,
and the line under it says which. Exit status is 0, 1 on a failure, or 2 when the brief is
missing.

**A failing gate is not a reason to lower the tier.** Lowering it is correct only where the
project reports no number.

---

## What not to do

- **Do not write the run's records by hand** (FT-13).
- **Do not answer an elicitation question on the builder's behalf**, and do not accept `unknown`
  where a human answer was required.
- **Do not report a number without an interval** (FT-06), and do not report accuracy alone
  (FT-10).

---

## The feature index

What this list names, the library ships. Check it before designing or building any capability, and open the named section before implementing around it. Each line is one document.

- **Pipeline** (`docs/pipeline.md`): the three node kinds §2 · a model per node §2.4 · delegate a subtask to a pipeline the model chooses §2.5 · branch, join and loop §1.2–1.4 · retries and `on_error` §1.5 · a pipeline as a node in another §1.6 · draw the graph and watch a run §1.7 · suspend a run and resume it §1.8 · stream a node's output §1.9 · fan out over a list, run nodes, items and tools concurrently, and what a failure inside one item does §1.10 · rerun what a dead run was given §1.13 · slice part of the graph §1.14 · what a node receives §3 · the output schema and `unknown` §4 · budgets per node and per run §5 · run with no backend §6.
- **Tools** (`docs/tools.md`): the contract and the four side-effect classes §1 · a tool's declared cost and spend ceiling §1.5 · replay and tool versions §3 · the fourteen built-ins §4: document search, page fetch with a host policy and a cache, web search, workspace I/O, a clock, typed extraction, a question to the end user, memory, conversation compaction · the finish check §5 · tools from an MCP server §7.
- **Retrieval** (`docs/retrieval.md`): search by meaning as well as by words §1 · what an index costs §2 · the embedding model, pinned §3 · fusion §4.1 · reranking §5 · a custom embedding client §8.
- **Memory** (`docs/memory.md`): a store the agent reads and writes across runs §1–2 · memory in an evaluation §3 · what redaction reaches §4.
- **Conversation** (`docs/conversation.md`): a conversation that outlives the run §1 · what a turn is §3 · reading one back §4 · compaction §5 · in an evaluation §7 · two turns at once §9.
- **Context** (`docs/context.md`): overflow and what happens at it §2–3 · a custom context builder §4.
- **Model clients** (`docs/model-clients.md`): the three shipped backends §2 · retries and pacing, `PacedClient` §4 · streaming §5 · reasoning output §6 · a custom adapter §7.
- **Run envelope** (`docs/run-envelope.md`): the manifest §2 · cassette record, replay and update §3 · cost, its three bases, and re-pricing an old run from its record §4 · seeds §5 · redaction §6 · reading runs back, and whether one with no outcome is still going §8.
- **Trajectory** (`docs/trajectory-format.md`): the seven record types and the four token classes on every model call.
- **Evaluation** (`docs/evaluation.md`): example sets and splits §1 · a label a model wrote §1.4 · the eight rates §3 · a figure per criterion §3.1 · intervals, rollout noise, and the do-nothing baseline §4 · per-node reach and accuracy §5 · scoring runs the evaluation did not make §5.5 · scoring one step at a time, back to front §5.6 · rollouts in parallel §6.2 · resuming one that stopped §6.5 · what an evaluation refuses to run §7 · every figure grouped by a property of the example §8.2 · comparing two versions §9 · variants, `ablate()`, and a sweep's cost before it runs §10 · a metric the project declares, ratios, counts and judged pairs §11 · a condition a model or a person decides §12 · an example that is a conversation §13.
- **View** (`docs/view.md`): the project on one page, `simple-agents view` · registering pipelines §2 · a step declared before it is built §3 · what flows between pipelines §4.
- **Product** (`docs/product.md`): the three product shapes §1 · the four interaction kinds §2 · a request is a run §3 · a question the run cannot settle, shelved, and what happens when the answer arrives §4 · the artifact that accumulates §5.
- **Shipping** (`docs/shipping.md`): a run that says it is live §1 · reading live runs back §2 · who answers the agent after it ships §4 · memory across a person's runs §5.
