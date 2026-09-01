# Item 9 — build log

**Kept while building, not reconstructed at the end.** On the precedent of `item8f-build-log.md`.
The end-of-item report and the shipped-document rewrites are reads of this file.

The design of record is `archive/plan-history.md` item 9. §1 records what was measured before the sitting,
§2 the sitting, §3 where building sharpened a decision, §4 where it turned out not to hold, §5
what the build found that is nobody's design, §6 doc consequences, §7 existing tests that had to
change.

**Status: built, and the shipped documents written.** 2026-08-05. Baseline 845 tests at
`73da46b`; **899 tests** now. Results file `0.3`; trajectory, manifest and suspension unchanged.
Six checks, 23 guards each disabled once and watched to fire.

---

## 1. What was measured, before any design

Item 8f §1 is the standard: two claims the plan carried as scheduled turned out false, and both
were found by making a call instead of reading a document. Item 9's equivalent is that **what an
artifact contains is a measurement**, so every claim below is read off a file the library
produced rather than off the document describing it.

**How the artifacts were produced.** `scripts/record_backend_cassettes.py::eval_suite` replayed
against the committed `tests/cassettes/eval.jsonl`, 3 examples × 3 rollouts, seed 41, written to
a scratch directory: one `results.json`, nine run directories each with a `manifest.json` and a
`trajectory.jsonl`. This is the library's own shipped evaluation recording, so it is the closest
thing to a conforming project that exists today.

### 1.1 Four of the seven cannot run without a tier, and only a declaration can supply one

`docs/failure-taxonomy.md` §1.2: "Gates fire only when the project claims the tier or higher."
FT-01, FT-02, FT-06 and FT-07 are `evaluated`. FT-13, FT-14 and FT-24 are `prototype`, which
every project claims, so those three need no tier to decide whether to run.

**The tier cannot be inferred from the artifacts.** FT-01 fires exactly when a project claims
`evaluated` and has no evaluation, so inferring the claim from the presence of an evaluation
makes FT-01 unable to fire by construction.

**Nothing in the library holds a tier.** `grep -rn tier src/simple_agents` returns nothing.

**Nine shipped failure messages name where it is declared**, in the same words: *"If this project
is a throwaway, declare tier `prototype` in the brief and this gate will not fire."* FT-01, FT-02,
FT-03, FT-05, FT-06, FT-07, FT-08, FT-10, FT-12. Four of those nine are in the v0 seven.

So a runner that ships six checks with the tier read from anywhere other than the brief ships six
messages that tell a coding agent to edit a file the library does not define.

### 1.2 FT-24 needs a required-question set, and nothing anywhere defines one or defines a stage

FT-24's check is "for each question required at the project's current stage". `grep -rn stage`
across `docs/` returns only FT-24's own two lines. `dev-docs/` has the concept and no
vocabulary: `simple-agents.md` §2.8 says staging exists, `plan.md` item 12 holds a four-question
seed set, and `runs/checkpoint-item5/findings.md` §7 and `runs/checkpoint-item7/findings.md` §8 hold
thirteen more with a scaffold and a piece of evidence each. None of it is a stage list.

With no required set, FT-24 passes on any brief that parses.

### 1.3 The `**Failure message.**` convention parses cleanly on all 27 entries

One `**Failure message.**` line followed by one blockquote, on every entry. Every placeholder is
a plain name inside backticks; no expressions, no alternations, and no unbackticked `<…>`
anywhere in a message.

| Entry | Placeholders |
|---|---|
| FT-01, FT-02, FT-07, FT-13 | none |
| FT-06 | `name` |
| FT-14 | `alias` |
| FT-24 | `stage`, `list` |

FT-06's placeholder is singular, so the runner emits one finding per metric rather than one
finding carrying a list.

### 1.4 What the results file actually holds

Read off the produced `results.json`, `eval_format_version` `0.2`.

