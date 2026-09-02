# The conformance suite

`docs/failure-taxonomy.md` specifies the failures. This document covers the part that runs: how a project declares what it claims, what each check reads, and what the report means. `docs/procedure.md` covers when in a build each check is run.

```
simple-agents check
```

The command reads the files the project has already produced. It executes nothing, makes no network call, and changes nothing on disk.

---

## 1. Tiers, stages and gates

**A tier is what the project intends to be**, declared once in the brief. The checks hold it to that intention from the moment it is declared, so a project claiming `evaluated` fails FT-01 until it has an evaluation. **A stage is how far along it is**, and it moves as the project is built. **A gate is a check the project has to pass to move on.** Each stage ends by running `simple-agents check`, which runs every gate the tier and the stage put in front of it.

| Tier | The project it describes | Its stages | Checks |
|---|---|---|---|
| `prototype` | built to find out whether the idea works, and reports no number about how well it does | every stage but `measure` | twenty of the twenty-seven |
| `evaluated` | reports a measured number about how well it works | all six | all twenty-seven |
| `trained` | an `evaluated` project that will also be trained on its own runs | all six | all twenty-seven |

**`prototype` drops seven of the twenty-seven checks, the ones that read a results file**, as it does not produce one. They are FT-01, FT-02, FT-03, FT-04, FT-06, FT-07 and FT-37 (§3).

**`prototype` has no `measure` stage**, because it reports no number. Its `measure` questions are not required. A `prototype` project that produced a results file anyway gets a note suggesting `tier = "evaluated"`.

**`trained` is on the roadmap and runs what `evaluated` runs.** The library ships no training core, so its one distinct taxonomy entry, FT-26, has no check. Declaring it says where the project is going and fires nothing more today.

**Every tier has `ship`, because shipping is a stage rather than a tier.** It is the point at which somebody other than the builder uses the agent, and a project reaches it from any tier (`docs/shipping.md`).

**FT-31, FT-34, FT-36, FT-37 and FT-38 also name a stage** and wait until the project reaches `ship`, `shape`, `research`, `ship` and `ship`, reporting `n/a` before that. They are the only entries that do so, and two of the ones that name `ship` read a change rather than an arrival: a stage a project has reached it stays at, so those go on firing.

**A throwaway that does not want the measurement gates declares `tier = "prototype"`**, and that is the only way to turn a check off. Nine entries in the taxonomy name it in their failure message.

### 1.1 Which stage a project is at

The brief declares it, and the artifacts can move it forward. A run directory shows the project reached `build`, a results file that it reached `measure`, and a run marked live that it reached `ship` (`docs/shipping.md` §1). Declaring an earlier stage does not reduce what the gate holds it to, and declaring a later one is taken at its word. A project that declares nothing and has produced nothing is at `brainstorm`.

**A stage the tier does not have is never reached.** At `prototype` a results file leaves the project where it was, and a brief declaring `stage = "measure"` at that tier is refused rather than read one way or the other. An entry `deferred_to` a stage the tier does not have is refused for the same reason: the answer would never come due.

---

## 2. The brief

A gate fires only when the project claims the tier it belongs to or higher, and the claim lives in `brief.toml` at the project root:

```toml
tier = "evaluated"
stage = "measure"
results = "evals/results/held-out-v3.json"

[entries.ground_truth]
status = "answered"
recorded_at = "2026-08-27T09:14:02Z"
answer = "The retailer's name, matched case-insensitively as a substring."

[entries.budget]
status = "deferred"
deferred_to = "measure"

[entries.anything_else]
status = "answered"
recorded_at = "2026-08-27T14:31:55Z"
asked_at = "measure"
answer = "brainstorm: nothing. research: 'the export is stale after Tuesdays.'"
```

`tier` is required. `stage` says how far the project has got, and is `brainstorm`, `research`, `shape`, `build`, `measure` or `ship`; a brief that leaves it out reads as `brainstorm`. The tier decides which of the six this project has (§1).

**Three keys name the stage at which each of the project's written accounts of itself was last confirmed**, and a gate reads them to say what has gone stale. `understanding_confirmed_at` is `idea.md`, which FT-29 reads against the stage the project is at; `design_confirmed_at` is `design.md`, which FT-34 reads from stage `shape`; `research_confirmed_at` is `research.md`, which FT-36 reads from stage `research`. A fourth key dates the entries against the code rather than against a stage: `confirmed_against` holds the `behaviour_fingerprint` of the pipeline the entries were last read against, and the report names the ones due when it and the newest run disagree (§4.4).

