# Build log — an answer key that says what it is

`plan.md` §1 P3-10. Started 2026-08-17. Written while building, not afterwards.

`P3-10` is `P3-5`'s stages 1 and 2 as one block, which the sitting of 2026-08-17 made one item.
That sitting's four decisions are in [`design/answer-shapes.md`](../design/answer-shapes.md#L830),
and this log does not restate them.

## 1. Before any design

Read in `src/` before anything was decided, and each of these is what a claim below rests on.

| Checked | What it was |
|---|---|
| [`Example.expected`](../../src/simple_agents/evaluation/examples.py#L128) | `Any`, untyped, round-tripping through `encode_answer`/`decode_answer`, so it is inside `content_hash` |
| [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) | Five outcomes, and `matches` is reached in exactly one branch of five |
| [`Outcome.asserted`](../../src/simple_agents/evaluation/outcomes.py#L117) | Two members; `succeeded` two; `measured` all but `no_response` |
| [`_SPECS`](../../src/simple_agents/evaluation/metrics.py#L102) | Six rates. **Every measured outcome was in at least one numerator**, checked one by one. That is the fact that forced a seventh rate |
| [`ProjectMetric.score`](../../src/simple_agents/evaluation/metrics.py#L428) | `(predicted, expected, rollout) -> float`. Dogfood #3 uses the third argument to open a trajectory (`/home/thilina/Projects/dogfood-3/evaluate.py:161`), so scoring over the run is live rather than hypothetical |
| [`config["matches"]`](../../src/simple_agents/evaluation/runner.py#L1887) | `source_version(self.matches)`, in the run config and the rescore config both |
| [`_rules`](../../src/simple_agents/evaluation/compare.py#L696) | Reads `config["matches"]` and marks **all six** rates as moved when it moves |
| `METRIC_DEFINITIONS` consumers | `compare.py` iterates it in four places, so a new rate is picked up without touching `compare.py` |
| `simple-agents.md` §9 | Nothing on it protects the rates, `matches` or `Example`. Confirms the sitting's own check |
| Break size, measured | 72 `matches=` sites across `tests/` and `docs/`, 16 `ProjectMetric(` |

**Two words were counted rather than argued about**, because the record used both for one thing.
`criteri*` appears **0 times** in `src/` and `docs/`. `requirement` appears **10 times** and every
one means a rule the library enforces on the builder, such as
[`docs/pipeline.md`](../../docs/pipeline.md#L866) "`allow_unknown=False` waives the requirement".

**And `partial` was counted**, because `partial_rate` was the first name proposed for the seventh
rate. It already means "a run that stopped part way" in four places, including
[`docs/evaluation.md` §6.4](../../docs/evaluation.md#L826) "A partial set is scored and says so"
and a local variable in [`results.py:314`](../../src/simple_agents/evaluation/results.py#L314) `EvalResults.report` holding
`config["incomplete"]`. Thilina read the proposed name as "runs that failed partway" before any of
this was measured, and the measurement is why the name is `partially_correct_rate`.

## 2. Design

The four decisions were settled and are not restated. What the build had to decide is below, and
the five problems the record set are answered under §2.4.

### 2.1 The mechanism, which is one sentence

**The answer key says how many comparisons there are and how their results fold; `matches` says
whether one pair matches.** That is what makes decision 1's rule, *a type says what the right
answer is, never how to compare it*, into code rather than a slogan.

- `AnyOf(values)` calls `matches` once per admissible value, right where any of them matches.
- `Contains(values)` calls it once per value the answer has to hold, giving it the whole answer
  and one value, and grades on how many were found.
- `WithinTolerance` calls nothing.
- `Criteria` calls each criterion's registered check.

**`matches` stays `bool`**, since decision 2 rejected a sliding scale. So a grade can only come
from a key with parts, and `partially_correct` is reachable from `Criteria` and from multi-value
`Contains` and from nothing else. A plain label, an `AnyOf` and a `WithinTolerance` admit one
answer or none.

**`WithinTolerance` computing its own answer is not the library shipping a matcher.** The task
decision is the tolerance and it is declared in the key, so it is in `content_hash`. S3.6 measured
the alternative: a tolerance written into `matches` lives in a closure, `source_version` does not
read a closure, and widening it from 2% to 5% moves every rate with nothing recording it.

### 2.2 Three calls the four decisions did not make, put to Thilina and decided

| | Decided |
|---|---|
| **`Criteria`/`Criterion` or `Requirements`/`Requirement`** | `Criteria`/`Criterion`, on the word counts in §1. The record says "requirements" in the decision and `Criteria` in the option it points at, which is a defect in our own record rather than two things |
| **A seventh rate** | Yes, and an eighth. Without one a `partially_correct` rollout is in no numerator anywhere and the only trace of it is that the rates stop accounting for the split. `graded_accuracy` came with it: a rate says how often, never how much, and "met 2 of 3" and "met 1 of 3" in one bucket with no number is the ExtractBench failure the survey recorded, where omission and hallucination are named as different errors, both scored `0.0`, and no breakdown is ever reported |
| **Weights, and `required`** | Both. The first recommendation was unweighted, on "no run of ours measures the fork". Thilina's objection was that the library is the instrument: ship the shape and the first project using it produces the evidence. That is right, and the argument was withdrawn |

**`required` was derived rather than preferred, and the derivation is decision 3's own.** FT-10
separates outcomes so a dangerous failure is never averaged into a harmless one. Decision 3 applies
that: rounding a partly-right answer into `correct` or `false_confidence` is that averaging. Run it
once more and a criteria list can hold one condition that is the difference between useful and
harmful and two that are cosmetic; reporting "failed the one, passed the two" as partly right is
the same error a third time. So an unmet `required` condition is `false_confidence` whatever the
grade, and the grade is recorded beside it.

**Negative weights were not taken.** The medical-checklist benchmark in the survey signs them −10
to 10, which lets a criterion penalise and lets one example's score go negative. That is a
different feature, and "this must not be true of the answer" is written as a criterion whose check
returns true when the thing is absent. §6 carries it.

### 2.3 `Scoring` cannot hold a `RolloutOutcome`, and that is why it is flat

Decision 4 says one context object carrying "the answer, the answer key, the example and the
rollout". It cannot carry a `RolloutOutcome`: `matches` is what **decides** the outcome, so the
object would carry a placeholder at the one seam it exists for. It carries the rollout's identity
instead — `rollout`, `seed`, `run_id`, `trajectory`, `node_id` — and `outcome`, which is `None`
inside `matches`, `node_matches` and a criterion's check, and set inside a `ProjectMetric`.

That is a departure from the decision's wording and not from what it settled: every seam still
takes one object and nothing is revisited when a fifth field is wanted.

### 2.4 The five problems the record set

1. **A criterion written as code cannot sit in a JSONL file.** The criterion is data (`id`, `text`,
   `weight`, `required`) and the check is code registered on the suite under the id. The key stays
   fully file-storable. `EvalSuite` refuses a criterion nothing registers and a check no example
   names, both at construction rather than on the first rollout.
2. **A criterion has to be versioned.** `config["criteria"]` carries each id's text and
   `source_version` of its check, beside `config["matches"]`. `_rules` reads it and marks every
   rate as moved when any check moves, because a check decides an outcome exactly as `matches`
   does. **This is `DF4-D11`'s shape** — a declaration surface rather than a hash — and it closes
   nothing there, which is about data the pipeline reads.
3. **What "the answer" is when the product is a conversation.** Half answered: a criterion's check
   is given the whole `Scoring`, so a requirement about the path and one about the content are
   written the same way in the same list, off `s.trajectory`. The other half, whether `_answer_of`
   should return a transcript, is untouched and is in §6.
4. **The third outcome and the six denominators.** `asserted` gains `partially_correct`.
   `accuracy` gives it nothing, `graded_accuracy` gives it its grade, `false_confidence_rate` loses
   it, `partially_correct_rate` counts it, `recall` holds it at 0, and
   **`precision_when_asserting` holds it in the denominator and not the numerator**: it asserted
   and what it asserted was not right, and leaving it out would raise the figure as the agent
   produced more partly-right answers.
5. **Whether per-field verdicts are a corollary of requirements.** Per-field **correctness** is: a
   record with a verdict per field is a criteria list over that record. Per-field **absence** is
   not, since an `Unknown` in one field is a criterion returning `False`, indistinguishable from a
   wrong value, which is exactly ExtractBench's recorded failure. **So stage 3's remaining content
   is J2 alone, not D1.**

### 2.5 A figure per criterion, which the four decisions do not contain

Raised by Thilina against the book example: an answer key that is a function of one end user is
useless to a builder shipping to many. Most of that is decision 4 — a check reads `s.example`, so
one registration covers every reader, and `weight` and `required` sit inside each example's key so
two readers can disagree about what matters. What was missing is reporting **across** them, so a
project sees which condition the agent keeps missing rather than only how much of the key it met.

`results.criteria[id]` is one `Metric` per criterion over the rollouts judged against it, with the
criterion's text as its definition, and `comparison.criteria[id]` pairs them between two
evaluations. Kept out of `results.metrics` so a criterion id can be any word the project finds
readable without colliding with a rate or a project metric.

## 3. Build

**Two new modules.** [`answer_key.py`](../../src/simple_agents/evaluation/answer_key.py) holds
`AnswerKey`, `AnyOf`, `Contains`, `WithinTolerance`, `Criterion`, `Criteria` and
`decode_answer_key`. [`scoring.py`](../../src/simple_agents/evaluation/scoring.py) holds `Scoring`,
`Verdict`, `verdict_of` and `criteria_in`.

**The keys are pydantic models, which cost `schema.py` nothing.** `encode_answer` already routes
anything with `model_dump` through it, so encoding needed no change at all; only decoding is new,
and `decode_answer_key` is read where a label is expected and nowhere else, so a tagged object
arriving from a model as an *answer* stays the data it was.

**Formats moved: results file `0.13` to `0.14`**, adding `criteria` beside `metrics` and `verdict`
on every rollout. Trajectory, manifest, suspension and variant formats are untouched.

**Surfaces touched.** `outcomes.py` (`PARTIALLY_CORRECT`, `asserted`, `classify` returning
`(Outcome, Verdict | None)`, `RolloutOutcome.verdict` and `graded_score`), `metrics.py` (eight
specs, a scorer taking the rollout rather than the outcome, `ProjectMetric.score`, `score_of`,
`criterion_scores`, `criterion_metrics`), `runner.py` (`criteria=`, `_scoring`, `_criteria_record`,
`_criteria_named_by`, the two config builders, both results paths), `examples.py` (decoding),
`results.py` (the new section, the version, the report block), `compare.py`
(`Comparison.criteria`, `moved_criteria`, `_rules` returning two mappings), and both `__init__.py`.

**What changed while building.** `_SPECS`'s scorer had to take the whole `RolloutOutcome` rather
than its `Outcome`, because `graded_accuracy` reads the verdict and no other rate does. That was
not foreseen and is a two-line change with a comment at the constant.

**The break is real and was taken as one.** `matches(predicted, expected)` and
`score(predicted, expected, rollout)` both become `lambda s: ...`. 72 matcher sites and 16 metric
sites were migrated across `tests/`, `docs/` and `scripts/`. Nothing resolves arity, which the
sitting's correction 2 said cannot work anyway, since `3B` and `3C` both produce a three-argument
function.

**Tests: 2276 to 2348**, with 70 new in
[`tests/test_answer_keys.py`](../../tests/test_answer_keys.py). Two of the first drafts were weak
and were rewritten: one duplicated the test above it, and one asserted a hand-written table instead
of reading `_SPECS`, so it would not have failed if a ninth outcome landed in no rate.

### 3.1 A defect in `check_citations.py`, found because this build moved a lot of lines

`--fix` **silently moved two correct anchors onto wrong lines.** `IDENT` matched a bare identifier
only, so a dotted label such as ``[`Example.expected`]`` matched no name at all, fell through to
the prose around it, and resolved against an unrelated symbol.

**Every dotted citation in `dev-docs/` was unchecked**, 32 of them, and one had been wrong since
before this build: ``[`runner._node_outputs`]`` in
[`pipeline-as-tool-build-log.md`](pipeline-as-tool-build-log.md#L299) pointed at a bare `]`.

A dotted label now resolves inside its class body, skipping docstrings and requiring a declaration
at the class's own indentation; a module-qualified name such as `runner._node_outputs` resolves to
the plain definition; a filename such as `runner.py` is not read as a member; and a class that
exists without the member resolves to nothing rather than to a namesake. **Labels only**, because
[`test_a_dotted_name_in_the_prose_is_not_read_as_a_subject`](../../tests/test_check_citations.py#L338)
records the decision
that a dotted name in prose is not the subject, and that is untouched. Four fixtures added, and all
32 now resolve.

## 4. Verification

**A green suite is not verification**, and this build is the reason to say so again: the suite went
green with every new path exercised only by a scripted client.

**The harness** is one pipeline over nine examples, one per answer key plus an absence plus three
built to be met only in part, at k=3, with `matches` written once for the whole set and four
registered criterion checks. It is in the session scratchpad rather than in `tests/`, because it
needs a backend.

### 4.1 Gemini, `gemini-3.1-flash-lite`, 27 rollouts

```
  accuracy                   66.7%  [33.3%, 88.9%]  n=9 over all rollouts
  graded_accuracy            80.6%  [55.6%, 97.2%]  n=9 over all rollouts
  false_confidence_rate      11.1%  [0.0%, 33.3%]  n=9 over all rollouts
  partially_correct_rate     22.2%  [0.0%, 55.6%]  n=9 over all rollouts
  ...
  criteria met
    names_a_line   100.0%  [43.9%, 100.0%]  n=3  names one of the best selling lines
    names_two      100.0%  [20.7%, 100.0%]  n=1  names at least two of them
    is_short       100.0%  [34.2%, 100.0%]  n=2  is one sentence under 30 words
    names_founder    0.0%  [0.0%, 65.8%]  n=2  names the founder

  correct 15, correct_abstention 3, false_confidence 3, partially_correct 6
```

Every designed behaviour appeared against a model that was told nothing about the evaluation:

- **A partly-right answer got the third outcome and the right grade.** `Criteria` with
  `names_a_line` and `is_short` met and `names_founder` unmet at weight 2 graded `0.50`, which is
  the weighted arithmetic and not the count.
- **A missed `required` condition was `false_confidence` with its grade recorded**:
  `unmet_required=('names_founder',)`, `grade=0.50`.
- **`Contains` graded 3 of 4** where the key asked for a depot the brief does not have.
- **`accuracy` 66.7% against `graded_accuracy` 80.6%** is the gap partial credit is worth here.
- **`names_founder` at 0.0%** is the per-criterion figure doing the job §2.5 built it for: which
  condition the agent keeps missing, rather than only how much of the key it met.
- The results file round-tripped every verdict and every criterion figure, and `compare()` paired
  all four criteria.

### 4.2 What the live run found that 2,344 tests did not

**`WithinTolerance` scored the right answer as a confident wrong one.** The model answered `'5200'`
and the key was `WithinTolerance(5200.0, relative=0.02)`, and `admits` refused it for not being an
`int` or a `float`. The answer schema types the field `Maybe[str]`, which is what a schema does
most of the time, so **the first real project to use a tolerance would have hit this on its first
rollout**. Fixed: a string that spells a number is read as that number, text that does not is still
wrong, and a bool is not a number. Three tests were added and the re-run scores it `correct`.

The unit tests missed it because every one of them passed a `float`, which is what someone writing
both sides of a test does.

**Two things about the machine**, neither a design finding. `_refuse_unauditable_cost` refused the
first harness for declaring `max_cost` with no cost basis, and `_refuse_a_used_directory` refused a
second run into the first one's directory. Both are the library working.

### 4.3 vLLM, `Qwen/Qwen3-1.7B`, 27 rollouts

A second adapter and a model two orders of magnitude smaller. It agrees with §4.1 on every path
that produced an answer:

```
  accuracy                   33.3%  [7.4%, 59.3%]
  graded_accuracy            47.2%  [21.3%, 73.1%]
  false_confidence_rate      11.1%  [0.0%, 29.6%]
  partially_correct_rate     22.2%  [0.0%, 55.6%]
  failure_rate               33.3%  [11.1%, 55.6%]

  criteria met
    names_a_line   100.0%  n=3      names_founder  0.0%  n=2
```

`Contains` graded 3 of 4, `Criteria` graded 2 of 3 at `0.50` by weight, and a missed `required`
condition came back `false_confidence` carrying `unmet_required=('names_founder',)` and its grade,
each identical to the hosted arm.

**`failure_rate` 33.3% is the harness and not the library.** Nine rollouts hit
`max_output_tokens=256` mid-JSON, so the response did not validate and the rollout is `failed`,
which is what a truncated answer is.

**Three things about getting it to run, none of them a finding about this item.** The environment
was missing `ninja` and the server would not start, which `uv pip install --python
~/.venvs/vllm/bin/python ninja` fixed. The reasoning parser is on and the model thinks at length,
so the local arm appends `/no_think`; **that makes the two arms non-comparable with each other**,
which costs nothing, since each exercises the code paths on its own and no claim here rests on
comparing them. And one call had to be bounded: a 1.7B model generates without stopping on some of
these prompts, and [`budget.py:129`](../../src/simple_agents/budget.py#L129) `Budget` already says what to do
about it, that the three consumption axes are checked between nodes and one call is bounded with
`max_output_tokens` on the node. The harness had not set it.

**One measurement was thrown away rather than reported.** An earlier attempt read 75 minutes for
20 rollouts. Two of this session's launches overlapped, both writing into one run directory, and
the trajectories hold two `node_execution` records 34 seconds apart to prove it. The model call is
0.16s. `_refuse_a_used_directory` refuses a second evaluation into a used directory and does not
refuse a concurrent writer, which is the operator's error and not a gap worth closing.

## 5. Doc consequences

- **`docs/evaluation.md` §1.6 is new**, on answer keys: the four types, what each folds, the
  criteria registry, and the encoded form. Placed at the end of §1 so nothing renumbered.
- **§2** carries the seventh outcome and what a verdict holds. **§3 is "The eight rates"**, with
  `graded_accuracy` and `partially_correct_rate` and the corrected denominators. **§3.1 is new**,
  on the figure per criterion.
- **§11.1 is rewritten** for `Scoring`, as a table of what the object carries.
- **§8's version is `0.14`**, and both sample report blocks were regenerated.
- **FT-10 in `docs/failure-taxonomy.md`** now says eight rates, and carries the paragraph on a
  decomposed key and the `required` exemption. **This is the shipped statement the sitting said
  would move, and it moved.**
- `docs/index.md`, `README.md` and `CHANGELOG.md` updated. The changelog entry names the break
  explicitly, since a project on disk has to rewrite every matcher and every metric.
- **One stale statement fixed on the way**: `results.py`'s module docstring said "Current version:
  `0.11`" against a constant of `0.13`.

## 6. Left open

- **Negative weights, and a criterion that penalises.** Positive weights ship; the signed −10 to 10
  form is not taken, and "this must not be true" is written as a criterion whose check returns true
  when the thing is absent. **Destination:** [`plan.md` §2.2](../plan.md#L101), to be added with the
  next sitting's approval, since it is a proposal rather than agreed work.
- **Whether `_answer_of` may return a transcript.** The path-against-content half is closed by a
  criterion check receiving `s.trajectory`; this half is not. **Destination:**
  [`design/answer-shapes.md`](../design/answer-shapes.md#L877), which is where the record states it.
- **Per-field absence, which is what is left of stage 3.** Per-field correctness is a criteria list
  over a record; absence is not, and an `Unknown` in a field is currently a criterion returning
  `False`. **Destination:** [`design/answer-shapes.md`](../design/answer-shapes.md#L898), stage 3,
  whose scope this narrows from D1 and J2 to J2.
- **A criteria set declared once and referenced.** 200 examples sharing five conditions write those
  five texts 200 times into the JSONL. Wasteful, not wrong, and `content_hash` covers it correctly.
  **Destination:** [`plan.md` §2.2](../plan.md#L101), with the entry above.
- **Every figure reportable grouped by a property of the example.** Raised by Thilina here; it is
  the same shape as an existing candidate and was widened into it rather than filed anew.
  **Destination:** [`runs/dogfood-4/inventory.md` DF4-I18](../runs/dogfood-4/inventory.md#L304),
  which P3-1 owns.
- **`DF4-I07`, an evaluation's identity not covering the data the pipeline reads.** Read at this
  build as the kickoff asked. The criterion registry is the same **shape** as what it wants, a
  declaration surface rather than a hash, and it closes nothing there. **Destination:**
  [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L65), unchanged, P3-1's.
- **Nothing about decisions 4, 5, 7 and 8 moved**, and stage 4 is untouched. They are
  [`design/answer-shapes.md`](../design/answer-shapes.md#L609)'s.
