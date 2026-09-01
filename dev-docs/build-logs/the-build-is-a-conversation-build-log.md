# Build log — the build is a conversation

`plan.md` §1 P3-37. Started 2026-08-27. Written while building, not afterwards.

Four candidates from dogfood #5's sitting 3: `DF5-I17` how a question is put, `DF5-I38` which
consultation mode a project needs, `DF5-I39` the coding agent as the person at the other end of
a run during the build, and `DF5-I40` the evaluation as the only repeated execution the coding
agent is shown, which by construction has nobody in it.

## 1. Before any design

Three things checked before anything was decided, and one of them moved the design.

**`Pipeline.resume` is called nowhere in dogfood #5's project.** Confirmed, and stronger than
`DF5-I39` recorded. The only occurrence of the name in the project is a docstring in
`tvtime/channels.py:30` describing what it would do. Across the project's **2,415 manifests,
zero carry a suspension**, zero carry `suspension.json`, and the string `resumed_at` appears in
no file under `runs/`. So the run never stopped at all: `engaged` mode is unreachable, which is
what `DF5-D3` found. The check `DF5-I39` asks for reads a state that project never reached, and
the procedure step is what would have produced it.

**`DF5-I17`'s ratchet is at zero violations.** No `ask` of the 47 carries a `docs/` path or an
`FT-nn`. 27 of the 47 scaffolds carry one, which is where they belong. *(47 rather than the
row's 46: `anything_else` arrived with `P3-36`.)*

**`answer_form`'s scaffold already said the thing, and it was not enough.** Read off the frozen
wheel at `dogfood-5/wheels/`, not the current tree: at the run's freeze the scaffold read
*"offer the five against one of the builder's own inputs, written each way"*, verbatim. The
builder still could not answer it. The project's own account, `BUILD-LOG.md:262`: *"the question
offered five library type-names against an abstract example. Re-asked by writing the same case
five ways against their own data."* The coding agent read the scaffold, took the five type-names
out of it, and dropped the half that anchored them.

That is what decided `DF5-I17`'s shape. A rule that lives in one scaffold is a rule the coding
agent can satisfy halfway. It has to sit where a question is composed, and the `ask` has to name
what goes in front of the builder.

**`may_suspend` is a channel attribute and reaches no manifest**
([`consult.py` `may_suspend`](../../src/simple_agents/builtins/consult.py#L554)), so a check cannot read that a
project's channel *would* stop a run. That bounds `DF5-I39`'s check to what a run recorded.

## 2. Design

### The rule for how a question is put (`DF5-I17`)

Four clauses, one per builder failure in [`findings.md` §3.8](../runs/dogfood-5/findings.md#L1):
put it against something of the builder's own (`:263`, `answer_form`); look up any number it
turns on and say where it came from (`:4751`, *"what's that random number 12?"*); name the
options and which is recommended (`:5764`); explain every term the builder has not used
themselves (`:6513`).

**Three places carry it, not one.** `docs/procedure.md`'s "What to settle first, and what to keep
doing", so it governs every stage; the `simple-agents questions` preamble, which is what a coding
agent reads at the moment it composes; and `Question`'s own docstring, which is what it reads if
it reaches the dataclass. Each says the rule governs a question the coding agent composes for
itself as well as the shipped ones.

**No vocabulary test**, on Thilina's call (`DF5-N8`). The existing
`test_no_ask_puts_the_library_s_own_words_to_the_builder` stands and gains nothing.

**Five `ask` strings rewritten**, agreed at the sitting on 2026-08-27 against a proposal of five
with four alternatives offered. All 47 were read; these five offered a menu of abstractions or
asked for a value with no instance in front of the builder.

| Key | Was | Is |
|---|---|---|
| `answer_form` | "What form does a correct answer take: one value, any of several, a collection, a quantity that is close enough, or a set of conditions?" | "For one of the builder's own inputs, written out: is there one correct answer, or several that would all be right? Does the answer have to contain particular things, land near a number, or meet a set of conditions?" |
| `absence_vs_error` | "What does a wrong answer cost, against a missing one and against one that is partly right?" | "Here are two things that could happen on one of the builder's own inputs: the agent asserts a wrong value, and the agent reports that it found nothing. Which is worse, and by how much?" |
| `judged_steps` | "Does any step inside the run have its own right answer?" | "Here are the steps this agent takes. Is there any one whose output the builder could call right or wrong without looking at what the run finally returned?" |
| `budget` | "What are the four budget numbers: steps, tokens, cost, and wall clock?" | "One run of this agent has been measured. Given what it took in steps, tokens, money and wall clock, where should each of those stop?" |
| `unevaluated_effects` | "Which of the things the agent does for real were never exercised by an evaluation?" | "Here is what this agent does for real outside the run, and which of those no evaluation has ever exercised. What should happen the first time one of them runs for somebody who is not the builder?" |

**`absence_vs_error` was not on `DF5-I17`'s list and belongs there.** Its scaffold says *"Do not
ask it in the abstract (FT-10)"* and its `ask` was the abstract version, which is the same trap
`answer_form` fell into with the same scaffold-versus-ask split.

**Left alone: `context_limit`, `too_similar`, `backend`, `rerun_cost`.** Each asks for something
the builder can answer in plain words once the coding agent has done the measurement its scaffold
names, and none offers a menu of library abstractions.

**One ratchet**, that no `ask` carries a `docs/` path or an `FT-nn`.

### Which consultation mode (`DF5-I38`)

Folded into `consultation`'s scaffold, read off `used_through`, which the builder answered a
stage earlier. Named in the builder's terms first and the library's last: somebody waiting can
be kept waiting; a run a schedule fired or a store write triggered cannot stop, so its question
goes on a list and the run finishes; a run nobody was ever going to answer finishes without it.
Then `Suspend`, `Shelved` and `Unavailable`, and `docs/product.md` §4 for what each takes to
build. **No new brief key**, and a project can need more than one of the three.

### The coding agent as the person at the other end (`DF5-I39`)

**A new taxonomy entry, FT-41**, agreed at the sitting on 2026-08-27 against folding it into
FT-25 or shipping a report note that never fails. `Suspend` also comes from `suspend_before=` and
`stop_when=`, so what fails here is the resume half of suspension rather than a consultation
failure; FT-25's subject is whether the agent asks at all, and a check failing for two unrelated
reasons carries two failure messages.

**Modelled on FT-40**: no `Stage:` field, counted at every stage, a failure from `ship`. The
condition is the row's: at least one suspension still open **and** no run under `runs/` ever
recorded a `resumed_at`. An open suspension beside a resumed run is a run waiting, which is
ordinary; a project that has never continued anything has the continuing half unwritten.

**And the procedure step that produces the state.** `docs/procedure.md` stage 4 now asks for one
run that reaches the channel, and, where the design has the run stop and wait, one
`Pipeline.resume` that continues it. The coding agent is `resume`'s own `ask_someone`: it carries
the answer in, and the builder is who gave it.

### The evaluation has nobody in it (`DF5-I40`)

**Said at `shape`**, where `consultation` is settled, rather than at `measure` where the cost is
sunk. A rollout is refused over a channel that reaches a person, so every rollout answers with a
stand-in or with `Unavailable`, and stage 5 is the only repeated execution the procedure asks
for.

**Reported rather than failed.** FT-25's `_was_it_ever_reached` note widens from the run's
manifest to the newest results file, and names the results file in the check's `read` when it
does.

## 3. Build

**Surfaces touched.** `src/simple_agents/conformance/elicitation.py` (the rule in `Question`'s
docstring, five `ask` rewrites, four scaffolds), `src/simple_agents/conformance/checks.py`
(`ft_41`, `Resumptions`, `_resumptions`, the widened `_was_it_ever_reached`, `_the_run_asked_nothing`,
`_consultations_in_the_results`), `src/simple_agents/cli/main.py` (`HOW_A_QUESTION_IS_PUT`),
`docs/procedure.md`, `docs/failure-taxonomy.md`, `docs/conformance.md`, `docs/product.md`,
`docs/shipping.md`, `README.md`, `scripts/prose_check.py`.

**Twenty-three checks became twenty-four and forty entries forty-one**, which the document counts
in nine places across `docs/conformance.md`, `docs/failure-taxonomy.md`, `README.md` and
`checks.py`'s own header table. `test_conformance.py` reads every one of them off the code, so
each moved with a failing assertion naming it.

**What the build found that the design did not know.**

- **`ft_25` went to 17 branches** on the first cut, because the widened note was reassembled by
  sniffing its own text for the phrase `"results file"` to decide the `read` tuple.
  `_was_it_ever_reached` returns `(note, also_read)` now and the sniffing is gone.
- **`_questions` in `cli.py` went to 72 lines** from the inline preamble. It is
  `HOW_A_QUESTION_IS_PUT`, a module constant, which is also where the rule wants to be read.
- **The note read with two `and`s**: *"…reaches a node, and the run read here asked nothing
  through it, and none of the 2 rollouts…"*. Sentences now, joined on `. `.
- **`open_` and `resumed` used different predicates** for the same field, `is None` against
  truthiness, so a `resumed_at` of `""` would have counted as neither. One predicate now.
- **`docs/pipeline.md` §5 is Budgets, not suspension**, which the first draft of the stage 4 step
  cited. §1.8 is suspension. Two shipped documents carried the same error; see §5.
- **`ask_on_stdin` blocks and never suspends.** The first draft of the stage 4 step named it and
  then described a channel raising `Suspend`, which is two different channels. The step separates
  them now: one run reaches the channel, and where the design has the run stop, one resume
  continues it.

**Test count 3415 passing**, up 13: six for FT-41, three for FT-25's widening, four in
`test_procedure.py` for the rule, the five rewrites and the consultation scaffold.

**`WORD_BUDGET` for `docs/procedure.md` raised 2600 → 3000**, at 2953 words, with the reason
recorded beside the four earlier raises.

**No format moved.** FT-41 reads `suspensions` and `resumed_at`, which the manifest has carried
since format `0.6`.

## 4. Verification

**A live vLLM run, `Qwen/Qwen3-1.7B` at revision `70d244cc` on port 8001.** A four-node probe
under the scratchpad with a `consult` channel that raises `Suspend`.

| What was run | What it showed |
|---|---|
| One run, stopping on the consultation | `suspension.json` written, manifest `suspensions[0].resumed_at` `null`, two `consultation` records, the first `resolution: "pending"` and the second `answered` carrying `answers` back to it |
| `simple-agents check` at `stage = "build"` | FT-41 `pass`: *"1 of 1 run(s) under runs/ stopped to ask something: 1 still waiting, 0 continued. `Pipeline.resume` is what continues one. This fails from stage `ship`."* |
| The same project at `stage = "ship"` | FT-41 `FAIL`, the taxonomy's own message with `<count>` filled |
| `Pipeline.resume` with the builder's answer | Ran to completion. `resumed_at` set, FT-41 back to `pass`: *"0 still waiting, 1 continued"* |
| The stage 4 code block, run verbatim | Suspends and resumes in one process. `stopped.waiting_for` and `stopped.options` are what the example reads |
| FT-31 on the same project at `ship` | `FAIL` on `answered_by: "builder"`, which is stage 6's existing instruction to swap the channel. The stage 4 step and the stage 6 step agree |
| A real evaluation, 2 rollouts, `end_user=unattended()` | `nodes.pick_a_tone.consultations` 2, all `unavailable`, `answered_by: nobody`. FT-25 prints no note, correctly: the call site was reached |
| The same with `DF5-D20`'s shape reproduced, a call site reading a key nothing upstream emits | `consultations` 0 over 2 rollouts. FT-25 `pass` with the widened note: *"consult is registered and reaches a node. The run read here asked nothing through it. None of the 2 rollout(s) in the newest results file asked through it."* |

The library's own construction refusals fired on the way: `FT-09` on an output schema with no
`unknown` branch, and `Budget` refusing three of four axes. Both are what `docs/procedure.md`
stage 4 says will happen.

**A crashed resume leaves the suspension consumed.** Observed once: the first resume attempt
claimed the suspension, ran the resumed node, and then failed inside a later node of the probe.
`suspension.json` and `suspension.claimed.json` were both gone and the run could not be resumed
again, while the manifest correctly recorded `resumed_at`. This is existing `claim_state` /
`discard_claim` behaviour and not something this item touched. Destination: [`plan.md`
§2.2](../plan.md#L244), the supervisor entry, which is where resuming at scale is decided.

## 5. Doc consequences

**`docs/procedure.md`** gains the four rules for how a question is put, at "What to settle first"
so they govern every stage; the statement at `shape` that an evaluation puts no question to a
person; and the stage 4 step that runs the consultation for real and continues the run, with the
`RunSuspended` example.

**`docs/failure-taxonomy.md`** gains FT-41 in Group G, the index row, the counts line, and FT-40's
stage sentence widened to name both. FT-25's **Check.** paragraph says the note reads the results
file too.

**`docs/conformance.md`** carries the count in five places and the row for FT-41 in the table of
what each check reads, and its sample report gains FT-41's line and the passed count.

**`README.md`**: 40 characteristic failures became 41, twenty-three checks twenty-four.

**Two shipped statements found false, corrected now.** `docs/product.md` §4.1 and
`docs/shipping.md` §4 both cited `docs/pipeline.md` §5 for suspension. §5 is Budgets; suspension
is §1.8. Three other citations of §5 are about budgets and are right. Logged at
[`inventory.md` §2](../runs/dogfood-5/inventory.md#L52).

**`CHANGELOG.md`** records FT-41 as a check a passing project can newly fail, and the five
rewritten questions as text a coding agent may have quoted.

## 6. Left open

- **A `Shelved` question that no later run ever answers has no check.** FT-41 reads suspension
  and resumption; the shelf's equivalent, a question on the list that nothing ever files an
  answer for, is unread. Destination: [`plan.md` §2.2](../plan.md#L244), the supervisor entry,
  which already owns resume-when-answered at scale and is the place that evidence lands.
- **`unevaluated_effects`'s scaffold still asks the builder something only the coding agent can
  know** in one clause, which this item changed to *"work out which of them the project has
  recorded"*. Whether the other 46 scaffolds carry the same shape was not audited; only the 47
  `ask` fields were. Destination: [`plan.md` §1 `P3-3`](../plan.md#L38), the shipped-document
  review.
- Beyond those two, destination: nothing.