**A fifth dates the picture rather than the answers.** `shape_confirmed` is a table of one `graph_fingerprint` per pipeline, holding the shape the builder was last shown and agreed to, so `simple-agents view` can say whether what is drawn is still what was confirmed (`docs/view.md` §6.1):

```toml
[shape_confirmed]
triage = "sha256:5cd1c1f4a52c0f1a"
```

No gate reads it. It is written at the `shape` gate, when the builder has looked at the drawing and said yes, and again whenever they agree to a change.

`results` names the evaluation the project reports, and the checks that read a results file read that one; a brief that leaves it out has the most recent under `evals/results/` read instead, which on a project that measured a variant last is the variant. `entries` records what the builder was asked. `decisions` records what the coding agent decided and what the builder said about it, one entry per decision, each naming its `kind`, carrying a `status` of `proposed`, `agreed`, `changed` or `not_applicable` (FT-30), and carrying a `recorded_at`, which every decision needs and §2.1 describes. A `shape` or `presentation` decision also names the entries it was derived from, under `from` (§4.4), and four of the kinds name what the decision became, under `produces` (§2.2). `simple-agents questions --decisions` prints the six kinds.

**A project declares its tier in the brief.** A project with no brief is refused: the command exits 2 and prints the `tier =` line to write.

### 2.1 Entries

Every entry carries a `status`, which is `answered`, `deferred` or `unanswered`. A `deferred` entry must name the stage it is deferred to, so the decision is postponed intentionally. An entry with any other status, or an entry deferred to anything other than a stage, is refused.

A deferral holds until the project reaches the stage it names. At that stage the answer is due, and an entry still deferred to it fails FT-24 with the blanks.

FT-24 compares these against the questions required at the stage the project is at. A question with no entry at all counts the same as one recorded `unanswered`.

**An entry may carry `asked_at`, the stage the question was last put at.** On most entries it records when the answer was taken, and nothing reads it back. On `anything_else`, which every gate puts again, FT-24 refuses while it is absent or names an earlier stage than the project is at: the answer accumulates under the stage it was given at, *nothing* is an answer, and a deferral is refused because there is no later stage to defer it to. This is what the three `*_confirmed_at` keys above do for a document, applied to a question.

**Every answered entry carries `recorded_at`, when what it now says was written down.** `simple-agents record` writes it from the clock (§2.3), in ISO 8601 in UTC; a value that is not a timestamp, or one naming no zone, is refused when the brief is read. A stage says how far the project had got and a clock says when, and the second is what a question of whether the code has moved since an answer was given anchors against. A re-asked question moves it with `asked_at`, whether or not the answer changed, since what it dates is the writing. A `deferred` or `unanswered` entry may carry one and is not held to it.

A stamp written by hand is a guess about the time, and FT-44 fails one ahead of the clock the suite runs on.

```
simple-agents questions --stage brainstorm   # and research, shape, build, measure, ship
simple-agents questions --stage ship --tier prototype
simple-agents questions --stage build --json
```

`--tier` drops the stages that tier does not have, which is `measure` at `prototype`. Without it every stage up to the one named is included.

Each question prints under its own heading, which is the question named for a builder, with the scaffold that makes it answerable, the words to put to them, and the entry key that records the answer. The key is the library's vocabulary name for the question, and `simple-agents view` shows the heading wherever it would otherwise print the key. The earlier stages are always included, so a project that declares a later stage is held to the earlier questions as well.

### 2.2 What a decision became

Four of the six kinds name what the decision produced in the code, under `produces`:

```toml
[decisions.uncommon_sources]
kind = "dependency"
status = "agreed"
recorded_at = "2026-08-27T09:14:02Z"
chose = "Goodreads Listopia tags, awesome-scifi, awesome-fantasy, publisher catalogues"
considered = ["the catalogue the project already has", "a web search per title"]
produces = ["uncommon_books", "explore_tag", "take_books_from"]
because = "the four sources the builder asked for are not in any catalogue this project holds"
```

| Kind | `produces` names |
|---|---|
| `dependency` | The tools it became, by the name each is registered under. |
| `shape` | The nodes it became, by `node_id`. |
| `constant` | The module-level numbers it settled, by the name each is written under. |
| `prompt_rule` | The nodes whose prompts carry the rule, by `node_id`. |

`presentation` and `measurement` carry none, and a brief recording one on either is refused: what a result looks like to a person and what an evaluation scores leave nothing in a run record to join a name against.

