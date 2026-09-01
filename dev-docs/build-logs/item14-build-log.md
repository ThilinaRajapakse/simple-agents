# Item 14 — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item13-build-log.md`, `item10-build-log.md`, `item8b-build-log.md`, `item8g-build-log.md`,
`item9-build-log.md` and `item8a-build-log.md`.

The design of record is `archive/plan-history.md` §3.1 item 14, six paragraphs written 2026-07-30 at the
document review and never built. Unlike item 13's one-line entry, this one is specific enough
to be wrong in named places, so §1 is aimed at its own claims. **Item 8b is the precedent:** its
entry also said the design was settled and four of its claims did not survive being run.

§1 records what was measured before the sitting, §2 the sitting, §3 where building sharpened a
decision, §4 where it turned out not to hold, §5 what the build found that is nobody's design,
§6 doc consequences, §7 existing tests that had to change.

**Status: sitting held 2026-08-07, building. Baseline 1091 tests at `855f761`.**

---

## 1. What was measured, before any design

Item 13 §1 is the standard: every claim is read off a file the library produced or off a live
run, never off a document. The probes are under `scratchpad/item14/`:
`probe_reachability.py`, `probe_by_hand.py`, `probe_recompute.py`, `probe_shapes.py`,
`probe_workaround.py`, `probe_nonrate.py`, `probe_matches_callsite.py`,
`probe_perrollout_cost.py`, `probe_ratio.py`, `probe_edges.py`.

**The artifact everything is measured against** is the committed evaluation recording
`tests/cassettes/eval.jsonl`, replayed through `scripts/record_backend_cassettes.py::eval_suite`
at seed 41, k=3, 3 examples, two nodes. Nine rollouts, no network. The results file it writes is
`scratchpad/item14/out/results.json`.

### 1.1 The results file, `report()`, `Metric` and FT-06 are already generic over the name

A `Metric` built by hand and assigned into `results.metrics` needs no library change to survive
everything downstream. `probe_workaround.py` does exactly that with a token-F1 over the answer
spans:

| | |
|---|---|
| `results.metrics["span_f1"] = Metric(...)` | accepted; the dict is mutable on the frozen dataclass |
| written to the results file | yes, seven entries under `metrics` |
| `EvalResults.read` round trip | yes, `value` 0.667 |
| `results.report()` | printed on its own line with its interval and n |
| FT-06's check | walks it: `_reported_metrics` iterates every key of `metrics` |

**So a project metric that reaches the results file gets the artifact half for free**, including
the one conformance check that reads metrics. Nothing in `to_record`, `from_record`, `write`,
`read` or `ft_06` is keyed on the six names.

### 1.2 `compare()` is the one place that is not, and it drops a seventh metric without a word

`compare.py:294` is `for name in METRIC_DEFINITIONS`. Comparing two results files that both
carry `span_f1`:

```
metrics compare() reports: ['accuracy', 'false_confidence_rate', 'recall',
                            'abstention_rate', 'failure_rate', 'precision_when_asserting']
span_f1 in the comparison: False
```

No entry in `metrics`, nothing in `moved`, nothing in `undecided`, no reason recorded. The
metric a project added because accuracy was the wrong number is the one metric a regression
comparison does not look at.

### 1.3 The results file never records the label, so a metric at (answer, expected) cannot be recomputed from it

`compare()` recomputes all six from the two files, through `scores_by_metric(rollouts,
expects_absence)`. Both inputs are in the file. A metric at `(answer, expected)` needs the
expected answer, and the file does not carry it.

| Block | Keys |
|---|---|
| `examples[id]` | `split`, `expects_absence`, `source` |
| `rollouts[i]` | `example_id`, `rollout`, `seed`, `outcome`, `answer`, `run_id`, `trajectory`, `error`, `nodes` |
| `config.example_set` | `content_hash`, `splits`, `held_out`, `absent_proportion` |

`expects_absence` is a bool. The label itself appears nowhere. The two occurrences of
`"Northgate"` in the file are both rollout answers.

**So a project metric cannot be recomputed at comparison time from two results files.** Either
the label goes into the file, or the per-rollout score does.

### 1.4 `matches` was called on 4 of the 9 rollouts, so the seam is not where `matches` sits

