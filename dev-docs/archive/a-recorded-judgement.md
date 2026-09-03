# A judgement the scoring code did not compute

**Closed 2026-08-18 and moved here from `items/`.** Both stages shipped, and the two build logs
say everything this file says:
[`build-logs/recorded-judgement-build-log.md`](../build-logs/recorded-judgement-build-log.md#L1)
for decisions 1 to 7 and
[`build-logs/consultation-reading-build-log.md`](../build-logs/consultation-reading-build-log.md#L1)
for decision 8, whose stated mechanism the build could not use and replaced. The text below is
what the record held while the item was open, unchanged.

`plan.md` §1 P3-12's record. **Stage 1 built 2026-08-18; this is stage 2's record.**
[`build-logs/recorded-judgement-build-log.md`](../build-logs/recorded-judgement-build-log.md#L1)
is stage 1. This file stays in `items/` because the item is half open, and it holds what
stage 2 still owes rather than a second copy of what shipped.

Stage 4 of `P3-5` and the judge half of what was `plan.md` §2.1's consultation entry, made one
item on 2026-08-17 at P3-5's second sitting. The survey behind it is
[`design/answer-shapes.md`](../design/answer-shapes.md#L1), and its decision 5 is this item's
first question.

**It builds in two stages**, agreed 2026-08-18: the scoring-time judgement, built, and the
run-time consultation reading, not built.

## Where it came from

Three surfaces arrived at one missing piece from three directions.

- **`P3-9`, 2026-08-17, measured.** Whole-answer equality read an option out of **0 of 24**
  stand-in answers and word-boundary containment out of 7. Three classes defeat any rule over
  the text alone: negation (*"anything but The Witch of Whispervale"*), the option word used as
  a determiner (*"I have no strong feeling either way, go ahead"*), and a condition (*"only if
  it is under 400 pages; otherwise, no"*). A model reads all three.
  [`build-logs/end-user-in-an-evaluation-build-log.md`](../build-logs/end-user-in-an-evaluation-build-log.md#L1) §2.3.
- **`P3-5` decision 5**, the survey's stage 4. F1, F2 and G1 need a scoring rule that costs a
  model call, and nothing supports one.
  [`design/answer-shapes.md`](../design/answer-shapes.md#L279) S2.2 seam 7.
- **`P3-5` decision 7**, settled 2026-08-17. A criterion code cannot decide is judged by a
  person, and `Label` is the seam for that judgement.

## What the problem is

**`RunEnvelope(role="labelling")` exists so a model that decides ground truth is pinned the way
the agent's is, and nothing routes a *scoring* call through it.** So a judge today is unpriced,
unrecorded and outside `source_version`, and the two other consumers have the same hole in
different places.

**The consultation half is a shipped surface that does not work.**
[`ConsultTool.read_answer`](../../src/simple_agents/tools.py#L1304) runs again on replay and on
resume and must not do work beyond matching, so a model-backed `match=` would make a live,
unrecorded, non-deterministic call on every replay.

**The recorded-judgement half works today and should not be used as it stands.** Measured
2026-08-17 by running it: a criterion check reading `read_labels(path)[key].verdict` scores
identically on a live run and on `EvalSuite.rescore`, and `report()` prints the judged condition
beside the coded one with nothing distinguishing them. Four edges came out of running it, and
two are silent.

1. **The judgements move and no recorded version moves.** *Closed by stage 1*, which
   records a digest of the judgements per condition and over the evaluation, and corrected
   `_stable_text` ahead of the build.
   [`_criteria_record`](../../src/simple_agents/evaluation/runner.py#L1476) writes
   `source_version(check)`, which is the lookup function's source, and
   [`_rules`](../../src/simple_agents/evaluation/compare.py#L696) reads exactly that. Measured:
   editing a verdict in the file from `true` to `false` leaves the hash **identical**; a path
   closed over as a `Path` rather than a `str` hashes identically for two different files,
   because [`_stable_text`](../../src/simple_agents/records/manifest.py#L557) renders anything outside
   the JSON scalars as its type name. So re-judging every label moves every number and
   `compare()` attributes all of it to the agent. `docs/evaluation.md` §11.6's shipped
   mitigation, *"put the value in the function"*, cannot be applied to 200 judgements.

   *Re-measured 2026-08-18 at the sitting, and the `Path` half is a defect in its own right.*
   Two functions closing over different files record the same version when the path is a `Path`
   and different versions when it is a `str`. That contradicts
   [`source_version`](../../src/simple_agents/records/manifest.py#L605)'s own docstring, *"Only captured
   data whose text is fixed by its value counts"*, since a `Path`'s text is fixed by its value.
   It is wrong for every function closing over a path and not only for a judgement lookup, so
   it is corrected ahead of the design rather than inside it.
2. **The key names the slot, not the answer.** *Closed by stage 1's decision 3.* It has to be flattened by hand into
   `f"{example_id}::r{rollout}::{criterion_id}"`. A later run's rollout is a **different
   answer**, and the same human verdict is re-applied to it with nothing detecting the mismatch.
3. **`criterion_id` was unreachable from a check.** *Closed.* Fixed at `P3-5` stage 3;
   [`Scoring.criterion_id`](../../src/simple_agents/evaluation/scoring.py#L83) carries it now.
4. **Chicken and egg.** *Closed by stage 1's decision 5.* `EvalSuite` refused construction
   when a criterion had no check, so the
   seeding run needs a placeholder whose wrong numbers are written to a results file. A missing
   judgement later raises `KeyError`, which `_call` turns into a `ConfigurationError` that ends
   the evaluation with a message that never mentions labels.

   *Corrected 2026-08-18, by running it.* This record said the evaluation ends "after every
   rollout has been run and paid for". It does not. Six examples at `k=2` with nothing judged
   ended after **7 of 12 rollouts**, because scoring runs as each rollout finishes and
   `DEFAULT_CONCURRENCY` is 4, so the failure cancels what has not started. **Every completed
   rollout's directory is on disk**, so `rescore` can pick them up and nothing paid for is lost.
   What is wrong is the message: it names a `KeyError`, and its instruction, *"it has to return
   a verdict for all of them"*, cannot be followed, because the answer did not exist when the
   judgements were written.

Nothing about the judgements reaches the results file: `labels.jsonl`, `decided_by` and `human`
are all absent from it.

## What has to be decided

**All eight are settled, 2026-08-18.** The eighth was not in this list until the sitting: the
seven below are all about a judgement the *measurement* consumes, and the consultation reading is
a judgement the *agent* consumes, which needed its own question.

1. **Whether a scoring rule may cost a model call at all**, which is `P3-5`'s decision 5. It
   runs into `simple-agents.md` §10's requirement that the whole suite run in CI with no network
   and no spend, and into `source_version`, cassette replay and `max_spend`.
2. **Where a judgement is recorded**, and whether `Label` is the record for a model's judgement
   as well as a person's.
3. **What a judgement is keyed on.** The slot, or the answer that was judged.
4. **What the results file records about it**, so `compare()` declines to attribute a change in
   the judgements to the agent.
5. **What happens on a missing judgement**, and whether the refusal comes at construction rather
   than after every rollout has been paid for.
6. **Whether a judged criterion is visibly different in a report** from one code decided.
7. **Whether `read_labels` keeps every judgement for one id** rather than the last. LeWiDi is
   the case for it: on items where annotators agreed only 40 to 60%, a hard label is wrong 46%
   of the time. This is H1's starting point and H1 is deferred.
8. **Where the consultation reading is made and recorded**, given that it routes the run and so
   cannot wait for scoring.

## What was decided, 2026-08-18

**Decisions 1 to 7 are built and their design is in
[`build-logs/recorded-judgement-build-log.md`](../build-logs/recorded-judgement-build-log.md#L47)
§2**, which is where a built item's design belongs. They are not repeated here. What that build
found the design did not know is its §3, and four of those changed the design: the text
comparison decision 4 specified turned out to be unreachable, two defects came out of the live
run, and `Judgements` needed a lock.

**Decision 8 is stage 2 and is not built**, so it stays here.

### 8. The consultation reading is made live, through a model handle, and stored

The reading routes the run, so it cannot wait for scoring, and no rule over the text reaches it:
0 of 24 measured at `P3-9`.

**The reading is a model call made through
[`ModelHandle`](../../src/simple_agents/tools.py#L162) inside the consult call, and its verdict is
stored on the consultation record.** Both halves do a job. The handle makes the call a
`model_call` record parented to the tool call, charged to the run's budget, and re-executed on
replay with the model call served from the cassette, so editing the reader's prompt is a
**cassette miss** reported with the fields that differ rather than the old reading silently
standing. The stored verdict is what `read_answer`, a resumed run and any reader of the
trajectory take, so nothing downstream re-derives anything. `match=` keeps its documented
contract for deterministic rules.

**The cost is the agent's, which is the opposite of the stand-in's.** A model playing an end user
is measurement machinery and
[`_answering_model`](../../src/simple_agents/runtime/consultation.py#L188) keeps its cost off the node's
figures for that reason. A reader ships with the agent: in production a real customer types prose
and something has to read it, so that call is part of what the agent costs to run.

**Rejected: storing the verdict alone**, with the project's reader calling a model however it
likes. That reproduces this item's own complaint one level down, since the reader's call would be
unpriced, unrecorded and outside the budget. **Rejected: leaving the consultation half in
`plan.md` §2.1**, since it is the half with the measurement behind it and the ordering of the
whole item rests on it.

**What the build has to settle.** [`_delivered_answer`](../../src/simple_agents/runtime/consultation.py#L29)
applies `read_answer` directly rather than through `run.call_tool`, so a handle is not reachable
on the resume path as the code stands.

## The two stages

Agreed 2026-08-18. No file is common to both, and stage 1 landed first so stage 2 inherits
decision 1's rule rather than being designed beside it.

| Stage | What lands | Where it touches | State |
|---|---|---|---|
| **1. The recorded judgement** | Decisions 1 to 7 | `runner.py`, `compare.py`, `labels.py`, `scoring.py`, `manifest.py`, the results file, `simple-agents.md` §10 | **Built 2026-08-18**, results file `0.17`, 2562 tests |
| **2. The consultation reading** | Decision 8 | `nodes.py`, `tools.py`, `builtins/consult.py`, the trajectory format | Not built |

## What it waits on

**Nothing.** It is `plan.md` §1's top row, and stage 1 is built, so what is left is stage 2.

**What waits on it**: F1 where code cannot decide a condition, J3's outcome half, and G1, which
also needs a figure that is not a function of one rollout
([`design/answer-shapes.md`](../design/answer-shapes.md#L965), "Where every kind stands"); and
`plan.md` §2.1's module split, which names this item because a scoring call routed through the
envelope moves `pipeline.py`. Decision 1 keeps that true, since the judging pass is a run under an
envelope.

**What it hands to other records.** A judge is a second model client and
[`_pace_for`](../../src/simple_agents/evaluation/runner.py#L2862) is applied to
`_clients_of(self.pipeline, model)`, which a judging client is in neither, so `plan.md` §2.2's
*A ceiling on how much reaches one model client* gains an instance. And the shipped example set
covers a judge and a panel, recorded at
[`items/example-projects.md` §19.9](../items/example-projects.md#L1).