**One decision covers as many names as it settled.** A decision agreeing the rate limits every source asks for names all of them.

FT-42 reads these against the node ids, tool names and constants of every run under `runs/` whose role is `agent`, and fails from stage `ship` on a name no run recorded. It reads across every run rather than the newest: a project with more than one pipeline runs whichever it was asked for, so the newest run describes one of them. The report prints the other direction, what the runs hold that no decision names (§4.4).

---

### 2.3 Recording an answer or a decision

`simple-agents record` writes the entry and stamps it from the clock, so `recorded_at` is read rather than composed:

```
simple-agents record answer used_through --text "A phone app over an HTTP API on the builder's machine."
simple-agents record answer anything_else --asked-at build --file answer.md
simple-agents record answer budget --status deferred --deferred-to measure
simple-agents record decision pool_size --kind constant --status agreed --chose "200" \
    --considered "60, the first guess" --produces CANDIDATES_RETRIEVED --from presentation \
    --because "the audit measured recall at 200"
```

The answer or the reason comes from `--text`, from a file, or from standard input as `--file -`. A table already in the file is replaced whole, keeping any key the command did not name, and the rest of the file is left as it was. The name is a question's key, a status one of the three, a stage one of the six, and the file is re-read as a brief before it is written, so a value the checks would refuse is refused here and nothing changes on disk. A question every gate puts again needs `--asked-at`.

The same two from Python:

```python
from simple_agents.conformance import record_answer, record_decision

record_answer("brief.toml", "used_through", answer="A phone app over an HTTP API on the builder's machine.")
record_decision("brief.toml", "pool_size", kind="constant", status="agreed", chose="200",
                considered=["60, the first guess"], produces=["CANDIDATES_RETRIEVED"],
                rests_on=["presentation"], because="the audit measured recall at 200")
```

`rests_on` is written as `from`. Both return what was written: the table, the stamp, and whether an earlier table was replaced.

## 3. What each check reads

All twenty-seven are `artifact` surface: they read files and run nothing.

| Entry | Reads | Fires when |
|---|---|---|
| FT-13 | `runs/<latest>/trajectory.jsonl` | no trajectory, or a file nothing can read as one |
| FT-14 | `runs/<latest>/manifest.json` | a model call happened and the identifier floats |
| FT-15 | `prompts` in `runs/<latest>/manifest.json` | a prompt records no version, which is a prompt whose source could not be read |
| FT-24 | `brief.toml`, against the stage the project is at | a question required at that stage has no answer |
| FT-29 | `idea.md`, and `understanding_confirmed_at` in `brief.toml` | the file is missing, a section is empty, or it was last confirmed at an earlier stage |
| FT-30 | `decisions` in `brief.toml` | a decision is still `proposed`, or one of the six kinds has no entry at all |
| FT-31 | `tools` in the run's manifest, and a live run's `consultation` records | at stage `ship`, a consultation channel reaching a stand-in |
| FT-25 | the brief's `consultation` answer, `tools` in the run's manifest, and `nodes` in `evals/results/<latest>.json` | the answer names something to ask and no consultation tool reaches a node; a pass notes where neither the run nor any rollout asked through it |
| FT-32 | the brief's `tool_effects` answer, and `tools` in the run's manifest | the run declares a side-effect class the answer never mentions |
| FT-33 | `BUILD-LOG.md`, and the newest run's `started_at` | the log was last written before that run started |
| FT-34 | `design.md`, and `design_confirmed_at` in `brief.toml` | at stage `shape`, a section is empty, the builder is not quoted, or it was confirmed earlier |
| FT-35 | `unfinished` in the manifest of every run this pipeline made | a node spent a whole allowance without calling a tool, consulting or delegating |
| FT-36 | `research.md`, and `research_confirmed_at` in `brief.toml` | at stage `research`, a section is empty, a candidate row has no outcome, or it was confirmed earlier |
| FT-01 | `evals/results/<latest>.json` | no evaluation, at tier `evaluated` |
| FT-02 | the same file | one split, or a held-out split that is missing or empty |
| FT-03 | the same file | the contamination report holds a pair spanning two splits |
| FT-04 | the same file | no held-out example expects absence, in its answer or in a condition of its answer key |
| FT-06 | the same file | a metric reported with neither an interval nor a reason |
| FT-07 | the same file, and the trajectories it points at | a rollout or a sampling node with no seed |
| FT-37 | `behaviour_fingerprint` in the same file, and in `runs/<latest>/manifest.json` | at stage `ship`, the reported number was produced by a pipeline that has since moved |
| FT-38 | `confirmed_against` in `brief.toml`, and `runs/<latest>/manifest.json` | at stage `ship`, the entries describing the pipeline were last read against something else |
| FT-39 | `comments.toml`, and `comments_block_gates` in `brief.toml` | a comment the builder left is still `open` and the brief says open comments block |
| FT-40 | the pipelines `agent.py` declares, or `nodes` in `runs/<latest>/manifest.json` where the code declares none | a step is still `NotBuilt`: counted at every stage, a failure from `ship` |
| FT-41 | `suspensions` in the manifest of every run under `runs/` | a run stopped to ask and is still waiting, and no run was ever resumed: counted at every stage, a failure from `ship` |
| FT-42 | `produces` in the brief, against `nodes`, `tools` and `constants` in the manifest of every agent run under `runs/` | a decision names something no run of this project recorded: counted at every stage, a failure from `ship` |
| FT-43 | `mcp` in `runs/<latest>/manifest.json`, one entry per MCP server the run declared tools from | a server offers a description, a schema or a set of tools other than what the project declared |
| FT-44 | `recorded_at` on every entry and decision in `brief.toml`, against the clock the suite runs on | a stamp is ahead of the clock by more than five minutes, so it was composed rather than read |