The entry's central claim is that the seam "has to sit where `matches` already sits, at
`(answer, expected)`, returning a float rather than a bool. That seam exists, which makes this
cheaper than it looks." `probe_matches_callsite.py` wraps `suite.matches` and counts.

| Rollout | Outcome | `matches` called |
|---|---|---|
| e1-0 | missed | **no** |
| e1-1, e1-2 | correct | yes |
| e2-0 | missed | **no** |
| e2-1, e2-2 | correct | yes |
| e3-0, e3-1, e3-2 | correct_abstention | **no** |

**4 of 9.** `classify` calls `matches` only when both sides are asserted values, and
`outcomes.py` states that as a guarantee: "so it never has to handle absence".

The six rates are functions of `Outcome`, which covers all nine. A float metric over the answer
has to score the other five as well: a rollout that reported absence where a value existed
scores 0 rather than being skipped, and a rollout scored against an absent label has no span to
overlap with. **The call site `matches` occupies is a strict subset of the one a project metric
needs**, and the difference is the case `matches` was deliberately kept away from.

### 1.5 `report()` prints every metric as a percentage, and a project metric is often not a rate

`results.py:131` formats each metric `{point:6.1%}`. `probe_nonrate.py` puts two non-rate
metrics in, with real per-rollout values:

```
  cost_per_rollout            0.0%  [0.0%, 0.0%]  n=3 over all rollouts
  tokens_per_rollout        86666.7%  [86666.7%, 86666.7%]  n=3 over all rollouts
```

0.00015 USD prints as `0.0%`. 866.7 tokens prints as `86666.7%`. The per-node table has the
same shape for `reach`. **The report is the surface `docs/evaluation.md` §8.1 shows a builder**,
and it is a rate formatter with no way for a metric to say it is not a rate.

### 1.6 One of the three metrics the entry names as a project metric does not fit the seam the entry proposes

The entry names "F1 over extracted spans, numeric tolerance on a measurement, cost per correct
answer". The first two are per-rollout functions of `(answer, expected)`. The third is neither.

**It is not a function of `(answer, expected)`.** Cost comes off the trajectory's `model_call`
records against the envelope's basis. Nothing on `RolloutOutcome` carries it; its nine fields
are listed in §1.3. `probe_perrollout_cost.py` reads it per rollout by opening each trajectory:
0.000111 to 0.000204 USD across the nine.

**It is also not a mean.** `probe_ratio.py`:

| | |
|---|---|
| ratio of totals, 0.001376 USD over 7 correct | **0.000197 USD** |
| mean over examples of each example's own ratio | **0.000206 USD**, `[0.000142, 0.000249]` |
| difference | 4.7% |

`bootstrap_ci`'s point estimate is the mean over examples of each example's mean over its
rollouts. For a ratio of sums that is a different quantity, and the interval it returns is an
interval on the wrong one. An example with zero correct rollouts divides by zero in the
per-example form and is absorbed by the ratio of totals.

### 1.7 `bootstrap_ci` does not refuse a flat list; it raises `TypeError`

`intervals.py`'s module docstring and `docs/evaluation.md` §4 both say it "cannot be handed a
flat list by accident". `probe_shapes.py`:

| Argument | What happens |
|---|---|
| `[0.5, 0.3, 0.9]` | `TypeError: 'float' object is not iterable` |
| `[1, 0, 1]` | `TypeError: 'int' object is not iterable` |
| `["a"]` | `TypeError: unsupported operand type(s) for +: 'int' and 'str'` |
| `[[0.5], [0.3], [0.9]]` | accepted, point 0.567, n=3, k=1 |

Every other refusal in the library is a `ConfigurationError` naming the call that fixes it.
This one is a Python exception from three frames in, and the two `ConfigurationError`s that do
exist cover an empty list and an empty inner list.

**The mistake is more available to a float metric than to a binary one.** A project computing
one score per example, which is what an F1 aggregated over an example's rollouts is, writes
`bootstrap_ci([0.5, 0.3, 0.9])` and gets the `TypeError`.

### 1.8 The private path a seventh metric would reuse is keyed on the shipped six

`metrics._metric` is the function that returns a `Metric` with no interval and a stated reason
when the denominator is empty, which is the entry's fourth open question. Its first line is
`definition = METRIC_DEFINITIONS[name]`, so calling it with any other name raises `KeyError`.
`probe_edges.py` confirms it.

