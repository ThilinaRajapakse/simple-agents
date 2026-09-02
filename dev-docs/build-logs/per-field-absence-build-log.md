# Build log — a condition the answer said nothing about

`plan.md` §1 P3-5, stage 3. Started 2026-08-17. Written while building, not afterwards.

Stage 3 of *What a correct answer can be*, decided at the sitting of 2026-08-17 alongside
decisions 7 and 8. That sitting's record is
[`design/answer-shapes.md`](../design/answer-shapes.md#L1) and this log does not restate it.

## 1. Before any design

Read in `src/` before anything was decided.

| Checked | What it was |
|---|---|
| [`Example.expects_absence`](../../src/simple_agents/evaluation/examples.py#L156) | `isinstance(expected, Unknown)`. The whole answer, and it drives `classify`'s branches and three rate denominators |
| [`_call`](../../src/simple_agents/evaluation/scoring.py#L353) | Refuses any return that is not a `bool`, from `matches` and from a criterion's check alike. **So no check on disk can return a third value**, which is what made the change additive |
| [`_criteria_verdict`](../../src/simple_agents/evaluation/scoring.py#L288) | `parts: dict[str, bool]`, weight met over weight declared, `unmet_required` |
| [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) | `unmet_required or empty` → `false_confidence`; `complete` → `correct`; else `partially_correct` |
| [`ft_04`](../../src/simple_agents/conformance/checks.py#L1333) | Counts held-out examples carrying `expects_absence` in the results file. `_absence_waived` needs `allow_unknown=False` on every model-calling node, which a `Maybe[...]` record does not have |
| [`ExampleSet.content_hash`](../../src/simple_agents/evaluation/examples.py#L518) | Over `to_json()` of every example, and `metadata` is inside `to_json`. **So per-field expected values held in `metadata` are already hashed**, which is what left P3-10's "per-field correctness is a criteria list" standing and narrowed this stage to absence alone |
| [`Metric`](../../src/simple_agents/evaluation/metrics.py#L178) | `no_response: int` sits beside the interval as a count that is not part of it, which is the shape a per-criterion absence count needed |
| Surface, measured | 38 `criteria=` sites, 16 `Criteria(` sites, 13 readers of `.parts` across `src/`, `tests/`, `docs/` |

## 2. Design

### 2.1 The three-way part verdict

A criterion's check returns `True`, `False`, or `Unknown()`. `False` keeps its meaning: the
answer asserted something here and it was wrong. `Unknown()` is new and means the answer
asserted nothing here.

An absent part is unmet. It adds nothing to `weight_met`, its weight stays in `weight_declared`,
it is not in `met` and it is in `total`, so leaving a condition alone cannot raise the grade.

`classify` gains a second input and splits one branch:

- `unmet_required or empty` → `false_confidence` where `asserted_wrong`, else `missed`
- `complete` → `correct`
- else → `partially_correct`

`asserted_wrong` is any part `False`, and for a key with no parts it is `grade < 1.0`.

**The change is additive by construction**, since `_call` refused a non-`bool` before it, so no
existing check can reach the new path. Verified rather than argued: §4.4.

### 2.2 `required` decides one axis and not the other

An unmet `required` condition still means the answer is not partly right. Which failure it was
is read off what the answer asserted, so a record that met two conditions and left the required
one empty is `missed` rather than `false_confidence`. FT-10's argument is that a dangerous
failure must not be hidden behind a harmless one; recording a safe omission as the dangerous
outcome is that same error pointing the other way.

**One consequence, and it is a judgement call rather than a derivation.** That rollout leaves
`precision_when_asserting`'s denominator and joins `abstention_rate`, because `Outcome.asserted`
is false for `missed`. It did put `vendor="Acme"` forward. The reading taken is that the project
declared the missing condition decisive, so the agent declined on the thing that mattered and
did not commit to an answer. `Outcome.asserted`'s docstring now says so. **The alternative is to
let a verdict with any met part keep the rollout inside that denominator**, which needs
`asserted` to read the verdict rather than the outcome alone.

### 2.3 Absence on both sides, which the live run forced

`Criterion(expects_absence=True)` declares that the right answer to a condition is that the
value is not there. **Silence meets it.**

The sitting agreed this flag as a declaration read by FT-04 alone, changing no scoring. §4.1 is
why that did not survive first contact: the model read a record stating no manager, reported
absence, and was scored partly right on a perfect answer. The check had reported "the answer
said nothing" and nothing asked whether saying nothing was right.

So the fold reads the flag. The four cells are `classify`'s own table one level down:

| | the condition asks for a value | the condition expects absence |
|---|---|---|
| the answer asserted something | the check decides | wrong, whatever the check returned |
| the answer asserted nothing | unmet, and safe | met |

The check then answers one question, whether a value was given and whether it was right, and
both sides of absence are read by the library as they are for a whole answer. One registered
check serves the example whose document states the field and the example whose document does
not, because the declaration is per example.

**The right-hand column is the library's and not the check's**, which §4.8 is the reason for: it
was the check's for one round, and a check returning `True` about an invented value scored that
value `correct`.

**This is a departure from what the sitting agreed** and is flagged as one. Reverting it means
reverting four lines in `_criteria_verdict` and the prose around them.

### 2.4 What was weighed and not taken

- **A `Record` answer key**, with `classify` applied per field. Cleanest on paper and it gives
  the library two ways to decompose an answer key with two reporting surfaces and two roll-up
  rules. P3-10 chose criteria.
- **`Criterion(about="po_number")`**, the library reading the field and deciding absence itself.
  It removes an `isinstance` line per check and ties a criterion to a field, which reopens D1.
- **A fourth part state**, separating met-by-value from met-by-absence. Recoverable instead from
  `absent_parts` per example in the results file beside `parts` per rollout.
- **A rate over parts rather than rollouts.** Parts within a rollout are not independent, so a
  Wilson interval over them would be wrong. The figure per criterion is over rollouts, which is
  the resampling unit the library already has.

## 3. Build

**Surfaces touched.** `scripts/build_conformance_fixtures.py` (`main` takes a destination, so
a test can regenerate into a temporary directory), `scoring.py` (`Scoring.criterion_id`,
`Verdict.parts` tri-state,
`wrong`, `absent`, `asserted_wrong`, `_criteria_verdict`, `_call`), `outcomes.py` (`classify`,
the table, `Outcome.asserted`), `answer_key.py` (`Criterion.expects_absence`,
`Criteria.absent_parts`), `examples.py` (`Example.absent_parts`), `metrics.py`
(`criterion_absences`, `Metric.absent`, two `METRIC_DEFINITIONS` entries), `results.py` (the
version, the report line), `runner.py` (`absent_parts` in both results paths, `node_matches`
through `_call`), `conformance/checks.py` (`ft_04`).

**Results file `0.15` to `0.16`.** Trajectory, manifest, suspension and variant formats are
untouched. `Criterion` gains a field, so every criterion's encoded form gains
`"expects_absence": false` and an example set carrying criteria has a new `content_hash`.
Criteria shipped the day before, so nothing on disk carries one.

**Tests: 2406 to 2528.** In [`tests/test_answer_keys.py`](../../tests/test_answer_keys.py),
plus one in `tests/test_conformance.py` for FT-04's new path and one in `tests/test_packaging.py`
for a version a module docstring states.

**What changed while building.** §2.3, found live. And `node_matches` was coerced with `bool()`
where [`EvalSuite._observed`](../../src/simple_agents/evaluation/runner.py#L1816) reads it, so a
check returning `Unknown()` recorded the node as having answered wrongly rather than naming the
mistake; it goes through `_call` now and refuses, as `matches` already did. *(This cited
`runner.py:1477` until 2026-08-18, which was a `judging_pipeline.run(...)` and had nothing to do
with the claim: the line had drifted and no symbol was named beside it.)*

## 4. Verification

Two backends, and a differential run against `HEAD` for the compatibility claim.

### 4.1 Gemini, `gemini-3.1-flash-lite`, 12 rollouts

Four depot records, three `Maybe[str]` fields, one criterion per field, k=3. The model was told
nothing about the evaluation beyond the task.

**The first arm scored a perfect answer as partly right**, which is §2.3's finding:

```
  d2 r0  partially_correct  grade=0.67  parts={'town': True, 'opened': True, 'manager': None}
```

The record states no manager, the model reported absence, and the criterion recorded silence.
After §2.3, the same 12 rollouts score `correct` end to end, `accuracy` 100.0% [51.0%, 100.0%].

### 4.2 The same answers under both declarations

The recording replayed against a key that declares no absent case, and with one condition made
stricter so a wrong value appears:

```
  d1  partially_correct  parts={'town': False, ...}  wrong=('town',)     absent=()
  d2  partially_correct  parts={..., 'manager': None}  wrong=()          absent=('manager',)
  d4  missed             parts={all None}              wrong=()          absent=(town,opened,manager)

  false_confidence_rate  0.0%   abstention_rate  25.0%   missed 3, partially_correct 9
    manager  25.0%  n=4, 9 asserted nothing  the manager, or that the record states none
```

**And the same rollouts scored the way a project wrote this before**, with the checks returning
`False` for silence instead of `Unknown()`:

| | checks returning `False` for silence | this build |
|---|---|---|
| d4, the model asserted nothing anywhere | `false_confidence` ×3 | `missed` ×3 |
| `false_confidence_rate` | **25.0%** | **0.0%** |
| `abstention_rate` | 0.0% | 25.0% |

An agent that invented nothing was reported as asserting a confident wrong value on a quarter of
its rollouts.

### 4.3 vLLM, `Qwen/Qwen3-1.7B`, 12 rollouts

Agrees with the hosted arm on every path, with one finding that is not this item's.

**The model returned the string `"unknown"` rather than the tagged `Unknown` the schema
offers**, so the answer asserted a value and the new path was never reached: d4 came back
`false_confidence` ×3 with `wrong=('town', 'opened', 'manager')`. That is FT-09's stated failure
("Do not model it as an empty string or a null: neither is read as absence") arriving in a live
run, and the library behaved as designed. With the sentinel normalised in the check, as a
project meeting it would, the arm reproduces §4.1 and §4.2 exactly: 12 `correct` declared, and
`missed 3, partially_correct 9` with `false_confidence_rate` 0.0% undeclared.

### 4.4 The compatibility claim, measured

A 35-case matrix run against `git archive` of `HEAD` and against this tree: every outcome,
grade, `met`/`total`, `parts`, `unmet_required`, `complete`/`empty` and every raised
`ConfigurationError` is identical. It covers `Contains` at 0/3, 1/3, 2/3, 3/3, a plain-label
miss, an `AnyOf` miss, `WithinTolerance` misses, `Criteria` all-`False`, required-unmet, weights
`0.1×3`, `1/3×3`, `0.7/0.2/0.1` and `1e-18`, both absence branches, `failed`, and the four
non-bool refusals. Grade is exactly `1.0` on every all-met weighting, so `complete`'s `>= 1.0`
never misfires.

### 4.5 Nine defects the verification pass found after the suite was green

1. The outcome table read `asserted nothing anywhere → missed` unqualified, and a key whose
   every condition declares `expects_absence` scores `correct`. Qualified in both places.
2. `Metric.absent` was documented as "asserted nothing about the condition" in four places, and
   it holds unmet silences: a silence that met an `expects_absence` condition is not counted.
   Reworded.
3. `node_matches` coerced with `bool()`. §3.
4. `precision_when_asserting` and `Outcome.asserted`. §2.2, taken as a judgement rather than a
   defect, with the docstring corrected.
5. 66 citations in `dev-docs` shifted by this build's line moves. `--fix` rewrote 54; one
   needed a hand, and it was stale before this build.
6. §1.6's encoded-form block did not carry the new field, and `answer_key.py` names that block
   the schema of record.
7. Fourteen fixture results files carried metric definitions the library no longer writes,
   because `METRIC_DEFINITIONS` was edited after they were regenerated. **`TestTheFixturesAreCurrent`
   compares version claims and not content**, so nothing caught it.
8. A test class docstring contradicted the test twelve lines below it.
9. `CHANGELOG.md` said a results file written before this reads back unchanged, and
   `EvalResults.read` refuses any version but the current one.

### 4.6 A second pass, and nine more

Run because the cycle rule says a fix needs its own verification. **One was a false claim about
behaviour and the rest were prose that had drifted past what the code does.**

1. **The `missed` rule was overstated in six places.** §2.1 above states it correctly and the
   prose written from it did not. The rule is *met none of it, asserting nothing wrong*, and
   the qualification matters: a key with one
   condition declaring `expects_absence` and one asking for a value, both silent, meets the
   first and is `partially_correct` at 0.5. Corrected in `outcomes.py`'s table and paragraph,
   `docs/evaluation.md` §1.6 and §2, FT-10, and `CHANGELOG.md`. `abstention_rate`'s definition
   had been widened to describe that rollout and does not count it, so it is back to its
   original wording. **Pinned by a test.**
2. **§3.1 said a rollout that abstained is outside every per-criterion figure**, which stopped
   being true: one that reported absence condition by condition was judged and is inside.
   **Pinned by a test.**
3. **`results.py`'s module docstring said `0.14`**, two bumps behind, and it had rotted the same
   way once before. **`test_every_module_that_names_its_format_version_names_the_current_one`
   is the rule put where it breaks**, and it was made to fail before it was kept.
4. **`docs/conformance.md` §2.5 and its table row** still said FT-04 needs a whole answer that
   is absent.
5. **`absent_proportion` does not see a per-field absent case**, which is right, and two places
   said it reports what FT-04 reads.
6. **`docs/evaluation.md` §5.2 primes a builder to return `Unknown` from a node matcher**, which
   is now refused, and said nothing about it.
7. **`Metric.no_response` promised `report()` prints it on every line** and the per-criterion
   lines never did.
8. The absence count sat mid-line and made the definition column ragged. It reads
   `n=1, 3 asserted nothing  <the condition>` now, with `no_response` after it as the eight
   rates have it.
9. **`graded_score`'s docstring** did not cover a rollout sorted `missed` with a nonzero grade.

### 4.7 The third pass, run after the session resumed

A first attempt was launched and killed when the session was parked; it had executed nothing and
returned nothing usable, so it was re-run split in two, on the argument that its brief had been
too wide to finish.

**The three interactions it named as uncovered are covered now, and none of them was broken.**
`compare()` between two evaluations where one carries absences pairs both criteria and withholds
the verdict on every rate when a check that reports silence moves; `rescore` from disk
reproduces every absent part, every outcome and the absence count; and a variant sweep over a
key declaring `expects_absence` carries the met-by-silence verdict into the baseline arm. Four
tests, and the sweep's first draft was refused by
[`variants.py`](../../src/simple_agents/evaluation/variants.py#L624) for passing a variant
identical to the baseline, which is the library working.

**The corrected `missed` rule is pinned across all six constructed cases**, including the one
§4.6 found: a key declaring `expects_absence` throughout is `correct` when the answer says
nothing, and one that declares it on some conditions and not others is `partially_correct`.

### 4.8 A fourth pass, and the hole it found

The documents-and-records half of §4.7, run separately. **One defect was behavioural and the
rest were statements that had drifted past the code.**

1. **An invented value could be scored `correct`.** §2.3 shipped one of the two absence cells:
   silence met a condition declaring `expects_absence`, and an asserted value there was left to
   the project's check. Measured, with a key whose right answer is that no PO number is stated
   and an answer of `PO-4471`:

   ```
   check returns True  -> (Outcome.CORRECT, grade 1.0, parts={'po_number': True})
   check returns False -> (Outcome.FALSE_CONFIDENCE, ...)
   ```

   **The library decides both cells now**: where the condition expects absence, reporting it is
   the only way to meet it and an asserted value is wrong whatever the check returned. That is
   what `classify` does for a whole answer, which never calls `matches` when the label is
   absent. **The four-cell table in §2.3 described this and the code did not do it.**

2. **The documented check ended the evaluation on the example it was written for.**
   `docs/evaluation.md` §1.6 printed `s.example.metadata["po"]`, and the declaring example has
   no value under that key, so it raised `KeyError` and `_call` turned it into a
   `ConfigurationError`. It reads `.get("po")` now, and the paragraph says why: on that example
   there is nothing to compare against and the library decides the condition.

3. **"A record whose fields are all empty lands where reporting absence lands" is false**, in
   five places including `classify`'s own docstring. Measured: with one condition declaring
   `expects_absence`, an answer with every field empty meets that condition and is
   `partially_correct` at 0.333. This is §4.6 item 1 surviving in the sentences written from it.

4. **Five links broke when this record moved to `design/`**, because they named a sibling in
   `items/`. `check_citations.py` reads a citation's anchor and not whether a dev-docs link
   resolves at all, and `check_docs.py` does not either, so both reported clean. §6 carries it.

5. **Nine section anchors pointed into the wrong section**, seven of them because §2.1 of
   `plan.md` gained an entry in this same change and moved §2.2 down. Repaired here and in three
   other build logs, and re-verified by resolving every `§n` label against the target's headings.

6. `checks.py`'s own table row, FT-04's failure message, `false_confidence_rate`'s definition
   string, `config.criteria` missing from §8's table, and what `s.expected` holds inside a
   criterion's check.

**Two of the report's items were already fixed** when it was written, since it read the tree
before the fixes landed: §4.7 naming three interactions as untested, and the build log's test
count.

### 4.9 The final pass, and what it is worth

Four passes each found something, so this one was built to be conclusive rather than another
reading.

**Every reachable case, against the rules as documented.** Two conditions, over every check
return, every declaration of `expects_absence`, and `required` on or off, is 72 cases; the
other keys and the whole-answer branches are 13 more. The expected column was implemented **from
the documents' own wording** rather than by calling the library, so the two implementations are
independent and agreeing means the prose and the behaviour are the same thing. **89 cases, no
mismatch.**

**The 72-case matrix now lives in the suite**, as
`TestEveryCaseAgreesWithTheDocumentedRules`, with the rules quoted in its docstring. That is the
structural answer to why this took four passes: the prose and the code were each written from
the design and never from each other, so nothing failed when one moved.

**Backward compatibility, re-measured over the diff as it now stands.** 67 cases a project could
already have written, scored by this tree and by `git archive HEAD`, including every key type at
every arity, the absence branches, weights that do not divide evenly, and the four refusals with
their messages. **Byte-identical.**

**Both backends, fresh rather than replayed.** `gemini-3.1-flash-lite` and `Qwen/Qwen3-1.7B`,
12 rollouts each, and they agree on every figure: 12 `correct` against a key that declares its
absent cases, and `missed 3, partially_correct 9` with `false_confidence_rate` 0.0% against one
that does not.

**What this does not cover**, stated so it is not mistaken for more than it is: three or more
conditions are covered by the earlier tests and not by the matrix; the matrix fixes the weights
at 2 and 1; and no case here runs against a project that was not written for this feature.

## 5. Doc consequences

- **`docs/evaluation.md` §1.6 gains "A condition the answer said nothing about"**: the three
  return values, the both-sides rule, and the declaration. §2's outcome table gains a row and
  the paragraph under it. §3's `false_confidence_rate` definition moved and `abstention_rate`'s did not.
  §3.1 gains `absent`. §8 is `0.16` and names `absent_parts`, `criteria` and `verdict`. §11.1's
  table gains `s.criterion_id`.
- **`docs/failure-taxonomy.md` FT-04** now names a declared condition as satisfying the gate,
  and its failure message says how. **FT-10's paragraph on the separation inside an answer said
  "the same separation applies" and covered only the partial half**; it now carries both.
- **`answer_form`'s scaffold routes a builder to the declaration.** Not a new question and no
  gate moves, so no project fails FT-24 over it. Without it this build repeats the finding
  `P3-11` was made of: a mechanism ships and no question a builder is asked reaches it.
- `CHANGELOG.md` names the break in `content_hash` and the `node_matches` refusal.

## 6. Left open

- **Neither check reads whether a dev-docs link resolves.** `check_citations.py` checks a
  citation's anchor and its symbol; nothing checks that a relative path names a file that
  exists, which is how five links broke silently when a record moved between directories
  (§4.8). A repository-wide sweep reports thousands of unresolved paths, most of them older
  than this item and pointing at dogfood projects outside the tree, so widening the check is a
  decision rather than a fix. **Destination:** [`plan.md` §2.2](../plan.md#L101), **deferred
  2026-08-17** on the decision that the backlog is not worth taking on now.
- **`Outcome.asserted` reading the verdict**, so a rollout that put some conditions forward and
  left a `required` one empty stays inside `precision_when_asserting`. §2.2 took the other
  reading. **Destination:** [`plan.md` §2.2](../plan.md#L101), **deferred 2026-08-17**.
- **A `Criteria` object shared across examples declares absence for all of them**, so silence
  scores as met where the value existed. `docs/evaluation.md` §1.6 says to declare per example
  and `content_hash` covers the declaration, and nothing in the library can detect a shared key.
  **Destination:** [`plan.md` §2.2](../plan.md#L101), **deferred 2026-08-17**.
- ~~**The fixture check compares version claims and not content**, which is why §4.5's seventh
  defect survived a green suite.~~ **Built 2026-08-17**, on the decision that it was cheap
  enough to take here: `test_every_fixture_holds_what_the_library_writes_today` regenerates
  every fixture into a temporary directory and compares each file, less the timestamps,
  durations and record ids two runs of the generator legitimately disagree about. It was made
  to fail on the exact rot it exists for, a stale metric definition in one results file, before
  it was kept. **Destination:** nothing.
- **Decision 5, and stage 4.** Not touched. **Destination:**
  [`plan.md` §1](../plan.md#L17) P3-12.