The report names the run and the results file it read, so a passing report can be checked by hand.

### 3.1 Which run, and which results file

A project accumulates runs, and an evaluation writes one directory per rollout. Every check but FT-35, FT-41 and FT-42 reads the most recent of each, by the manifest's own `started_at` and the results file's own `created_at`. An older run made before a model was pinned does not fail the project.

**Three read more than one run.** FT-35 reads every run the pipeline as it now stands has made (§3.7), since one run does not show what it looks for. FT-41 reads every run under the directory whatever made it. FT-42 reads every run whose role is `agent`, because a project with more than one pipeline runs whichever it was asked for and the newest run describes one of them.

```
simple-agents check                                   # the working directory
simple-agents check path/to/project
simple-agents check --run runs/run_7f2a               # a particular run
simple-agents check --results evals/results/v2.json   # a particular results file
simple-agents check --brief config/brief.toml
simple-agents check --since 2026-08-14 --last 500     # narrows what FT-35 reads
```

`--since`, `--last`, `--role` and `--live` narrow the runs FT-35 reads and reach no other check. `--run` names the run the other checks read and does not narrow FT-35.

**The run and the results file are found separately, and nothing requires them to be the same measurement.** FT-13 and FT-14 read a run; FT-01 through FT-07 read a results file. A project that measured, changed the pipeline, and measured again can have the run checks describing one evaluation and the results checks describing another, especially where the brief's `results` key names a file and stays pointing at it. The report says so when it happens, as a note under the checks:

```
The checks that read a run and the checks that read a results file are describing
different measurements. The run is runs/eval/eval_9c1f/e4-1; the results file
evals/results/held-out-v2.json was scored from runs/eval/eval_4b02.
```

Point `results` in the brief at the measurement the project reports, or pass `--run` and `--results` naming one. A run outside any evaluation, which is what a project has after running its agent once by hand, is not reported.

**FT-37 is the one check that reads both**, and it asks a narrower question than this note: whether the pipeline that produced the reported number is the one the newest run was made by. Two files describing different measurements is ordinary; a reported number produced by a pipeline the project has replaced is not.

### 3.2 FT-13 and what counts as a trajectory

FT-13 passes when the newest run holds a readable trajectory. Every line parses, every record carries the common fields of `docs/trajectory-format.md` §2 and one of the seven record types, and at least one is a `node_execution`. A file that exists and holds something else fails.

The check reads `runs/`. Where a project's envelope writes somewhere else, the failure names the run directory it found and the `--run` that reads it.

**`<latest>` is the most recent run that finished**, by the manifest's own `started_at`, where finished means an `outcome` of `completed` or `stopped_early`. Where no run finished, the newest is read anyway and the checks report what is wrong with it. `--run` names one directly.

**Only runs of the agent are read.** A project's labelling pass, judge or ablation goes through the same envelope and writes into the same directory, and declares itself with `RunEnvelope(role=...)` (`docs/run-envelope.md` §2.1). The checks read the newest run whose role is `agent`, which is every run unless the envelope said otherwise. A project whose only runs declare another role fails FT-13, and the reason counts what it found by role.

### 3.3 FT-14 and what counts as a pin