### 1.9 `scores_by_metric` is not reachable from `simple_agents.evaluation`

The entry says "`bootstrap_ci` and `scores_by_metric` are public so a correct interval is
reachable". Half of that is true.

```
sorted(simple_agents.evaluation.__all__)  # 26 names; `bootstrap_ci` is one, `scores_by_metric` is not
hasattr(simple_agents.evaluation, "scores_by_metric")  # False
```

It is in `metrics.__all__` and is not re-exported. `grep` over `docs/` finds no mention of it.
Reaching it means importing `simple_agents.evaluation.metrics`, which no shipped document names.

### 1.10 A project metric named `accuracy` overwrites the shipped one, silently

`probe_edges.py`: `results.metrics["accuracy"] = Metric(...)` moved the reported value from
0.778 to 0.200. The results file, `report()` and FT-06 then all report the project's number
under the shipped name. Nothing refuses it and nothing records that it happened.

### 1.11 Nothing about a metric reaches a cassette key or an `eval_id`, so this item cannot move the six transcribed numbers

Item 13 §5.2 is the live hazard: six tests in `TestEvaluation` transcribe numbers the live
recording produced, and re-recording moved accuracy from 5/9 to 7/9. Checked rather than
assumed:

- A cassette key is `_hash` over the request payload (`cassette.py:521`). No metric, and no
  `matches`, is in it.
- `_eval_id` is over the example set's content hash, the seed, the split, k, the graph
  fingerprint and the prompt versions (`runner.py:262`). No metric, and no `matches`.

**So any movement in those six numbers during this item is a re-recording and not the metric.**
The current replay reproduces the committed figures: accuracy 7/9, recall 4/6, `hunt` 19 tool
calls, 4 tool-call cassette entries.

### 1.12 No elicitation question asks which number the builder would act on

The seventeen questions are listed in `conformance/elicitation.py`. Two are adjacent and
neither asks it.

| Question | Stage | Asks |
|---|---|---|
| `absence_vs_error` | shape, required | whether a wrong answer costs more than a missing one, which is what makes `false_confidence_rate` and `recall` worth separating |
| `improvement` | measure, required | "How will the builder know that a change helped?", scaffolded as k rollouts on the held-out split compared on the interval |

`improvement`'s scaffold names the method and no metric. **FT-10 is what created this item, and
Thilina's objection at the document review was that accuracy is a mediocre metric in many
situations.** Nothing in the elicitation set puts that objection to the builder.

### 1.13 Per node, a project's ground truth is a bool and nothing else

`node_matches` takes `Callable[[Any, Any], bool]` per node and produces one rate, `accuracy`,
over the rollouts that reached the node and carry a label. There is no per-node equivalent of a
float-valued score. `simple-agents.md` §4.2 records that per-node accuracy was not anticipated
and what ships per node is behaviour: calls, tokens, cost, terminations, absences.

### 1.14 FT-10 has no check, and the seam does not obviously give it one

Seven checks ship: FT-13, FT-14, FT-24, FT-01, FT-02, FT-06, FT-07. FT-10's declared check is
"the results artifact reports false-confidence rate separately from recall, each with its own
interval", and its own text says it "fails only for a project that reports its own numbers".
Every results file the library writes passes it by construction, because `aggregate` writes all
six whatever the project asked for.

---

## 2. The sitting, and what it settled

Held 2026-08-07, after §1's measurements and before any code. Nine questions were put over two
rounds. **The entry's central claim did not survive §1 and the item did**, which is item 8b's
shape: `docs/evaluation.md`'s machinery is already generic over a metric's name, so what this
item builds is a declaration surface and a comparison, not a metrics engine.

**Two of Thilina's answers changed the design rather than choosing between the options put.**
§2.1 was re-put after he rejected the framing, and §2.6 was reversed.

### 2.1 The library keeps the absence branch, and the denominator is declared

**Settled after the question was put as a choice between three signatures and re-put.** The
options offered were `(answer, expected) -> float | None`, a pair of `included`/`scored`
functions, and `(rollout, example) -> float | None`. Thilina's objection was that all three make
the project handle absence, and that the fix is to give the project a clear choice rather than a
wider signature: "one that handles unknowns and one that ignores unknowns".