| Check | What it needs | What the file has |
|---|---|---|
| FT-01 | a labeled set, a scoring function, results produced by running one over the other | `config.example_set.content_hash`, `examples` per example, `rollouts` with an outcome each. **No record of the scoring function** |
| FT-02 | at least two splits, one marked held-out, non-empty | `config.example_set.splits`, which is `{"held_out": 3}` on this recording: **counts by name, over the whole set, with nothing marking which is held out** |
| FT-06 | every reported metric carries an interval and its n | six metrics each with `interval.{point,low,high,n,k,confidence,resamples,seed,method}`, plus `nodes[].reach` in the same shape and `nodes[].accuracy` |
| FT-07 | a seed per rollout | `rollouts[].seed`, and `rollouts[].trajectory` as an **absolute path** |

**`config.example_set.splits` is over the whole example set, not the evaluated split**
(`runner.py:428` calls `self.examples.splits()`), so FT-02 is answerable from the results file
alone.

**The library's own recorded evaluation fails FT-02**, because every example in it is `held_out`
and there is no dev split.

**`config` records no scoring function.** `compare()` walks `config` to build `changed`
(`compare.py:381`), so today a change to `matches` moves every metric and appears in `changed` as
nothing at all.

### 1.5 An empty denominator writes `interval: null`, which a naive FT-06 fires on

Measured by aggregating three rollouts of one example whose correct answer is absence, so
`recall` has no denominator:

```
"recall": {..., "rollouts": 0, "examples": 0, "interval": null,
           "reason": "No rollouts fall under rollouts of examples where a value exists,
                      so this rate has no denominator."}
```

`nodes["hunt"].accuracy` is `null` on the same recording, because no example carries
`expected_by_node`. Both are correct library output, documented at `docs/evaluation.md` §3 and
§5.2, and both are a metric-shaped object with no interval. This is item 8f §4's shape arriving
before any code was written.

### 1.6 Two of the four record types carry no seed at all

Read off a produced `trajectory.jsonl`, format `0.14`:

| Record type | `seed` |
|---|---|
| `node_execution` | present; the run seed, and `null` on a `deterministic` node |
| `model_call` | present; derived per call |
| `tool_call` | **field absent** |
| `consultation` | **field absent** |

`trajectory.py` gives a `seed` parameter to `NodeRecord` and `ModelCallRecord` and to neither of
the other two. `docs/trajectory-format.md:83` says so and names the reader: "FT-07 reads this
field". FT-07's own text says "Every trajectory record carries a seed", which is false against
every trajectory this library has ever written.

FT-07's second clause, "re-running an eval with the recorded seeds and cassette reproduces the
recorded outputs", is a `runtime` measurement inside an entry declared `artifact`.

### 1.7 What the manifest holds for FT-14, and what it does not

```
"models": {"configured": {"backend": "hosted_api",
                          "request_model": "mistral-small-2603",
                          "model_revision": null}, "observed": [...]}
```

The vLLM cassettes carry the other shape: `request_model` `Qwen/Qwen3-1.7B`, `model_revision`
`70d244cc86ccca08cf5af4e1e306ecf908b1ad5e`.

**Sampling parameters are not in the manifest.** FT-14's check asks for "a fully-qualified model
identifier and all sampling parameters for every model call". Temperature, `max_output_tokens`,
the tools offered and the output schema are on `model_call.params` in the trajectory. So FT-14
reads two artifacts, and the entry names one.

**What the two adapters give the check to work with.** `MistralClient.identity` reports
`model_revision=None` always, because the provider exposes no revision. `VLLMClient.identity`
reports whatever the constructor was given, and `None` when it was given nothing. So the
self-hosted case is decidable mechanically and the hosted case is a judgement about a string,
which is what `plan.md` item 5's probe already found: `GET /v1/models` publishes aliases
symmetrically and marks no canonical form.

### 1.8 Nothing in the shipped documents mentions a CLI