For self-hosted weights the rule is exact: `model_revision` is a commit SHA, and a bare repo ID or a branch name such as `main` fails.

For a hosted API the identifier is the only signal, since a provider publishes its aliases and its dated names side by side and marks neither as canonical. The check fails an identifier carrying `latest`, `stable`, `preview`, `experimental` or `main`, and passes one it cannot classify. So `mistral-small-latest` fails, `mistral-small-2603` passes, and a hosted name that floats without saying so passes with the identifier named in the report.

A run without model calls passes without requiring a model pin, with the report saying so. What the check reads is the manifest's `observed` list rather than the configured identity alone, so a run that called a model and recorded no pin still fails.

**Every model the run could call is checked.** A node may declare its own client, so the check resolves each node's model, falling back to the run's where the node declares none, and reports one failure per unpinned identifier naming the nodes it serves. Pinning the run's client and leaving one node's floating fails.

### 3.4 FT-03 and an evaluation that ran no contamination check

`contamination_threshold` has no default, so an evaluation that was given none records `contamination: null` and there is nothing for the check to read. That reports `n/a` rather than `pass`: the example set is on disk and the property is computable, so no check was made rather than none was needed, and the line under it says so. The brief's `too_similar` entry is where a project that assigns whole sources to a split records that decision. `EvalSuite.run` refuses a contaminated split before the first rollout, so contamination is normally caught there and never reaches a results file. FT-03 is the backstop for a results file produced some other way.

### 3.5 FT-04 and an output with no absent state

A pipeline whose every model-calling node declares `allow_unknown=False` has stated that this output cannot be absent. FT-04 does not fire for it, because no example could carry an absent answer. Anything else needs at least one held-out example whose correct answer is `unknown`, or one whose answer key declares a condition whose right answer is absence (`Criterion(expects_absence=True)`, `docs/evaluation.md` §1.6). Where the answer is a record, the absent case is usually one empty field, and the condition covering that field is what carries the declaration. What the check reads is `config.nodes` and `examples` in the results file, which is where the evaluation records what each node and each example declared.

### 3.6 FT-06 and a metric with no denominator

Recall over a split where every answer is absent has no denominator. The library reports no value and states why, rather than reporting zero, and that passes. What fails is a number with neither an interval nor a reason.

### 3.7 FT-35 and which runs it reads

**FT-35 reads every run the pipeline as it now stands has made**, and it is the only check that reads more than one. A project spending a quarter of its model calls on executions that produce nothing can have nine runs in ten come back clean, so a figure over the newest run says nothing about the project.

**Which runs those are is decided by `behaviour_fingerprint`**, which every run records in its manifest (`docs/run-envelope.md` §2.1): the newest finished run of the agent names the pipeline, and the runs carrying the same fingerprint are the pool. A prompt, a tool, a budget or a model that changed moves it, so the runs made before a fix are outside the pool the moment the fix has run once. Nothing has to be deleted for the gate to pass.

**A run this cannot read is counted under the reason.** A run of another role, one whose manifest cannot be parsed, one that has not finished, one made by an earlier pipeline, and one older than the counts are each counted and named, so what was read and what is on disk account for each other. A run still executing carries an empty block until it ends, and reading that as a clean run would report a project that spun as one that did not. A run whose process ended before it wrote an outcome is counted apart from one still executing, because only one of them will ever say what it produced (`docs/run-envelope.md` §8.3).

**The counts come from each run's manifest**, under `unfinished` (`docs/run-envelope.md` §2.8), so the check opens no trajectory and its cost grows with the number of runs rather than with their size. A run whose manifest is older than those counts is reported as unread rather than counted as clean, and a project upgrading to this version has them once it has run the agent again.

**What was read is named**, on the report and in the failure message: how many runs of how many, each reason above with its count, and what `--since`, `--last`, `--role` or `--live` left out.

```
     pass  FT-35  Steps spent without a tool call                          runs/, 195 manifest(s)
        Read 195 of the 3,293 run(s) under runs/, 32 under another role, 3,066 made by a
        pipeline this one has changed since. No node spent an allowance without acting.
        `simple-agents report runs/` reads every run under it, including those.
```

**`AgentNode(..., allow_unfinished=True)` waives it for one node**, and the manifest records the waiver, so the gate reads what the run declared rather than what the source says now. A node whose loop is expected to spend its budget without acting declares it; every other node stays gated.

**An execution that acted and then ran out is not this.** A cap that binds after real work is the cap doing its job, and whether the remedy is the cap or the task is a judgement about the project. Those are reported under the checks as a note, and `simple-agents report runs/` prints them per node.

