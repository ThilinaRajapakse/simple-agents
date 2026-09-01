# Consultation — the sitting

Held 2026-08-15 on `runs/dogfood-4/inventory.md` **DF4-I01**, the largest thing dogfood #4 found after
`DF4-D1`, with **DF4-I04**, **DF4-I13**, **DF4-I25** and **DF4-I05** blocked behind it. The subject: what answers
a consultation during the life of a project the library owns, and whether the library has a
concept of what happens after a project is measured.

**What it settled.** Consultation had a production answer and no development answer, because
"development" is not one situation. It is three, and they have different right answers. The
library records *what happened* to a question and never *who answered it*, which is why 97
consultations answered by a canned string read the same as 97 answered by a person. And the
absence behind all of it is that a project's life, in the library's account of it, ends at a
number.

**Nothing is built yet.** §5 is what is scheduled and §6 is what went elsewhere.

---

## 1. What was verified against the artifacts, before any design

`runs/dogfood-protocol.md` §1's rule, and it earned its place three times: two of the four decisions changed
shape on something found by reading the source or the runs rather than the record.

### 1.1 The counts in the record hold

| Claim | Checked | Result |
|---|---|---|
| Dogfood #4: 104 consultations, 97 `answered`, 7 `declined` | every `trajectory.jsonl` under `runs/dogfood-4/runs/` | exact |
| Dogfood #3: 152 `declined` | the same, under `runs/dogfood-3/` | 148 in `runs/` and 4 in `recovered/`, so exact once the recovered evaluations are counted |
| The shipped dogfood-4 pipeline does not consult | the newest evaluation's rollout manifest | `look_closer` declares five tools and `consult` is not among them |
| "production" appears four times in all of `docs/`, every one incidental | `grep` | exact: two in `run-envelope.md`, one in `failure-taxonomy.md`, one in `evaluation.md` |

### 1.2 The format already reserved a name for this and nothing filled it