`grep` for `simple-agents check`, `CLI` and `console` across `README.md` and `docs/*.md` returns
nothing. `pyproject.toml` carries a comment saying the console script is declared at item 9. So
this item introduces the first command-line surface and the first shipped document describing
one.

### 1.9 A check text and its failure message disagree in three of the seven

The message is the contract, so where the check can fail in a way no message describes, the
runner has nothing true to print.

| Entry | A failure the check admits | What the message says |
|---|---|---|
| FT-13 | a trajectory exists and does not conform to the format | "No trajectory log was produced by this run." |
| FT-02 | one split exists and it is the held-out one | "The example set has no held-out split." |
| FT-24 | no brief exists at all | "Required brief entries are `unanswered` at stage `<stage>`: `<list>`." |

The FT-02 row is not hypothetical: it is what the library's own recorded evaluation would print.

### 1.10 `EvalResults.read` refuses a file it did not write

`results.py:201` raises `ConfigurationError` when `eval_format_version` differs from the current
one. A hand-rolled results file is exactly what FT-06 exists to catch, so a runner built on the
typed reader dies where it is supposed to report.

---

## 2. The sitting, and what it settled

Held 2026-08-05, after §1's measurements and before any code. Twelve decisions were put; §1 is
why each was put in the shape it was, since every one of them turns on what an artifact contains
rather than on what a document says about it.

| Question | Settled |
|---|---|
| The tier has no home, and four checks need one | Item 9 defines the brief file: `tier`, `stage`, `entries` with statuses. Item 11 inherits the elicitation half |
| FT-24, whose required set and stage vocabulary do not exist | Built at item 12, where both are created. Six checks here |
| Nothing marks a split held out | The library marks it: `ExampleSet(held_out=...)`, default `"held_out"`, recorded in `config.example_set` |
| FT-07's check text is false against our own trajectories | Implement against `node_execution` and `model_call`; amend the entry, and move the reproduce clause to `What the library provides` |
| What counts as an alias for FT-14 | Fail on a known floating marker; the self-hosted revision rule stays exact |
| What counts as a reported metric for FT-06 | An interval carrying `n`, or a null value with a stated reason. Nothing else passes |
| Whether FT-13 validates the trajectory | **Open.** See §2.2 |
| Which artifacts the runner reads | Conventions, most recent, overridable, and the report names what it read. Missing artifacts block dependents rather than failing them. Raw JSON, never the typed readers |
| The command surface | `simple-agents check [path]`, `--json`, exit 1 on any failure, four per-check states, all of them printed |
| How the fixtures are built | Generated from a real replayed run and committed, with each failing fixture one documented mutation away |
| `held_out` and the scoring function in `config` | Both recorded; results format `0.2` → `0.3` |
| Doc consequences | A tenth shipped document, written after the build |

### 2.1 The scope amendment was written at the sitting rather than after it

At Thilina's instruction, and it is the one thing here that did not wait for the build. `archive/plan-history.md`
§3.1 items 9, 11 and 12 and §6, and `handoff.md`'s two scope statements. The rest of the table
above lands in the shipped documents after the build, on the instruction items 8c through 8f
followed.

### 2.2 The FT-13 recommendation did not survive being asked whether it was laziness

Presented as "checks existence and readability only", on the ground that FT-13's failure message
has nothing to say about a malformed file. Thilina accepted it conditionally on the reason not
being effort, which is what sent it back.

**The recommendation does not survive.** A check that reads existence alone is satisfied by
`touch runs/<id>/trajectory.jsonl`, and a plausible artifact that passes is the failure class the
library exists to prevent.

**What was actually wrong with it was the framing.** The message was treated as fixed, and it is
editable. One message covers both failures if it takes a placeholder:

> No usable trajectory log was found for this run: `<reason>`. Nothing about the agent's
> behaviour is recoverable afterwards without one: no debugging a failure, no per-node
> evaluation, no ablation, and no later use of the runs as training data. Run the agent inside
> the run envelope, which records by construction.