---

## 4. Reading the report

The header names the project, the tier, and **the run the checks that read one read, by its
nodes**. A path does not say what was in it: a corpus build, a labelling pass or a batch script
that goes through the envelope with no `role` writes into `runs/` beside the agent's runs, and
the newest of them is what those checks read (`docs/run-envelope.md` §2.1).

```
simple-agents check: ~/projects/inseam-agent
tier evaluated, declared in brief.toml
reading runs/run_7f2a, 2 node(s): hunt → verify. A pass the project makes for itself
declares RunEnvelope(role=...) so it is not read as the agent (docs/run-envelope.md §2.1).

     pass  FT-13  No trajectory logging                                               runs/run_7f2a/trajectory.jsonl
     pass  FT-14  Model version unpinned                                              runs/run_7f2a/manifest.json
     pass  FT-15  Prompts unversioned                                                 runs/run_7f2a/manifest.json
        2 prompt(s), each with a version recorded.
     pass  FT-24  Elicitation skipped                                                 brief.toml
     pass  FT-29  The project has no current account of itself                        brief.toml, idea.md
     pass  FT-30  Design decisions the builder never saw                              brief.toml
      n/a  FT-31  Shipped on a development channel
        Fires at stage ship, and this project is at measure.
     pass  FT-25  Consultation treated as a fault path                                brief.toml
        The `consultation` answer records that there is nothing to ask.
     pass  FT-32  The brief describes a pipeline that no longer exists                brief.toml, runs/run_7f2a/manifest.json
     pass  FT-33  The build log stopped before the work did
        This project keeps no BUILD-LOG.md. docs/procedure.md asks for one, recording each
        exchange with the builder as it happens, and whether to keep one is the builder's
        decision.
     pass  FT-34  The design the builder agreed to was never written down             brief.toml, design.md
     pass  FT-35  Steps spent without a tool call                                     runs/, 9 manifest(s)
        Read 9 run(s) under runs/. No node spent an allowance without acting.
     pass  FT-36  The ground was never checked                                        brief.toml, research.md
     FAIL  FT-01  No evaluation at all

        No evaluation results found, but this project claims tier `evaluated`. A demo run is
        a single input chosen by someone who wanted it to pass, so it does not measure
        behaviour on inputs nobody chose. Create a labeled example set, define a scoring
        function over it, and run the evaluation. If this project is a throwaway, declare
        tier `prototype` in the brief and this gate will not fire.

  blocked  FT-02  No held-out split
        No readable evaluation results, which FT-01 reports.
  blocked  FT-03  Development examples leaked into the held-out set
        No readable evaluation results, which FT-01 reports.
  blocked  FT-04  Happy path only, no absent-data cases
        No readable evaluation results, which FT-01 reports.
  blocked  FT-06  Point estimate with no interval
        No readable evaluation results, which FT-01 reports.
  blocked  FT-07  Seeds uncontrolled
        No readable evaluation results, which FT-01 reports.
      n/a  FT-37  The reported number came from a pipeline the project no longer has
        Fires at stage ship, and this project is at measure.
      n/a  FT-38  The brief was never read against the code again
        Fires at stage ship, and this project is at measure.
     pass  FT-39  An unanswered comment                                               brief.toml
        No comments.toml; the builder has not commented on anything.
     pass  FT-40  A step that was declared and never built                            runs/run_7f2a/manifest.json
     pass  FT-41  A run stopped to ask, and nothing continued it                      runs/
        None of the 9 run(s) under runs/ stopped to ask anything. A channel returning
        `Shelved` or `Unavailable` never stops one.
     pass  FT-42  A decision names something the project never built                  brief.toml, runs/
        6 name(s) under `produces` were all recorded by runs under runs/.
     pass  FT-43  The MCP server changed under the project                            runs/run_7f2a/manifest.json
        This run declared tools from no MCP server.
     pass  FT-44  A stamp the clock did not write                                     brief.toml
        39 stamp(s), none ahead of the clock.

1 failed, 18 passed, 5 blocked, 3 not applicable
```

| | Means |
|---|---|
| `pass` | the check ran and found nothing |
| `FAIL` | the check ran and fired, and the text below it is the taxonomy's own message |
| `blocked` | the artifact this check reads is missing, and another check reports why |
| `n/a` | the check does not apply: at a tier above the one this project claims, at a stage this project has not reached, or to what this project declared, and the line under it says which |