[`trajectory.py`, `ConsultationRecord`](../../src/simple_agents/records/trajectory.py#L456) declares six
resolutions: `pending`, `answered`, `unmatched`, `declined`, `timed_out`, `defaulted`.
[`tools.py`, `ConsultTool.resolve`](../../src/simple_agents/tools.py#L1392) produces four.
**`timed_out` and `defaulted` are produced by nothing.**

[`docs/trajectory-format.md` §4.3](../../docs/trajectory-format.md#L368) tells a reader
*"FT-25 reads `resolution` to tell them apart"*, and FT-25 is not one of the eleven checks that
ship. A shipped document describes a mechanism that does not exist.

### 1.3 A recorded consultation replays for its own rollout and no other

[`docs/evaluation.md` §7.4](../../docs/evaluation.md#L968) says a consultation is *"served from
the cassette like any other tool call, so the channel is never reached and the recorded answer
stands in for the person on every rollout."*

[`context.py`, `call_tool`](../../src/simple_agents/context.py#L844) keys a tool call on
`(node_id, tool_name, tool_version, arguments, occurrence)`, and `arguments` carries the
question the model wrote. Rollouts of one example take different derived seeds, so they ask
different questions and each one misses. **The recorded answer stands in for the person on its
own rollout, not on every rollout.**

**This is what killed the record-and-replay option.** It would cost a person one live pass over
roughly k×n consultations, and the next prompt edit turns the replay into a cassette miss.

### 1.4 The questions are unpredictable, which killed the first design for the evaluation answer

**103 of dogfood #4's 104 consultations are distinct**, and 73 of the 104 offered no options at
all. They are built from the books that particular run happened to find:

> "Among the books that remain unverified — Crossroads of Ravens, The Witch of Whispervale, The
> Wolf and the Crown of Blood, Secrets of the Bees, Daughter of Crows — do you have a preference
> for which one to prioritize…"

The first proposal at this sitting was `Example.answers`, a list of what the end user says,
consumed in order. **Thilina's objection was that it requires the project to know the questions
in advance, and the artifacts say he is right**: a list of pre-written answers cannot serve
those, and the agent whose consultation is worth measuring is exactly the one that was given
"quite a bit of agency" over when to ask.

### 1.5 FT-25's check cannot be built from what a run records, and its own text over-promises

[`pipeline.py`, `_tool_entry`](../../src/simple_agents/pipeline/recording.py#L147) records a tool's
`name`, `version`, `side_effect_class`, `declared_cost`, `re_executed` and `offered`. **Nothing
says a tool is a consultation tool**, and `consult(name=...)` lets a project rename it, so a
check matching the string `"consult"` is guessing.

And FT-25's check reads *"reachable from the relevant nodes"*. Which nodes are relevant is a
judgement no artifact carries. What a check can read is that a consultation tool is offered to
at least one node.

---

## 2. The four decisions

Scoping first, ruled before the brief was written: **DF4-I05's decision is taken here and its build
deferred**, and **question 4 is decided here and built inside DF4-I03**.

### 2.1 What answers a consultation during the life of a project

**Ruled: name the three situations and give each its mechanism.** There is no single development
answer because development is not one situation.

| Situation | Who answers | Mechanism |
|---|---|---|
| An interactive run, a handful of times | The builder, standing in for the end user, with the coding agent relaying | `Suspend` and `Pipeline.resume`, which already work. The procedure has to say who the person is |
| An unattended run: smoke runs, fake runs, sweeps | Nobody, or the coding agent with the builder's permission | §2.2's sentinel, or `answered_by="coding_agent"` |
| An evaluation, k×n rollouts | A stand-in end user the example describes, played by a model | §2.3 |

**`ask_on_stdin` ships.** The sitting first argued against it, on the grounds that the library
owning a terminal is what `simple-agents.md` §2.9 rules out. **Thilina overruled it and the
overrule is right**: §2.9 is about the library asking the *builder*, and what ships here is a
function handed to the project, not a terminal the library reads.

**The coding agent may stand in for an unattended run, with the builder's permission, and never
for a measurement.** The permission half is not decoration. A coding agent inventing what an end
user would say is FT-24's failure one level down, and its own failure message is the argument:
*"a plausible invented answer is worse than a blank."* It is worse here, because the coding agent
knows what its pipeline needs to hear. `DF4-L3` is three cases in this run where an apparent model
advantage was a defect in the harness measuring it, each flattering the same arm.

**Weighed and not taken.**

- **Record once from a person, then replay.** §1.3 is why: k×n live answers, invalidated by any
  prompt edit. No dogfood could have used it; this one ran 33 evaluations and 3,293 runs.
- **Ship a stub and nothing else.** Stops the lie and leaves every evaluation for the life of the
  project measuring an agent whose consultations nobody answers.
- **Declare it the project's business and document the three cases.** Leaves a results file
  unable to distinguish a measured consulting agent from a measured stub, which is the same
  defect one layer up.

### 2.2 What the library ships for "nobody can answer"

**Ruled: a sentinel, a shipped channel, one new resolution, and the two dead ones removed.**

A channel returns `Unavailable(reason=...)` where there is nobody to ask; `unattended()` is a
shipped channel that returns it; the resolution is `unavailable`; the model is told once that no
one can answer and not to ask again; later consult calls in the same run return it without
reaching the channel, and the count is reported. `timed_out` and `defaulted` are removed:
`Unavailable(reason="no answer in 60s")` carries the timeout case in its reason, and one value
with a reason beats three values nothing produces.

**`unavailable` gets its own branch in `on_reply`, required, waivable by `exhaustive=True`.**
The sitting first proposed routing it to the `declined` branch, for implementation convenience.
**Thilina rejected it and the rejection is right**: a person who is there and will not answer and
no person at all lead to opposite next moves. Declined means stop or narrow, because someone
chose not to help and the choice is information. Unavailable means proceed on what there is and
say what is missing, because nobody chose anything.

**Weighed and not taken.**

- **Reuse `declined`.** No format change, and a results file still cannot separate "the end user
  said no" from "there was no end user", which is the distinction the finding is about.
- **Reuse `defaulted`.** Its documented meaning is that the agent proceeded on a default, which
  is a different event, so its gloss gets rewritten either way. The saving is one string.
- **Refuse an evaluation whose consultations were all unanswered.** Dogfood #3's sitting weighed
  this and declined it: *"A project may want the declined arm as a baseline. Make the number
  visible first and see whether anyone reaches for the refusal."* One run later nobody reached
  for the refusal and the visibility was defeated by answering instead, so the bet lost. A
  refusal is still too strong on its own; the reported line comes first.

**`answered_by`, which came out of the coding-agent question and is the largest thing here.**
The library records what happened to a question and never who supplied the answer, so a real
reader, the builder standing in, the coding agent, an evaluation's stand-in and dogfood #4's
canned string are all `answered`. That is why 97 of 104 looked fine for two days. The
consultation record gains `answered_by`: `end_user`, `stand_in`, `coding_agent`, `simulated`,
`example`. The channel declares it once at registration, the shipped channels fill it in
themselves, and a hand-written channel is refused without it, which is exactly where both
dogfoods went wrong. `per_node.consultation_resolutions` reports it beside the resolution, so
`answered: 97, by coding_agent` cannot be read as a number measured against readers.

**Where this touches `simple-agents.md` §9 item 16, surfaced and not moved.** Item 16 says
consultation is a designed interaction and not a fault path. Recording that a designed
interaction could not take place is the opposite of treating asking as failure, and `DF4-X2` in the
inventory is the evidence: the rule is true of the design and false of both projects that have
used it. This is the change that makes it true of the projects. Nothing in §9 moves.

### 2.3 The stand-in end user, and why it is neither a node nor a bare function

**Ruled: a function-shaped seam the library owns, declared on the evaluation, with the end user
described on the example.**

```python
Example(id="q4", inputs={...}, expected=..., split="held_out",
        end_user="Reads a lot of grimdark, has read all of Abercrombie, "
                 "wants something under 400 pages, and finds questions "
                 "about difficulty useless and says so.")

suite.run(envelope=env, model=client, split="held_out", k=3,
          end_user=StandIn(model=cheap))
```

**Not an `LLMNode`.** A consultation happens inside an agentic node's tool loop, mid-turn, at the
moment the model decides to ask. There is no point in the graph where another node could run.
Beyond that, a node for the stand-in enters the builder's graph: the manifest as one of their
nodes, per-node metrics as the agent's own work, the agent's budget, `graph_fingerprint`, and
`ablate()`'s reach.

**Not a bare function either**, though the channel seam takes one and a project may still pass
one. A plain function gets none of four things: a model to call that is not the one being
measured, a record of the call, separation from the agent's budget, and a seed and cassette entry
so the evaluation repeats. Repeating is what `noise_floor` and `compare()` rest on.

**The precedent is `Example.memory`**, which is the same idea about a different part of the world
around the agent, and [`runner.py`, `_scoped_for_rollout`](../../src/simple_agents/evaluation/runner.py#L2556)
is the seam that already swaps it per rollout.

**Four consequences, one of which is a defect if it is forgotten.**

1. The stand-in's answer is recorded on the consultation record with the model that produced it
   and what it cost, so it is visible and stays out of the node's model-call counts.
2. Seeded off the rollout seed and stored in the cassette, so a replay gets the same reader.
3. **The stand-in belongs in the evaluation's identity.**
   [`runner.py`, `_eval_id`](../../src/simple_agents/evaluation/runner.py#L1162) covers the
   examples through `ExampleSet.content_hash`, so the reader's description is covered once it is
   a serialised field on `Example`. The stand-in's own model is covered by nothing, so two
   evaluations differing only in which model plays the reader resolve to one directory and the
   second is refused after the first has been paid for. That is `DF4-D14`, which is `DF4-I07`.
4. Comparing reader types falls out: same agent, same examples, three stand-ins, three arms, with
   the noise floor measurable underneath them.

**What it costs, stated rather than argued away.** The number is now partly a measurement of the
stand-in, and a simulated reader is more agreeable and more articulate than a real one. The
results file says the consultations were answered by a model, every time, in the same place the
figure is. Holding the stand-in fixed across arms keeps an arm-to-arm comparison fair even where
the absolute number is not a claim about real people.

### 2.4 FT-25's occurrence check

**Ruled: build it, with FT-25's own text corrected, inside DF4-I03's brief-against-code reader.**

FT-25 is *"Consultation treated as a fault path"*. Its entry claims a check and describes it: if
the brief says the agent must ask the end user something, a consultation tool must be registered
and reachable. `checks.py` registers FT-01, 02, 03, 04, 06, 07, 13, 14, 24, 29 and 30, and FT-25's
only appearances in the source are a citation inside an elicitation question's guidance and a line
in `consult`'s module docstring. Its surface line reads *"elicitation-only, with a static
occurrence check"*, so a reader is told something runs.

It would have caught `DF4-D9`: the `consultation` entry is the one the builder was most expansive
about, `consult` was built onto `hunt`, the back half was redesigned, consultation left the graph,
and the suite read 11 of 11 for two days with his words still in the brief marked `answered`.

**Two things it needs, from §1.5**: a marker on the manifest's tool entry, and FT-25's check text
narrowed to what a check can read. The second is required whatever is decided, because the
taxonomy currently describes a check that could not be written.

**Weighed and not taken.** Correcting FT-25 to elicitation-only and building nothing. Cheapest and
honest, and it gives up the one check that would have caught a whole elicited capability leaving
the graph when the data was already on disk.

---

## 3. Whether the library has a concept of after

**Ruled: yes, and it is a fifth stage with a gate, called `ship`.** Thilina's reasons: a clean
separation, a clear goal, and a project reaching a defined end rather than trailing off after a
number.

**What the absence had cost.** 60% of dogfood #4's runs landed after the last gate (`DF4-D7`).
The product was a queue assembled by every version of the pipeline that ever ran, with 85% of
its judgements having no case where a fresh evaluation the same day had 5% (`DF4-D1`). And the
UI session read that whole queue, including output from the design the builder later called a
stupid system, because nothing separated runs made while building from runs whose output a person
sees.

**What has no other reader.** `Trajectory.sampled(rate)`, `runs()`, memory scoped to one end
user, and suspend and resume. `simple-agents.md` §1.3 is the improve-your-agent loop and §5's
second rung is SFT on the project's own successful traces, which come from live use. An account
of after is already load-bearing and was unnamed.

**Settled here.** There is a fifth stage; it is called `ship`; live runs mark themselves as live
so they are separable from development runs and from what the checks read; and the tier ladder
does not change. Shipping is not a tier: `trained` sits above `evaluated` and belongs to the
improvement ladder.

**What the gate asks, narrowed.** Not "is this any good", which `measure` answers and which the
library is explicit it cannot judge. **"Is this fit for someone to use, and is what they use
separable from what it was built with."**

**Open, and it is the first thing the `ship` sitting settles.** Stage requirements are cumulative
over stages, so `stage = "ship"` would require `measure`'s questions, which says a project may not
ship what it has not measured. `how_far`'s own guidance says the opposite: *"Most answers are
`build` for something they will use themselves."* Three ways out, and the recommendation carried
into that sitting is the third:

- Shipping requires measuring. Defensible on the library's thesis, and it refuses the largest real
  category of builder.
- `ship`'s questions are its own and do not inherit `measure`'s. One exception to a rule that has
  none, and the exception is the hole the rule exists to close.
- **The requirement becomes cumulative over the stages the project's declared tier includes.** No
  rule gains an exception, and shipping stops being downstream of measuring.

**One candidate check for the `ship` gate that exists only because of §2.2**: once a channel
declares who answers, the gate can refuse a project going live whose consultation channel still
declares `coding_agent`, or is `unattended()`. That is a stub reaching production, caught.

### 3.1 What `ship` does not close, and this is the paragraph a later session needs

**`ship` does not close `DF4-D7`.** A fifth stage adds one more gate at the end of a longer road
and does not govern the road. Everything in that 60% would still happen before the new gate
fires: the judging node redesigned twice, the store rebuilt, four model arms, and the reported
figure moving from 0.41 to 0.89, all while `stage` read `measure`. `DF4-D2` is worse, because it
happened early: an answer recorded on day one, one entry away from the answer that made the design
look right, with FT-29 and FT-30 passing over it throughout. `DF4-D7`'s own text says *"This is
not an argument for a fifth stage."*

**The general statement, and it is why more gates cannot close this.** Every enforcement the
library has is triggered by **time**, a project reaching a point. Every failure this run found is
triggered by **change**, something moving and nothing re-reading what it invalidated. The same
shape whether the change is a redesigned node, a superseded brief entry, or a capability leaving
the graph.

**So `DF4-D7`'s remaining half goes to DF4-I03**, whose drift reader needs a trigger that is not a
stage gate. Part of the trigger is already detectable: the graph fingerprint moves when the
pipeline changes and the brief does not. `DF4-D6`, the one decision after 2026-08-12 that never
reached the builder, is what a per-decision surface catches and a per-gate one cannot.

---

## 4. The documentation corrections, applied 2026-08-15

**Applied at the sitting rather than held for the shipped-document review**, on Thilina's
correction: a documentation fix goes in when it is found, so the review reads a corrected
document once. `plan.md` §1 P3-3 said the opposite until today, and it said it because this
session misread *"the full-test pass's corrections are merged into this item"* as deferral when
those corrections had already been applied and merged.

Six statements, all false before the build and correctable without it.

| Statement | Where | Corrected to |
|---|---|---|
| The recorded answer "stands in for the person on every rollout" | `docs/evaluation.md` §7.4 | It is served to the rollout that recorded it, since the key carries the model-written question, so recording an evaluation over a consulting agent asks a person one question per rollout. §1.3 |
| "Results do not depend on how many ran at once", with nothing on a tool holding state | `docs/evaluation.md` §6.2 | What the library holds per rollout is named, and what a tool reaches is the project's and is shared. `DF4-I11`, `DF4-X1`, and the finding that destroyed a measurement |
| Nothing says what a fanned-out prompt receives | `docs/pipeline.md` §2.2 | The whole input, with the named key holding one item, with an example. A function written to take the item alone raises `KeyError`. `DF4-I12` |
| Nothing says a fake run may reach a node's own model, or the real tools | `docs/pipeline.md` §6 | Both, and the consult channel named as the case that blocks a run meant to take milliseconds. `DF4-I13`, and why DF4-I01 blocked it |
| FT-25's surface is "elicitation-only, with a static occurrence check" | `docs/failure-taxonomy.md` FT-25 | "elicitation-only". `DF4-X6` |
| FT-25's check reads "reachable from the relevant nodes" | the same | No check runs, and which nodes ought to be asking is a judgement no artifact carries. §1.5 |

**One is left for the build, because it cannot be corrected ahead of it.** `resolution` is
documented as taking `timed_out` or `defaulted`, which nothing produces (§1.2). Both leave the
enum in `trajectory.py` and the field table in `docs/trajectory-format.md` in one change.

**2117 tests pass** after the corrections, with `prose_check` and `check_citations` clean.

---

## 5. What is scheduled

**One item, two halves, one build log**, on Thilina's ruling: the second half is meaningless
without the first and both edit the same records and the same documents.

**Half one — who answers, and what the record says.** `Unavailable(reason=...)` and a shipped
`unattended()` channel; the `unavailable` resolution, with `timed_out` and `defaulted` removed;
its own required branch in `on_reply`, waivable by `exhaustive=True`; `answered_by` on the
consultation record and in `consultation_resolutions`, required of a hand-written channel;
`ask_on_stdin` shipped; the coding agent as a stand-in for an unattended run with the builder's
permission recorded. Trajectory format bump.

**Half two — the evaluation stand-in.** `Example.end_user`, `EvalSuite.run(end_user=StandIn(...))`,
the swap per rollout, the answer recorded with its model and its cost, seeding and replay, and
the stand-in inside `_eval_id`.

**A sitting: the `ship` stage.** DF4-I05 with its should-we half ruled. Settled going in: the stage
exists, its name, live runs marking themselves, and the tier ladder unchanged. Open: §3's
cumulative-requirement collision, the question set, what the gate reads, and the document the
stage points at. **§3.1 is what it must not be read as closing.**

### 5.1 Why this is built before the rest of the inventory is decided

**Ruled 2026-08-15: build DF4-I01, rather than take all 41 candidates in sittings first.** Three
reasons, and the first is this project's own record.

**Five consecutive build items had their design change on contact with the code**, each recorded
in `plan.md` where the brief was written: §1.4's claim that §8.2 already settled replay; §1.5's
redaction and cassette scope; §1.9's pre-flight arithmetic and its headline measurement; §1.10's
cassette decided at run start, which would have left the runs most worth replaying with no
recording; and §1.11's lean on where the decision record lives. Deciding 41 candidates in a row
means deciding all of them on today's information and finding out about all of them at once.

**This build delivers data another item would otherwise build twice.** The channel declares
`answered_by` at registration, so the manifest's tool entry records it. That is at once the
marker FT-25's check needs to tell a consultation tool from any other, and the input to the
`ship` gate's check that a live project is not running on a coding-agent stub. Taking DF4-I03 first
means adding a marker and then changing it.

**Several cheap candidates land on surfaces half two edits.** `DF4-I08`, `DF4-I22`, `DF4-I23`, `DF4-I17` and
`DF4-I19` are all about the results file and per-node metrics. Deciding them against a results file
that is about to change is deciding them against the wrong file.

**What comes after, proposed and not ruled.** One short pass for the cheap code fixes: `DF4-I08`,
which is one line and removes the workaround that cost 1,584 model calls in a single evaluation
arm, `DF4-I09`, and `progress_of`. Then DF4-I02 and DF4-I03 as sittings, with DF4-I03 carrying FT-25's check and
`DF4-D7`'s remaining half.

---

## 6. What went elsewhere, and what stays open

| | Where |
|---|---|
| FT-25's occurrence check, and the manifest marker it needs | DF4-I03, with the general brief-against-code reader |
| Whether the end user sees what was measured, as a `ship` gate check | DF4-I02. Taking it here would decide DF4-I02 inside a consultation sitting |
| `DF4-D7`'s remaining half, the between-gate drift | DF4-I03, per §3.1 |
| The `Reply` matcher | **DF4-I04, untouched.** `PENDING-SIGNOFF.md` item 6 stays open and is now unblocked |

**Every decision here is a claim about behaviour no run has met.** `DF4-Q1` says it: two runs have
used `consult` and neither reached a person. The part most likely to be wrong is the interactive
row of §2.1, which assumes a coding agent will stop, relay a question and resume rather than
routing around the stop. That goes into `dogfood-5-setup.md` §2 as something the next run is set
up to show.

---

## 7. The build, 2026-08-15

Built the same day as the sitting. §5's two halves in one pass, one trajectory bump, and the
documentation correction §4 left for the code.

### 7.1 What shipped

**Half one.**

| | |
|---|---|
| `Unavailable(reason=...)` | A `str` subclass whose text is the instruction the model reads, carrying `reason`. [`consult.py`, `Unavailable`](../../src/simple_agents/builtins/consult.py#L135) |
| `unattended()` | A shipped channel returning nothing else, declaring `answered_by` of `nobody` |
| `ask_on_stdin` | Shipped, declaring no answerer of its own. §7.3 is why |
| The `unavailable` resolution | Produced by [`ConsultTool.resolve`](../../src/simple_agents/tools.py#L1392); `timed_out` and `defaulted` are gone from the enum and from `docs/trajectory-format.md` §4.3 |
| Told once, then answered without the channel | [`RunContext.note_no_one_to_ask`](../../src/simple_agents/context.py#L1263) and [`nodes.py`, `_no_one_answered`](../../src/simple_agents/runtime/consultation.py#L144) |
| `on_reply(unavailable=...)` | Required, waivable by `exhaustive=True` with the other two |
| `answered_by`, declared and recorded | `consult(answered_by=...)`, required; on every `consultation`; on the manifest tool entry ([`pipeline.py`, `_tool_entry`](../../src/simple_agents/pipeline/recording.py#L147)); counted as `per_node.consultation_answered_by` |
| The coding agent, with permission | `consult(answered_by="coding_agent", permission=...)`, required together, recorded in the manifest |
| A run saying who answers | `RunEnvelope(end_user=...)` and `env.with_end_user(channel, answered_by=...)` |

**Half two.** `Example.end_user`; [`SimulatedEndUser`](../../src/simple_agents/evaluation/stand_in.py#L102), a model
playing that person, bound per rollout by
[`runner.py`, `_scoped_for_rollout`](../../src/simple_agents/evaluation/runner.py#L2556) at
the seam §2.3 named; `EvalSuite.run(end_user=...)` and `EvalSuite.record(end_user=...)`; the
answer recorded with its model, its tokens and its cost and kept out of the node's counts; the
stand-in inside [`runner.py`, `_eval_id`](../../src/simple_agents/evaluation/runner.py#L1162);
and a refusal before the first rollout where an example carries no description.

**Formats.** Trajectory `0.21` to `0.22`, manifest `0.22` to `0.23`, results file `0.12` to
`0.13`. `dev-docs/design/trajectory-format-changelog.md` `0.22` is the record.

### 7.2 The four decisions the sitting did not take, and what was decided instead

**`answered_by`'s values changed on contact with the other names in the item.** The sitting's
§2.2 listed `end_user`, `stand_in`, `coding_agent`, `simulated`, `example`, in the same order as
the five situations in the sentence above them, which fixes the mapping. Two of the five names
collide with something else the same sitting fixed: §2.3 names the evaluation's reader `StandIn`,
which under that mapping records `simulated` while `stand_in` means the builder; and `example`
names a hardcoded string with the name of `Example`, which supplies no answers and whose
`end_user` field this item adds. Put to Thilina, who ruled: `builder` for the person standing in,
`simulated` kept because it says a model wrote the answer where `stand_in` would not, and
`canned` for the fixed string. **And the class renamed to `SimulatedEndUser`**, on his objection
that the argument for `simulated` is an argument for moving the class rather than the value.

**A sixth value, `nobody`, was needed and is not an answerer.** `unattended()` has to declare
something: the manifest entry is what FT-25's check and the `ship` gate read, and a channel that
answers nothing still has to be visible there. `answered_by` is therefore what the channel says
it reaches, recorded on every consultation including a `pending` and a `declined` one, rather
than an observation of who typed. `docs/trajectory-format.md` §4.3 says which it is, because a
reader taking it for a verified fact would draw a stronger conclusion than the record supports.

**The seam is on the envelope, and it is public.** An evaluation holds a constructed pipeline and
the channel is closed over inside the tool, so the swap has to travel on the envelope, which is
what `_scoped_for_rollout` already does for `memory`. Making it public rather than internal was
put to Thilina and taken: it is also §2.1's unattended row, since `env.with_end_user(unattended())`
is how a smoke run gets an answerer without the project's registration being edited, and it is
what `docs/pipeline.md` §6 needed for `DF4-I13`.

**`per_node` gained a sibling field rather than a nested one.** `consultation_resolutions` keeps
its shape and `consultation_answered_by` sits beside it. The pairing (which resolution came from
which answerer) is in the trajectory; the finding this closes needs only the counts.

### 7.3 What the build found that the sitting did not

**`ask_on_stdin` cannot declare its own answerer, and shipping one would have been the lie the
item removes.** §2.2 says the shipped channels fill `answered_by` in themselves. `unattended()`
can. A terminal cannot: it is the builder's while a project is being built and the end user's
once a CLI agent ships, and a default of `end_user` would record the builder's own answers as
readers' on every development run. It takes the declaration beside it instead, and the refusal
says why.

**Overriding the channel left the record naming the wrong answerer.** The first implementation
swapped the channel per call and kept the tool's declared `answered_by`, so an evaluation whose
stand-in answered recorded `end_user`, which is the defect the field exists to close, one layer
down. Found by a test asserting the case rather than the mechanism. The rule that came out of it:
**the manifest carries what the project declared and the trajectory carries what the run did.**

**`Cost` reaches a record as text.** Found on the first live Gemini run: `answered_by_model.cost`
read `"Cost(value=0.0001, ...)"` rather than a figure. `Cost` is a slots dataclass with no
serialiser, and `to_record_data` falls through to `str(value)` for anything with no `__dict__`
and no `model_dump`. Every other cost in the format is written by a caller that converts it
first, so the consultation record was the first to hand one over raw. `nodes.py` `_cost_entry`
builds the same five keys, and a test asserts the shape.

**A library edit to `ask_the_user`'s body invalidates every project's recorded consultations.**
`consult()` derives its version from three sources, and the first is the library's own tool
function. This item changed that body, so both suspend cassettes missed and had to be re-recorded
even though nothing about what the backend saw had changed. On an upgrade a project would get a
silent cassette miss on every consultation. **Not fixed here**, because the fix is a change to
how a shipped tool's version is composed and it reaches further than this item: recorded against
`runs/dogfood-4/inventory.md` for the cheap-fixes pass.

**A suspended run whose channel was replaced wrote two records that disagreed.** Found on the
read-back rather than by a test. A question that stops the run is two records, and only the first
went through the binding, so the answering record named the registered channel while the question
named the run's. `_delivered_answer` binds the same way now, and two tests hold the pair to one
answerer.

**`compare_variants` could not be given a stand-in**, so §2.3's fourth consequence, that
comparing readers falls out of the design, did not hold: every arm would have fallen back to the
project's own channel. It takes `end_user=` and passes it to every arm, which is also what makes
the sentence about holding the stand-in fixed across arms true.

**A `SimulatedEndUser` put on an envelope was accepted and unusable.** The envelope takes a
channel, which is a function of the question and the options; a stand-in is bound per rollout and
is not one. It was accepted because the refusal exempted anything that could be bound, which is
the wrong test. It now names the call to make instead.

**`ModelAnswer` is not called `Answer`.** `prose_check` caught the first name resolving to the
new class in every docs example that had been using `Answer` as a project's own output schema,
which is the running example across `pipeline.md` and `tools.md`. A shipped name has to avoid the
names a project's own code is most likely to use.

### 7.3.1 Two the documentation sweep found

**The elicitation set was changed to ask who answers, and changed back.** §2.1's interactive row
says the procedure has to say who the person is, and the library now refuses a channel declaring
no answerer, so the sweep read that as a gap and added *"and who answers it?"* to the
`consultation` question. **Reverted the same night, on Thilina's objection, and the objection is
the finding.** Three things were wrong with it. It overloaded a question already asking something
else, and it was written that way to avoid adding a question rather than because it belonged
there. *"What must the agent ask"* already reads as a scripted list, which this run's own evidence
contradicts: 103 of dogfood #4's 104 questions were distinct and written by the model out of what
that run found. And **who answers is not a constant**: it differs between development and
production and between one stage of development and the next, so a question with one answer is
wrong the day after it is answered, and `deferred` does not help because the answer is not
unknown, it is plural.

**What the objection settles.** Three things had been treated as one:

| | Where it belongs |
|---|---|
| Who the end user is | Stable and builder-owned. Already asked, `end_user` at `brainstorm`, whose scaffold already says the answer decides whether consultation reaches somebody other than the builder |
| Who answers a given run | Configuration, and the library already carries the variation: the channel's declaration is the default, `RunEnvelope(end_user=...)` replaces it per kind of run, an evaluation replaces it per rollout. Not a builder question |
| Whether the coding agent may answer in the builder's place | Builder-owned, and already forced at registration by `permission=` |

**Nothing is added to the elicitation set.** What is still missing is a different question and a
stable one: **will anyone be there at all when this runs for real?** An agent designed around
consultation that ships into a nightly job is broken by design and nothing catches it. That is
§3's *"is this fit for someone to use"* rather than a `shape` question, so it goes to the `ship`
sitting, beside the gate check §3 already proposes over `answered_by`.

**FT-25 described one of the three things the library now provides.** Its entry named only the
`unmatched` case. It names three now, one per way a designed interaction turns back into a fault
path: an answer that was none of the options, a run with nobody to ask, and a channel that does
not say who it reaches.

### 7.4 What the live runs showed

**Gemini, `gemini-3.1-flash-lite`.** The unattended run completed: the model asked once, read
the `Unavailable` text, did not ask again, and reported absence through the `unknown` branch
naming what it could not settle. The short-circuit was therefore not reached, which is the better
of the two outcomes and not the one it was built for. `Unavailable`'s text is doing work a
resolution alone could not.

**The stand-in, four rollouts over two examples.** Every consultation `answered` and
`answered_by` `simulated`, with the model, 31 to 34 output tokens and a cost near $0.0001 on each
record. The node's own model calls stayed at 23 with none of the stand-in's among them. The
answers are in character to a degree the sitting's §2.3 warning is worth re-reading against:
against the example describing a reader who *"finds questions about difficulty useless and says
so"*, the stand-in answered *"Just give me some grimdark under 400 pages and stop wasting time
asking about difficulty"*. Two rollouts of one example asked different questions and got
different answers, which is what the per-rollout binding is for.

**Both suspend cassettes were re-recorded.** The Mistral arm is gone: it is out of credits, and
on Thilina's ruling the hosted arm became Gemini, `tests/cassettes/suspend-gemini.jsonl`, which
matches what `handoff.md` has said since 2026-08-12. Three of its assertions were counts of what
Mistral did (three model calls, the answer in the third, options offered) and are now written
against what the recording shows rather than against a fixed index: Gemini made eight calls and
offered no options.
