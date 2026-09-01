# A figure that is not a mean over examples, and a win rate

`plan.md` §1 P3-48's record. **The sitting was taken 2026-08-28 and all six decisions are
settled**; nothing is built yet. What the sitting decided is below, and what it found while
deciding changed the item's shape and its size.

## Where it came from

Dogfood #5's sitting 4, 2026-08-27, closing [`DF5-I31`](../runs/dogfood-5/inventory.md#L116),
taking `plan.md` §2.1's count-or-total seam and lifting G1 out of §2.2's six answer shapes.
Thilina's call: *"Count seam and G1 as one item to be handled along with the rest of this sitting's
items."* His framing at the sitting: *"Being able to reliably score only binary classifications is
kinda pathetic for a library dealing with agents."*

*(That framing is wider than the library's actual state, and the correction is recorded at
`DF5-X13`: fourteen of the survey's twenty-four kinds ship or are expressible, including graded
criteria, partial credit, per-field absence and conditions a model or a person decides. G1 is one
of six that do not.)*

## What the problem is

**The blocker on record shipped ten days ago.**
[`design/answer-shapes.md`](../design/answer-shapes.md#L1002) says G1 "needs `P3-12` as well".
`P3-12` and `P3-13` both closed on 2026-08-18. What shipped is the judge seam: `Judged()` as a
condition on an answer key, `Scoring.judgement(question, over=...)` at every scoring seam, a
judging pass handed the whole worklist through `suite.judge`, `run(judge=)` and
`compare_variants(judge=)`, judgements keyed so k rollouts of one answer are judged once,
`evals/judgements.jsonl` as the store, and a gate refusing to compute numbers while an answer is
unjudged. A model-judged condition works today.

**What G1 still needs, having removed that.**

1. **A judgement over a pair.** [`compare_variants`](../../src/simple_agents/evaluation/variants.py#L313)
   runs each arm and judges each arm's own worklist. Nothing hands one arm's scoring rule the other
   arm's answer. `Scoring.judgement(over=)` takes arbitrary material, so the judge side is already
   general and the plumbing that pairs two arms is not there. *(**A pair of arms is one pairing of
   three and the narrowest**, corrected at the sitting on 2026-08-28: this project's own instrument
   paired two items from one ordering, and a bracket pairs winners with winners. Decision 3.)*
2. **A figure that is a count over pairs.** A win rate has no per-rollout float to average.

**And (2) is the count-or-total seam**, `plan.md` §2.1, accepted 2026-08-15 and open since
2026-08-07. Three of three dogfoods that reached an evaluation reached for one, and dogfood #2
built eight by hand in a `Deterministic` node. *(**Four projects, and every one of them wanted the
same shape**, read off at the sitting on 2026-08-28: the table under "What the sitting found".)* It waits on one decision: whether `compare()` shows
a figure that is not a mean over examples. A win rate is that seam's hardest case, so settling the
seam without it means settling it twice.

**The project needed G1 and built the whole instrument outside the library.** Measured on the
frozen copy: a pairwise labelling surface on its own website, drawing two bands of the same live
ordering, **40 comparisons**, rank 1+ against rank 2001+, `prefer_this` 7, `prefer_that` 7,
`prefer_neither` 26. It never entered `EvalSuite`. `compare()` pairs on example id and computes
per-rollout floats independently on each side, which
[`answer-shapes.md` S3](../design/answer-shapes.md#L331) already records. It was also one of the
seven interventions the builder was forced into
([`findings.md` §3.8](../runs/dogfood-5/findings.md#L985), `BUILD-LOG.md:6360-6363`), and the
instrument returned no signal at 7 to 7 with 26 neither.

## What the sitting found, 2026-08-28

**The two halves are one aggregation, not a seam and its hardest case.** Read the four projects
that reached for this and every figure is the same shape:

| Project | The number it wanted | What it is |
|---|---|---|
| dogfood #2 | 8 counts: candidates dropped, pages unreadable, bucket sizes | count over count, over items inside the run |
| dogfood #3 | `backlist_share` | backlist picks over all picks |
| dogfood #4 | unverified citations per judgement, per-class recall | count over count |
| dogfood #5 | 40 pairwise comparisons | wins over pairs |

**Every one is a ratio of two totals where the unit counted is not the rollout**: candidates,
pages, picks, citations, pairs. The counts dogfood #2 printed bare were bare because it had no
denominator to declare. A win rate is that same aggregation with the unit being a pair, so G1
adds one ingredient to the seam rather than being a case of it. The two cannot sensibly be
separated, which is what Thilina's decision to take them as one item already assumed.

**What the mean gets wrong, arithmetically.** Two examples, one returning 10 picks of which 1 is
backlist and one returning 2 picks of which 1 is backlist. The mean over examples is
`(0.1 + 0.5) / 2 = 0.30`. The figure the builder means is `2 / 12 = 0.167`. Both are defensible
and they are not the same quantity. Dogfood #3 met this and put the rate through `ProjectMetric`
anyway; the count it asked for by name reached the trajectory and no results file.

**What a figure outside the results file costs.** It is outside FT-06, outside `compare()`,
outside `behaviour_fingerprint`, and outside the conformance suite. Dogfood #4's whole model
comparison, four arms and twenty rollouts, lived in `compare_arms.py` and printed to a terminal.

**H1's recorded blocker is stale, in the same way G1's was.**
[`design/answer-shapes.md`](../design/answer-shapes.md#L1002) says *"`read_labels` collapses
repeats, which is where it would start"*, which reads as several annotators' verdicts being lost.
They are not. [`read_labels`](../../src/simple_agents/evaluation/labels.py#L133) returns
`dict[str, Label]` with last-line-wins, and **the file keeps every line**: collapsing is the
reader's choice. Any project that appended holds the whole multi-annotator history on disk. What
is missing is a reader returning `dict[str, list[Label]]`. That is two of six shapes whose
recorded blocker had already been overtaken.

**The 26, and what they were.** Thilina, at the sitting, on his own labelling of dogfood #5's 40
pairs: *"Those 26 were because both the TV shows I was offered in each of those 26 were TV shows
that I had no interest in watching. It's possible that there were some where I was mildly
interested in one or the other or both, but not enough that I would confidently pick one over the
other."* So `prefer_neither` meant **both bad**, not **equally good**, and a three-way
this/that/tie verdict destroys the distinction. What it costs, measured:

| Figure | Value | What it says |
|---|---|---|
| wins over all 40 pairs | 0.175 [0.087, 0.319] | reads as "this arm rarely wins", dragged down by pairs where nothing was wanted |
| wins over the 14 with a preference | 0.500 [0.268, 0.732] | the honest win rate: the two bands are indistinguishable |
| **pairs where nothing was wanted** | **0.650 [0.495, 0.779]** | **the actual finding, and nobody computed it** |

Two thirds of the shortlists held nothing the end user wanted, which is a more actionable
statement about the recommender than either win rate.

## What has to be decided

**All six were settled at the sitting on 2026-08-28**, and each
carries its ruling below. The questions are the ones this section listed while the item was
open, in the order it listed them.

**1. `compare()` shows a figure that is not a mean over examples, and the shape is a ratio of two
totals.** The project declares a numerator and a denominator per rollout; the library sums each
over the rollouts in the figure's population, divides, and takes the interval by resampling
**examples**, summing both sides inside each resample and dividing. That is a sibling of
[`bootstrap_ci`](../../src/simple_agents/evaluation/intervals.py#L134) with the same guards, the
same seed and the same `MIN_RESAMPLES`, and it keeps the k-rollout dependence handled the way it
already is. **A denominator is the default and not a requirement**: a project with no natural one
declares a denominator returning `1.0`, which makes the figure a per-rollout rate, and the raw sums
are recorded either way, so dogfood #2's eight counts land in the file with a denominator rather
than in a print statement. *(This read "**No bare total ships**" until later the same day, when
Thilina defeated it. Decision 1b.)* **What this does not cover, stated rather than hidden:** dogfood #4's confidence
separation between right and wrong answers is a difference of two conditional means and fits
neither shape.

**1b. A figure the project cannot put an interval on goes on file anyway, and FT-06 gets
stricter.** Raised by Thilina on 2026-08-28, against decision 1's "no bare total ships": *"Makes
me wonder if interval discipline is straying into dogmatic doctrine then. Because we can't forsee
all possible combinations and permutations of the forms that metrics may take. Maybe if a project
has a metric that cannot compute an interval, we should allow an exception so that it at least
goes on file instead of just being a print?"*

**Three things checked, and all three favour him.** Interval discipline is **not** in
[`simple-agents.md` §9](../simple-agents.md#L515)'s do-not-change list; it is one line of §10's
checkable list and FT-06. **The doctrine is enforced in the wrong place**: FT-06's check passes any
non-empty `reason`, measured 2026-08-28 with `reason="n/a"`, and what actually refuses is
[`Metric`](../../src/simple_agents/evaluation/metrics.py#L178), whose `value` is
`interval.point if interval is not None else None`, so **a number with no interval is
structurally unrepresentable**. FT-06's documented exception is for a metric that *reports no
value*, which is a different state. **And the rule improved no figure**: three projects met it and
every one left the artifact rather than finding a better number, so the rule protecting the
results file is the reason those numbers are not in it.

**Decision 1's refusal is reversed.** Declaring a denominator stays the default and the
documentation's advice; the refusal goes. A project declares `interval=None` with a reason, which
lands in `config.metrics` under a source hash, prints in a form that cannot be quoted as a
measurement, and travels through `compare()` with its verdict withheld, which
`MetricChange.moved: bool | None` and `verdict_reason` already support.

**FT-06 tightens rather than loosens, agreed at the same exchange.** It stops reading a free-text
string and starts reading a **declared state**: a figure passes carrying an interval, or carrying a
declaration that it has none and why. `reason="n/a"` stops passing. **The check ends up stronger
than it is today** while admitting the exception, and it moves
[`docs/failure-taxonomy.md` FT-06](../../docs/failure-taxonomy.md#L147) and
[`simple-agents.md` §10](../simple-agents.md#L344)'s "the reported metric carries an interval".

**2. `denominator` is renamed, and the freed name takes the number.** Thilina's call, against the
first proposal, which was to leave the prose field alone and call the numbers `total` and
`out_of`: *"I would still say that 'denominator' sounds like a pretty bad name for whatever that
is... don't you think that that's a bad name as currently used AND is the best name for what we
want to use?"* Both halves hold. [`Metric.denominator`](../../src/simple_agents/evaluation/metrics.py#L217)
holds a **sentence** ("rollouts of examples where a value exists"), which is a description of the
denominator rather than a denominator.

- `Metric.denominator: str` becomes `Metric.population: str`, which is the vocabulary the public
  surface already uses for this concept: `Comparison.population_changed` and
  `MetricChange.population_note` both mean which rollouts a figure covers.
- `Metric` gains `numerator: float | None` and `denominator: float | None`, the two numbers.
- `ProjectMetric.denominator` (a property deriving the prose from `over`) becomes `population`,
  and `_OVER_DENOMINATORS` and `CRITERION_DENOMINATOR` follow it.

**The migration is small, and the hazard is absent.** Measured 2026-08-28: as a name rather than
as an English word, `denominator` is **22 sites in `src`** across four modules and one view
template, 36 in tests, 20 committed results fixtures and one in `docs/`. The 82 remaining uses are
the word in prose and most stay correct. The JSON key changes meaning from a string to a number,
which would be a trap if anything read an old file; nothing does.
[`EvalResults.read`](../../src/simple_agents/evaluation/results.py#L604) **refuses any file whose
`eval_format_version` is not current**, so there is no dual-reading path to get wrong.

**3. The pair is declared by the project, not derived by the library.** The first proposal had the
library forming pairs on `(example_id, rollout)` across two arms. Thilina defeated it: *"Just pair
up the winners together and the losers together."* The proposal had anchored on `compare_variants`
because this record framed G1 as *"a judgement over a pair of arms"*, and dogfood #5's own
instrument was not that shape at all: it drew two items from **one** live ordering, rank 1+ against
rank 2001+. **Three pairings of one figure**, and the library must fix none of them: two arms on
one example, two items from one ordering, and a bracket where winners meet winners. So the library
takes a set of pairs the project declares, reads judgements over them, and reports the figure. It
ships the arm-versus-arm helper because it holds both results files, and it documents that **how
the pairs are formed is where the instrument's quality comes from**: a flat random pairing across a
wide quality gap produces mostly uninformative pairs, and a bracket resolves the ambiguity by
position rather than by asking the annotator to express it.

**The library names no verdict set.** [`Label.verdict`](../../src/simple_agents/evaluation/labels.py#L68)
is already `Any`, and that file's own opening says the library *"holds no opinion about the
verdicts in it"*. So the pairing pass records whatever verdicts the project chose, the library
counts what it finds, and the ratio declares which count is the numerator and which set is the
denominator. Dogfood #5 declares four and gets both figures with their own intervals, and no `tie`
concept ships. **A figure computed over a subset records the population it was drawn from**, so
`7 of 14` cannot be reported without `40 judged` beside it.

**Arm order is randomised by default and both orders are offered.** Thilina's call. A judge shown
A then B prefers A more often than chance. The order is drawn from the evaluation's seed and
recorded; a project declaring both orders pays double and gets the disagreement rate, which is a
reading on the judge.

**Where the model call goes.** `P3-12`'s discipline transfers whole and
[`simple-agents.md` §10](../simple-agents.md#L1)'s requirement that the suite run in CI with no
network survives: [`Scoring.judgement`](../../src/simple_agents/evaluation/scoring.py#L100) **reads**
a decision out of `evals/judgements.jsonl` and calls nothing, and
[`suite.judge`](../../src/simple_agents/evaluation/runner.py#L1601) is the separate pass that makes
them under `RunEnvelope(role="labelling")`. `over=` already takes arbitrary material, so a pair
needs no new request shape. A pairing worklist is the sibling of `suite.judge` that this adds.

**4. The results file records nothing for a paired figure.** It belongs to two arms and to neither,
so it goes on `Comparison`, which `compare_variants` already embeds per arm in the file it writes.
**This corrects the `plan.md` row**, which said the item "moves the results file": the ratio half
moves the results file `0.25` to `0.26`, and the paired half moves the variant comparison `0.2` to
`0.3`. Both are formats a project holds, so the reason for preceding `P3-31` holds and its
statement did not.

**Two defects in the comparison record, found while deciding this and fixed inside the item.**
`Comparison` carries no format version at all, so a project writing `to_record()` gets a file
nothing can date. And [`Comparison.to_record`](../../src/simple_agents/evaluation/compare.py#L416)
returns `shared_examples`, `only_before`, `only_after`, `changed`, `moved`, `undecided`,
`moved_nodes`, `population_changed`, `metrics` and `nodes`: **`criteria` and `groups` are computed
and then dropped**, so every per-criterion movement and every grouped cell is lost on write.
[`docs/evaluation.md` §10.4](../../docs/evaluation.md#L2415) calls it "the full comparison record",
which is false.

**5. Two elicitation scaffolds are rewritten and no question is added.** The gap is in two places
and the more serious one is at `shape`, not at `measure`.
[`ground_truth`](../../src/simple_agents/conformance/elicitation.py#L384) and
[`answer_form`](../../src/simple_agents/conformance/elicitation.py#L403) are both `required` and
both assume a correct answer exists; a project that can only say which of two is better has none,
so it either answers a question that does not apply or leaves a required entry unanswered.
Dogfood #5 is that project and its answer is the log's *"I don't get what you are asking"*.
[`improvement`](../../src/simple_agents/conformance/elicitation.py#L749) routes every number to a
`ProjectMetric`, which is right only for a mean over examples, and four of five projects named
something else. `ground_truth` learns that "there is no correct answer, only a preference between
two" is a real answer and records it as one; `improvement` learns the ratio and the paired
comparison. The precedent is `P3-11`'s own build, which rewrote three questions and added none.

**6. All four remaining answer shapes are pulled in.** Thilina's call: *"I would prefer to do this
properly rather than leave hanging threads."* `plan.md` §2.2's four-shapes entry is deleted and
B2, F2, G2 and H1 are this item's. **The deciding work is the entry's own afternoon** — writing
each against what ships — **and it runs before any of the four is built**, because G1 and H1 both
had stale blockers that a read produced and only a worked example would have caught.

| | What a read suggests | Confidence |
|---|---|---|
| **G2** | The example-group unit, one more step on the unit axis this item extends for pairs. Small | High, traced |
| **H1** | A reader returning `dict[str, list[Label]]`, plus a project declaration of what "right" means against a distribution. Small | High, code read |
| **F2** | `results.criteria` already gives a figure per criterion with its own interval; the gap is grouping them into named axes. Small | Medium, from a read |
| **B2** | Likely a graded `AnyOf`, which touches `classify`, `graded_accuracy` and `partially_correct_rate`. **Could be its own item** | Low |

**What the seam generalises, and how far this item takes it.** Every figure is a unit and a fold.
Today the unit is the rollout and the fold is the mean over examples. This item builds the **fold**
axis in full and takes the **unit** axis as far as the pair and the example group. Nothing else
moves.

## What was pulled in with it

- **§2.2's four answer shapes.** Decision 6 above. The entry is deleted.
- **§2.1's arm-fingerprint entry**, accepted 2026-08-25 and waiting on nothing but a slot.
  `graph_fingerprint` cannot see a reworded prompt, a moved temperature or a swapped model, so two
  arms differing only in a prompt record the same value, which is the blind spot FT-37 exists for.
  The fix is one `.get("behaviour_fingerprint")` per arm, since each arm's results file carries it
  from `0.24`, **and a variant format bump `0.2` to `0.3`**, which this item pays for anyway. Taken
  separately it buys a second bump. It was not taken inside `P3-34` because that item's sitting
  decided the results file and not the comparison.
  [`build-logs/what-the-checks-read-build-log.md`](../build-logs/what-the-checks-read-build-log.md#L1) §6.
- **`DF5-I30`**, [`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L110). The results
  file says which `Over` a figure was computed under in `config.metrics` and not beside the figure.
  A new figure kind arriving is when a reader most needs it there, and it is one field on the
  record this item already edits.

## Build order

1. `ProjectRatio`, the ratio interval, the `denominator` rename, the no-interval declaration and
   FT-06 reading a declared state, results format `0.25` to `0.26`.
2. The pair unit, declared pairs, the arm-versus-arm helper, the pairing worklist, randomised order.
3. The comparison record: its own version, `criteria` and `groups` written, the paired figure,
   variant format `0.2` to `0.3`, and `behaviour_fingerprint` per arm.
4. **The four-shapes decider pass, reported before anything is built for it.** A shape that comes
   back needing its own item is Thilina's call, not the build's.
5. Whatever that pass says is small.
6. The two elicitation scaffolds, and `over` recorded beside the figure (`DF5-I30`).

Then the live run against vLLM and Gemini, then the read-and-verify cycles.

## What it waits on


Nothing blocks it. It is the only item of dogfood #5's sitting 4 that needs a sitting before it can
be built, and it moves the results file, so it precedes `P3-31`.
