# Build log — What the checks read

`plan.md` §1 P3-34. Started 2026-08-25. Written while building, not afterwards.

Dogfood #5's sitting 2, five candidates: `DF5-I08` to `DF5-I12`, plus `plan.md` §2.2's
variant-arm entry folded in at the sitting. Every one of them is a check that passed over
something it should have seen. The decisions are
[`runs/dogfood-5/inventory.md` §3](../runs/dogfood-5/inventory.md#L177), written to the rows at
the sitting, and this log is what building them cost.

## 1. Before any design

Measured against the frozen copy at `~/Projects/dogfood-5-frozen` and against the current
source, at the sitting on 2026-08-25. Nine things, and three of them changed what was proposed.

**The project set `role=` on none of its envelopes, and `live=True` on some.** Thirteen
`RunEnvelope(...)` constructions across `web/app.py`, `scripts/evaluate.py`,
`build_summaries.py`, `ingest_all.py`, `discover_once.py`, `first_run.py`, `probe_resolve.py`,
`smoke.py` and `vllm_smoke.py`; 2,669 manifests all carrying `role: "agent"`; 51 carrying
`live: true` through `env.with_live()`. **The same object's other field was found and used**,
which is what ruled out "the docs should say it again" as the fix:
[`docs/run-envelope.md` §2.1](../../docs/run-envelope.md#L110) describes `role` with a labelling
pass and a judge as its examples, both model-calling passes over the project's own data, which
is what `build_summaries.py` is.

**Nineteen distinct pipelines have run under `role="agent"` in that project.** The two corpus
ones account for 2,310 runs: `seed_resolution → attempt_fetch → validate_match →
fold_resolution → finish_resolution` (1,318) and `write_summary → keep_summaries` (992). The
product accounts for 308 across nine of the nineteen, which is what four days of iterating on a
graph looks like and is why *more than one pipeline under one role* is not the signal.

**FT-03 is the only check that passes having measured nothing.** Seven checks can pass carrying
a detail. Six are vacuously true: no model call so no model to pin (FT-14), no tool so nothing
to describe (FT-32), no prompt so no version (FT-15), the brief records there is nothing to ask
(FT-25), no build log and keeping one is the builder's call (FT-33), and absence waived by every
node declaring `allow_unknown=False` (FT-04). FT-03 is the one where the artifact is on disk and
the property is computable. That is what kept `DF5-I09` a one-check fix.

**The project's `too_similar` answer is the documented no-threshold case**, `brief.toml:565`:
*"This project assigns whole sources to a split and needs no text threshold, which
`contamination_threshold` is left unset to say."* The elicitation scaffold
([`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L691), `too_similar`)
allows exactly that, so the answer is sound and the report line was the defect.

**The results file carries `graph_fingerprint` and not `behaviour_fingerprint`**, while every
manifest carries both ([`runner.py`](../../src/simple_agents/evaluation/runner.py#L2444),
`_config`). Its `config` already holds `nodes`, `containers`, `prompts`, `tools`, `model` and
`budget`, which is most of the digest's material undigested.

**The rollout paths in a results file are absolute into the tree the project ran in.** Read off
`evals/results/eval_7423149289e3.json`: `/home/thilina/Projects/dogfood-5/runs/…`. In the frozen
copy every one of them points outside the tree, so a check comparing paths would have reported
27 false failures. This is what made the join an identity join.

**`simple-agents check` prints the `confirmed_against` note with twelve entries due**, and the
log records it printing on all 21 runs of the suite with nothing recorded on any of them. Its
rationale is in shipped code ([`run.py` `_the_pipeline_moved`](../../src/simple_agents/conformance/run.py#L369)): *"It reports and never fails."*

**`simple-agents report runs/` prints three produce-nothing lines the check does not.**
`judge_candidates` 29 units spending 251 of 3,451 model calls, `find_candidates` 5 units
spending 117 of 175, `hunt_reviews` 12 units spending 56 of 87. FT-35 passed on the same tree
saying *"Read 6 of the 2,669 run(s) under runs/ … 2,650 made by a pipeline this one has changed
since. No node spent an allowance without acting."* The scope is deliberate
([`spend.py`](../../src/simple_agents/conformance/spend.py#L66)) and right; nothing said the
excluded set was readable elsewhere.

**A `ship`-stage check is not a one-time event.** `stage = "ship"` stays in the brief and
[`reached`](../../src/simple_agents/conformance/stages.py#L98) never goes backwards, so a check
naming that stage runs every later time the suite does. This is the fact the whole of `DF5-I12`
rests on, and it was checked in the source before it was proposed.

## 2. Design

Five decisions, taken at the sitting on 2026-08-25 and recorded on their rows. What follows is
what each became; the arguments are in the inventory.

**`DF5-I08`, the batch pass that ran as the agent.** The report names the pipeline the
run-reading checks read, by its nodes, on every run. A path does not say what was in it, and
`write_summary → keep_summaries` under a recommender's conformance report is visible where
`runs/run_20260821T…` is not. **It is a header line and not a note**, decided while building: a
clean project prints no notes, and making one unconditional would have changed what a note
means. `procedure.md`'s one sentence about `role=` generalises past a labelling pass and moves
from the Layout section into stage `build`, where a batch script gets written. **FT-33's rule is
unchanged**: `role` was the defect, and with the corpus passes declared the newest agent run
dates the log again.

**The variant-arm entry, folded in.** `plan.md` §2.2 had deferred *"a variant arm saying it is
not the agent"* since 2026-08-10 with its decider named as *what FT-13 and FT-14 are for*. The
answer taken here: **an arm declares `role="variant"` and the baseline keeps `agent`**. An arm
is a pipeline the project does not have; the baseline is the pipeline it has, run over the
example set, so a project that has only ever swept still has runs to certify and the entry's
stated cost does not land.

**`DF5-I09`, FT-03.** `not_applicable` rather than `passed`, detail unchanged in substance. The
example set is on disk and the property is computable, so no check was made rather than none was
needed. `n/a` gains a third reason.

**`DF5-I10`, the headline and the pipeline that made it.** Three parts. The results file records
`behaviour_fingerprint`. `check` **fails at `ship`** where it differs from the newest agent run's
and reports it before that, because a pipeline moves several times an hour while it is being
built and what clears the failure is another evaluation. The rollouts join by the evaluation's
identity rather than by the recorded paths, and drift is a note rather than a failure.

**`DF5-I11`, the two ungated instructions.** `confirmed_against` becomes a gate at `ship`, which
defeats a rationale written into shipped code; the objection is accepted rather than argued
away, since the clearing action is mechanical and the measured alternative is that it is never
done at all. **There is no report gate.** A report is read rather than passed, and the signal the
instruction wanted is inside `check` and scoped away, so FT-35's own pass line names the runs it
did not read and points at `simple-agents report runs/`.

**`DF5-I12`, the road after the last gate.** No seventh stage. A stage moves the boundary rather
than removing it. What governs that road is checks whose subject is change, which is what FT-37
and FT-38 are, on the fact from §1 that a `ship`-stage check goes on firing. **And the limit is
stated rather than left to be found next run**: the library cannot see the web app, the queue
worker or the scheduled job, and the one artifact that road leaves is the live run, which no
check but FT-31 reads. `check` gains a note at `ship` naming what the live runs did.

**What was weighed and not taken.** A note rather than a header line for what the checks read,
dropped for the reason above. A gate on `simple-agents report`, dropped because nothing records
that a command ran. Reporting the produce-nothing figures across pipelines, dropped because a
stale figure reported as a live finding is what the scope rule exists to prevent. An elicitation
question asking what else writes runs, dropped because the six decision kinds cover none of it
and it is the coding agent's decision rather than the builder's.

## 3. Build

**Two taxonomy entries**, written into `docs/failure-taxonomy.md`, which is where the suite
parses them from. **FT-37**, *the reported number came from a pipeline the project no longer
has*, `artifact · evaluated · Stage: ship`. **FT-38**, *the brief was never read against the code
again*, `artifact · prototype · Stage: ship`. The suite runs twenty-one checks and the taxonomy
holds thirty-eight entries. Five entries now name a stage.

**Results file `0.23` to `0.24`**: `config.behaviour_fingerprint`, written by
[`_config`](../../src/simple_agents/evaluation/runner.py#L2401) from the pipeline and the model,
and by [`_rescored_config`](../../src/simple_agents/evaluation/runner.py#L2464) off the rollouts'
own manifests, since re-scoring runs nothing.
[`_behaviour_fingerprint`](../../src/simple_agents/evaluation/runner.py#L2451) records `null`
where the stamp cannot be taken, which FT-37 reports as blocked.

**`Report` gains `reading`**, a header line under the tier, and the JSON carries it.

**One header line and three notes**, none of which fails anything:
[`_what_the_checks_read`](../../src/simple_agents/conformance/run.py#L130) is the header;
[`_what_the_live_runs_did`](../../src/simple_agents/conformance/run.py#L164) fires at `ship`;
[`_the_number_came_from_elsewhere`](../../src/simple_agents/conformance/run.py#L187) is FT-37
before `ship`; and
[`_rollouts_the_results_file_does_not_describe`](../../src/simple_agents/conformance/run.py#L273)
is the identity join. `_the_pipeline_moved` now stops at `ship`, so the report carries that
comparison once.

**Two shared readings** lifted out of the note that had them:
[`entries_about_the_pipeline`](../../src/simple_agents/conformance/checks.py#L1586) and
[`current_fingerprint`](../../src/simple_agents/conformance/checks.py#L1604), both used by the
check and by the note.

**`compare_variants` gives every arm but the baseline `role="variant"`**, exported as
`VARIANT_ROLE`. No format moved for it: the manifest has carried `role` since `0.16`. **And it refuses an envelope declaring `live=True`**, before the baseline
runs. `RunEnvelope` already refused `role` and `live` together, so declaring the arm made that
refusal reachable from a sweep, on the first arm, after the baseline had been paid for; the
guard moved it to the front and says what is wrong with the call.

**What the build found that the design did not know.** Four things, all from reading the code
back rather than from the suite. The verification cycles below found the rest.

- **A rescored results file would have been reported as an evaluation whose rollouts are gone.**
  Its identity is the rescoring configuration's and names no directory, so the note told the
  reader to `rescore` a path that never existed. `config.scored_from` separates the two, and the
  note now reads a file written by a run of the suite alone. Reproduced and fixed with a test.
- **The timestamps were compared as text.** Both are written by `utc_now()` at millisecond
  precision, so it was right for every file the library writes; one written at second precision
  sorts after the same instant with milliseconds, because `Z` is above `.`. Parsed now.
- **`textwrap` broke `docs/run-envelope.md` across a line** as `docs/run-` and `envelope.md`, in
  the new header line and in every message the report has ever wrapped. `break_on_hyphens=False`.
- **The sample report in `docs/conformance.md` would have shown a wrap the text does not have.**
  The test substitutes a short path into a rendered report, so the header wrapped where the long
  fixture path put it. The substitution happens on the `Report` now and the text is re-rendered.

**Tests: 3048 to 3082.** Thirty-four new, in six classes: FT-37, FT-38, the header line, the
rollout join, the live-runs note and the three §4.4 samples against what the code renders, plus
the arm's role and the live refusal in `tests/test_variants.py`. The conformance fixtures were
rebuilt, so `conforming/`'s results file carries the stamp its manifests do.

**`scripts/shape_baseline.json` moved three times**, each deliberate: units already recorded
that grew by a key, a note or a guard. Two new functions crossed a threshold they had never been
over and were decomposed rather than recorded, and `compare_variants`' two literal preflight
refusals moved into `_refuse_before_planning` when the live guard pushed it over.

**`docs/procedure.md`'s word budget went from 2160 to 2400**, recorded with its reason in
`tests/test_procedure.py`, for the role instruction and what the ship gate goes on doing.

## 4. Verification

**Fifteen full cycles**, each one a reading of the code, a reading of the documents, the suite
and the four scripts, and a live run against vLLM. A cycle is clean only when all four steps find
nothing, and each cycle's findings are listed below. **Fourteen of the fifteen found something
the suite and the checks could not see, and most of it was prose**: what the shipped documents
said about the code, and what these records said about the build. **The shipped source moved in
the first two cycles and not after**, so what the later ones found was always a statement about
it rather than it.

**Live, against vLLM `Qwen/Qwen3-1.7B` on port 8001.** A probe of thirty-two assertions over ten
sections, run to completion in every cycle. Nothing in it replays: every run is a real call, so
the manifest, the results file and the report are what the library writes.

What only the live run showed: the stamp a real evaluation writes equals the one the pipeline
computes and the one its manifests carry; `rescore` records what produced the rollouts and not
the pipeline it was handed; a `Deterministic` corpus pipeline run under `role="corpus"` leaves
the header naming the agent's node, and the same pipeline run without one takes it over, which
is dogfood #5's failure reproduced end to end; editing a prompt version moves the stamp, and the
two notes fire before `ship` while neither gate does; at `ship` both gates fail, FT-37 naming
both stamps; and recording the value and re-running the evaluation clears both. **A real sweep**
writes two runs under `agent` and two under `variant`, each role's runs carrying one stamp and
the two differing, each arm's results file recording its own; a project whose only runs are that
sweep still certifies the baseline, which is what the deferred entry's cost note asked about.
**The commands** were run over the project the probe built: `check` exits 1 with the header
naming the pipeline it read, and `report` reads the same directory.

**Cycle 1, eleven defects.** Four in the code: `compare_variants` under a live envelope raised a
confusing refusal on the first arm, after the baseline was paid for; `_summary`'s docstring said
`n/a` covers two reasons; a helper named `_fingerprint_in` was reading `started_at`, and the
manifest's stamp was read three ways; and `_started_after` raised `TypeError` rather than saying
nothing on a naive timestamp. Seven in the documents: two entries in the shipped taxonomy carried
anecdotes from this run's own project, which is history in the surface a builder reads; FT-38's
`Check` said a project with no pipeline entry gets a note where it passes; `docs/conformance.md`
§4.2 did not name the new JSON key; `docs/run-envelope.md` §2.1 did not say the library declares
`variant` itself; `docs/procedure.md` told a builder to declare an ablation arm the library now
declares; `docs/shipping.md` generalised from one project with *"often"*; and FT-37 said *"says
which"* for *"says so"*.

**Cycle 2, six defects.** A local named `found` shadowing the module's own word for the
artifacts. `docs/conformance.md` §3.1 is about a run and a results file describing different
measurements and did not name the check that now reads both. Two of the three new §4.4 samples
were trimmed to fit and read as whole notes, one of them dropping the sentence naming the action:
**that is what `TestTheDocumentedNotesAreWhatIsPrinted` now guards**, on the precedent of the
sample-report test, and writing it is what found them. The rollout sample named three rollouts in
an order a lexical sort does not produce. And FT-37 and FT-38 had no test for the other blocked
path, a manifest written before the field existed.

**Cycle 3, four defects, all in what the work says about itself.**  The results-file bump makes
`EvalResults.read` and `compare` refuse every file on disk, which `docs/evaluation.md` §8 did not
say and which is what a project meets first. The `CHANGELOG` entry read *"They read a change
rather than an arrival, which every other check does"*, which says the opposite of what it means.
Its FT-03 paragraph said *"The check made no check"*. And the live refusal was in the code and in
no record. **The records themselves were a cycle's finding**: this log, `plan.md` §4 and
`handoff.md` all described the build as cycle 1 left it.

**Cycle 4, three defects, two of them older than this item.** The taxonomy's `Counts.` line
tallied its own index wrongly, 26 artifact against 27 and 3 static+artifact against 2: it was
already off by one before this item and this item moved the number without recomputing it.
Nothing read that line, so **`test_the_index_counts_what_the_index_lists` now does**, checked
against the wrong line it was written for. And the record of the sitting repeated the deferred
entry's cost note, *"declaring the arms makes a project that has only ever swept fail FT-13"*,
which is true of the option not taken: the live probe measures that a project whose only runs
are a sweep certifies the baseline. The row said the entry was folded in and never what was
decided.

**Cycle 5, three defects, two of them in this log.** §5 named every document and not `CHANGELOG.md`,
which the template asks for by name, and its list of shipped statements that stopped being true
was short by two. §4 stopped at cycle 3. **The handoff named the checks and the format and not
the new refusal**, which is the one a project trips on without reading anything.

**Cycle 6, three defects.** §1 of this log said the product accounted for 269 runs, which was
the sum of the three fingerprints that had been printed rather than a measurement: it is 308
across nine pipelines, and the nine are why *more than one pipeline under one role* was rejected
as a signal. §1 is the section whose rule is that a figure is measured rather than asserted, and
every other figure in it re-measured correctly. `docs/shipping.md` §1 is where a builder learns
the checks read the runs that are not live and did not name the note that now says which. And
the sweep's role test read each manifest twice.

**Cycle 7, two defects, both statements with no guard.** `docs/conformance.md` §3 is a row per
check and nothing compared it to the registered set; the taxonomy's own sentence naming the
staged entries duplicates `conformance.md`'s claim in the other document and only that copy was
read. Both were right and both are now checked. **The first guard written for the second was
itself weak**: the paragraph names two of the five entries again after the claim, so a set over
the whole line let an id dropped from the claim be covered by its own second mention. Each guard
here was run against the defect it was written for, which is what found that.

**Cycle 8, four defects, three of them in §3 of this log.** It said *"Four notes"* and then named
one of the four as the header line; it dated `role` to manifest `0.24` where the manifest has
carried it since `0.16`; and it carried a running count of what the cycles had found, which was
right for one cycle. The fourth was a test helper whose `live` parameter had one value at every
call site and no case that could use the other.

**Cycle 9, three defects, all in the two new taxonomy entries.** Both *"What happens"* sections
said no gate catches the failure, which is what an entry says when nothing does and is what
these two now do; the house pattern is to describe the behaviour and leave the checks to the
*Check* section. And FT-38 said *"no other check compares the two"*, which is false for one of
the twelve: FT-32 reads `tool_effects` against the manifest's tools, and the report's own note
has said so all along. Its counts are guarded now.

**Cycle 10, two defects, both in the sitting's own record.** `DF5-I10`'s subsection said the
suite knows the model at write time so the fingerprint's refusal *"cannot fire"*. It can:
`EvalSuite.run` takes `model=None`, and the build wrapped the call for exactly that. The
subsection also described the identity join without the carve-out the build added for a rescored
file. Both are corrected in place, the first with what was said at the sitting kept beside the
correction, because a record that quietly becomes right hides that the sitting was wrong.

**Cycle 11, two defects, both the same kind.** `DF5-I11` and `DF5-I12`'s record called
`DF5-I08`'s header line a note, and described the live-runs note as naming how many there are and
which pipeline made them, which is what the sitting wrote down and more than what shipped. The
count is a second pass over every manifest on top of the one FT-35 makes, and the pipeline is what
the header line already names; both were dropped at the build and the record now says so beside
what it said before.

**Cycle 12, one defect.** The whole diff read end-to-end, deletions included, `pyflakes` over
every file this item touched, and the four scripts and the live probe clean. What it found was in
this section: the stability line below still counted the tests as cycle 3 left them.

**Cycle 13, one defect, and it was this section claiming the next cycle was clean.** The line
above said cycle 13 found nothing, written before cycle 13 ran; the paragraph opening this section
said nine of thirteen cycles found something where twelve had. Writing down a verification's
result before running it is the failure this whole item is about, one level up.

**Cycle 14, one defect.** The opening of this section said four defects were in the shipped
source; cycle 2's rename is a fifth, and a count of that shape rots on the next cycle. It says
what is checkable instead: which cycles the source moved in.

**Cycle 15 found nothing**, which is what ends this.

**Against the frozen dogfood #5 copy**, which is the project the item was written from.
`simple-agents check` there now reports `1 failed, 18 passed, 1 blocked, 1 not applicable`:
FT-38 fails naming twelve entries and the fingerprint to record, FT-37 is blocked because that
results file predates the field, FT-03 reads `n/a`, the header names the nine-node pipeline the
checks read, and the live-runs note names `runs/queue-20260824-235159`. Before this item the
same tree reported `0 failed, 19 passed`.

**Stability.** Fifteen cycles, the fifteenth clean; forty-six defects across the fourteen that
were not, and the shipped source stopped moving after the second. The suite at 3086, the live probe over every cycle, `prose_check`,
`shape_check`, `check_citations` and `check_docs` clean.

## 5. Doc consequences

`docs/failure-taxonomy.md`: FT-37 and FT-38 as full entries, two index rows, the counts, and the
sentence naming the entries that carry a stage.

`docs/conformance.md`: the tier table's counts, the staged-entry sentence, two rows in §3's
table, a paragraph in §3.1 naming the check that reads both a run and a results file, §3.4
rewritten for `n/a`, the outcome table's `n/a` row, §4's header paragraph, a regenerated sample
report, `reading` in §4.2, three new notes in §4.4 and the `confirmed_against` one saying where
it stops, and the FT-35 sample line.

`docs/procedure.md`: the `role=` instruction generalised and moved into stage `build`, the
`confirmed_against` line naming its gate, the `report` line saying the gate reads less than the
report, the `n/a` definition, and two paragraphs after the ship gate on what goes on firing and
what the library cannot see.

`docs/evaluation.md`: `behaviour_fingerprint` in the results-file field table, the format
version, what the bump does to a file already on disk, and the arm's role in §10.

`docs/shipping.md`: the ship gate not closing, in the opening; and §6 saying that FT-37 reads the
same stamp for a different question and says nothing about what is in the store.

`docs/run-envelope.md`: §2.1 pointing at the header line that names what the checks read, and
saying that the library declares one role itself.

`CHANGELOG.md`: the entry above the consultation one, carrying the results-file bump and what it
does to a file already written, both gates, the header line, FT-03's outcome, the two notes,
FT-35's pass line, the arm's role and the live refusal.

`README.md`: the two counts it states, 38 entries and twenty-one checks. **That file is held by
another session's uncommitted work on `P3-31`**, and the edit is one line inside a sentence that
work does not touch.

**Shipped statements that stopped being true**: `docs/conformance.md` said FT-03 passes where no
threshold was set, and that `n/a` covers two reasons; `docs/procedure.md` said `role=` is for a
labelling pass and told a builder to declare an ablation arm the library now declares;
`docs/shipping.md` generalised from one project; both `docs/conformance.md` and
`docs/failure-taxonomy.md` counted nineteen checks and thirty-six entries; and
`docs/failure-taxonomy.md`'s surface tally had been wrong by one in two buckets since before
this item.

## 6. Left open

- **`variants.to_record` records `graph_fingerprint` per arm and not `behaviour_fingerprint`.**
  Found while reading the code back for this item. Arms differ by a plan the shape fingerprint
  cannot see, so two arms differing only in a prompt record the same value, which is the blind
  spot FT-37 exists to close for a headline. One `.get()` per arm and a variant-format bump.
  Not taken here because it was not what the sitting decided. →
  [`plan.md` §2.1](../plan.md#L43).
- **A shipped comment names an internal run.**
  [`artifacts.py:78`](../../src/simple_agents/conformance/artifacts.py#L78) `SURVEY_SECTION` opens *"empty outcome
  is what dogfood #4's four-source table recorded against award shortlists"*, which is
  development history in the source a builder reads, and no check sees it. One line, and the
  question is whether `prose_check` should read it. → [`plan.md` §2.1](../plan.md#L54).
- **The rollout join reads a manifest per rollout on every invocation of the suite.** Bounded by
  one evaluation's directory, so 27 files on the project this was measured against and unbounded
  in principle. Destination: nothing, until a project makes it slow.