`<reason>` fills as `no trajectory.jsonl in runs/run_7f2a` or `record 4 of
runs/run_7f2a/trajectory.jsonl declares no record_type`. That stays inside the one-blockquote
contract and needs no second-message convention, which is what the alternative would have cost.
**Awaiting sign-off**, since it edits a signed-off entry.

### 2.3 The held-out mark, and the question it was tested against

Thilina's question: does marking the split in the library still need the brief to say what to
mark? It does not. The project states it where it already states the split names, at
construction, and it lands in one artifact the check reads.

The argument against the brief carrying it is item 4's, that no value has two sources: a split
name is a fact about the example set, and the brief holds elicited answers rather than
configuration. Cross-referencing a name in `brief.toml` against a name in `results.json` also
means a typo in either fails a correct project.

**The half of the question that lands, and is recorded rather than argued away:** a project that
declares nothing still falls back on a name. The difference is that the fallback is a documented
default with a one-line override the FT-02 message can name, rather than a list of names the
runner happens to accept.

---

## 3. What building it changed about the design

### 3.1 The brief requires one field, and validates two more

`tier` is required. `stage` and `entries` are optional, validated when present, and read by
nothing that ships here.

The rule they were tested against is the library's own, that a field must have a reader. They
survive it on a different ground: item 9 defines the file so items 11 and 12 do not have to
redefine it, and a brief written today has to stay valid when the elicitation gate arrives.
Requiring them would refuse a project for leaving out something nothing yet reads.

### 3.2 A project with no brief is refused rather than defaulted to `prototype`

The alternative was to default, on the ground that a first run should not fail for want of a
file nobody has written yet. It is a suppression mechanism by another name: deleting
`brief.toml` would silence the four `evaluated` gates, and the taxonomy has no suppression
mechanism at v0 or later.

The refusal carries the two lines to write and exits 2 rather than 1, so a gate can tell "the
suite could not run" from "a check failed".

### 3.3 The JSON report is not versioned

Every other artifact the library writes carries a format version, because a project holds files
written in it. The report is one run's output on stdout and nothing writes it to disk, so
versioning it would add a fifth version for something no project keeps. Item 10's gates are the
first reader; if they need one, the reader will exist to design it against.

### 3.4 FT-14's sampling-parameter clause moved out of the check

The entry asked for "a fully-qualified model identifier and all sampling parameters for every
model call", and §1.7 measured that the manifest holds no sampling parameters. The first
correction put the parameters on the trajectory and left them in the check, which reintroduced
§1.9's problem in a new place: FT-14's message is about an alias and can say nothing about a
missing `params`. It is now a fact in `What the library provides`, pointing at
`docs/trajectory-format.md` §4.1, and the check reads the pin alone.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Five guards were disabled and their tests kept passing

The mutation pass ran 23 guards. Eighteen failed the test named against them, and five did not:

| Disabled | Why the test still passed |
|---|---|
| FT-13's "the trajectory has to exist" | reading the absent file reports the same failure with a worse reason |
| FT-13's "at least one `node_execution`" | the fixture trips the malformed-record check first |
| FT-01's "results have to hold rollouts" | the fixture has no results file at all, which fails earlier |
| FT-02's "the held-out split has to exist" | the one-split fixture also trips the two-splits rule |
| the brief's "a tier has to be declared" | the missing-file refusal fires before the missing-key one |

**Every one is the same shape**, and it is item 8f §7.4's seventh row: the test was exercising a
path an earlier guard already covered, so the guard under test was never the thing that made it
pass. Four new fixtures and one new brief close them: a run whose trajectory is deleted rather
than garbled, a trajectory of readable records holding no `node_execution`, a results file
holding an empty `rollouts`, splits named `train` and `test` with none of them the declared
held-out one, and a `brief.toml` carrying a stage and no tier. **23 of 23 now fire.**

