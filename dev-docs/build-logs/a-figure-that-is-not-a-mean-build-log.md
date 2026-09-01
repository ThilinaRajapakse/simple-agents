# Build log — a figure that is not a mean over examples, and a win rate

`plan.md` §1 P3-48. Started 2026-08-28. Written while building, not afterwards.

## 1. Before any design

Every claim the sitting rested on was checked against the code first, and three of them were
wrong on the record.

- **The count-or-total seam's own evidence.** Four projects built a figure by hand, and reading
  all four found they wanted **one shape**: a ratio of two totals over a unit that is not the
  rollout. Dogfood #2's eight counts (candidates dropped, pages unreadable, bucket sizes),
  dogfood #3's `backlist_share`, dogfood #4's per-class recall and unverified citations per
  judgement, dogfood #5's 40 pairwise comparisons. The bare counts were bare because there was
  no denominator to declare.
- **`ProjectMetric` is used, not ignored.** Three of the four adopted it on sight and dropped to
  a print statement only where the shape refused them. `test_it_pairs_on_the_recorded_scores_rather_than_on_the_labels`
  ([`test_project_metrics.py`](../../tests/test_project_metrics.py#L504)) asserts the recorded
  scores travel in the file. **Why the wall is there:** FT-06 requires an interval,
  [`bootstrap_ci`](../../src/simple_agents/evaluation/intervals.py#L134) was the only calculation,
  and it needs one float per rollout. The mean-over-examples shape is the interval machinery
  showing through the API.
- **G1's blocker had shipped nine days earlier.** `P3-12` and `P3-13` both closed 2026-08-18.
- **H1's blocker was wrong.** [`design/answer-shapes.md`](../design/answer-shapes.md#L1012) said
  `read_labels` collapses repeats, which reads as the annotator data being lost.
  [`read_labels`](../../src/simple_agents/evaluation/labels.py#L133) returns `dict[str, Label]`
  on last-line-wins and **the file keeps every line**. Collapsing is the reader's choice.
- **Interval discipline is not a protected rule.** Nowhere in
  [`simple-agents.md` §9](../simple-agents.md#L515); one line of §10 and FT-06.
- **The doctrine was enforced in the wrong place.** Measured: `_carries_interval` passed
  `reason="n/a"`. What refused was [`Metric`](../../src/simple_agents/evaluation/metrics.py#L178),
  whose `value` was `interval.point if interval is not None else None`, so a number with no
  interval was structurally unrepresentable.
- **The rename's real size.** As a name rather than an English word, `denominator` was 22 sites
  in `src`, 36 in tests, 20 committed fixtures, 1 in `docs/`. And
  [`EvalResults.read`](../../src/simple_agents/evaluation/results.py#L604) refuses any file whose
  version is not current, so no dual-reading path existed to get wrong.
- **Two defects in the comparison record**, found while checking where a paired figure would go.
  `Comparison` carried no format version, and `to_record` computed `criteria` and `groups` and
  dropped both on write while `docs/evaluation.md` §10.4 called it "the full comparison record".

## 2. Design

The sitting was 2026-08-28. Its full record, with the arguments and the numbers, is
[`archive/a-figure-that-is-not-a-mean.md`](../archive/a-figure-that-is-not-a-mean.md#L1).

**The finding that set the item's shape: the two halves are one aggregation.** A win rate is a
ratio of two totals whose unit is a pair. Building the seam gives G1 its figure; G1 adds the unit.

**1. `compare()` shows a figure that is not a mean, and it is a ratio of two totals.** The project
declares a numerator and a denominator per rollout; the library sums each and divides, resampling
examples with both sums taken inside each resample. Rejected: doing nothing (four of five dogfoods
built one by hand), and a bare total only (every real case had a denominator).

**1b. A figure the project cannot put an interval on goes on file anyway, and FT-06 gets
stricter.** Thilina, against decision 1's original "no bare total ships": *"Maybe if a project has
a metric that cannot compute an interval, we should allow an exception so that it at least goes on
file instead of just being a print?"* Three checks favoured him, all in §1. **The refusal was
reversed.** The escape is made visible rather than hard: declared in `config.metrics` under a
source hash, printed so it cannot be quoted as a measurement, verdict withheld by a comparison.
**FT-06 tightens while admitting it**, reading a declared state rather than free text.

**2. `denominator` is renamed.** Thilina, against the first proposal of leaving it alone and
naming the numbers `total`/`out_of`: *"that's a bad name as currently used AND is the best name
for what we want to use"*. Both halves hold. `Metric.denominator` held a **sentence**.
`population` takes it, which is the word `Comparison.population_changed` and
`MetricChange.population_note` already use for the same concept.

**3. The pair is declared by the project, not derived by the library.** The first proposal had the
library forming pairs on `(example_id, rollout)` across two arms. Thilina defeated it: *"Just pair
up the winners together and the losers together."* The proposal had anchored on this record's own
phrase *"a judgement over a pair of arms"*, and dogfood #5's instrument was not that shape at all:
it drew two items from **one** ordering. **Three pairings, and the library fixes none**: two arms
on one example, two items from one ordering, a bracket. It ships the arm helper because it holds
both results files, and documents that how the pairs are formed is where the instrument's quality
comes from.

**The library names no verdict set.** Thilina's account of dogfood #5's 26 `prefer_neither`:
*"both the TV shows I was offered in each of those 26 were TV shows that I had no interest in
watching."* That is **both bad**, not **equally good**, and a three-way this/that/tie verdict
destroys the distinction. Measured on his data:

| Figure | Value | What it says |
|---|---|---|
| wins over all 40 pairs | 0.175 [0.087, 0.319] | dragged down by pairs where nothing was wanted |
| wins over the 14 with a preference | 0.500 [0.268, 0.732] | the honest win rate: indistinguishable |
| **pairs where nothing was wanted** | **0.650 [0.495, 0.779]** | **the finding, and nobody computed it** |

Since [`Label.verdict`](../../src/simple_agents/evaluation/labels.py#L68) is already `Any`, both
counting rules take `(pair, verdict)` and read `pair.this_is`/`that_is`. No `tie` concept ships.

**Arm order is randomised by default**, from a seed, and recorded.

**4. The results file records nothing for a paired figure.** It belongs to two arms and to neither.
**This corrected the `plan.md` row**: the ratio half moves the results file, the paired half moves
the variant comparison.

**5. Two elicitation scaffolds rewritten, no question added.** The gap was in two places and the
worse one was at `shape`: `ground_truth` and `answer_form` are both `required` and both assume an
acceptable answer exists. Dogfood #5 is that project and its answer is the log's *"I don't get
what you are asking"*.

**6. All four remaining answer shapes pulled in.** Thilina: *"I would prefer to do this properly
rather than leave hanging threads."* With the deciding pass run **before** building any of them,
because G1 and H1 both carried a blocker a read produced.

## 3. Build

Six steps, in order. **3,701 tests after six reverification cycles, up from 3,662.**

**Step 1.** [`ratio_ci`](../../src/simple_agents/evaluation/intervals.py#L354) and
[`paired_ratio_ci`](../../src/simple_agents/evaluation/intervals.py#L192);
[`ProjectRatio`](../../src/simple_agents/evaluation/ratios.py#L83) in a new
[`evaluation/ratios.py`](../../src/simple_agents/evaluation/ratios.py#L83); `Metric.population`,
`numerator`, `denominator`, `estimated`, `over`; `RolloutOutcome.ratios`. **Results file `0.25` to
`0.26`.** FT-06 reads a declared state.

**Step 2.** [`evaluation/pairs.py`](../../src/simple_agents/evaluation/pairs.py#L34): `Pair`,
`pairs_from_arms`, `unjudged_pairs`, `paired_figure`.

**Step 3.** `COMPARISON_FORMAT_VERSION` `0.1`; `criteria` and `groups` written;
`behaviour_fingerprint` per arm. **Variant comparison `0.2` to `0.3`.**

**Step 4, the decider pass.** Each shape written against what ships, not read off it:

| | Outcome | What it turned on |
|---|---|---|
| **B2** | expressible | A two-criterion `Criteria` grades the half-right answer 0.5 and `partially_correct_rate` reads it. A graded `AnyOf` is not expressible: `AnyOf` is a membership test, and it scored the half-right answer 1.0 |
| **G2** | expressible | **The pair seam gave it away, having not been designed for it**: the k rollouts of one example are pairs, so agreement across them is a figure over pairs with no label anywhere |
| **F2** | one thing missing | Per-criterion figures already shipped. `Scoring` carried `outcome` and not the `Verdict`, so a figure could not roll conditions up per axis |
| **H1** | one thing missing | A reader returning every label under an id |

Neither gap needed its own item, so the checkpoint's escalation condition did not fire.

**Step 5.** `Scoring.verdict` inside a project figure (F2);
[`read_every_label`](../../src/simple_agents/evaluation/labels.py#L176) (H1).

**Step 6.** `ground_truth` and `improvement` rewritten; `Metric.over` (`DF5-I30`).

**Three defects the verification pass found**, none visible to the suite:

1. **`report()` printed `undefined: a count over this run` for a figure whose value was 34.**
   Found by the live run, the first time a metric had a value and no interval.
2. **`results.grouped(...)` reported every ratio undefined**, with the self-contradictory reason
   *"No rollouts fall under all rollouts"*. `metrics_over` recomputed from `scores`.
3. **`compare()` gave a false reason** for a ratio, blaming pairing for examples that did pair.

**And three the checks found.** A guard in `ratio_ci` was unreachable (validation ran after
conversion). An import never landed because its anchor did not exist, and passed only by import
order. **The `ground_truth` scaffold never landed at all**: a batch script raised on a later
assertion before writing, and only the read-and-verify sweep caught it.

**One rule was enforced in one place and not the other.** `paired_figure` built a `RatioShape`
directly, bypassing `ProjectRatio`'s refusal of a bare total. The guard moved to
[`refuse_a_bare_total`](../../src/simple_agents/evaluation/ratios.py#L57), called from both.

**The refactor worklist net-grew 8 lines**, with `EvalSuite` and `runner.py` shrinking. Growth was
taken only after moving code to where it belonged: `ratios.py` and `pairs.py` are new modules, and
`figures_for` and `ratio_changes` moved out of `runner.py` and `compare.py`.

### Reverification, six cycles

Each cycle is: read the docs, read the code, cross-verify one against the other, probe the pieces,
run the whole suite, run it live. **Six cycles. One to three each found something the suite could
not see, four found one document stale, and five and six found nothing**, which is where they
stopped.

**Cycle 1 — the documented example did not work.** `docs/evaluation.md` §11.9 passes
`read_labels(...)` to `paired_figure`, which hands the counting rule a `Label` where the rule
compares a string, so the figure came back `0 of 0` blaming its denominator. **Every test passed
raw verdicts, so none of them exercised the path the docs teach.** `paired_figure` unwraps a
`Label` now, and `TestTheDocumentedPath` runs the section verbatim. Every other example in the
changed sections was then executed rather than read, and the rest held.

**Cycle 2 — a ratio declared per node.** `node_metrics` takes a mean, and a `ProjectRatio` there
reached `score_of`, which reported *"'ProjectRatio' object has no attribute 'score'"*: an internal
attribute name where an instruction belongs. Refused at the declaration now, naming where to put
it instead, and the gap is [`plan.md` §2.2](../plan.md#L331). The same cycle confirmed by running
them that `grouped()`, `baseline_metrics`, `against_baseline`, `report(group_by=)` and `rescore`
all carry a ratio correctly.

**Cycle 3 — the view, twice.** `_figure` read the point off the interval, so a census reached the
page as absent: the defect already fixed in `report()`, surviving in the other renderer. Filling
it in exposed the second half, which is that at the default unit the page then drew a count as a
percentage with a 0-to-100 bar. Both fixed, and checked in a real browser rather than in the JS
alone: `accuracy` draws a bar, `hit_share` draws a bar and shows "9 of 17" beside the share, and
`cities_listed` draws no bar and reads "17 cities a count over this run, not an estimate of a
rate".

**Cycle 4 — `docs/view.md` described the old field.** It said a figure keeps "its denominator",
which is the name that moved, and said the page names "figures with no denominator", which is now
two different states. Rewritten, with what the page does with a census.

**Cycle 5 — nothing.** Every example in every changed section executed rather than read, and
every behavioural claim the build log and `CHANGELOG.md` make checked against the code: the three
format versions, the six new public names, the two refusals, and the three interval methods being
distinct.

**Cycle 6 — nothing, from a different angle.** The wheel built and its twenty bundled documents
checked for the new sections, then a copy of the `conforming` fixture given a real ratio and a
real census and put through `run_checks`: the gates pass, and the same project with a bare
percentage carrying `reason="n/a"` fires FT-06.

**What the cycles say about the tests.** Two of the four defects were in a renderer and two were on
a path the docs teach and the tests did not take. A suite that only ever calls the library the way
its own fixtures call it does not check the surface a builder meets.

## 4. Verification

**Live against Gemini** (`gemini-3.1-flash-lite`), three examples at k=2, four times as the build
progressed. Mistral is out of credits and vLLM was not running; port 8000 is taken.

**The run that justifies the item.** Two figures over the same data, described identically in
English:

```
hit_share_per_example      62.5%  [37.5%, 100.0%]                 mean over examples
hit_share                  52.9%  [37.5%, 100.0%] (18 of 34)      ratio of two totals
cities_listed             34 cities  (a count over this run, not an estimate of a rate)
self_consistency           3 of 3   1.000 [0.439, 1.000]          over 3 example(s)
```

The last line is G2, computed through the pair seam on a real run. The Wilson fallback keeps
3 of 3 from reading as certainty.

**What the live run found that the suite did not:** the `report()` defect in §3, and one
constraint worth stating. A ratio counting things **inside** an answer reaches only what
`answer=` extracted; the first probe set `answer=` to one field and the count had nothing to
count. The library's error named it exactly.

**Every check clean**: 3,701 tests, `prose_check`, `shape_check`, `check_docs`, `check_citations`.

## 5. Doc consequences

- **`docs/evaluation.md`** gained §11.7 (a ratio of two totals), §11.8 (a count over this run),
  §11.9 (a figure over pairs, with the bracket guidance and the four-verdict worked example), the
  verdict inside a project figure at §11.1, `read_every_label` at §1.5, and `over` at §8. §10.4
  and §11.3 were corrected.
- **`docs/failure-taxonomy.md` FT-06** rewritten: what the library provides, the check, and the
  failure message. **The check is stricter than it was**: a reported value with a free-text reason
  no longer passes.
- **`simple-agents.md` §10** amended: *"the reported metric carries an interval"* became *"or a
  declared reason for having none"*.
- **`CHANGELOG.md`** carries every format move and what each costs a project.
- **What stopped being true.** `docs/evaluation.md` §11.3 said a ratio of two totals is
  "arithmetic on the results file". §10.4 called the sweep record "the full comparison record"
  while it dropped `criteria` and `groups`. FT-06's check description said a metric reporting no
  value states why, which did not cover a value with no interval.
- **`scripts/prose_check.py`'s own guidance was a defect**, found by Thilina mid-build. It said to
  check whether the unit wants decomposing **before** trimming, and called two shorter docstrings
  "the fix" — which is a workaround, since two docstrings under the limit carry more text than the
  one that failed. His replacement wording ships. **The rule had no fixture**, so nothing fired
  it; `TestTheProseLengthRule` in `tests/test_prose.py` now does, both sides.

## 6. Left open

- **A figure whose input is the k rollouts of one example together.** G2 is expressible through
  pairs, and a scoring rule taking the group is still not a thing.
  **Destination:** [`plan.md` §2.2](../plan.md#L331), as its own entry.
- **A graded `AnyOf`.** B2's figure and key both work through `Criteria`; what stays inexpressible
  is grading the alternatives of an `AnyOf` directly.
  **Destination:** [`plan.md` §2.2](../plan.md#L331), with the negative-weights entry, which is
  the same arithmetic from the other side.
- **A ratio reaches only what `answer=` extracted**, so a figure counting things inside an output
  needs the collection to be the answer. **Destination:** `nothing`; stated in
  `docs/evaluation.md` §11.7 and it is the documented behaviour of `answer=`.
- **`compare_variants` does not build the pairs itself.** A sweep produces both arms and a builder
  calls `pairs_from_arms` afterwards. **Destination:** `nothing`; the sitting decided the library
  fixes no pairing, and a sweep that pairs automatically would fix one.