**A missing artifact fails once.** A project claiming `evaluated` with no evaluation gets one failure from FT-01 and five blocked checks. All twenty-seven are printed either way, so the counts on the last line add up to twenty-seven.

The failure text is read out of `docs/failure-taxonomy.md` and is the same string that document specifies, so acting on the report and acting on the document are the same thing.

### 4.1 Exit status

| | |
|---|---|
| 0 | no check failed |
| 1 | a check failed |
| 2 | the suite could not run, which is a missing or unreadable brief |

### 4.2 As JSON

```
simple-agents check --json
```

Every check with its outcome, its findings, and what it read, plus `reading`, `notes` and the counts. This is the report of one run rather than an artifact the project keeps, so nothing writes it to disk.

### 4.3 From Python

```python
from simple_agents.conformance import run_checks

report = run_checks("~/projects/inseam-agent")
report.ok                                   # False when any check failed
[c.entry_id for c in report.failed]         # ['FT-01']
print(report.text())
```

### 4.4 The notes under the checks

A note is a fact about what the report read, printed under the checks. It never changes the exit status, and it is addressed to the coding agent rather than to the builder.

**The run and the results file are different measurements**, which happens where the project measured, changed the pipeline and measured again (§3.1).

**The newest run is a live one**, so the checks that read a run are reading what an end user did (`docs/shipping.md` §1).

**The tier drops stages the artifacts show**, which is a project with a results file claiming `prototype` (§1.1).

**The pipeline has moved since the brief was confirmed.** Every gate fires when a project reaches a point, and what makes a brief entry wrong is a change, so the answer is still `answered` and the code beneath it is not what it describes. The brief records `confirmed_against`, the `behaviour_fingerprint` of the pipeline its entries were last read against (`docs/run-envelope.md` §2.1), and the note fires where the newest run recorded a different one:

```
The pipeline has moved since the brief was confirmed at sha256:213998182146fc28, and
the run at runs/run_7f2a recorded sha256:94e59c769d747f81. These entries describe the
pipeline and are due for re-reading against the code; correct what has gone stale,
then record confirmed_against = "sha256:94e59c769d747f81": agency_boundary,
consultation, presentation, backend, budget, tool_effects.
```

It names entries whose answers describe something the fingerprint covers: the shape, the prompts, the sampling, the tools, the declared model, `allow_unknown` and the budgets.

It reads the fingerprint the newest run recorded, so a pipeline edited and not run leaves it silent until the project runs again. `tool_effects` is checked against the manifest directly and needs no fingerprint (FT-32).

**The note stops at stage `ship`, where FT-38 fails on the same comparison.** A pipeline moves several times an hour while a project is being built, which is why the gate waits; a project about to be used by somebody else has read its own claims against the code at least once since the code last moved.

**The number was measured over a different pipeline.** The same comparison for the results file the brief names, and it stops at `ship` for the same reason, where FT-37 fails on it:

```
The number in evals/results/held-out.json was measured over sha256:213998182146fc28,
and the newest run under runs/ was made by sha256:94e59c769d747f81. A prompt, a
node's version, a sampling parameter, a tool, the model or a budget has moved since
that file was written. FT-37 fails on this from stage ship; until then it is
reported, because what clears it is another evaluation.
```

**The rollouts a results file describes are not the ones on disk.** An evaluation's directory is named for its identity, so the join needs no path (`docs/evaluation.md` §6); the recorded rollout paths are where the project ran, which a copy or a move breaks. Two things fire it: the directory is gone, or a rollout in it started after the file was written, which is a re-run into a directory that was cleared.

```
runs/eval/eval_7423149289e3/ holds 21 rollout(s) that started after
evals/results/held-out.json was written at 2026-08-21T11:46:26.485Z, so the file does
not describe them: cut-2024-09-23-0, cut-2024-09-23-1, cut-2024-09-23-2
and 18 more. An evaluation re-run into the
same directory writes under the same identity, and the seeds match while the figures
are of the earlier rollouts. Re-score against what is there, or point the brief's
`results` key at the file that describes it.
```

**What the live runs did.** From stage `ship`. Every check but FT-31 reads a run that is not live, so what a shipped project does now is reported rather than certified. A live run carries the end user's material and can be sampled down to no payloads, which is why it is not what the suite reads.