---

## 5. Findings

### 5.1 The library's own recorded evaluation fails FT-02

`scripts/record_backend_cassettes.py::eval_examples` puts all three examples in `held_out`, so
the recording every eval test replays has no dev split. The check is right and the recording is
what a project should not copy. The fixture adds two dev examples that are never run, since the
cassette holds responses for the held-out three alone.

### 5.2 Nothing pinned the results format version, and the bump proved it

`0.2` → `0.3` was made and the whole suite passed, because the one test that reads the version
compares it against the constant rather than against a number. The trajectory format has both:
a test pinning the literal and `test_packaging.py` checking the document states it.
`docs/evaluation.md` stated `0.2` with nothing reading that. It now has the packaging test.

### 5.3 A results file and a manifest record absolute paths

`rollouts[].trajectory` and `paths.trajectory` are absolute, so a run directory copied or moved
leaves them dangling. FT-07 resolves what it can and reads the rest of the trajectories from the
latest run, and `scripts/build_conformance_fixtures.py` rewrites them relative to the project
root so a committed fixture survives being checked out anywhere. **The library's own behaviour is
unchanged and is worth a decision later**: a project that archives a run directory cannot follow
the paths its results file records.

---

## 6. Doc consequences

Written after the build, on the instruction items 8c through 8f followed.

| Document | What it said | What it says now |
|---|---|---|
| `docs/conformance.md` | did not exist | **New, the tenth shipped document.** The brief and the tier, what each check reads, which run and which results file, the four outcomes, exit status, JSON and the Python entry point. |
| `docs/failure-taxonomy.md` FT-02 | "no held-out split", one shape | **Done.** The set names its held-out split; the check reads that name; the message takes `<reason>` so it fits both shapes. |
| `docs/failure-taxonomy.md` FT-06 | every metric carries an interval | **Done.** A metric reporting no value states why and passes. |
| `docs/failure-taxonomy.md` FT-07 | "every trajectory record carries a seed", plus a re-run clause | **Done.** The two record types that carry one, the `deterministic` exemption, and the two that carry no seed field. The re-run clause is gone: the entry already says reproduction comes from the cassette. |
| `docs/failure-taxonomy.md` FT-13 | "executing the agent produces…", message about absence only | **Done.** What conforming means, and one message taking `<reason>` that covers a missing file and an unreadable one. |
| `docs/failure-taxonomy.md` FT-14 | manifest holds the pin and all sampling parameters | **Done.** The pin alone, plus what the check calls a floating marker and what it passes without classifying. |
| `docs/evaluation.md` §1.1, §8, §9 | `0.2`, splits by convention | **Done.** `held_out=` on the set and on `from_jsonl`, `0.3`, `config.matches` and what it buys `compare()`. |
| `docs/index.md`, `README.md` | ten documents | **Done.** A row each for `conformance.md`. |
| `CHANGELOG.md` | Unreleased | **Done.** The command, the brief, and the results bump with what a project has to do. |
| `dev-docs/plan.md` §3.1 items 9, 11, 12, §6 | the design as scheduled | **Done at the sitting**, on Thilina's instruction, rather than after the build. |
| `dev-docs/handoff.md` | seven checks next | **Done at the sitting.** |

**Not touched, and deliberately.** `docs/trajectory-format.md` owes nothing: FT-13 validates
against §2 and adds no field. `docs/run-envelope.md` owes nothing: no manifest field changed.
`docs/pipeline.md`, `docs/tools.md`, `docs/context.md` and the model-client pages own nothing the
checks read.

---

## 7. Existing tests that had to change

**None.** All 845 tests at `73da46b` pass unchanged, including the results-format bump, which
§5.2 records as a gap rather than a pass. 54 were added: 53 in `tests/test_conformance.py` and
one in `tests/test_packaging.py`.
