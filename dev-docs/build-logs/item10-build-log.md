# Item 10 — build log

**Kept while building, not reconstructed at the end.** On the precedent of `item9-build-log.md`,
`item8a-build-log.md`, `item8g-build-log.md` and `item8b-build-log.md`.

The design of record is `archive/plan-history.md` §3.1 item 10, which is one line. §1 records what was measured
before the sitting, §2 the sitting, §3 where building sharpened a decision, §4 where it turned
out not to hold, §5 what the build found that is nobody's design, §6 doc consequences, §7
existing tests that had to change.

**Status: sitting held 2026-08-06, building.** Baseline 1015 tests at `7b0ffb7`.

**This item absorbs `archive/plan-history.md` §3.1 items 11 and 12**, on Thilina's ruling at §2.2.

---

## 1. What was measured, before any design

Item 8b §1 is the standard: every claim is read off a file the library produced or off a live
run, never off a document. The entry for this item is a single line, so there is no premise to
measure. What is measurable instead is the thing the skill has to drive and the thing its gates
have to invoke, so §1 builds a conformance-passing project from nothing and watches
`simple-agents check` at every intermediate state.

The probes are `scratchpad/build_trivial.py` and `scratchpad/probe_minimal_pass.py`. The first
builds a trivial agent over a three-document collection, runs it live against Mistral
`mistral-small-2603`, evaluates it at k=3 over a held-out split, and runs the shipped command
after each increment. The second measures the other end: how little a project can hold and pass.

### 1.1 The seven states of building a trivial agent, and what the gate saw at each

`scratchpad/trivial/`, built one increment at a time. The exit status and the report are the
shipped command's own output, captured in `scratchpad/trivial_states.json`.

| State | What the project held | exit | Report |
|---|---|---|---|
| A | an empty directory | **2** | the brief refusal, naming the two lines to write |
| B | `brief.toml`, `tier = "prototype"` | 1 | FT-13 fails, FT-14 blocked, four not applicable |
| C | **plus `agent.py` and a three-document corpus** | 1 | **byte-identical to B** |
| D | plus one live run under `runs/` | **0** | FT-13 and FT-14 pass |
| E | the brief changed to `tier = "evaluated"` | 1 | FT-01 fails, three blocked |
| F | **plus `evals/questions.jsonl` and `evaluate.py`** | 1 | **byte-identical to E** |
| G | plus the evaluation run, 3 examples × 3 rollouts | **0** | six passed |

**Two of the seven increments are invisible to the gate.** Writing the agent changed nothing in
the report, and neither did writing the labeled example set and the scoring function. Every
check is `artifact` surface, so what a gate can observe is the brief, a run directory and a
results file, and nothing else the project contains.

**The whole ladder has four observable rungs**: no brief (exit 2), a brief with no run, a run,
and a results file. A gate placed anywhere else in the procedure has nothing to read.

### 1.2 A hand-written run directory passes the prototype tier

`scratchpad/probe_minimal_pass.py` writes `brief.toml`, one `manifest.json` of six keys and one
`trajectory.jsonl` of one record, by hand. The library is never called.

```
0 failed, 2 passed, 4 not applicable at tier prototype     exit 0
```

Three files, 46 lines, no envelope, no pipeline, no model call. **This is not an adversarial
case.** It is the shape a coding agent produces when it writes its own logging instead of
finding `RunEnvelope`, which is the failure class `simple-agents.md` §1's coding-agent objection
describes. The prototype tier's two gates read whether files of the right shape exist, and a
plausible artifact of the right shape is exactly what a coding agent is good at producing.

### 1.3 A pipeline that makes no model call fails FT-14

The same probe, run through the library rather than by hand: a `Pipeline` of one `Deterministic`
node, run inside a `RunEnvelope`.

```
[manifest] models: {"configured": null, "observed": []}
FAIL  FT-14  Model version unpinned   ... The manifest records model alias `none recorded`
```

A pipeline with no model client is a legitimate thing to build and the prototype gate refuses
it, telling the project to pin a model it does not use. So the two `prototype` checks pass a
project the library never touched (§1.2) and fail one it did. **Fixed at §8.1.**

### 1.4 The library's refusals outnumber its checks by a factor of nineteen

| Surface | Count |
|---|---|
| conformance checks a gate can invoke today | **6** |
| `raise ConfigurationError` sites in `src/simple_agents/` | **115** |