```
The newest run an end user made is runs/live/2026-08-24/run_9e12, started 2026-08-24T21:51:59.618Z,
and the checks above read runs/eval/eval_4b02/cut-1, which is a run made while building.
Live runs are what this project does now, and they are not certified here: a live
run carries the end user's material and can be sampled down to no payloads. FT-31
reads one, and `runs("runs/", live=True)` reads them all.
```

**The builder's comments are open.** A comment arrives unprompted from the served view, and between gates nothing else brings it to the coding agent. FT-39 fails the gate where the brief says `comments_block_gates = true`; otherwise the open threads print here:

```
1 comment thread(s) from the builder are open: recommend/judge_candidates: 'Why does this
rank the whole catalogue before truncating?'. Each is the builder pointing at a part of the
system from the view. Read them with `simple-agents comments`, do what each asks or take it
back to the builder, then set status = "addressed" with addressed_by naming what answered
it. comments_block_gates = true in the brief makes an open thread refuse the gate.
```

**Spend that produced nothing.** A node with an execution or a fan-out item that ended without producing an output, where some of them acted before running out (§3.7). It names what those spent:

```
Over 195 of the 3,261 run(s) under runs/, these produced no output and spent to do it: hunt
28 execution(s), spending 772 model call(s). An execution that ends on a budget axis returns
None to the node after it and the run completes, so no other figure reports it.
```

**Answers no design decision rests on.** A `shape` or `presentation` decision records `from`, naming the brief entries it was derived from:

```toml
[decisions.pipeline_shape]
kind = "shape"
status = "agreed"
recorded_at = "2026-08-27T09:14:02Z"
chose = "a stateless run over the export, re-read each time"
considered = ["a queue the agent adds to", "a batch job"]
from = ["not_building", "one_real_input"]
because = "the interface is out of scope until the output schema settles"
```

From stage `shape`, the report prints the complement: the answers about what the builder wants built that no such decision names.

```
Answers about what the builder wants that no shape or presentation decision rests
on: finished_version. Read each against what is being built. Where one does not
bear on the shape, say so in the decision that supersedes it; where it does, name
it under `from`.
```

Seven entries are read: `what_it_does`, `purpose`, `end_user`, `smallest_worthwhile`, `finished_version`, `not_building` and `success_story`. The rest of the brief says how the project is built or how well, which the note above and the checks already cover. A `from` naming an entry the brief has none of is reported beside it.

**What the runs recorded that no decision names.** The other side of `produces` (§2.2), from stage `shape`. A decision names what it became; this is everything the runs hold that no decision named: a tool that ran, a step that ran, a number the code defines.

```
What the runs recorded that no decision names, which `produces` on a dependency,
shape, constant or prompt_rule decision records: 25 of 34 node id(s):
apply_shortlist, attach_evidence, attempt_fetch and 22 more. 8 of them were last
seen before 2026-08-24. 3 of 4 tool name(s): http_fetch, read_page, wiki_fetch.
43 of 48 constant(s): ARTICLE_CHARS, CANDIDATES_WANTED and 41 more. A name that is
gone goes under `produces` on the decision that removed it, recorded `changed`.
```

**It reports and never fails.** Which of a project's numbers change what the agent does and which are a source's published rate limit is a judgement, and a gate over all of them would be cleared by naming them rather than by reading them. FT-42 is the direction that gates, and it fires on a decision naming something no run has.

**A name carries the day of the newest run that recorded it**, shown where that is earlier than the day of the newest run read, so a step the project removed reads as removed. Naming it under `produces` on the decision that removed it takes it off the list, and that decision reaches the builder as `changed`.

Manifests record constants from format `0.33`. A project whose runs all predate it is told that rather than being read as one whose code defines no number, and FT-42 leaves out the names only a `constant` decision records rather than failing a project for numbers it has.

---

## 5. What the suite does not do

Twenty-seven of the taxonomy's forty-four entries are checked here. The rest are the specification of correct practice and are not yet enforced, except the six the library enforces by construction: an output schema with no `unknown` branch (FT-09), a loop with no budget (FT-18), a tool with no side-effect class (FT-19), an evaluation over a tool that spends or cannot be undone (FT-20), a tool with no description (FT-23), and a node reading a type nothing reaching it can be (FT-28). Those refuse at author time rather than reporting at the end of a run.

**Every check verifies that a process was followed. Whether the result is correct cannot be verified by the library.** A project at full conformance measured something carefully. FT-24 establishes that the builder was asked what the right thing to measure is. Two checks read an answer's text and neither judges it: FT-25 reads whether the `consultation` answer opens on a negation, and FT-32 whether the `tool_effects` answer mentions each class of effect the run declares.
