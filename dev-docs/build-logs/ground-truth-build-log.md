# Ground truth — the sitting, and the build

Held 2026-08-09, on the labelling machinery (`archive/dogfood-absorption.md` item 10) and **DF2-D8**
(`runs/dogfood-2/findings.md` §11.2), merged into one sitting on Thilina's ruling that `label.py` is
the artifact behind both. The subject: how a project's ground truth gets made, where it is
stored, and whether any check can see it.

**What it settled.** The disposition this sitting inherited rested on a test that was never
administered, so the ruling it recorded was never actually challenged. Underneath that were
three separable problems and only one of them was a missing feature. What shipped is `§1.4`
rewritten to a shape that was measured rather than argued, `role=` on a run, a label store with
one required field, and one elicitation question moved to the stage where the work happens.

---

## 1. What was measured, before any design

### 1.1 The test at `runs/dogfood-1/run2-findings.md` §9.3 was never administered

The disposition read: "If a third does it with §1.4 in place, the docs are not the problem."
Dogfood #2 did it, so the record concluded the docs were not the problem. **Neither half of
the fix reached that session**, and the two reasons that matter would reach any builder.

| Route | Measurement |
|---|---|
| Whether §1.4 was opened at all | `BUILD-LOG.md` is 120,122 bytes. It names `procedure.md` ×10, `pipeline.md` ×10, `tools.md` ×9, `run-envelope.md` ×1, `index.md` ×1, and **`evaluation.md` zero times**. A subsection of a document nothing routed the session to is a subsection it never saw. |
| The elicitation | `who_labels` was `stage="measure"`; `questions_at` is cumulative upward only; the log records one invocation, `simple-agents questions --stage shape`; `brief.toml` declared `stage = "build"` throughout and holds nine entries, none of them `who_labels`. The scaffold that names §1.4 was never printed and no gate required it. |

Those two are the finding, and they are what stage 2's routing and the move of `who_labels`
answer. **A third reason existed and is not evidence about the library**: this project's venv
carried a `docs/` copy dated 2026-08-06 19:10 CEST, a day and a half older than §1.4, because
an editable install onto the live tree gives live code and a frozen `force-include` copy of the
docs. That can only happen to someone who is both the builder and the library's author. A
builder installs a released wheel and gets the docs that shipped with it, verified here against
a clean install of the wheel this build produced. It is recorded so a later reader does not
re-derive it and mistake it for a defect.

**The same routing failure, independently, in run 2.** `brief.toml` mtime is 18:05 and
`evals/verification.jsonl` is 16:10. The question that governs how ground truth is made was
answered nearly two hours after the ground truth was made — with no stale anything involved.

### 1.2 The pass with no record, re-derived from the files