§1.4 measured why the entry's seam is not enough on its own: `matches` was called on 4 of the 9
rollouts, and `outcomes.py` states as a guarantee that it "never has to handle absence".

**What ships is one declared denominator, from three, and one signature.**

| `over=` | The denominator | What `score` is called with |
|---|---|---|
| `ASSERTED` | rollouts that put a value forward, of examples whose label is a value | two asserted values |
| `VALUE_EXISTS` | every rollout of an example whose label is a value | two asserted values; a rollout that did not assert scores 0.0 without `score` being called |
| `ALL` | every rollout | whatever the rollout produced, absence included |

`ASSERTED` and `VALUE_EXISTS` are `precision_when_asserting`'s and `recall`'s denominators, which
is the whole set the six use once "all rollouts" is excluded, so the enumeration is short because
§1 measured that it is short.

**A second re-put, on the signature.** The first presentation offered the narrow
`(predicted, expected)` seam and named what it gives up: per-rollout cost, and a faithfulness
metric over the answer and the trajectory together. Thilina's ruling: "Can't we just add the
option to also use the full trajectory? Choosing one or the other seems like an unnecessary
handicap." **So there is one signature and it always takes three arguments**,
`score(predicted, expected, rollout)`. A metric that does not need the third ignores it, and the
unused parameter is what makes the capability discoverable in a signature a coding agent reads.

**What `rollout` is, and the cost stated rather than implied.** The `RolloutOutcome`, which
carries `trajectory` as a path. Reading it is a file open per rollout, and the library does not
pre-read them: `runner.py:200` already passes trajectories to `per_node` as a generator, so
handing every metric the parsed records would hold n×k of them in memory.

### 2.2 Means only, so the interval is an interval on the metric

**Settled.** §1.6 measured that "cost per correct answer", named in the entry as a project
metric, is a ratio of sums: 0.000197 USD as a ratio of totals against 0.000206 USD as the mean
over examples the bootstrap computes, 4.7% apart, with an example scoring zero correct dividing
by zero in the per-example form.

A project metric is a per-rollout float aggregated as a mean over examples. A ratio of sums is
computed by the project from `results.totals`, which already carries both figures.

**Thilina's question, and the answer:** are there figures that are useful and should not carry an
interval? Yes, and the library already reports seven of them, none of which is a metric:
`totals.cost`, `totals.tokens`, and per node `model_calls`, `tool_calls`, `terminations`,
`wall_clock_ms` and `absent_outputs`. A figure wants an interval when it is a mean over examples
and the question is whether it would hold on other examples; a count of what happened in one run
is not that claim. **Recorded as note 2 of `random-thoughts-questions.md`** on his instruction:
there is no seam for a project-supplied count or total.

### 2.3 The score is recorded per rollout, and the version is derived from the function

**Settled.** §1.3 measured that the results file records `expects_absence` and never the label,
so a metric at `(answer, expected)` cannot be recomputed at comparison time as all six are.
`rollouts[i].scores` holds the per-rollout float, and `compare()` reads the metric names out of
the two files rather than out of `METRIC_DEFINITIONS`. That also closes §1.2, where a seventh
metric present in both files was dropped from the comparison without a word.

**Thilina's objection, which is a live defect rather than a hypothetical.** If the scoring
function changes between two evaluations, a comparison against the older file is corrupted.
Measured on `matches`, which is already recorded and already scored at evaluation time
(`probe_matches_trap.py`): two replays of one cassette, same pipeline, same seed, only the
matcher differing.

| | |
|---|---|
| accuracy, lenient matcher | 0.778 |
| accuracy, after the matcher changed | **0.333** |
| `compare().changed` | `['matches.version']` |
| `accuracy` delta reported | **−0.444** |

It reads as the agent losing 44 points. `moved` is empty only because n=3 sits below the
20-example floor; at n≥20 it reports `moved: ['accuracy']`.

**Settled: `moved` is `None` when the scoring function's version differs between the two sides**,
with `verdict_reason` naming both versions. The delta and the interval are still reported. Item
8a §5.4's shape for the 20-example floor, applied to a second reason a verdict cannot be
supported. **And `matches` gets the same treatment**, which is outside item 14's boundary as
written and inside it on the measurement.