By module: `graph.py` 14, `tools.py` 13, `nodes.py` 12, `evaluation/examples.py` 11,
`evaluation/runner.py` 9, `pipeline.py` 8, and the rest across sixteen more.

The 115 fire when an object is constructed or a run starts. The 6 fire when a command is run
over files. A gate built only on the command reaches 6 of 121; a gate that also makes the
project construct its pipeline and run it once reaches most of the rest, and this is what
states C and F of §1.1 were unable to see.

### 1.5 A brief carrying no entries at all passes six of six at tier `evaluated`

State G's brief is two lines, `tier` and `stage`, with no `[entries.*]` table. The report is
`0 failed, 6 passed`. FT-24 has no check (`item9-build-log.md` §2), so **the occurrence of
elicitation is unenforced at every tier today**, and a project that asked the builder nothing is
indistinguishable from one that asked everything.

### 1.6 `stage` is inert, and any string passes

Verified by running rather than by reading. `brief.toml` carrying
`stage = "not-a-stage-anyone-defined"` produces the same report as one carrying `stage =
"measure"` or no stage at all. `brief.py:94` validates that it is a non-empty string; nothing
else in `src/`, `docs/` or `tests/` reads it. `docs/failure-taxonomy.md` FT-24's failure message
already interpolates `<stage>`, so the vocabulary is cited by a message that cannot yet be
emitted.

### 1.7 The three artifact locations are conventions no document states as requirements

`conformance/artifacts.py:22` fixes `brief.toml`, `runs/` and `evals/results/`. Measured by
running a project whose envelope wrote to `output/` instead:

```
FAIL  FT-13  No trajectory logging
      No usable trajectory log was found for this run: `no run directory under runs/`.
      ... Run the agent inside the run envelope, which records by construction.
```

The project **did** run inside the envelope. The message describes a different failure, because
the check cannot tell a missing envelope from a run directory somewhere else.
`RunEnvelope(run_dir=...)` defaults to `runs`, so this bites only a project that changed it, and
a procedure that does not state the layout is a procedure that lets a project change it.
**Fixed at §8.2.**

### 1.8 `python -m simple_agents.cli check` prints nothing and exits 0

```
$ python -m simple_agents.cli check tests/fixtures/projects/no-evaluation
$ echo $?
0
```

`cli.py` has `main()` and `_entry_point()` and no `__main__` guard, so the module imports and
returns. The console script on the same project prints the report and exits 1. **A gate written
as `python -m simple_agents.cli check` reports success on every project**, including one with no
brief at all.

### 1.9 There is no procedure anywhere in the shipped surface

Eleven documents, **40,780 words**. Grepping the whole tree for ordering language returns one
sentence:

> `docs/index.md:7` — **Start with `docs/pipeline.md`.** It covers the shape everything else
> attaches to.

`docs/index.md`'s "When to open it" column says when a document becomes relevant and does not
order the work. Nothing says what to do first, what to establish before writing code, or when to
run the check. `__init__.py` exports **83 public names**.

### 1.10 What the trivial build actually had to read, and what it cost

Five of the eleven documents were opened to build §1.1's project: `pipeline.md`, `tools.md`,
`evaluation.md`, `run-envelope.md` and `conformance.md`. That is **18,196 words of 40,780, 45%**.
`failure-taxonomy.md`, 9,084 words on its own, was needed only to read a failure message the
report already prints in full.

**One API error was made and it is worth recording against the maintainer rather than the
document.** `AgentNode(max_steps=6)` was written from a prior about other agent libraries;
`AgentNode` takes `budget=Budget(...)` and `docs/pipeline.md` §2.3 shows exactly that, six lines
long. The document was not opened before the code was written. A cold session has no prior about
this library and a strong one about others, which is the shape the procedure has to interrupt.

### 1.11 Four budget numbers were invented, and the run needed a fraction of one of them

The trivial agent declares `max_tokens=200_000` on the pipeline and `100_000` on the node. The
live run consumed **1,357 tokens** across two model calls and two tool calls.

| Axis | Declared | What one run used |
|---|---|---|
| `max_tokens` | 200,000 | 1,357 |
| `max_steps` | 12 | 2 model calls |
| `max_cost` | `None` | no basis declared |
| `max_wall_clock_ms` | 300,000 | not measurable, the timed run replayed from cassette |

