# Build log — the dogfood #3 fixes, and an evaluation that can be watched and re-entered

Built 2026-08-11 in one sitting, straight off the sitting that
decided them. `runs/dogfood-3/findings.md` §9.3 is the decision record and this is what came of it.

**Eight things shipped**, six from item 1 and two from item 2. **1721 tests**, up from 1707.
Results file `0.10`. **Live verification against a local Qwen3-30B-A3B-Instruct with tool
calling**; Mistral is out of credits, so the hosted arm is unverified and §5 says what that
leaves open.

---

## 1. What shipped

| Finding | What shipped |
|---|---|
| `DF3-D2` | An argument the model invents is refused as `ModelFacingError` and handed back, on both declaration paths. A declared schema offering a property the function cannot receive is refused at build time |
| `DF3-D4` | `totals.cost` gains `measured` and `unpriced_nodes`, and `report()` prints them |
| `DF3-D5` | `EvalResults.write` refuses an existing results file, and with no path names one after the `eval_id` |
| `DF3-D6` | `Report.notes` says when the run checked and the results file checked come from different evaluations |
| `DF3-D7` | `NodeMetrics.consultation_resolutions`, and the counter no longer double-counts a resumed question |
| `DF3-P1` | `docs/trajectory-format.md` §4.2 gives the `parent_id` join, with an example |
| `DF3-D3` | `EvalSuite.run(resume_from=...)` |
| absorbed | `on_rollout=` with `RolloutProgress`, and `progress_of()` over a directory |

---

## 2. Two things the build found that the sitting did not

**`per_node` was double-counting a resumed consultation.** `DF3-D7` was recorded as "counts
them and does not say how they ended", which was right. What the fix surfaced is that the
counter incremented on every `consultation` record, and `docs/trajectory-format.md` §4.3 has
said since it was written that a question answered in a later process is **two** records and
that counting means counting the ones where `answers` is null. The counter did not. Nothing in
dogfood #3 exercised it, because nothing there suspended.

**A moved pipeline cannot reach `resume_from`'s fingerprint check.** The brief had
`resume_from` refusing rollouts a different pipeline produced, reusing
`_refuse_a_moved_pipeline`. In practice `eval_id` already covers the pipeline's shape, so a
changed graph produces a different directory name and the name check fires first, with a better
message that points at `rescore`. The fingerprint check stays as a guard against a renamed
directory, and the test asserts the behaviour that actually happens rather than the one the
brief predicted.

---

## 3. `DF3-D2`, and the one decision inside it

The failure was that `Tool.call` validated against a pydantic model built with no config, so
pydantic's default applied and an unknown key was **ignored**; the arguments then went into the
function and raised `TypeError`, which `_run_tool` classifies as caller-facing.

**The obvious fix is `extra='forbid'` on that model, and it is the wrong one.** Pydantic emits
`additionalProperties: false` into the JSON schema for a model configured that way, and that
schema is what `tool.parameters` holds and what the backend is sent. Taking it would have
shipped the wire-level change the sitting explicitly did not take, as a side effect of a config
flag. **The check is in `Tool.call` instead**, and a test asserts `additionalProperties` is
absent from what a tool offers.

**The two declaration paths now behave the same**, which the sitting asked for and which is
worth more than the invented argument on its own: a schema derived from a signature was
validated and a schema passed as `parameters=` was not, and nothing said so. Dogfood #3
declared every tool explicitly and opted out of all argument checking without knowing it.

**A function taking `**kwargs` is not checked**, which keeps the guard that project built by
hand: absorb the argument, and name it back to the model as ignored.

---

## 4. What the live run showed

Against `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit`, a tool whose description promises a
`year` argument its signature does not carry, which is the shape dogfood #3's `find_book` had:

```
tool_call  {"title": "Piranesi", "year": 2020}
           → model_facing: Call to 'find_book' passed ['year'], which it does not take.
             It takes ['title'].
tool_call  {"title": "Piranesi"}
run outcome: completed
```

**The model invented the argument, was told, and corrected itself on the next step.** Before
this the same sequence ended the run. This is the measurement no fake client can produce, and
it is the reason the item was verified live rather than only in tests.

**One thing the live run showed that was not being looked for.** With a clear tool description
the model did **not** invent anything: the first attempt at this test asked for a year against
a tool whose docstring said it takes none, and the model complied with the schema. The invented
argument appeared only once the description promised something the schema did not carry, which
is FT-23's drift. So the failure mode is a description-schema mismatch rather than model
carelessness, and that is worth knowing when reading the next occurrence.

**Item 2, live:** 4 rollouts, two removed to stand in for a kill, `progress_of` reporting
`finished: 2, done: false` over the part-populated directory, then a resume that ran 2 rollouts,
kept the same `eval_id`, and produced the same accuracy as the uninterrupted run.

---

## 5. What is left open

- **The hosted arm is unverified.** Mistral is out of credits. Nothing in `DF3-D2` is
  backend-specific, since the refusal happens in `Tool.call` before anything is sent, but the
  claim that it behaves the same against a hosted API is untested.
- **The strict tool schema was not taken**, and the sitting's reason stands: nobody has measured
  `additionalProperties: false` on a *tool* schema against any backend. `R2-D1` measured it on
  an *output* schema against Mistral alone. Revisit when credits return.
- **Refusing an evaluation whose channel declines every consultation** was proposed and not
  taken, on the reasoning that a project may want the declined arm as a baseline. The number is
  visible now, and whether anyone reaches for the refusal is the thing to watch.
- **`progress_of` reports `cost: null` under no cost basis**, which is correct and means the
  live check exercised the `unpriced_nodes` path rather than the `measured` one. The measured
  path is unit-tested and has not been seen live.