**Thilina's second question: is versioning something the builder has to remember?** No. It is
derived from the function's source by `manifest.source_version`, which is what `config.matches`
already carries: `{'version': 'sha256:6b024a74f756', 'source': 'derived'}`. The two bounds are
measured in `probe_version_derivation.py` and are the ones item 13 §2.1 recorded for a tool: a
threshold the function closes over changes the metric and not its version, and a function defined
where its source cannot be read records `unavailable`.

### 2.4 One flat `metrics` block, refusing the six names

**Settled.** §1.10 measured that assigning over a shipped name moves the reported value silently:
accuracy 0.778 to 0.200, with the results file, `report()` and FT-06 all then reporting the
project's number under the shipped name.

A separate `project_metrics` block was offered and declined. Thilina: the library/project
separation is not important to him either way. A second block would cost edits to FT-06's
`_reported_metrics`, to `report()` and to `compare()`, and §1.1 measured that everything
downstream is already generic over the name. **No `source` key**, on the same reasoning.

### 2.5 A metric says whether it is a rate

**Settled.** §1.5 measured `report()` formatting every metric `{point:6.1%}`: 0.00015 USD prints
as `0.0%` and 866.7 tokens as `86666.7%`. `Metric` gains `unit`, defaulting to a rate.

### 2.6 Per-node project metrics, which the first presentation recommended against

**Settled, reversing the recommendation.** The question was put as "not in this item, state the
bound", on the grounds that it roughly doubles the surface and no project on this machine has
ever supplied a `node_matches`. Thilina: "I was going to bring this up anyway. I think we
absolutely need per node custom metrics."

`node_metrics={"hunt": [ProjectMetric(...)]}`, called with the node's recorded output and
`example.expected_by_node[node_id]`, over the rollouts that reached the node and carry a label.
Recorded at `rollouts[i].nodes[node_id].scores` so `compare()._nodes` pairs on it. `NodeMetrics`
gains `metrics` beside `reach` and `accuracy`, and FT-06's `_reported_metrics` walks it.

**"Did this node report absence" is already solved.** `per_node._holds_absence` walks a node
output recursively for `type == "unknown"` and is what `absent_outputs` counts, so `VALUE_EXISTS`
uses the function that exists.

**One inconsistency accepted rather than removed.** `node_matches` is called on every rollout
that reached the node and carries a label, including one whose label is `Unknown`, and the
project handles absence itself; measured at 9 of 9 in `probe_node_matches.py`. `node_metrics`
follows the end-to-end rule instead. Bringing `node_matches` into line would change per-node
accuracy for any project labelling a node with an absence, which is a change to a shipped
surface. Thilina: "I'm not sure about this. But let's do it this way for now." Both rules go in
`docs/evaluation.md` §5.

### 2.7 `improvement`'s scaffold, and no eighteenth question

**Settled: option (a).** §1.12 measured that `improvement` asks "How will the builder know that a
change helped?" and its scaffold answers a different question, naming the method and no metric.
The scaffold is extended to print the six with the project's own numbers and ask whether one of
them is the number the builder would act on. No new brief entry, no new gate, and eleven fixture
briefs unchanged.

**This item does not give FT-10 a check**, and that is stated rather than implied. The seam makes
the right metric reportable; it does not make the wrong metric detectable. §1.14 measured that
FT-10's declared check passes every results file the library writes, because `aggregate` writes
all six whatever the project asked for.

### 2.8 Three small fixes §1 turned up, all taken

| | |
|---|---|
| §1.7 | `bootstrap_ci` raises `TypeError` on a flat list where every other refusal is a `ConfigurationError` naming the fix. The mistake is more available to a float metric than to a binary one |
| §1.9 | `scores_by_metric` is in `metrics.__all__` and is not reachable from `simple_agents.evaluation`. Dropped from `__all__` rather than exported, since the seam is what a project reaches for |
| §1.8 | `metrics._metric` looks its definition up in `METRIC_DEFINITIONS`, so the shared empty-denominator path raises `KeyError` for any other name. It takes the definition instead |

### 2.9 Scope

Results format `0.4` to `0.5`. **No cassette is invalidated and no `eval_id` moves**, checked at
§1.11 rather than assumed, so item 13 §5.2's six transcribed numbers cannot move from this work.