`dogfood-1-run2/evals/verification.jsonl` holds **60 records: 2 answerable, 2 flagged, 57
clean, 1 answerable whose quote did not verify**. That is pass 2. Pass 1's 39 are nowhere, and
the mechanism is the project's own:
[verify_unanswerable.py:162](../../../dogfood-1-run2/tools/verify_unanswerable.py#L162) opens
the path with `"w"`. The store is single-slot; pass 2 overwrote pass 1 in place.

`runs/` in that project holds **635 manifests**, every one naming
`prepare,retrieve,answer,finalize`. Dogfood #1: **474**, all `prepare,retrieve,answer,report`.
Neither project has a single labelling run.

**The downstream cost is on disk.**
[build_examples.py:44-52](../../../dogfood-1-run2/tools/build_examples.py#L44) drops SQuAD id
`5a2eb84ba83784001a7d241f` from the shipped set, reasoning "Not flagged by the second judge,
but flagged by the first". Checked against the surviving artifact: `answerable: False,
flagged: False`. The id is absent from the 60 examples in `evals/questions.jsonl`. **An example
was removed from the held-out set on a disagreement between two passes, and only one of the two
exists.** The reason is a Python string literal in a build script. Nothing can reconcile them.

Pass 1 ran on `mistral-small-2603` and pass 2 on `mistral-medium-2604`, recorded in build-log
prose and nowhere machine-readable. FT-14 pins the model the agent ran on; nothing pinned the
model that decided what the agent was graded against.

### 1.3 The probe: §1.4 ran, and was wrong in three ways

Run against the current library with `FakeModelClient` over 60 candidates, rather than reasoned
about. **It works** — output validates, manifest written, cassette written, model pinned. The
capability claim in §9.3 was correct.

| | §1.4 as written | Fan-out (`over=`) |
|---|---|---|
| Run directories | **60** | **1** |
| Bytes written | **613,218** | **93,091** |
| Cost of the pass | across 60 manifests, no total | one figure, `$0.00084` |
| What `max_cost` bounds | **one candidate** | the pass |
| Whether `max_steps=1` works | yes | **no, `BudgetExceeded` after item 1** |

The budget point is measured: with `max_cost=$0.00002`, all 60 runs completed and the pass spent
`$0.00084`, **42× the declared limit**, nothing `stopped_early`. A reader takes `max_cost=0.05`
on a labelling pipeline to be the pass's ceiling; over 60 candidates it was `$3.00`.

`max_steps=1` is correct for the shape shown and wrong for the shape that costs 6.6× less, so
the example taught the expensive one.

### 1.4 Following §1.4 broke the two checks that always fire

§1.4 wrote `run_dir="runs/labels"`. `docs/procedure.md` says `runs/` is where the checks look
and a run written elsewhere is reported as a run that does not exist. Both true. Together, on
the real CLI against a synthetic project with one agent run then a labelling pass:

```
  pass  FT-13  No trajectory logging      runs/labels/run_20260809T173846Z_cb9d/trajectory.jsonl
  pass  FT-14  Model version unpinned     runs/labels/run_20260809T173846Z_cb9d/manifest.json
```

**A project that followed §1.4 had its labelling run certified as its agent run**, with FT-14
reporting the labeller's model as the pin. This was new at this sitting and is a defect
independent of everything else in it.

### 1.5 The store, measured

`runs/dogfood-2/evals/results/` **exists**, created 2026-08-07T19:22Z at scaffolding, 19 minutes into
the run, and empty ever since. `simple-agents check` on the project today: **0 failed, 3 passed,
6 not applicable**. Its one measured number is in `evals/labels.json` and in stdout.

That is stronger than the naming accident `runs/dogfood-2/findings.md` §10.2 recorded. The project
built the reserved path and put its measurement somewhere else seven hours later. Both that
section and §11.2 are corrected.

### 1.6 Two of the hand-rolled pieces had already closed

`wilson_ci` shipped at the DF2-D2 sitting, is documented at `docs/evaluation.md` §4, names hand
labelling in its docstring, and carries `wilson_ci(4, 4) → 0.51 to 1.0` as its worked example,
which is dogfood #2's own figure. Against `label.py`'s hand-rolled version: `0.5101092` against
`0.5100999`, the difference being `z = 1.959964` against `1.96`.

A second piece nobody had counted: run 2's `quote_is_real` is `contains_normalised`, shipped at
absorption item 9.

**The n=4 headline checks out.** `results/shortlist.json` holds `count: 19`, `label.py --limit`
defaults to 5, `todo` is the unlabelled shortlist truncated to it. Five offered, four answered.

### 1.7 The census is bigger than three files, and they are not one shape

The 565 is right as arithmetic (182 + 219 + 164) and is the wrong denominator.

| Project | Artifact | What it is | Where labels land |
|---|---|---|---|
| dogfood-1 | `verify_unanswerable.py`, 182 | model pass, pre-run | `data/verification.jsonl`, 30 records, 8 flagged |
| dogfood-1 | `data/hand_review.json` | **human adjudication store**, hand-written, with `what / why / reviewed_by / verifier_model / method / standard / flags[]` | itself |
| dogfood-1 | `build_evalset.py`, 189 | merges both into the set | `evals/questions.jsonl` |
| run 2 | `tools/verify_unanswerable.py`, 219 | model pass, pre-run | `evals/verification.jsonl`, mode `"w"` |
| run 2 | `MANUAL` in `build_examples.py`, 145 | **human adjudication, as a Python literal** | source code |
| dogfood-2 | `label.py`, 164 | **human labelling CLI, post-run, no model call** | `evals/labels.json`, 4 records |

Two things follow that the merged finding did not carry.

**`label.py` makes no model call.** §1.4 was titled "A label a model wrote" and does not
describe it. DF2-D8 is not R2-D7 a third time; it is the other half — `who_labels`'s second
route, which no shipped document showed how to do.

**Five stores, five formats.** Their common fields are an item id, a verdict, a reason and a
timestamp. Only `hand_review.json` records which model decided. None records a run id, because
there was no run.

### 1.8 What §1.4 already collapsed, and what it did not

Dogfood-1's `ModelRequest` construction, retry loop, give-up record, progress print and JSONL
write are about 50 of its 182 lines. §1.4's `Pipeline` + `Budget` + `RunEnvelope` + the
comprehension is 10. **A dedicated one-line `label()` helper would have saved about four lines
on top of that**, which is why the one-call envelope was not built at this sitting either, this
time on a measurement rather than on a ruling.

There is also no bridge from labels to a results file: `EvalSuite` takes a `Pipeline` and
re-runs it. Dogfood #2's number could not have been made visible to a check without re-running
the agent against an example set it never had.

---

## 2. The sitting, 2026-08-09

Four decisions, all Thilina's.

**A — §1.4's example.** Rewrite to the fan-out, one budget over the pass. Options were rewrite,
show both shapes, or leave it. No labelling case was found that wants the per-candidate shape,
and a fan-out already resumes item by item through `node_state`.

**B — should a labelling run be visible to the checks *as* a labelling run, or invisible as
*not the agent's*?** This was the crux. B1 was to move §1.4's `run_dir` outside `runs/`, which
costs one line of prose and makes the pass invisible on purpose, restating DF2-D8's complaint
as policy. **B2 was chosen**: a run declares what it is for. It answers §1.2's loss directly —
two passes become two run directories, both kept, both with the model pinned, and a drop reason
can cite a run id instead of a memory.

**C — should the library own an artifact for labels no run produced?** B2 does nothing for
`label.py`, `hand_review.json` or run 2's `MANUAL`, which are human judgements with no run to
point at. C1 was nothing; C2 a reserved path and a shape; C3 C2 plus a conformance check.
**C2 was chosen, and C3 was declined on the ceiling.** The argument that decided C3: run 2's
pass 1 would have *passed* it. It wrote 39 verdicts with a model that existed and a run that
existed, and every one of the 39 was nonsense. A check of that shape catches the loss of the
record and never the badness of the labels, and `simple-agents.md` §3.2 with do-not-change #15
is what makes that distinction load-bearing rather than pedantic.

**C's sub-decision, put separately: prose or code.** C2 read two ways about 40 lines apart. The
measurement that decided it: every one of the five stores was hand-built, and the two
hand-rolled pieces that will not recur are the two the library shipped *code* for. The field
whose absence caused §1.2's loss is `decided_by`, and a dataclass makes it required where a
documented shape makes it a suggestion. **C2-code, minimal.**

**D — where the labelling question is asked.** `who_labels` moves from `measure` to `build`.
Every project that made ground truth did so before reaching `measure`: one answered two hours
late, one never reached the stage. A project with no evaluation ahead of it answers `deferred`
naming `measure`, which is what deferral is for.

**Not foreclosed.** Thilina flagged that he is considering a pre-build planning stage
(`random-thoughts-questions.md`, Thilina's Corner). D does not foreclose it: `stage=` is a
string and `up_to()` orders them, so a new stage moves `who_labels` again for one field.

---

## 3. What shipped

### 3.1 `RunEnvelope(role=...)`

Defaults to `"agent"`, takes any non-empty string, refused when empty or not a string.
`env.with_role("labelling")` copies an envelope configured once, and the other three `with_*`
helpers carry the role forward so `EvalSuite`'s `with_run_dir` does not lose it.

Free-form rather than an enum, on the instruction to design for the general case: the record
says three times that a labelling pass, an ablation and a judge are all project-side model
calls. The default is the safe direction — a typo only ever makes a run *not* the agent's, and
the check that reads it says so.

Reaches `Manifest.role`, `RunHandle.role`, `runs(role=...)` and
`conformance/artifacts._latest_run`, which now reads the newest run whose role is `agent`.
`other_roles()` counts the rest so FT-13's reason can name them.

### 3.2 `Label`, `read_labels`, `write_labels`

`evals/labels.jsonl`, one JSON object per line. `id`, `verdict` and `decided_by` required;
`reason`, `run_id`, `decided_at` and `metadata` optional and left out of the file when empty.
`verdict` is whatever the project judges with, so a boolean, a string and a structure all
survive the round trip. The last line wins on a repeated id, so re-labelling appends and the
earlier judgement stays in the file, which is the direct answer to `"w"`.

No check reads it, and `docs/evaluation.md` §1.5 says so in the same breath as naming the file.

### 3.3 The documents

`docs/evaluation.md` §1.4 rewritten to the fan-out, with the budget claim and the role stated;
§1.5 added for the store. `docs/run-envelope.md` §2.1 gains the `role` field and the paragraph
explaining it, §8 gains `RunHandle.role` and `runs(role=...)`. `docs/conformance.md` §2.2 and
`docs/failure-taxonomy.md` FT-13 both say the run read is the agent's. `docs/procedure.md`
gains `evals/labels.jsonl` in the layout and two sentences of routing, which also edits the
skill. `docs/index.md`'s two rows updated.

### 3.4 Formats

Manifest `0.15` → `0.16`, additive: the manifest gains `role`, and one written without it reads
as `agent`. No trajectory record changed, so the trajectory format stays at `0.18` and
`design/trajectory-format-changelog.md` takes no entry. `CHANGELOG.md` carries all of it.

### 3.5 One convention moved, with approval

`WORD_BUDGET` in `tests/test_procedure.py` rose from **1300 to 1350**. The file was at **1299**
before the routing sentences, so the ceiling was saturated before any change, which is the same
position as `archive/library-analysis-2026-08-08.md`, where it moved 1200 to 1300. The budget's purpose
is that the skill must not restate the documents, and that is untouched: what went in is two
paths and one keyword, pointing outward. The argument for putting it in the skill at all is
§1.1 — dogfood #2 read `procedure.md` ten times and `evaluation.md` never, so routing that
lives only in `evaluation.md` repeats the failure this sitting found. `docs/procedure.md` is at
1345.

### 3.6 Tests

`tests/test_runs.py` gains seven: the default, a declared role, a manifest written before the
field existed, the `runs(role=...)` filter, `with_role` keeping the rest, the other copies
carrying it forward, and the refusal. `tests/test_conformance.py` gains three, of which the
first is the §1.4 finding as a regression: a labelling run newer than the agent's is not the one
`_latest_run` reads. `tests/test_labels.py` is fifteen over the store.

**`tests/test_labelling_pass.py` executes §1.4.** The example that was wrong in three ways was
wrong because nothing ran it, which is `CLAUDE.md`'s standing concern reaching a shipped
document for the second time. Six tests: the pass is one run, it has one cost and one model
pin, `max_steps` counts every item, the pass is not read as a run of the agent, §1.5's block
runs over §1.4's result, and the prose still teaches the shape the file pins.

1413 pass.

---

## 4. The verification pass

Run after the build, on Thilina's instruction: check every claim, verify the implementations,
check code against the documents, check nothing broke.

**Clean:** 1414 tests, `prose_check`, 44 doc-against-code claims, and 37 of the sitting's own
measurements re-derived from the artifacts.

**Three defects of this build's own making, all fixed.** `DEFAULT_LABELS` was left dead in
`conformance/artifacts.py`, and that module is "finding the files a check reads", so a labels
constant there implies a check will read them, which is what declining C3 was for.
`runs/dogfood-2/findings.md` §9.2 and `archive/dogfood-absorption.md` item 10 still read as open. And seven
line-anchored citations into files this build touched were shifted by it.

**The behaviour change, pointed at the projects that produced the finding.** `simple-agents
check` on dogfood #2 goes from `0 failed, 3 passed` to `1 failed`: **FT-24 on `who_labels` at
stage `build`**. That is D firing on the one project it was drawn from, and on neither of the
others, both of which answered `who_labels`. FT-13 and FT-14 pass on all three, so the `agent`
default reads dogfood #1's 474 and run 2's 635 pre-role manifests correctly. A clean install of
the wheel this build produced carries §1.4, §1.5, the skill copy matching `procedure.md`, and
manifest `0.16`.

### 4.1 `scripts/check_citations.py`, and what it found

`dev-docs` cites code by file and line, and line numbers rot silently: every edit above a
cited line moves it. **Nine of 21 line anchors did not land on what they claimed**, most of
them predating this build. `prose_check.py` skips `dev-docs` on purpose and this is a
different question, so it is its own script, on Thilina's instruction.

It checks five things and only the last needs a heuristic: an unresolvable path, a path that
resolves from the repository root but not from the citing file, a label whose own line number
disagrees with its anchor, an anchor landing on a blank line, and **symbol drift** — the name
the citation is about, defined exactly once in the cited file, more than three lines away.

**The heuristic was measured before it was kept.** A first version looked for any name in
backticks near the link: 8 of 18 fired, with false positives such as `held_back_ms` cited
against backoff code that legitimately does not contain it. Narrowing to *the nearest name
before the link, with exactly one definition* keeps every true positive and drops the noise.
Run against the documents as they stood before this pass, it independently rediscovers all
seven of the fixes made by hand, and **corrects one of them**: `_latest_run` is at 138 and not
139, because removing `DEFAULT_LABELS` moved it after the hand fix was written.

**One known false positive**, left rather than tuned around: `runs/dogfood-2/findings.md`:370 cites
the refusal that requires a `DeclaredCost`, and the tool reads `DeclaredCost` as the subject.
Suppressing it would need either a marker, which is Thilina's to grant, or a wider window that
would hide a genuine four-line drift.

**Not wired into `pytest`.** `CLAUDE.md` says `dev-docs/` is not checked, and making it
checked is a change to that rule rather than a consequence of this one.

### 4.2 The path convention, and all 21 citations repaired

**Settled 2026-08-10 on Thilina's ruling: a citation's path is relative to the file it is
written in.** `CLAUDE.md` said "repository-relative", and its example is written in `CLAUDE.md`
at the repository root, where the two conventions produce the same string. Followed literally
from inside `dev-docs/`, it produced a link no renderer resolves, and **18 of 21 citations
were written that way**. The rule now names the file-relative form and shows it from all three
depths, with the correction dated.

`--fix` rewrote the 18 paths. Verified independently of the tool: every rewrite changed the
path only, no anchor moved, each new path names the same file the old one meant, and all 21
resolve from their citing document.

**Then the anchors themselves, eight of which the tool cannot judge** because nothing in the
sentence names the cited line. Fixed by hand against the source: `nodes.py:618 → 663` (the line
building a fan-out item's input), `1411 → 1433` (`elapsed_ms`), `1423 → 1501` (`run.charge`),
`pacing.py:33 → 34` (`DEFAULT_MAX_WAIT_S`), `69 → 72`, `cassette.py:238 → 288`,
`runner.py:378 → 374`, `779 → 800`. **Two of those cite behaviour that has since been fixed** —
the `RolloutOutcome` built with no `nodes=`, and `min_remaining_requests` defaulting to `1` —
so they anchor to the enclosing definition rather than to current code, and the prose stays as
the run's record.

**All 21 now land on what they claim.** The one remaining report is the known false positive.

---

## 5. Open, and what would reopen it

- **A conformance check over labels (C3).** Declined on the ceiling, not on cost. What would
  reopen it is a failure message that a builder cannot read as "my labels were checked". Draft
  the message first.
- **The one-call envelope.** Declined a second time, now on the measurement in §1.8 rather than
  on the ruling in §9.3. What would reopen it is a project where §1.4's shape is written out by
  hand anyway with §1.4 in front of it, which is the test §9.3 set and which has still not run.
- **`plan.md` §2.1 was reached and not decided.** A labelling store
  produces exactly the figures that entry says have no seam. The rate is covered by `wilson_ci`;
  what has no home is the coverage count, which for dogfood #2 is 19 in the store, 4 labelled,
  15 not. No resampling unit, no pairing, no interval that answers a question anyone asked.