Every one of the four was chosen without evidence. This reproduces
`runs/checkpoint-item5/findings.md` §7 exactly — "session B invented three of its four budget numbers
and said so" — on a build made today by a session that had read that finding. The scaffold that
section proposes, run one example and read what it consumed, was available throughout and was
not used because nothing prompted it.

### 1.12 Two shipped Python libraries already put a skill inside their wheel

`simple-agents.md` §11 item 7 leaves skill-distribution mechanics open. Measured against what is
installed on this machine rather than against a specification:

```
.../site-packages/fastapi/.agents/skills/fastapi/SKILL.md
.../site-packages/typer/.agents/skills/typer/SKILL.md
```

FastAPI's is **1,403 words** with three files under `references/` beside it, and its frontmatter
is two keys, `name` and `description`. The layout is `<package>/.agents/skills/<name>/SKILL.md`.

The wheel this library builds today already force-includes `docs/` to `simple_agents/docs/`
(`pyproject.toml`), so the same mechanism reaches `.agents/` with no new machinery.

**What is not measured, and must not be assumed: whether a coding-agent harness discovers a
skill inside `site-packages` on its own.** Two libraries shipping one is evidence that the
convention exists, not evidence that it is read.

### 1.13 What a skill on this machine looks like, by size

662 `SKILL.md` files are installed here across harnesses and plugins.

| | Words |
|---|---|
| median | **827** |
| mean | 1,160 |
| 10th percentile | 210 |
| 90th percentile | 2,621 |
| longest | 16,783 |

254 of the 662 carry exactly one file beside `SKILL.md` and 46 carry none; the rest use a
`references/` directory, which is the progressive-disclosure shape FastAPI's uses.

**The shipped documents are 40,780 words and the median skill is 827.** A skill that restates
the library is not a skill, and a skill that duplicates any part of `docs/` is a second copy of
something that moves, which is `CLAUDE.md`'s drift hazard in a new place.

---

## 2. The sitting, and what it settled

Held 2026-08-06, after §1's measurements. Eight questions were put and all eight were answered.
Q1 was answered in two passes: the first recommendation rested on an unmeasured claim about skill
discovery and was sent back (§2.1).

The entry is one line, so unlike items 8g and 8b there was no design of record to be wrong.
What §1 supplied instead was the ceiling on what a gate can see, and six of the eight questions
turn on it.

### 2.1 The skill ships in the wheel, and a command registers it

**Settled: force-included into the wheel at the `.agents/skills/` convention, plus
`simple-agents init`, which the builder runs once after installing.**

The first recommendation was the wheel path alone plus a shipped document, offered with the
caveat that whether a harness discovers a skill inside `site-packages` was unmeasured. Thilina
asked directly whether it could be automatic on `pip install`. It cannot, and the answer is
structural rather than a limitation of ours:

| Mechanism | Why not |
|---|---|
| a post-install hook in the wheel | The format has none. An installer unzips; only the dead egg format ran scripts |
| the harness reading `site-packages` | Measured: Claude Code does not read `.agents/` at all. [Library Skills](https://library-skills.io/) exists to bridge exactly this and says so |
| a `.pth` file, which does execute | It fires at every interpreter startup, not once at install, and would write into a user's filesystem on every `import` |

**What decided the shape is that the two levels have different failure modes.** The content is
already reachable with no command: 22 files in `src/` carry 46 citations of `docs/*.md` and
`docs_path()` returns the installed directory, so an agent that reads any docstring is pointed
into the docs. What that does not buy is the skill *firing*. A document read at the top of a
session is 40,000 tokens back by the time the evaluation gate matters, and `simple-agents.md`
§3.1 already says prose depending on faithful recall drifts.

**Thilina's ruling on who runs it:** the builder, once, immediately after installing, rather than
the coding agent as step 0 of the procedure. The reason is ordering: a skill loaded before the
agent starts work is context it has while deciding what to build, and an agent that inits itself
has already decided. The agent may still run it where the builder forgot.

The destination is an argument rather than a hard-coded path: `.agents/skills/` by default,
`--claude` for `.claude/skills/`, `--to` for anything else. Symlinked so the skill tracks the
installed version, with `--copy` where symlinks are impractical.

### 2.2 Items 10, 11 and 12 are one item

**Settled, on Thilina's argument: thirteen questions is smaller than it sounds, and with all
three built the dogfood can run.**

The recommendation offered was to fold only item 11's "what a stage means to a project" into
this item and leave item 12 separate, on the ground that its questions are earned from evidence
and folding would rush them. That was overruled, and the counting supports the ruling: the
questions are 7 in `runs/checkpoint-item5/findings.md` §7, 6 in `runs/checkpoint-item7/findings.md` §8 and
4 seeds in `plan.md` item 12, so **17 with three overlaps, 14 or 15 distinct** — and every one
already ships with a scaffold and a piece of evidence, which is the expensive half and is
already written.

**One condition recorded rather than argued:** `runs/checkpoint-item5/findings.md` §7 states that a
required question a builder cannot answer cold is a wall, and a wall is how gates get disabled.
So any question that cannot be scaffolded from measured evidence ships **optional rather than
required**, and the dogfood's intervention log promotes it.

Items 11 and 12 keep their rows in `archive/plan-history.md` §3.1 and are marked folded, since about 290
citations resolve against the letters.

### 2.3 Three stages, and each one is a measured artifact transition

**Settled: `shape`, `build`, `measure`.** §1.1 measured that the gate has four observable rungs
and that two of the seven build increments are invisible to it, so a stage boundary anywhere
else has nothing to read.

| Stage | Settled by the end of it | What its gate reads |
|---|---|---|
| `shape` | what the agent is for, what counts as an answer, where agency sits, the tier, the backend | `brief.toml` exists and declares a tier |
| `build` | the pipeline exists and has run once inside the envelope | `simple-agents check` passes at `prototype` |
| `measure` | the labeled set, the split, the scoring rule, the evaluation | `simple-agents check` passes at the declared tier |

**No `improve` stage in v0.** Item 8a shipped `compare()` and variants and nothing in the ship
criterion needs them, so a fourth stage would be prose with no gate. Thilina's reason was
narrower and better: there are no training features yet.

**The wrinkle that made the `shape` boundary what it is.** A `build` gate requires a run, a run
requires a backend and a credential, so a procedure that has not asked which backend by the end
of `shape` presents the `build` gate to the builder as a wall rather than as a question. With
the fold this stops being a boundary problem and becomes one entry in the question set.

### 2.4 A gate is the command plus an instruction to construct

**Settled: the command, plus the skill instructing the agent to import and construct the
pipeline before running it. No new gate subcommand in v0.**

§1.2 and §1.4 are why the question existed. Three hand-written files pass at tier `prototype`
with the library never called, and there are **115 `ConfigurationError` sites against 6 checks**,
so a gate built only on the command reaches 6 of 121.

**The forged-directory result was reframed at the sitting and the reframing is the point.** It is
not an adversarial case. It is the bytes a coding agent produces when it writes its own logging
instead of finding `RunEnvelope`, which is the failure class `simple-agents.md` §1 exists to
name. Making the project construct its pipeline fires most of the 115 at no cost in library code.

A `simple-agents gate <stage>` subcommand was the alternative and is the right long-run answer.
It was declined for v0 because the requirement it would add at `build` is "this run directory was
produced by this library", and whether that is checkable without adding a field to the manifest
is not known. The dogfood's intervention log decides it with evidence.

**Two shipped defects are filed rather than fixed here**, on the ground that neither blocks a
gate: FT-14 firing on a pipeline that makes no model call (§1.3), and FT-13's message describing
a missing envelope when the run directory is merely elsewhere (§1.7).

### 2.5 FT-24's check and the required-set mechanism land here

**Settled.** §1.5 measured a brief carrying no entries at all passing six of six at tier
`evaluated`, so the validity mechanism of `simple-agents.md` §2.8 ships unenforced at every tier.

Thilina's correction to how it was argued: the recommendation had leaned on the item boundary,
and moving work between items is not a reason for anything. Re-argued on merit alone, the
measurement is the whole case.

### 2.6 A stage is declared, and the gate enforces monotonicity

**Settled: self-declared like the tier, with a project unable to claim a stage whose
predecessor's artifacts are absent.**

The tier is deliberately a declaration that cannot be inferred (`item9-build-log.md` §1.1), and
the same argument covers the stage: the library cannot know what the builder intends. What it
can refuse is a claim the artifacts contradict. Deriving the stage from the artifacts was
rejected for FT-01's reason, that a state inferred from artifacts cannot be the thing a gate
refuses.

This makes `stage` the first field anything reads, and it is what makes the procedure resumable:
a builder returning a week later has the stage in the brief and does not re-answer `shape`.

### 2.7 The skill is held by tests, because prose drifts

**Settled: six pins, none of them expensive.** `simple-agents.md` §3.1 says a skill "depends
entirely on how faithfully the coding agent follows prose" and that this is what makes the
library a library rather than a markdown file. This item ships the markdown file, so it ships
the tests that hold it: a command it names exists in the CLI, a stage name is in the stage set,
an `FT-nn` and a `docs/*.md` §n resolve (`prose_check.py` already does both), a project path is
the constant in `conformance/artifacts.py`, and the word count is under budget.

### 2.8 Scope, and what the skill may not contain

**Settled.** A hard budget of **1,200 words** for the skill, against a measured median of 827
across 662 installed skills and FastAPI's 1,403 (§1.13). No API example that is already in
`docs/`, since a second copy of something that moves is `CLAUDE.md`'s drift hazard in a new
place. What the skill owns is what no document holds: the order, the three gates, the project
layout, and the command at each gate.

`docs/index.md` gains the skill and its twelfth row. The README gains a quick start above the
fold and keeps its table of contents, since that is where a builder looks first. **Nothing in
`docs/evaluation.md`**, which is next in the review and already carries unreviewed text from
items 9 and 8a, on the precedent items 8g and 8b each set.

**Folded in without a question**, on the item 8g §2.8 precedent: §1.8's `python -m
simple_agents.cli check` printing nothing and exiting 0.

### 2.9 Dogfood #1 survives, at one session rather than three

**Settled after a push-back.** Thilina's position was that dogfood #1 is too simple to be worth
running and that going straight to the shopping agent was tempting. The argument against
dropping it is `archive/plan-history.md` §4.2's, that a failure in the shopping agent is ambiguous between "the
library misled the coding agent" and "this task is hard", and §1 gave it evidence rather than
leaving it an argument: building §1.1's three-document toy today, with full context on this
library, **four budget numbers were invented** (declared `max_tokens=200_000` against 1,357 used)
and `AgentNode(max_steps=...)` was written from a prior about other libraries without opening the
six-line section that shows the right call (§1.10, §1.11). On a task where retailer HTML is
fighting back, neither would be visible.

**What was conceded is the cost, not the order.** One session rather than the two or three
`runs/dogfood-protocol.md` §1 asks for. Do-not-change #13 is untouched.

`archive/plan-history.md` §3.3's ship criterion is rewritten: it was written before any code existed and says
"conformance-passing" without naming a tier, and §1.1 measured that at tier `prototype` the bar
is a brief and one run.

---

## 3. What building it changed about the design

### 3.1 Monotonicity is not a check, it is what a cumulative requirement already does

§2.6 settled that a project cannot claim a stage whose predecessor's artifacts are absent, and
the first reading of that was a separate refusal. Building it showed the rule was already
covered twice over and that a third mechanism would have been the redundancy item 8g §3.1
deleted.

**Skipping ahead cannot skip a question, because the required set is cumulative.** `up_to`
returns every stage through the declared one, so declaring `measure` at the start makes eleven
questions required rather than five. A project cannot shorten its obligations by claiming to be
further on.

**Claiming to be behind does not work either, because artifacts move the stage forward.**
`reached()` takes the later of what the brief declares and what the project has produced: a run
directory shows `build` and a results file shows `measure`. Declaring `shape` with an evaluation
on disk is read as `measure`.

So the two directions are closed by one function and no new refusal. The artifact side also
keeps to §1.1's ceiling: a run directory and a results file are two of the four things a gate
can observe, and nothing here reads anything that is not already read.

### 3.2 The gate names the entries and a command explains them

FT-24's message interpolates a list of entry names, which is the shipped contract. Running it
for the first time against the fixtures produced eleven names and nothing saying what any of
them meant, which is `runs/checkpoint-item5/findings.md` §7's wall arriving through the report rather
than through a question.

`simple-agents questions --stage <stage>` is the answer, and it pays twice. It gives the report
somewhere to send a reader, and it keeps the skill under its word budget: the procedure names
one command instead of restating sixteen questions and their scaffolds.

### 3.3 A brief entry gained nothing, and the candidates are why

`plan.md` item 11 asks what an entry holds beyond its status. Every candidate was tried against
the library's own rule that a field must have a reader, and none of them had one: the date it
was asked, who answered, the question text, and a link to the taxonomy entry are all either
unverifiable or already derivable from the question set the entry's name keys into.

**What did change is `deferred_to`**, which now has to name one of the three stages. It had a
reader the moment stages existed, and a deferral to a stage nobody defined is a deferral to
nowhere.

### 3.4 `init` links a directory when installed and a file when not

The first implementation linked the parent of whatever `_skill_source` returned, which is right
for a wheel, where the source is `.agents/skills/simple-agents/SKILL.md`, and wrong in a source
checkout, where the source is `docs/procedure.md` and the parent is the whole `docs/` directory.
Running it in this repository linked all twelve documents into `.agents/skills/simple-agents`.

It now branches on what the source is: an installed skill directory is linked whole, and the
repository's single file gets a directory built around it. The wheel case was verified by
installing the built wheel into a fresh venv rather than by reading the code, and the link
resolves into `site-packages`, so the procedure tracks the installed version.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Twenty-four guards, disabled one at a time, and the three that stayed quiet were all tests

Twenty-one of twenty-four failed the test named against them on the first pass. All three quiet
ones were the test being wrong rather than the guard being redundant, which is item 8g §4.1 and
item 8b §4.1 again, and one of them is a shape none of the earlier passes produced.

| Disabled | Why the test still passed | What it was |
|---|---|---|
| `required_at` keeping only the required questions | **the test built its fixture by calling `required_at`**, so disabling the function changed the answer and the fixture together | a test that cannot fail |
| FT-24 reading the stage the artifacts show | the fixture's brief answered the `measure` questions anyway, so reading it as `build` changed nothing | needed a brief answering less than its artifacts imply |
| `--copy` placing a copy | the assertion was on the directory, which `mkdir` builds in both paths, and `is_file()` follows a symlink | asserted nothing about the thing under test |

**The first is worth naming, because it is new.** Every quiet guard in items 8a, 8g and 8b was a
test that never reached the guard. This one reached it and could not observe it: the test wrote
`{q.name: "answered" for q in required_at("build")}` and then asserted the gate was satisfied, so
whatever `required_at` returned, the brief answered exactly that. The names are now transcribed
into the test, with a separate assertion that the transcription still matches the shipped set.

New fixtures for all three: a transcribed question list, a project whose brief answers the
`build` questions with a results file on disk, and an assertion on the `SKILL.md` rather than on
the directory around it. A test for the link case was added beside the copy one, since only the
pair distinguishes them. **24 of 24 fire.**

The pass ran each case with `PYTHONDONTWRITEBYTECODE=1` and cleared every `__pycache__` after
restoring, per item 8g §4.2. `scratchpad/guard_pass_item10.py` is the script.

---

## 5. Findings

### 5.1 The ladder gained one rung, and the two invisible increments are still invisible

The same seven-state build, re-run with the gate in place. `scratchpad/build_trivial.py`.

| State | exit before | exit now | What changed |
|---|---|---|---|
| A, empty directory | 2 | 2 | |
| B, a brief claiming a tier and answering nothing | 1 | 1 | **FT-24 now fails as well as FT-13** |
| B2, the five `shape` questions answered | did not exist | 1 | **new rung. FT-24 passes before any code exists** |
| C, the agent written | 1 | 1 | still byte-identical to the state before it |
| D, one run | 0 | 0 | three pass rather than two |
| E, tier `evaluated`, no evaluation | 1 | 1 | |
| F, the example set written | 1 | 1 | still byte-identical to the state before it |
| G, the evaluation run | 0 | 0 | seven pass rather than six |

**The gate now fires before a line of code is written**, which is what a `shape` stage is for.
**Writing the agent and writing the example set are still invisible**, and no check added here
changes that: both are source, and every check is `artifact` surface. The procedure covers it by
telling the agent to construct the pipeline, which is prose rather than a gate, and §2.4 records
that this is what the dogfood measures.

### 5.2 FT-24 raises the floor, and it is not a defence against a plausible artifact

§1.2's hand-written three-file project now fails, because its brief carries no entries. That is
worth stating precisely rather than claiming more than it does: **the cheapest passing project
went from three files to three files plus eleven recorded answers**, and the answers are prose
no check reads. A coding agent that wrote its own trajectory would write brief entries too.

What FT-24 buys is that the eleven questions were put to a person. What it does not buy is that
the artifacts came from the library, and §2.4 declined to build that here.

### 5.3 An evaluation's run directory is named for a fresh uuid, so a committed fixture churns

`runner.py:179` is `eval_id = f"eval_{uuid.uuid4().hex[:12]}"`. Rebuilding
`tests/fixtures/projects/` therefore renames every run directory, and one test had the old name
transcribed into it. It read the name off the fixture instead.

This is nobody's design and it predates this item: an evaluation is otherwise reproducible from
one integer, and the directory it writes into is the one part that is not. Whether it should
derive from the seed and the content hash is a decision for later.

**Measured cost.** The first rebuild renamed 180 committed files, so the diff said nothing
about what had changed. **Fixed in the library at §8.3 rather than worked around**, and the
workaround the fixture builder briefly carried was deleted.

### 5.4 The skill fits, at 1,038 words against a 1,200 budget

Measured after writing it. It restates no API, cites six documents by path and eight taxonomy
entries by id, and every one of those is resolved by a test or by `prose_check.py`. The
comparison from §1.13 holds: the shipped documents are 40,780 words and this is 2.5% of them.

---

## 6. Doc consequences

Written after the build.

| Document | What it said | What it says now |
|---|---|---|
| `docs/procedure.md` | did not exist | **New, the twelfth shipped document, and the skill.** Three stages, the layout the checks read, the gate at each stage, what a failing gate means, and four things not to do. Force-included to `simple_agents/.agents/skills/simple-agents/SKILL.md` as well, from the same source file |
| `docs/index.md` | eleven documents, start with `docs/pipeline.md` | Twelve, start with `docs/procedure.md`, and a row for it |
| `docs/conformance.md` §1 | `tier` is the only field the six checks read | `tier`, and `stage` as one of three with `shape` the default |
| `docs/conformance.md` §1.1 | the tiers run two of six and all six | FT-24 added to `prototype`, and all seven |
| `docs/conformance.md` §1.2 | the elicitation gate arrives later | What FT-24 compares, that a missing entry counts as unanswered, and `simple-agents questions` |
| `docs/conformance.md` §1.3 | did not exist | **New.** Which stage a project is at, and that artifacts move it forward and never back |
| `docs/conformance.md` §2, §3, §4 | six checks | Seven, with FT-24's row, its line in the example report, and the counts |
| `docs/failure-taxonomy.md` FT-24 | no `What the library provides`; the check in one sentence | The questions, the scaffolds and the command. The check now states the missing-entry rule, where the stage comes from, and that the requirement is cumulative |
| `README.md` | Install | **Quick start**: install, `simple-agents init`, what to say next, and the two commands. Plus rows for `docs/procedure.md` and `docs/index.md` |
| `CHANGELOG.md` | Unreleased | The skill and `init`, the stages, FT-24, the question set, and the `python -m` fix |

**Not touched, and deliberately.** `docs/evaluation.md`, which is next in Thilina's review and
already carries unreviewed text from items 9 and 8a, on the precedent items 8g and 8b each set.
`docs/pipeline.md`, `docs/tools.md`, `docs/context.md`, `docs/trajectory-format.md`,
`docs/run-envelope.md` and the model-client pages own nothing this item changed.

**No format version moved.** Trajectory `0.15`, manifest `0.10`, results `0.4`, suspension `0.1`
and variant `0.1` are all untouched: nothing here writes a record. The brief has never carried a
format version, and a brief written yesterday is still valid, since `stage` was optional and the
three names it now accepts include the one every fixture used.

---

## 7. Existing tests that had to change

Seven, and none is a defect in the library. Six are counts that widened from six checks to
seven, and one had a fixture's directory name transcribed into it.

| Test | What it asserted | Why it failed |
|---|---|---|
| `test_conformance.py::TestTheConformingProject::test_all_six_pass` | six outcomes, all passed | seven checks. Renamed `test_all_seven_pass` |
| `test_conformance.py::TestTheTierGate::test_an_inapplicable_check_is_reported_rather_than_dropped` | `len(report.checks) == 6` | the same |
| `test_conformance.py::TestTheTierGate::test_a_prototype_project_is_held_to_two_checks` | two `prototype` checks | three. FT-24 is `prototype` |
| `test_conformance.py::TestTheCommand::test_json_carries_every_check_and_the_counts` | `passed: 2` | `passed: 3` |
| `test_conformance.py::TestTheBrief::test_it_reads_the_entries_a_project_recorded` | the fixture's two entries by name | the fixture brief is now generated from the required set |
| `test_conformance.py::TestTheAliasRule`, via `_self_hosted` | a bare `tier = "prototype"` brief, then `report.ok` | FT-24 fires on it. The helper now copies the conforming brief, so the report turns on FT-14 alone |
| `test_conformance.py::TestTheConformingProject::test_the_report_names_the_artifacts_it_read` | `runs/eval_3c7b8a11983c/...` | §5.3. It reads the name off the fixture now |

**The eleven fixture projects were rebuilt**, and their briefs are generated from the shipped
question set rather than transcribed, so a question added later leaves them failing FT-24 until
they are rebuilt rather than passing against a stale list. One new fixture,
`unanswered-question`, is the conforming project with one required entry set to `unanswered`.

**Total: 7 existing tests changed, 48 added. 1063 tests**, and 1072 after §8.

---

## 8. The three defects, fixed after the item

Filed at the sitting rather than fixed there, on the ground that none of them blocked a gate.
Thilina asked for them, and each was measured before it was touched.

### 8.1 FT-14 reads what a run did rather than what it declared

§1.3 measured the check failing a `Deterministic`-only pipeline. The manifest holds two fields
and only one was read:

| Run | `models.configured` | `models.observed` |
|---|---|---|
| no model client passed | `null` | `[]` |
| a model call happened | the identity | one entry, `calls: 1` |
| a client passed, no node called it | the identity | `[]` |

`observed` is what happened. The check passes where both are empty, with the report saying the
run made no model call, and the third row is unchanged: a pin exists and is checked. **A run that
called a model and recorded no pin still fails**, which the second row makes checkable and a test
pins.

### 8.2 FT-13 names the run it found rather than describing a missing envelope

§1.7 measured the message telling a project to run inside the run envelope when it had. The
reason it interpolates now names what was found:

```
no run directory under runs/, and a run was found at output/run_4b623358bc38. The checks
read runs/; pass --run output/run_4b623358bc38 to read that one, or set
RunEnvelope(run_dir='runs')
```

**No shipped message text was edited**, since the correction fits inside FT-13's existing
`<reason>` placeholder. The fixed tail of the message still says to run inside the envelope,
which is wrong for this one case and is left for the taxonomy review rather than changed here.

The search walks the project once with the directories no run is written into pruned rather than
filtered, so a tree carrying a virtualenv is not descended into. Measured at 0.11s on a project
holding one. Pruning rather than filtering was what the guard pass caught: the first test had
nothing to prune and never reached the guard (§4.1's shape, a fifth time).

### 8.3 An evaluation names its directory for what defines the evaluation

§5.3 measured `eval_id = f"eval_{uuid.uuid4().hex[:12]}"`. It is now a digest over the example
set's content hash, the seed, the split, k, `graph_fingerprint()` and the version of every prompt
in the pipeline.

**The prompt versions are what the first draft would have missed, and leaving them out would have
been worse than the uuid.** `graph_fingerprint` deliberately excludes prompts, so two versions of
a pipeline differing only in a prompt would have shared an id, and the second would have
overwritten the first. That is exactly the `compare()` workflow, so the fix would have broken the
thing it was meant to serve. A test pins it.

**Overwriting is unchanged rather than newly introduced.** A colliding `run_id` already
overwrites today, measured, so a re-run of one identical evaluation behaves as `Pipeline.run`
already does.

`docs/evaluation.md` §6.1 writes `<run_dir>/<eval_id>/` and makes no claim about how the name is
formed, so nothing in it became false. The change is in `CHANGELOG.md`, and stating it in that
document is owed at its review.

### 8.4 What the fixes cost the suite

**31 of 31 guards fire**, seven of them new. **1072 tests**, nine added and none changed. The
fixture builder's `_stabilise_eval_id` workaround was deleted, and two consecutive rebuilds were
confirmed to produce an identical file list.