`docs/evaluation.md` is touched, on item 13 §2.7's precedent. §5.2's sentence that a node
matcher receives an absent answer "as `Unknown`, as it does everywhere else" is wrong and is
fixed: a node output is a schema object, so an absence sits in a field and arrives as a plain
dict.

**Dogfood #1 runs before the shipped-document review**, on Thilina's instruction, reversing the
first presentation's recommendation. His reason: the last cold read was after item 7, and 8a, 8b,
8g, 9, 10, 13 and 14 have all landed since, so the surface under test has roughly doubled and
none of it has met a cold session. The cost accepted is that the intervention log will mix prose
bugs in never-reviewed documents with design bugs, and §4.1 as amended runs it once; the log
separates the two.

---

## 3. What building it changed about the design

### 3.1 The score function takes the pieces explicitly, not a rollout standing in for an answer

The first implementation had `score_of(metric, rollout, expected)` reading `rollout.answer` and
`rollout.outcome.asserted`. Per node there is no `Outcome` and the answer is a node's recorded
output, so that version built a fake `RolloutOutcome` with the output substituted for the
answer, which reads as a trick rather than as a rule.

`score_of(metric, predicted, expected, rollout, *, asserted=...)` instead. End to end,
`asserted` is `rollout.outcome.asserted`. Per node, it is whether the recorded output holds an
absence anywhere in it. The rollout is still handed through, because that is the third argument
the score function gets.

### 3.2 `_metric` and `_rate` were the same function, and the empty-denominator path was two

§1.8 measured that `metrics._metric` looked its definition up in `METRIC_DEFINITIONS`.
`per_node._rate` was a copy of it that took the definition. Making `_metric` take the definition
collapsed the two: `_rate` now filters the empty inner lists and calls `_metric`, so the
empty-denominator `Metric` with a stated reason is written in one place for the six, for `reach`,
for per-node accuracy and for every project metric.

### 3.3 The refusal of two node arguments naming a node the pipeline does not hold is one function

`node_matches` had its own refusal. `node_metrics` needs the same one, so both go through
`_refuse_unknown_nodes(argument, given, declared)` and the message names whichever was given.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Twenty-nine guards, disabled one at a time, and the one that stayed quiet was the test

Twenty-eight of twenty-nine failed the test named against them on the first pass. The quiet one
is item 8g §4.1's shape a seventh time: **the test could not observe the guard.**

| Disabled | Why the test still passed | What it was |
|---|---|---|
| `_project_names` requiring the metric in the later file too | the fixture declared the metric on the **after** side only, and the walk is over `before.metrics`, so the name was never produced and the disabled clause was never what excluded it | a test exercising a path an earlier filter already covered |

The test now compares in both directions, `without → with` and `with → without`, so the walk
produces the name in one of them and only the disabled clause can exclude it. **29 of 29 fire.**

The pass ran each case with `PYTHONDONTWRITEBYTECODE=1` and cleared every `__pycache__` after
restoring, per item 8g §4.2. `scratchpad/guard_pass_item14.py` is the script.

---

## 5. Findings

### 5.1 The first per-node project metric run on the library's own recording localised a failure the end-to-end number hides

`probe_built.py`, over the committed evaluation recording. `hunt` scored 1.0 on rollout 0 of
`e1`, and that rollout's end-to-end outcome is `missed`.

```
  e1-0 missed              {'span_f1': 0.0}  hunt={'span_f1': 1.0}
```

`hunt` found the answer and `verify` rejected it. That is item 8a §1.7's finding arriving through
a different instrument: on this recording the node worth removing is the `LLMNode`, and a
per-node figure says so on a single rollout without a variant sweep. It is also what Q6 was built
for, decided against the first presentation's recommendation.

### 5.2 The six numbers the recording produced did not move, which is what §1.11 predicted

`TestEvaluation`'s nine tests pass unchanged: accuracy 7/9, recall 4/6, `hunt` 19 tool calls, 28
model-call cassette entries, 4 tool-call entries, `["missed", "correct", "correct"]` on both `e1`
and `e2`. No cassette was re-recorded and no `eval_id` moved, so item 13 §5.2's hazard did not
fire. **Any movement in those literals in a later item is a re-recording.**

### 5.3 `docs/evaluation.md` §8.1's sample output had been stale since item 13

