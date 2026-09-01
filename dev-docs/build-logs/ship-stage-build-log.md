# The `ship` stage — the sitting

Held 2026-08-15, and `runs/dogfood-protocol.md` has the outcome. The fifth stage that
[`consultation-build-log.md` §3](consultation-build-log.md#L246) decided exists and did not
design. The subject: what a project does at the point where somebody other than the builder
starts using what was built, and what a gate can read about it.

**What was settled going in, and none of it was reopened.** The stage exists, it is called
`ship`, live runs mark themselves as live so they are separable from development runs and from
what the checks read, and the tier ladder does not change: shipping is not a tier, and `trained`
sits above `evaluated` on the improvement ladder. What the gate asks was already narrowed to
*"is this fit for someone to use, and is what they use separable from what it was built with"*,
rather than *"is this any good"*, which `measure` answers.

**Built the same day**, and **§6 is the build**: what shipped, the three decisions the sitting
did not take, what the build found that the sitting did not, and what the live runs showed. §4
is what it had to touch and §5 is what the sitting did not settle.

---

## 1. What was verified against the artifacts, before any design

`runs/dogfood-protocol.md` §1's rule. It earned its place once: the collision this sitting was called to
resolve is not a consequence of adding a fifth stage, and reproducing it changed where the fix
goes.

### 1.1 The collision is in the shipped suite today, with no `ship` stage involved

A project at `tier = "prototype"`, `stage = "build"`, every required entry answered, and one file
under `evals/results/`. `simple-agents check` reports both of these:

```
  FAIL  FT-24  Elicitation skipped                                brief.toml

        Required brief entries have no answer at stage `measure`: `improvement, leakage,
        too_similar`.

  FAIL  FT-29  The project has no current account of itself       brief.toml, idea.md

        ... `the brief confirms idea.md at stage 'build' and the project is at 'measure'`

    --  FT-01  No evaluation at all
        Fires at tier evaluated, and this project claims prototype.
    --  FT-02  No held-out split
        Fires at tier evaluated, and this project claims prototype.
```

The measurement checks report that they do not apply to this project, and the elicitation gate
in the same report demands the measurement questions.
[`checks.py`, `ft_24`](../../src/simple_agents/conformance/checks.py#L522) calls
[`stages.py`, `reached`](../../src/simple_agents/conformance/stages.py#L98) with
`has_results=True`, which moves any project with a results file to `measure` whatever its tier.

**Two things follow.** The fix is not an accommodation for `ship`; it repairs something already
shipped. And **it belongs in `reached` rather than in the question set**, because FT-29 makes the
same demand through a different path: filtering `required_at` alone would leave the report
half incoherent.

### 1.2 The counts in the brief for this sitting

| Claim | Checked | Result |
|---|---|---|
| 33 questions, 23 required, brainstorm 13 / shape 6 / build 10 / measure 4 | `QUESTIONS` in [`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L83) | exact |
| `checks.py` registers eleven checks | `CHECKS` | exact |
| The taxonomy has 31 entries | `docs/failure-taxonomy.md` §11 | **30**, FT-01 to FT-30. `FT-31` is the next free ID |

### 1.3 The marker the gate needs exists, and one half of it does not reach the manifest

[`pipeline.py`, `_tool_entry`](../../src/simple_agents/pipeline/recording.py#L147) records `answered_by`
and `permission` on every tool entry, set on a consultation tool and `null` on every other kind.
Nothing under `src/simple_agents/conformance/` reads either. That is what
`consultation-build-log.md` §5.1 predicted when it argued for building DF4-I01 first, and it holds.

**What is not there.** `manifest.py` records `role` and does not record the envelope's
`end_user`. A run that replaces the channel with `env.with_end_user(...)` records the
replacement on each `consultation` and nowhere else, so a live run that asked nothing looks, to
the manifest, like whatever the pipeline registered. §2.4 is what that costs and what is done
about it.

### 1.4 `docs/procedure.md` has three words of room

1,352 words against `WORD_BUDGET = 1355` in
[`tests/test_procedure.py` `test_the_six_are_ordered`](../../tests/test_procedure.py#L114). A fifth stage does not fit inside
it, so the budget is part of the decision rather than a detail of the build (§2.5).

### 1.5 What could not be verified

**Any of this against a project that has shipped.** None has. Every decision here is a claim
about behaviour no run has met, which is the standing `runs/dogfood-4/inventory.md` `DF4-Q1` already put
on the consultation sitting's decisions, and it applies to this sitting in full.

---

## 2. The decisions

### 2.1 The cumulative-requirement collision

**Ruled: the tier decides how many stages the project has.** `consultation-build-log.md` §3's
third option, implemented in `reached` rather than in the question set, per §1.1.

- **`prototype` includes four stages**: `brainstorm`, `shape`, `build`, `ship`. **`evaluated` and
  `trained` include five**, with `measure` between `build` and `ship`. `ship` is in every tier,
  because shipping is not a tier.
- **`reached()` never moves a project into a stage its tier excludes.** A results file at
  `prototype` no longer moves it to `measure`.
- **A brief declaring a stage its tier excludes is refused** at read time, naming the two lines
  that fix it. `stage = "measure"` with `tier = "prototype"` says both that the project measures
  and that it claims no number.
- **A deferral to an excluded stage is refused** for the same reason: `deferred_to = "measure"`
  at `prototype` is an answer that never comes due.
- `up_to(stage)` takes the tier and stops being a prefix slice. Ordering stays global in
  `STAGES`; inclusion is per tier.

**What it resolves, in one sentence.** *A project may not ship, at a tier that claims a number,
what it has not measured.* A project at `evaluated` still cannot ship unmeasured and FT-01 still
fires; a project at `prototype` goes `build` → `ship`.

**What it costs, recorded rather than argued away.** A project can produce a results file,
declare `prototype`, and never be asked `improvement`, `leakage` or `too_similar`. Today it is
asked. The mitigation is the one the library already rests on: `docs/procedure.md` says lowering
the tier is correct only where the project reports no number, and nine failure messages say the
same. Where the tier drops questions the artifacts would otherwise have required, the report
says so, so the omission is visible rather than silent.

**Weighed and not taken.**

- **Shipping requires measuring.** Defensible on the library's thesis, and it refuses the
  category `how_far`'s own scaffold names: *"Most answers are `build` for something they will use
  themselves."* That builder either invents an evaluation or turns the gate off.
- **`ship`'s questions are its own and inherit nothing.** One exception in a rule that has none,
  and the exception is the hole the rule exists to close: a project could declare `stage = "ship"`
  having never been asked what a correct answer is, what the budget is, or what its tools do.
- **Filtering inside `required_at()`.** Cheaper, and §1.1 is why it is wrong: FT-29 would still
  demand `understanding_confirmed_at = "measure"` from a project the tier says is not measuring.

### 2.2 How a live run marks itself

**Ruled: `RunEnvelope(live=True)`, with `env.live()` beside `env.with_role(...)`, recorded on the
manifest, and `runs("runs/", live=True)` reading them back.** Manifest `0.23` to `0.24`.

Two axes rather than one. `role` says what the run is **for**: `agent`, `labelling`, a judge, an
ablation arm. `live` says whether a real end user is on the other end of it. A live run is a run
of the agent, so `role="labelling", live=True` is refused.

**Which runs the checks read.** FT-13 and FT-14 read the newest run that is **not** live. Where
every run under `runs/` is live, the newest live run is read and the report says so: failing a
project that recorded everything would be a false positive, which
`docs/failure-taxonomy.md` §1.2 calls a bug in the check. The precedent is
[`artifacts.py`, `_latest_run`](../../src/simple_agents/conformance/artifacts.py#L423), which
already prefers a run that finished and falls back to the newest when none did.

**Weighed and not taken.**

- **`role = "live"`.** No new field, and `_latest_run` filters `role == "agent"`, so every live
  run drops out of FT-13 and FT-14 unless the filter learns a second name. The field stops
  answering one question.
- **A second run directory.** `runs/` is what the checks read and what `runs()` walks. A second
  convention doubles the layout for a boolean.
- **Infer it**, from the channel or from the absence of an evaluation. This is `brief.py`'s own
  argument about the tier: FT-01 fires exactly when a project claims `evaluated` and has none, so
  reading a claim off the artifacts is what stops a check from firing at all.

### 2.3 The question set

**Ruled: four questions, three required.** The stage's work is mostly a check, and the moment a
project reaches `ship` is the worst moment to put a wall in front of it.

#### `someone_there` — required

> **Will anyone be there when this runs for real?**

[`consultation-build-log.md` §7.3.1](consultation-build-log.md#L521)'s question, in its own
words. **Scaffold:** read the `consultation` entry back to the builder first. Three shapes, and
the library carries each: a person who answers while the run waits, which is `ask_on_stdin` or
the project's own channel; a person who answers later, which is `Suspend` and `Pipeline.resume`;
nobody, which is `unattended()` and a run where every consultation returns `Unavailable`. An
agent that cannot finish without an answer and a run nobody attends do not go together, and this
is where that is found.

**Why it is stable, which is what §7.3.1 settled.** *Who the end user is* is asked at
`brainstorm`. *Who answers a given run* is configuration and not a builder question. What is
left is neither, has one answer, and decides whether a design resting on consultation can ship.

#### `live_records` — required

> **The runs a real person makes are recorded the way the builder's were. What may be kept?**

**Scaffold:** say what a run keeps, then what changed. Every run writes a trajectory and a
cassette holding the whole prompt and the whole response, plus counts, timings, tokens, seeds and
cost at every rate; redaction removes credentials and the values the project declares and nothing
else. What changed is that the material is the end user's rather than the builder's. Offer the
three with what each gives up: `Trajectory.full()`; `Trajectory.sampled(rate)`, decided per run
as it starts; `Trajectory.sampled(0.0)`, which drops the payloads and gives up replay, re-scoring
and any later use of the runs as training data. Read the `keep_payloads` answer back first: it
was given about the builder's own runs.

**Why a new entry rather than re-asking `keep_payloads`.** Two answers under one name is a
per-entry re-confirmation mechanism, which is DF4-I03's shape, and it overwrites the first answer
instead of showing the change. A second entry keeps both visible.

#### `watching_live` — required

> **What would tell the builder that the agent has stopped being right, and who looks?**

**Scaffold:** every live run is recorded, and `runs("runs/", live=True)` reads them back. Offer
the forms: a person reads a sample of live runs on a schedule; the end user has a way to say an
answer was wrong and that judgement lands in `evals/labels.jsonl`; a fresh evaluation at an
interval against the same held-out split. Ask which, and who does it. "Nobody, the builder will
notice" is an answer, and recording it makes it a choice rather than an omission.

**What it rests on.** `DF4-D1` was found by a second session on a different task, reading a store
by accident, two days after the number read green. The library's after-surfaces have no other
reader: `runs()`, `Trajectory.sampled`, memory scoped to one end user, and `simple-agents.md`
§5's second rung, which is SFT over the project's own successful traces.

#### `unevaluated_effects` — optional

> **Which of the things the agent does for real were never exercised by an evaluation?**

**Scaffold:** an evaluation refuses a rollout over an `irreversible` tool, and over a
`spends_money` one with no declared ceiling, and the path it offers instead is
`suite.record(...)` followed by `Cassette.replay(path)`, where each distinct call is performed
once and every rollout after that is served from the file. List the tools from the manifest's
entries with what one call does, ask which of them the project has actually recorded, and ask
what should happen the first time one runs for a person who is not the builder.

**Optional, and it applies exactly when a `spends_money` or `irreversible` tool is declared.** No
dogfood evidences it; the argument is structural. §5.1 is Thilina's objection to the rule it
rests on, which is why the scaffold points at the recording path rather than at the refusal.

#### One existing question changes

`how_far`'s scaffold maps each stopping point to a tier, and `docs/procedure.md` says the same
in one line: *"The first says which stage this project stops at and so which tier."* **`ship`
decouples them.** A project may go live at any tier, and the tier says whether a number is
claimed. Both sentences are rewritten with the stage, or the question cannot be answered for.

#### Weighed and not taken

- **A question about what the end user actually gets, and whether it came from a version anybody
  measured.** That is `DF4-D1`, and `consultation-build-log.md` §6 ruled it to **DF4-I02** so it is
  not decided inside a sitting about something else. §3 says what the gate therefore does not
  look at.
- **A rollback condition at ship.** `abandon_condition` at `brainstorm` is the same shape, and
  asking it again is a re-read mechanism, which is DF4-I03's.
- **A live cost ceiling.** `budget` bounds a run, and the library enforces nothing per end user
  or per day, so the answer would land nowhere.
- **Folding attendance into `consultation`.** §7.3.1 of the consultation log is what that costs:
  the same overload was written and reverted the night it was written.

### 2.4 What the gate reads

**Ruled: the suite at stage `ship`, plus one new entry, and no new artifact is required to run
it.**

Three of the four things the gate needs already exist and gain nothing but the new stage:

| | What it does at `ship` |
|---|---|
| **FT-24** | Requires the four questions above |
| **FT-29** | Requires `understanding_confirmed_at = "ship"`, so `idea.md` is read again before anyone else uses it |
| **FT-30** | Every decision settled |

#### FT-31 — shipped on a development channel

*Surface: artifact · Tier: prototype · Stage: ship*

**What it reads.** `answered_by` on the consult tool's manifest entry, and `answered_by` on the
consultations of a live run where one exists. The trajectory wins over the manifest, under the
rule the consultation build already set: the manifest carries what the project declared and the
trajectory carries what the run did.

| `answered_by` | At `ship` |
|---|---|
| `end_user` | passes |
| `nobody` | passes, with the report naming the `someone_there` answer as where it is settled |
| `coding_agent`, `simulated`, `canned` | **fails.** A stand-in reaching a real person |
| `builder` | **fails.** `builder` is the author standing in for the end user. Where the builder *is* the person the agent is for, the declaration is `end_user`, and [`consult.py`, `ask_on_stdin`](../../src/simple_agents/builtins/consult.py#L561) already draws that line: a terminal is the builder's while a project is being built and the end user's once a CLI agent ships |

A project with no consultation tool passes, with the detail saying so.

**The check never reads the brief**, which is what keeps it clear of FT-25 and of DF4-I03. FT-25's
check is *the brief says ask, so a tool must be registered*, and it is built inside DF4-I03. FT-31 is
*a tool is registered and it reaches a stand-in*, read entirely off a run.

**Where a project is at `ship` and no run is marked live**, FT-31 passes and the report says the
mark exists and nothing carries it. The gate runs before the agent is handed over, so requiring a
live run before the gate that says it is fit for one is backwards. This is the one place where
`ship` differs from `build`, whose gate does read a run.

**One gap it exposes, and what closes it.** §1.3: a project that registers a development channel
and replaces it per run with `env.with_end_user(...)` records the replacement only on
consultations, so a live run that asked nothing looks like the registered channel. **The
envelope's declared answerer goes on the manifest** in the same bump as `live`, so FT-31 reads a
declaration rather than an absence.

#### Stage-gated checks are new machinery

Every check today fires by tier alone, in one place in
[`run.py` `_not_applicable`](../../src/simple_agents/conformance/run.py#L715). FT-31 must not fire on a project that
has not shipped, so the entry header gains an optional third field, `· Stage: ship`, the
taxonomy's `_SURFACE_TIER` regex learns it, and `run.py` gets the symmetric skip: *"Fires at
stage `ship`, and this project is at `build`."* The report's `--` gains that second meaning and
its summary line stops naming the tier alone.

**Weighed and not taken:** registering the stage beside the check in `CHECKS`. Same behaviour,
and a reader of `docs/failure-taxonomy.md` could no longer see when FT-31 fires.

#### A property worth naming, and not overclaiming

Under §2.1 a live run moves a project to `ship` through `reached()`, so a project that quietly
starts being used is held to `ship`'s questions at its next `check` without anyone declaring
anything. That is the first enforcement in the library triggered by an artifact appearing rather
than by a declaration. **It is not the change-triggered enforcement `DF4-D7` asks for**, and §3
says so. It also means marking a run live costs something, which is the same incentive as
declaring a lower tier; the library already lives with that and says so in
`docs/conformance.md` §1.1.

### 2.5 The document the stage points at

**Ruled: a new `docs/shipping.md`, with `docs/procedure.md` gaining a terse stage 5 that points
at it.**

`consultation-build-log.md` §3 already found the argument: `Trajectory.sampled(rate)`, `runs()`,
memory scoped to one end user, and suspend and resume have no other reader. Five mechanisms exist
for live use, are documented in five places by what they do, and nowhere says when a project
reaches for them. `docs/index.md`'s "when to open it" column has no row for after.

**What it holds.** What a live run is and how it declares itself; what a live run records and
what sampling costs; reading live runs back with `runs()`; the channel at `ship` and what FT-31
reads; consultation with nobody there against consultation that waits; memory scoped to one end
user; and what live traces feed on the improvement ladder. **What it does not hold:** deployment,
serving, scheduling and monitoring, none of which the library ships.

**The word budget moves, and it is a convention that shipped.** §1.4: `docs/procedure.md` has
three words of room, and the test's own reason is that the skill must not restate the documents.
A fifth stage is new content rather than restatement, so `WORD_BUDGET` goes to 1600 and stage 5
stays short by leaving the detail in `docs/shipping.md`. **Approved by Thilina at this sitting**,
as a change to a shipped convention rather than a detail of the build.

**One trap for the build.** Stage 5 must carry no *"N questions, M required"* sentence.
`tests/test_procedure.py` reads those against `questions_at(stage)` cumulatively, and under §2.1
the cumulative count at `ship` depends on the tier.

---

## 3. What `ship` does not close, and this is the paragraph a later session needs

**It does not close `DF4-D7`.** Every enforcement the library has fires on **time**, a project
reaching a point. Every failure dogfood #4 found fires on **change**, something moving with
nothing re-reading what it invalidated. A fifth stage adds one more gate at the end of a longer
road and does not govern the road: everything in that 60% would still have happened before this
gate fired. `DF4-D7`'s own text says *"This is not an argument for a fifth stage."* The remaining
half is DF4-I03's, and §2.4's artifact-triggered stage move is not it.

**It does not close `DF4-D1`.** The gate looks at runs and does not look at the product. **DF4-I02**
owns whether the library has anything to say about a project that owns state, and if DF4-I02 takes
the wide reading, `ship` is where its check or its question lands. The slot is left empty
deliberately and named here, so its absence is not read as a ruling.

**It does not close `DF4-D2`.** Reading one brief entry against another is DF4-I03's, and FT-31 is
built to read a run rather than the brief so that it takes no bite out of that.

---

## 4. What the build has to touch

| | |
|---|---|
| `stages.py` | `STAGES` becomes five; `up_to` and `reached` take the tier; a tier-to-stages map |
| `brief.py` | Refuse a stage the tier excludes, and a deferral to one |
| `elicitation.py` | Four questions; `how_far`'s scaffold |
| `checks.py`, `run.py`, `taxonomy.py`, `report.py` | FT-31; the stage gate and the `--` it prints; the note where a tier drops questions |
| `envelope.py`, `manifest.py` | `live=True`, `env.live()`, `runs(live=)`, the envelope's declared answerer on the manifest, manifest `0.23` → `0.24` |
| `artifacts.py` | `_latest_run` prefers a run that is not live |
| `docs/` | New `docs/shipping.md`; `procedure.md` stage 5 and the tier sentence; `conformance.md` §1.1 and §3; `failure-taxonomy.md` FT-31, §11 and the counts; `run-envelope.md`; `tools.md` §4.6.2; `index.md` |
| `tests/test_procedure.py` | `WORD_BUDGET` to 1600 |
| `CHANGELOG.md` | The manifest bump. **`design/trajectory-format-changelog.md` gets nothing**: it is keyed on trajectory versions and the trajectory did not move |

**The two names were settled after the sitting**, on Thilina's ruling. The brief key is
`watching_live` rather than `still_working`, which sits beside `keep_payloads` and `who_labels`:
each is named for what the builder has to arrange rather than for the condition it protects.
FT-31 is *"Shipped on a development channel"* rather than *"The agent went live with nobody to
ask"*, which is the voice of every other entry title, names the artifact the check reads, and
avoids being wrong about `simulated`, where somebody answers and it is the wrong somebody.

---

## 5. What this sitting did not settle

### 5.1 An evaluation over a tool that cannot be undone

**Raised by Thilina against `unevaluated_effects`, and it is a challenge to
`simple-agents.md` §9 item 5**: *"Evaluation shouldn't refuse an irreversible tool. What it
should do is make sure everything is in place to handle what an irreversible tool will do."*

**One correction to what was put to him.** The sitting said an evaluation refuses an
`irreversible` tool outright. The docstring says that; the code does not.
[`runner.py`, `_refuse_unsafe_tools`](../../src/simple_agents/evaluation/runner.py#L2129) returns
immediately when the cassette is replaying, and the refusal message names the path:
`suite.record(...)` performs each distinct call once, live, and `Cassette.replay(path)` scores
every rollout after that with the tool's body never running. The library does not force a builder
to ship what no evaluation touched; it forces the effect to happen once rather than
`examples × k` times.

**What survives the correction, which is most of it.**

1. The recording pass performs the action for real, and nothing in the library says what should
   be in place before it does.
2. A replayed rollout is served the recorded result, so a call whose arguments the recording
   never covered is a cassette miss rather than an effect. The behaviour most worth measuring is
   the one replay structurally cannot reach.
3. `irreversible` is one class covering effects that need different handling: an email to a
   customer, a deleted row, a placed order. The class is a refusal trigger and carries nothing
   else.

**Where it goes.** `plan.md` §2.2, as a design question deferred and undecided, with the survey
Thilina asked for as its first work: the common kinds of irreversible tool, what each does, and
what "in place" means for each. It moves `simple-agents.md` §9 item 5 only by defeating that
entry's rationale in writing.

### 5.2 The cross-artifact verification, which widens DF4-I03

Thilina, at this sitting: the re-read at `ship` is right, other checkpoints need thinking about,
and it should be a verification across `idea.md`, `BUILD-LOG.md` and the code.

**What is already true.** FT-29 fires at every gate, not only at `ship`: §1.1's reproduction
shows it refusing a confirmation at `build` from a project at `measure`. Advancing any stage
means re-reading the file and writing the new stage. `ship` adds one instance of a mechanism that
is already there.

**What is missing.** FT-29 reads that five sections exist and that the confirmation names the
current stage; it cannot read whether any of it is true. And **nothing in the library reads
`BUILD-LOG.md`**: `docs/procedure.md` asks for one in one line and no check opens it, which is
the mechanical half of the dogfood-4 note that the coding agent struggles to keep it live.

**Where it goes.** DF4-I03, whose frame widens from brief-against-code (`DF4-D8`, `DF4-D9`) to
`idea.md`, the brief, the build log and the code. Recorded here so that sitting opens with the
wider frame rather than the narrow one.

---

## 6. The build, 2026-08-15

Built the same day as the sitting. §4's list in one pass, one manifest bump, and one new shipped
document. **2230 tests pass**, `prose_check` and `check_citations` clean, and the wheel is
rebuilt with `docs/shipping.md` in it.

### 6.1 What shipped

| | |
|---|---|
| Five stages, and the tier decides which a project has | [`stages.py`, `STAGES_BY_TIER`](../../src/simple_agents/conformance/stages.py#L49); `up_to(stage, tier)`, `reached(..., has_live_run=, tier=)`, `stages_for(tier)`, which returns all five for a tier it does not know so a caller that cannot say is held to everything |
| Two refusals | A brief declaring a stage its tier excludes ([`brief.py`, `_outside_the_tier`](../../src/simple_agents/conformance/brief.py#L298)), and an entry deferred to one |
| A live run | `RunEnvelope(live=True)` and `env.with_live()`; `runs("runs/", live=True)`; `RunHandle.live`; `live` on the manifest; `role` other than `agent` with `live=True` refused |
| The run's own channel on the manifest | `end_user: {"answered_by": ...}`, `null` where the run used the registered one ([`pipeline.py`, `_end_user_entry`](../../src/simple_agents/pipeline/recording.py#L115)) |
| Four questions at `ship` | `someone_there`, `live_records`, `watching_live` required, `unevaluated_effects` optional; `how_far`'s scaffold separates the stage from the tier |
| FT-31 | [`checks.py`, `ft_31`](../../src/simple_agents/conformance/checks.py#L796), reading a live run's consultations first and the manifest otherwise |
| The stage gate | A taxonomy entry may carry `· Stage: ship`; [`run.py`, `_not_applicable`](../../src/simple_agents/conformance/run.py#L715) prints *"Fires at stage ship, and this project is at build."* |
| Which run the checks read | [`artifacts.py`, `_latest_run`](../../src/simple_agents/conformance/artifacts.py#L423) prefers a run that is not live, falls back to one, and the report says when it did |
| `docs/shipping.md` | New, and `docs/procedure.md` stage 5 points at it. Manifest `0.23` to `0.24` |

### 6.2 The three decisions the sitting did not take

**`env.live()` is `env.with_live()`.** The sitting named the field `live` and the method
`live()`, which a slots dataclass cannot have both of. Two things settled it beyond the clash.
The five existing copies are `with_run_dir`, `with_role`, `with_trajectory`, `with_end_user` and
`with_cassette`, so `with_live` is where a reader already looks. And **the method needs an
argument the sitting's name could not carry**: `with_live(False)` is what an evaluation uses to
force a rollout back, so a no-argument `live()` would have left that to a private path.

**An evaluation's rollouts had to be made not live, and the sitting did not say so.** A project
whose envelope is the one it ships with would have written every rollout as a live run, so
`runs(live=True)` would return rollouts nobody asked for and FT-13 would certify one.
[`runner.py`, `_scoped_for_rollout`](../../src/simple_agents/evaluation/runner.py#L2556) clears it
alongside the memory store and the stand-in, which is where the same argument already lives.

**`simple-agents questions --stage ship` needed a `--tier`.** Without one it lists `measure`'s
questions to a project that has no `measure` stage, which is the collision §2.1 removed arriving
back through the command. `--tier prototype` drops them, and a tier the command does not know is
refused rather than ignored.

### 6.3 What the build found that the sitting did not

**The library's own example project carried the contradiction.**
`tests/fixtures/projects/prototype/brief.toml` declared `tier = "prototype"` with
`stage = "measure"` and `understanding_confirmed_at = "measure"`, and deferred `prices` to
`measure`. So did `tests/test_procedure.py`'s brief helper, on every brief it wrote, and the
helper behind the FT-14 tests. Four places, all written by us, all saying a project reports no
number and is measuring. §1.1 measured the collision in the report; this is the same thing in
the fixtures, and it is why the refusal is worth its friction.

**Six copy methods each enumerated every field, and a seventh field had to be added to all of
them.** A field forgotten in one is how a live run stops being one on the next `with_cassette`.
They are `dataclasses.replace` now, one line each, and a test holds every copy to carrying
`live` forward. This is the same shape as `simple-agents.md` §10's redaction rule: what is
enumerated should be what is skipped, not what is covered.

**The report's last line had to stop naming the tier.** It read *"7 not applicable at tier
prototype"*, which is false as soon as one of those is inapplicable by stage. Each check's own
line carries the exact reason and the report's second line names the tier, so the summary now
says *"7 not applicable"* and nothing is repeated. `docs/conformance.md` §3's sample report and
one test moved with it.

**FT-31's passing note carries two facts rather than one.** A project can both register no
consultation tool and have no run marked live, and the first implementation returned whichever
it tested first. Found by a test that expected the second and got the first.

**`Artifacts.discover` walks the run tree twice**, once for the newest development run and once
for the newest live one. Measured over a synthetic 3,000-run project: 0.22s for both walks
together, against dogfood #4's 3,293 runs. Left as two named functions.

### 6.4 What the live runs showed

**Gemini, `gemini-3.1-flash-lite`, and vLLM, `Qwen/Qwen3-1.7B`.** One development run and one
live run of a consulting agent through each, then `simple-agents check` over the project.

- The two runs are separable: `runs(live=True)` returned the live one on both backends, and the
  manifest carried `live: true`.
- **FT-13 and FT-14 read the development run and FT-31 read the live one**, in the same report.
- FT-31 passed against `answered_by="end_user"` and failed against `coding_agent` with the
  permission recorded, naming the live run's trajectory as what it read.
- The vLLM arm's consultation resolved `answered` and the Gemini arm's `unmatched`, which is the
  channel returning prose against a question that offered options. Both record
  `answered_by: end_user`, which is what FT-31 reads.