The block a builder reads to see what `results.report()` prints showed accuracy 44.4%, `hunt`
with 18 calls and 20 tool calls, and `correct 1, correct_abstention 3, missed 5`. The library
prints 77.8%, 19 and 19, and `correct 4, correct_abstention 3, missed 2` for the same recording.

Item 13 §5.2 re-recorded the evaluation cassette and updated the six tests that transcribe its
numbers; §6's doc-consequences table did not include this block, which transcribes the same
numbers into a shipped document. **A test pins the tests and nothing pins the sample output.**
Corrected here, with the project metric shown in it.

---

## 6. Doc consequences

Written after the build.

| Document | What it said | What it says now |
|---|---|---|
| `docs/evaluation.md` §11 | did not exist | **New**, "A metric the project declares": `ProjectMetric`, what `score` is given, `Over`'s three denominators, the shape of the figure, `unit`, per node, and what a comparison does with it including the withheld verdict |
| `docs/evaluation.md` §3 | the six rates | Plus what they are functions of, and that a figure computed from the answer is a `ProjectMetric` |
| `docs/evaluation.md` §4 | `bootstrap_ci` "cannot be handed a flat list by accident" | It refuses one, with the one-score-per-example shape shown beside it |
| `docs/evaluation.md` §5.2 | a node matcher receives an absent answer "as `Unknown`, as it does everywhere else" | It receives the tagged object inside the output, and absence is the node matcher's to handle, which is the one place it is. **§5.3 is new**, for per-node project metrics |
| `docs/evaluation.md` §8 | results `0.4`, the config and rollout fields | `0.5`, plus `config.metrics`, `config.node_metrics`, `rollouts[].scores`, per-node `metrics`, and `unit` |
| `docs/evaluation.md` §8.1 | a sample report carrying numbers item 13's re-recording moved | What the library prints for that recording today, with a project metric in it |
| `docs/evaluation.md` §9 | the 20-example floor | Plus a changed `matches` withholding the verdict on all six, with `rule_moved` |
| `docs/index.md`, `README.md` | evaluation covers the intervals and per-node metrics | Plus a metric the project declares itself |
| `CHANGELOG.md` | results `0.4` | `0.5` with what a project does, the seam, the withheld verdict, the `bootstrap_ci` refusal, and the elicitation change |

**One format moved.** Results `0.4` to `0.5`. Trajectory `0.15`, manifest `0.11`, suspension
`0.1` and variant `0.1` are untouched: nothing about a metric reaches a trajectory record, a
manifest or a cassette key.

**The first draft of every one of these defended the feature**, on Thilina's review: it opened
§11 with "A metric the library does not ship", led §3 and the changelog entry with "accuracy is
the wrong number for many tasks", and repeated that line in the `improvement` scaffold. His
ruling: nobody will complain about having custom metrics, and the decision is not one to
defend. `CLAUDE.md`'s "never defend the design" rule is the one that was broken, and the fix
was to say what the thing is. §11 is now "A metric the project declares", §3 states what the six
are functions of, and the scaffold asks which number the builder would act on without
editorialising about accuracy.

**Not touched.** `docs/pipeline.md`, `docs/context.md`, `docs/tools.md`,
`docs/trajectory-format.md`, `docs/run-envelope.md`, `docs/conformance.md`, `docs/procedure.md`
and the model-client pages own nothing this item changed. FT-06's entry is unchanged: its check
already walked every key of `metrics`, and the code change is that it now walks a node's too.

---

## 7. Existing tests that had to change

Two, and neither is a defect in the library.

| Test | What it asserted | Why it changed |
|---|---|---|
| `test_packaging.py::test_every_format_version_is_pinned_to_a_literal` | results `0.4` | `0.5`. Item 9 §5.2's gap doing its job for the second time |
| `test_packaging.py::test_the_evaluation_document_states_the_results_version_the_writer_writes` | `docs/evaluation.md` states `0.4` | The document states `0.5` |

**No cassette was re-recorded and no fixture project was rebuilt.** The elicitation change is to
a scaffold rather than to the required set, so the eleven fixture briefs are unchanged and
`test_procedure.py`'s transcribed list of required `build` names still holds.

**Total: 2 existing tests changed, 36 added. 1127 tests**, from 1091 at `855f761`.
