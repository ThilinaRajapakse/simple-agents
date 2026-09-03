# What a correct answer can be

**The design of record for what a project can hold about a right answer.** `P3-5` was built in
two blocks and closed on 2026-08-17, and this is its record, kept because the survey below is
standing reference: twenty-four kinds of answer, what each needs to be scored, and sixteen
external sources read in full.

Everything above the divider is what the item was before the survey; "The survey, 2026-08-16" is
its result; "What has to be decided" is the agenda the two sittings worked through, and each
entry now says how it was settled.

## Where it came from

Thilina's note after dogfood #4, written in `random-thoughts-questions.md` and moved here on
2026-08-15, verbatim because the framing and the constraint are both in the wording:

> I also think another reason why the coding agent and I kept butting heads and misunderstanding
> each other is that the library seems to force _one_ correct answer per question/example. In all
> the dogfoods except for the trivial QA dogfood, there was no _one_ correct answer. So the coding
> agent keeps trying to force the evaluation, and because of how the library is set up, the design
> of the project and everything else to fit this very narrow 1:1 mapping. The result being a
> "product" that ticks the boxes the library demands, but is useless. We allow for the absence of
> a correct answer, but do we allow for the presence of multiple possible answers? Sets, ranges,
> estimates? What about natural language answers? I'm sure there are MANY more that I am missing
> that we need to think of and list. We can evaluate most of them, even though it's not
> necessarily easy, and I think providing the machinery to do so would be a good selling point for
> the library. I'm hesitating to give examples, because of your tendency to tunnel vision only on
> those, but a STARTING point would be LLMs-as-judge, LLM-Panels, Reward Models etc.

**The constraint in the last sentence governs the survey**: LLM-as-judge, panels and reward models
are named as a starting point and not as the answer. A survey that returns those three has not
surveyed anything.

## What the problem is

*Added 2026-08-16 after the survey, because `templates/item.md` requires this section and the
file did not have one. The evidence is S3 and the measurements are S3.4 and S3.5.*

**Three things are fixed and a project needs at least one of them not to be.** An evaluation
compares what a rollout produced with what the project holds, and
[`Example`](../../src/simple_agents/evaluation/examples.py#L53) holds **one value**,
[`matches`](../../src/simple_agents/evaluation/runner.py#L261) is **one boolean over two values**,
and [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) sorts **one rollout** into
five states with no partly-right one.

**Measured**: four of the five example sets any dogfood built are not that shape, and the fifth
fits because dogfood #4 reduced its task to a two-class verdict on one book, which is the set its
brief certifies. Two projects used `expected` in opposite senses through the same seam and nothing
records which. Dogfood #3's certified evaluation reports `false_confidence_rate` **0.939** for a
recommender that recommended books, because an imperfect answer has nowhere to go but the outcome
FT-10 defines as the dangerous one.

## What makes it a survey rather than a build item

"Sets, ranges, estimates, natural language" is four evaluation models, not one feature. A judge is
a technique for scoring an answer, not a shape an answer can have, so the two are different axes
and a design that conflates them will ship the technique and miss the shape.

## What the survey has to produce

- **The kinds of answer a project can have.** Enumerated, not exemplified.
- **What each needs in order to be scored**, and whether the library or the project supplies it.
- **What the library assumes today.** `Example`, `ProjectMetric`, `compare()` and the grounding
  helpers each encode the 1:1 mapping somewhere, and the survey names where.
- **What an example carries about its end user, for an agent that consults.** Added 2026-08-16 at
  the P3-9 sitting. For a consulting agent the end user's answers are part of the task definition
  rather than a separate axis: the right answer to "file this invoice" depends on the cost centre
  the end user knows and the agent has to ask for. An example carries no such thing today, and
  `SimulatedEndUser` is given the persona alone, so a consultation asking for a value gets a
  deflection and `expected` is unreachable. A survey that enumerates answer shapes for
  non-interactive agents leaves [`end-user-in-an-evaluation-build-log.md`](../build-logs/end-user-in-an-evaluation-build-log.md#L1)
  to re-derive the interaction, which is why P3-9 is scheduled behind this.
- **What external work exists** for each kind, on the evidence standard
  `items/example-projects.md` §19 set after most of that survey's sourcing did not hold.

## Why it is not in the dogfood #4 records

It is not in `runs/dogfood-4/findings.md` and not in `runs/dogfood-4/inventory.md`. Both were checked on
2026-08-15 and return nothing for it. The finding was made by the builder during the run and went
into his notes rather than into the record, which is the gap `plan.md` §1's collection rule now
closes.

## Evidence already on hand

- ~~**Three of four dogfoods had no single right answer.** Dogfood #1, extractive question
  answering, is the exception.~~ **Corrected 2026-08-16 by S3.4 below, on a measurement of the
  example files.** Dogfood #1 is not the exception: 30 of its 59 labels are lists of admissible
  spans and none is a single value. **Four of the five example sets any dogfood built are not the
  shape the library ships**; dogfood #2 built none at all; and the fifth fits only because
  dogfood #4 reduced its task to a two-class verdict on one book, which is the set it certified.
  Dogfood #2's t-shirt fit, dogfood #3's and dogfood #4's book recommendations all have sets of
  acceptable answers.
- **Dogfood #3's `DF3-D1`**: the project met the ship criterion with an evaluation whose chance
  rate was about 0.5%, and the replacement design's whole confidence interval sat below the chance
  rate the project computed for itself.
- **Dogfood #4's `DF4-D1`**: the artifact its end user sees was never what any evaluation
  measured, and its measured noise floor of 0.04 is wider than every model comparison it ran.

---

## The survey, 2026-08-16

**Nothing here is a design and nothing is agreed.** The five sections below are the five outputs
"What the survey has to produce" asks for, in its order. S6 records what the survey found to be
false in records already written, and the last section is what a sitting has to decide.

**Method, and what each claim rests on.** Three passes.

| Pass | What was done |
|---|---|
| The library | Every evaluation surface read in `src/`: `examples.py`, `outcomes.py`, `metrics.py`, `compare.py`, `runner.py`, `labels.py`, `grounding.py`, `schema.py`, and the `ground_truth` and `answer_form` elicitation questions. Every claim in S3 names a file and a symbol |
| The four dogfoods | Their example files and scoring code read on disk at `/home/thilina/Projects/dogfood-{1,1-run2,2,3,4}`, and their results files parsed. Every number in S3.4 and S3.5 was computed from those files today, not quoted from a findings record |
| External | **Sixteen sources read in full**, four of them including the shipped implementation, against the standard [`example-projects.md` §19](../items/example-projects.md#L1182) set. S5.4 lists the nine claims the full-text pass corrected and the two it withdrew; S5.3 lists what was searched for and not found |

**The constraint in Thilina's note governs S5**: LLM-as-judge, panels and reward models are the
starting point and not the answer. They appear in S5 as three entries of thirteen, on the
technique axis, and the survey's weight is on the shape axis, which is where they do not reach.

### S1. The kinds of answer a project can have

**Derived rather than listed.** An evaluation compares what one rollout produced against what the
project holds about that example. Three questions generate the whole space:

- **(a) What does the project hold?** Nothing, one value, several values, a rule, criteria in
  prose, a distribution, or a reference computation.
- **(b) What relation between the answer and that counts as right?** Identity, equivalence,
  proximity, membership, overlap, order, satisfaction, execution equivalence, or judgement.
- **(c) What is the figure over?** One rollout, one example over its k rollouts, or the whole
  evaluation.

**The library fixes all three.** (a) is one value, (b) is one boolean function of two values, and
(c) is one rollout aggregated to a mean over examples. Every kind below is a place where at least
one of the three is not what the project has. They are grouped by (a), because that is what an
`Example` would have to carry.

#### A. The project holds one value

| Id | Kind | What "right" means |
|---|---|---|
| **A1** | One value, compared exactly | The answer is that value |
| **A2** | One value under an equivalence | The answer is that value written differently: case, accent, alias, unit, format, synonym. The label is a value plus a normalisation rule |
| **A3** | One value within a tolerance | A quantity, right when close enough. The label is a value plus an absolute or relative tolerance |
| **A4** | A range on either side | The label is an interval and the answer a point, or the answer is an interval and the label a point, or both are intervals and the relation is overlap or containment |

#### B. The project holds several values and any one of them is right

| Id | Kind | What "right" means |
|---|---|---|
| **B1** | Any-of | The answer is one item, the label is the set of admissible items, and right is membership |
| **B2** | Any-of, graded | The admissible items are not worth the same. The label carries a grade per item and the score is the grade of what was answered |

#### C. The answer is itself plural

| Id | Kind | What "right" means |
|---|---|---|
| **C1** | A set | Order does not matter. Overlap against a labelled set: precision, recall, F1, exact set match, or coverage of a required subset |
| **C2** | A ranked list | Order matters. Where the wanted items landed |
| **C3** | A set with a target composition | No item is labelled. What is labelled is a property of the whole: a proportion, a spread, a floor on variety |

#### D. The answer is structured

| Id | Kind | What "right" means |
|---|---|---|
| **D1** | A record of fields | Each field is its own A, B or C, with its own absence. Right is per field, and one number is a roll-up over fields |

#### E. The project holds a rule rather than a value

| Id | Kind | What "right" means |
|---|---|---|
| **E1** | A predicate over the answer | Nothing enumerates the right answers; a check recognises one. "Under 400 pages, an author they have not read, in print" |
| **E2** | A predicate over the answer and the input | The rule needs the example, not only the answer |
| **E3** | A policy over what the run did | What is checked is not the answer but the path: which tools were called, in what order, what was asked before acting |
| **E4** | A reference computation | The label is a program, and right is producing the same effect: the same result set, the same final state, the repository's own tests passing |

#### F. The project holds criteria written in prose

| Id | Kind | What "right" means |
|---|---|---|
| **F1** | A checklist | A list of statements that must hold of the answer, each judged separately, weighted or not |
| **F2** | A rubric with named dimensions | Scores on axes rather than one number, so an answer can be accurate and badly communicated |

#### G. The project holds nothing absolute, only a comparison

| Id | Kind | What "right" means |
|---|---|---|
| **G1** | Better than a reference answer | A win rate against a named baseline. There is no label, only a pair |
| **G2** | Consistent with itself | Agreement across the agent's own rollouts, with no label at all |

#### H. The truth is not single, and that is the finding

| Id | Kind | What "right" means |
|---|---|---|
| **H1** | A distribution over answers | Annotators disagree and the disagreement is signal rather than noise. The label is the spread and the score is over the spread |
| **H2** | Correct for this end user | The label is a function of state the example holds about the person the agent is answering. **This is the fourth required output and S4 is its section** |

#### I. There is no per-example label at all

| Id | Kind | What "right" means |
|---|---|---|
| **I1** | A property of the evaluation as a whole | Calibration, coverage across the set, diversity, non-repetition, a count, a total, a ratio of two totals. Nothing about one rollout is right or wrong |

#### J. The answer is that there is no answer

| Id | Kind | What "right" means |
|---|---|---|
| **J1** | Absence | **Shipped.** `Unknown`, and the two rates that exist because of it |
| **J2** | Partial absence | Some fields answered and some genuinely absent. Not a state the whole-answer axis has |
| **J3** | Not yet answerable | The agent cannot answer until it asks. The right behaviour is a consultation and there is no answer to score yet |

**Twenty-four kinds in ten groups.** Thilina's four — sets, ranges, estimates, natural language —
are C1, A4, A3 and F. **What the note did not name and the derivation reaches**: E (a rule instead
of a value), G (no label at all), H1 (a label that is a distribution), I1 (nothing per example),
J2 and J3.

**What is one kind and what is two.** A2 and A3 look like one kind and are not: an equivalence is
a relation the project can write once for the whole set, and a tolerance is a number per field
that a schema can carry. B1 and C1 look like one kind and are not: **in B1 the label is plural and
the answer is singular, and in C1 it is the other way round.** S3.4 is the measurement that makes
that distinction load-bearing rather than pedantic.

### S2. What each needs in order to be scored

**The split the library already states holds**: the library supplies the seam, the aggregation,
the interval, the recording and the comparison discipline; the project supplies the content.
Nothing below proposes shipping a matcher or a dataset, which
[`example-projects.md` §19.7](../items/example-projects.md#L1542) measured the library refusing in two
places for a stated reason.

#### S2.1 What each kind needs, and from whom

| Kind | The label must carry | The comparison needs | The figure is over | Not there today |
|---|---|---|---|---|
| A1 | a value | two values | a rollout | — |
| A2 | a value, a normalisation | two values | a rollout | — |
| A3 | a value, a tolerance | two values | a rollout | the tolerance has nowhere to live but the closure, and a closure is not in `source_version` |
| A4 | an interval | two values | a rollout | — |
| B1 | the admissible set | two values, and which side is plural | a rollout | **the reading**: nothing says whether a list means "the answer" or "any of these" |
| B2 | the set with grades | two values | a rollout | a graded result, which `matches` cannot return |
| C1 | the labelled set | two values | a rollout | a graded result |
| C2 | relevance per item | two values | a rollout | a graded result |
| C3 | a target for the whole answer | the answer, and often the run | a rollout | a graded result |
| D1 | a value and an absence per field | two records, field by field | a rollout, rolled up | **per-field absence**; absence is whole-answer only |
| E1 | a predicate | the answer | a rollout | — |
| E2 | a predicate | the answer **and the example** | a rollout | **`matches` never sees the example** |
| E3 | a policy | the trajectory | a rollout | reachable through a `ProjectMetric`, at one file read per rollout |
| E4 | a reference computation | executing it | a rollout | **scoring becomes a side effect**: it runs something, costs something, and may need its own effect class |
| F1 | criteria, weights | a judge, per criterion | a rollout | **a model call inside scoring**, which is unpriced, unrecorded and unversioned today |
| F2 | criteria per dimension | a judge | a rollout, per dimension | more than one figure per answer |
| G1 | a baseline answer | a judge over a pair | the pair | **no label at all**, and a figure that is not a function of one rollout |
| G2 | nothing | the k rollouts of one example together | an example | **the resampling unit is the score's input**, which nothing supports |
| H1 | the annotator spread | the answer against a distribution | a rollout | a label that is not a value |
| H2 | what the end user knows | the answer, the example, the consultation | a rollout | **S4** |
| I1 | nothing | the whole results file | the evaluation | **scheduled**, `plan.md` §1 `P3-48`, as the count-or-total seam. It left §2.1 on 2026-08-27 |
| J1 | absence | absence on both sides | a rollout | — |
| J2 | absence per field | two records | a rollout | as D1 |
| J3 | that asking is required | the trajectory | a rollout | **S4** |

#### S2.2 The nine seams the table reduces to

Read down the last column and the twenty-four kinds ask for nine things.

1. **A declared reading for a plural label.** Whether a list in `expected` is the answer or the
   admissible set. Costs a field on `Example` or a second field, and it is the one seam that
   makes an existing results file mean something definite.
2. **A comparison that returns a grade.** `matches` is `bool` and `classify` is binary, so every
   kind whose answer can be partly right has no way to say "0.6 right" except through a `ProjectMetric` that the six rates then
   contradict. **S3.5 is what that costs, measured.**
3. **A comparison that sees more than two values.** E2, E3, C3 and H2 need the example or the
   rollout, and `matches(predicted, expected)` is given neither.
4. **A verdict per field.** D1 and J2. Absence is read at the whole answer, so a record with one
   absent field is an asserted value and `Unknown` never applies to part of an answer. **Two
   pieces of external design are transferable here** and both are in S5.1: the metric is declared
   **on the field in the schema** and resolved when the record is walked, which keeps the content
   in the project where the library's own position puts it; and a state resolution runs **before**
   any metric, so absence is handled once rather than in every comparison. Alignment for a list
   field has a deterministic answer as well, VAREX's Hungarian matching over normalised leaves,
   which costs nothing and does not penalise order.
5. **A figure that is not a mean over examples.** I1. **Decided 2026-08-28** at `P3-48`'s
   sitting: `compare()` shows one, and its shape is a ratio of two totals over a unit that is not
   the rollout, with the interval resampling examples and summing both sides inside each resample.
   **This seam and seam 8 are one thing**, which is what that sitting found: a win rate is this
   aggregation with the unit being a pair.
6. **A scorer that executes something.** E4. The library refuses an `irreversible` tool inside a
   rollout; a scorer that runs a reference computation is the same question arriving from the
   other side, and [`plan.md` §2.2](../plan.md#L101)'s irreversible-tool entry is where it would
   be argued.
7. **A scorer that costs a model call.** F1, F2, G1. The library already has the shape for this:
   `RunEnvelope(role="labelling")` exists so a model that decides ground truth is pinned the way
   the agent's is. Nothing routes a *scoring* call through it, so a judge today is unpriced,
   unrecorded and outside `source_version`. **A second judge wants the same seam**, added
   2026-08-17 by `P3-9`: reading which option an end user's free-text answer was defeats every
   rule over the text alone, and `ConsultTool.read_answer` runs again on replay, so a
   model-backed `match=` needs the judgement recorded beside the answer for the same reason a
   scoring judge does. The two are one design and are accepted together at
   [`plan.md` §2.1](../plan.md#L59).
8. **A label that is not a value.** H1's distribution, and G1's absent label.
9. **What the end user knows.** S4.

**Seams 1 to 4 are one item's worth of work and change what an `Example` carries.** 5 to 8 are
each their own item, and 6 and 7 move settled rules. That ordering is a survey finding rather
than a plan.

#### S2.3 The two axes stay separate, which the table shows

**A technique is not a shape.** A judge scores F1, F2, G1, and it can also be used on C1 or on
A2; a reward model scores G1 and can be used on any of them; self-consistency is G2 and needs no
label. **The column "the comparison needs" is the technique axis and the column "the label must
carry" is the shape axis, and they are independent.** A design that ships the technique gets a
judge seam and still cannot say that an example has thirty right answers.

### S3. What the library assumes today

#### S3.1 The three fixed points

| | Where | What it fixes |
|---|---|---|
| One label | [`Example`](../../src/simple_agents/evaluation/examples.py#L53), `expected: Any` | The field is untyped, so a project can put anything in it, and **nothing anywhere says what a non-scalar means** |
| One boolean | [`matches`](../../src/simple_agents/evaluation/runner.py#L261) on `EvalSuite.__init__`, `Callable[[Any, Any], bool]` | Two arguments, both values, and a `bool`. Not the example, not the rollout, not a grade |
| One rollout | [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) | Five states, decided by absence on both sides and one call to `matches` |

#### S3.2 Every site that encodes it

| Site | What it assumes |
|---|---|
| [`expects_absence`](../../src/simple_agents/evaluation/examples.py#L156) | `isinstance(expected, Unknown)`. Absence is a property of the whole label, so J2 does not exist |
| [`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) | An asserted answer that does not match is `false_confidence` **whatever it is**. There is no partially-right state |
| [`Outcome`](../../src/simple_agents/evaluation/outcomes.py#L66) | `asserted` and `succeeded` are both memberships of a two-element set |
| [`_SPECS`](../../src/simple_agents/evaluation/metrics.py#L102) | All six rates are functions of the outcome and of whether the example expects absence. **No rate can read the answer**, so no rate can be graded |
| [`Over`](../../src/simple_agents/evaluation/metrics.py#L356) | Three denominators, all defined by absence and assertion. There is no denominator defined by the shape of the answer |
| [`score_of`](../../src/simple_agents/evaluation/metrics.py#L476) | Reads absence at the whole answer under every `Over` but `ALL`, then hands `score` two asserted values. `asserted` comes from `rollout.outcome.asserted`, so a rollout the matcher scored `MISSED` is outside `Over.ASSERTED` even where the answer held a value |
| [`_scored`](../../src/simple_agents/evaluation/metrics.py#L511) | Refuses a `bool` return and names `matches`. **The split is enforced in one direction only**: a graded rule is pushed out of `matches`, and nothing pulls the resulting grade back into the rates |
| [`ProjectMetric`](../../src/simple_agents/evaluation/metrics.py#L396) | A float per rollout, a mean over examples, one interval. A figure that is not a mean has no seam |
| [`scores_by_metric`](../../src/simple_agents/evaluation/metrics.py#L617) and [`project_scores`](../../src/simple_agents/evaluation/metrics.py#L535) | Everything downstream is `{metric: {example_id: [float, ...]}}`. A comparison that is not a per-rollout float cannot travel |
| [`compare`](../../src/simple_agents/evaluation/compare.py#L440) | Pairs on the example id. Refuses two evaluations whose example sets differ, on `content_hash`, unless `allow_different_sets=True`. **The refusal is the one thing that already works for a plural label**: the hash covers `expected`, so widening an admissible set is a change the comparison declines to attribute to the agent. What it cannot express is G1, a comparison **between the two arms on one example**, since both sides carry independently computed per-rollout floats |
| [`node_matches`](../../src/simple_agents/evaluation/runner.py#L263) | The same two-value boolean, per node |
| [`_answer_of`](../../src/simple_agents/evaluation/runner.py#L1864) | One field of the output, or one function over it. One answer per rollout |
| [`contains_normalised`](../../src/simple_agents/grounding.py#L50) and [`same_url`](../../src/simple_agents/grounding.py#L71) | **The only comparison primitives in the 145 public exports**, with `normalise_text`, `urls_read` and `url_was_read` beside them. All five are identity or containment over text. Nothing ships for tolerance, overlap, order or per-field |
| [`contamination`](../../src/simple_agents/evaluation/examples.py#L536) | Compares `inputs` text and `source`. **Nothing reads the label**, so two splits sharing an answer key is invisible. S3.6 |
| [`ground_truth`](../../src/simple_agents/conformance/elicitation.py#L252) | *"For one input, what is the correct answer"*. Singular, in the question a builder is asked |
| [`answer_form`](../../src/simple_agents/conformance/elicitation.py#L263) | *"the shortest span that answers it, a full sentence, and a structured value"*. Three candidate forms, **all three of them one value** |
| FT-04, `docs/failure-taxonomy.md` §2 | The only alternative to a value is absence |
| FT-10, `docs/failure-taxonomy.md` §3 | The pair that matters is defined over a binary match |
| `docs/evaluation.md` §11.3 | *"A yes-or-no comparison belongs in `matches`"*. The graded figure is a `ProjectMetric` and the headline stays binary |

#### S3.3 The one place it is not assumed

**`Label`** ([`labels.py`](../../src/simple_agents/evaluation/labels.py#L34)) takes any verdict,
records who decided it and why, and holds no opinion about it. It is the surface that already
admits H1 and F1: a file of judgements, several per thing, each naming its decider. **It is not
connected to an evaluation.** `read_labels` returns a dict keyed by id and nothing in `EvalSuite`
reads it. That is the nearest existing thing to a seam for the criteria kinds and it should be
looked at before a new one is designed.

#### S3.4 What the dogfoods actually put in `expected`, measured

Read off the example files on disk, 2026-08-16.

| Example set | Examples | What `expected` holds | What the matcher does | Kind |
|---|---|---|---|---|
| dogfood-1 `questions.jsonl` | 59 | **30 lists** of 1 to 3 spans, 29 `unknown`, **0 single values** | `exact_match`: normalised prediction is **in** the set of golds | B1 |
| dogfood-1 run 2 `questions.jsonl` | 60 | **30 lists** of 1 to 3 spans, 30 `unknown`, 0 single values | `matches`: any gold equals the prediction | B1 |
| dogfood-2 | — | **no `ExampleSet` and no `EvalSuite` anywhere in the project** | a hand-written Wilson interval over four labelled shirts | — |
| dogfood-3 `questions.jsonl` | 26 | **24 lists of 30 titles**, 2 `unknown` | `wanted_it`: **any** pick is in the labelled set | B1 |
| dogfood-4 `questions.jsonl` | 30 | 24 strings, 6 `unknown` | `contains_expected`: the labelled title **appears in** the answer, which is a shortlist | C1, as recall-at-k |
| dogfood-4 `queue-questions.jsonl` | 73 | 71 strings, 2 `unknown`, each `shelve` or `skip` | `matches`: `predicted == expected` | **A1** |

**Four of the five example sets any dogfood built are not the shape the library ships**, and the
readings run in opposite directions through one seam. Dogfood-1 and dogfood-3 are B1: the label is
plural and the answer is one thing. Dogfood-4's discovery set is C1: the label is one thing and
the answer is plural, so the relation is membership in the **answer** rather than in the label.
Both are written as `matches(predicted, expected) -> bool` and nothing in the results file or the
manifest records which reading is in force. The brief's `answer_form` entry records the **output**
form, which for dogfood-4 is "A structured record per recommended book"; it does not say what
`expected` means or how it is compared.

**The fifth set is the one that fits, and how it came to fit is the finding.** Dogfood-4's
`queue-questions.jsonl` is a plain single value compared by equality, and it fits because the
task was reduced to a two-class verdict on one book at a time. **That set is the one
`brief.toml` certifies** (`results = "evals/results/eval_5680e78cdcfc.json"`, accuracy 0.793 over
29 held-out examples, k=3). The shortlist a reader actually sees is what
`questions.jsonl` measured, and that is the C1 set. So the project reached a clean 1:1 evaluation
by measuring something other than its product, which is `DF4-D1` arriving by a second route:
that finding says the artifact the end user sees was never what any evaluation measured, and
this says what the evaluation measured instead and why that shape was available.

**Corrected 2026-08-16, second pass.** The first pass attributed `contains_expected` to dogfood-4
as though it had one evaluation. It has two, under two scripts and two example sets, and the
certified one is the other one. The claim "not one project ever used the 1:1 mapping" was wrong
and is withdrawn.

#### S3.5 What the binary outcome costs a graded shape, measured

Dogfood-3's own results files, read today.

| Results file | Outcomes | `accuracy` | `false_confidence_rate` | The graded figures beside them |
|---|---|---|---|---|
| `held_out-k3-vllm-c956458fe71a.json`, **the file `brief.toml` certifies** | 31 `false_confidence`, 2 `failed` | **0.0** [0, 0.259] | **0.939** [0.818, 1.0] | `backlist_share` 0.696 |
| `toread-k3-vllm-rescored.json` | 32 `false_confidence`, 5 `failed`, 1 `missed`, 1 `correct` | **0.026** [0, 0.077] | **0.821** [0.692, 0.923] | `neighbourhood` 0.238, `backlist_share` 0.641 |

**A book recommender that recommended books is reported as asserting a confidently wrong value in
94% of rollouts, and that is the number on its certified evaluation.** FT-10 defines
`false_confidence` as the dangerous failure, the one that is worse than nothing because whatever
consumes it acts on it. Here it means "none of the five picks was one of the thirty titles on the
shelf", which is neither dangerous nor, on its own, informative. **The graded figure is a
`ProjectMetric` and the report puts it under six rates that contradict it.** The certified file
carries `backlist_share` alone; `neighbourhood`, the figure that measures whether the picks were
the right kind of book, exists only in the later rescored file.

This is `DF3-D1` seen from the other end. That finding says the evaluation could not detect its
own effect at a 14.6% chance rate; this says that even where the graded measurement worked, the
headline the library forces on top of it was wrong in the other direction.

#### S3.6 Two consequences nobody has written down

**A shared answer key is invisible to the contamination check.** All 24 of dogfood-3's
value-labelled examples carry **the same 30-title label**, spanning both splits. `contamination`
compares the words in `inputs` and the `source` string; the labels are read by nothing. Its 26
sources are distinct and none spans a split, so `shared_source` could not fire either, and the
project set `contamination_threshold=None` with a recorded reason. **Every mechanism FT-03 has
was either off or blind, and the thing genuinely shared across the split was the answer key.**
For B1 this is the ordinary case rather than a mistake: when the label is an admissible set, two
examples in different splits sharing that set is exactly the leak a split exists to prevent, and
nothing looks at it.

**A tolerance is versioned in one of the two ways it is written, and this finding had the halves
the wrong way round.** *Corrected 2026-08-18 at the `P3-12` sitting, by measuring it.* It read *"A
tolerance is not versioned"*, resting on `docs/evaluation.md` §11.6's sentence that a threshold
the function closes over is not in the hash.
[`source_version`](../../src/simple_agents/records/manifest.py#L605) hashes the source **and what the
function closed over**, so a tolerance a factory captured moves the version; a constant the
function reads from module level does not, and neither does what a file it opens holds. Measured:
two closures over 0.02 and 0.05 version apart, and a module constant rebound from 0.02 to 0.05
versions identically.

**Where §11.6's sentence came from**, since it was true of a real function: `tools.py`'s
[`derived_version`](../../src/simple_agents/tools.py#L1054) hashes source alone and covers no
closure, which `docs/tools.md` §3.1 states correctly. That true sentence was written beside the
other function in three shipped places, all corrected 2026-08-18.

**What survives for A3.** The reason a tolerance belongs in the answer key rather than in
`matches` is not versioning. It is that a tolerance in the key travels into the example file and
into `content_hash`, so the set says what close enough means and a reader does not have to open
the code. The unversioned case is narrower than this finding claimed: a project whose tolerance is
a module constant widens it from 2% to 5%, every number moves, and `compare()` reports the move as
a change in the agent with a verdict attached.

### S4. What an example carries about its end user

**The fourth required output, added at the P3-9 sitting.** S1 files it as H2 and J3, and this is
what the survey adds to what [`end-user-in-an-evaluation-build-log.md`](../build-logs/end-user-in-an-evaluation-build-log.md#L1)
already measured.

#### S4.1 The two are one problem, and the survey settles which way round

P3-9's decision 2 asks whether what the end user knows is separate from `expected` or part of it.
**The survey's answer is that it is a third thing, and both kinds in S1 say why.**

- **H2 makes the label a function.** "File this invoice against the right cost centre" has one
  right answer per end user, and the example holds the state that determines it. If the state
  goes into `expected`, then `expected` is holding two things: the answer, and the input the
  agent has to obtain to reach it. That is the B1/C1 ambiguity again in a worse place, because
  here the two are different **types**, not two readings of one list.
- **J3 makes some examples have no answer to score yet.** An agent that should have asked and
  answered instead is wrong even when its answer happens to be right, and an agent that asked
  when the value was already in `inputs` wasted a turn. Neither is a comparison between two
  values, so neither reaches `matches` at all.

#### S4.2 What the external work supplies here, and it is the strongest finding in S5

**τ-Rec's reveal-tagged elicitation is the mechanism this needs**, and it is already checked
against the paper. Each constraint on a task is tagged, and the tag says **when the end user
says it**:

| Tag | The paper's definition, verbatim |
|---|---|
| `volunteer` | "the user states it proactively in the opening turn" |
| `on_ask` | "the user states it only when explicitly asked about that attribute" |
| `hidden` | "the user never states it explicitly but rejects recommendations that violate it" |

**The tag is on a constraint, not on the end user.** A task carries typed constraints and each
one is tagged independently; the task-level label is derived by presence, so a task with any
`hidden` constraint is a hidden task and one with any `on_ask` and no `hidden` is **mixed**. That
is the shape this needs: the thing tagged is a single fact, and it separates the three things
P3-9's assumption 1 has tangled — what is in `inputs`, what the stand-in supplies when asked, and
what the stand-in only ever enforces.

**The three tags are three different mechanisms, and this is the part that changes a design.**
`volunteer` is a first-turn dump and `on_ask` is a question-and-answer gate. **`hidden` is not
reachable by asking at all**: it is observable only when the agent proposes something that
violates it and is refused. An evaluation that models the end user as facts retrievable by the
right question cannot express `hidden`, and it needs a rejection channel rather than an answer
channel. That is the assumption behind P3-9's decision 5 and it is not one the current stand-in
could satisfy by any prompt.

**What the paper measures.** Table 3 stratifies pass^1 by reveal difficulty. The column for
DeepSeek V4 Flash without thinking: **0.846 on 13 volunteer tasks, 0.586 on 32 mixed tasks, 0.200
on 15 hidden tasks**, which the paper calls "a 4× gap purely from how information is revealed",
volunteer against hidden. One configuration of nine, over six base models. An evaluation that
does not distinguish the three is measuring a mixture whose composition it does not record.

**Two things about it that a design must not copy uncritically**, both found by reading the
implementation rather than the paper.

- **The scoring is deterministic and the episode is not.** "Zero LLM calls" and "fully
  deterministic and reproducible" are claims about the scoring function, which evaluates typed
  predicates against a 153-title catalogue. **The user is GPT-5 mini at temperature 1.0**, and
  every constraint including the hidden ones is placed in that model's system prompt, with an
  instruction never to state them. **The information barrier is advisory.** A hidden fact leaks
  at whatever rate the simulator disobeys, and nothing measures that rate. A library wanting a
  real guarantee has to hold the hidden facts outside the stand-in's context and expose them only
  through an accept-or-reject oracle, which τ-Rec does not do.
- **The reward is binary despite reading graded.** The paper gives `constraint_score ×
  policy_score`, "both in [0, 1]". In `evaluator/constraint.py` and `evaluator/policy.py` each is
  `1.0` or `0.0`, so the product is too. The per-constraint and violation lists exist to attribute
  a failure, never to soften it. The same holds for τ-bench, whose reward is `r_action × r_output
  ∈ {0, 1}`. **Neither benchmark is a precedent for partial credit on partially elicited
  knowledge**; both deliberately multiply gates so any single miss zeroes the episode.

**Two smaller things worth carrying.** τ-Rec reserves 5 of its 60 tasks where nothing in the
catalogue satisfies the constraints, and inverts scoring there: abstaining scores 1.0 and
recommending anything scores 0.0. That is J1 made a first-class outcome in an elicitation setting,
and its absence is what would reward an agent that asks forever. And the paper's own limitation is
a warning about our `MINIMUM_EXAMPLES_FOR_A_VERDICT`: at 4 trials over 60 tasks the 95% intervals
on pass^4 are ±0.10 to ±0.13 and the whole top tier overlaps. **Stratifying by what the end user
disclosed multiplies the cells**, and the hidden cell here holds 15 tasks.

#### S4.3 What this does not settle

P3-9's decisions 3, 4, 5, 7 and 8 are untouched by the survey: more than one answerer, whether
the other end is a person at all, whether the stand-in sees the conversation, the reply shapes,
and the prompt seam. **The survey narrows decisions 1 and 2 and leaves the rest where P3-9 has
them.** It does not change P3-9's ordering: an `Example` still moves under it.

**P3-9 shipped 2026-08-17 and took S4's shape**, with one departure worth reading before this
section is used again: `hidden` is not a tag on a fact the model is told to withhold, as τ-Rec
has it, but a fact the model is never given, read by the answer key instead. That is the
guarantee S4.2 says τ-Rec does not have.
[`build-logs/end-user-in-an-evaluation-build-log.md`](../build-logs/end-user-in-an-evaluation-build-log.md#L1) §2.1.

### S5. What external work exists

**The standard is [`example-projects.md` §19](../items/example-projects.md#L1182)'s**: fetched and read,
n and date named, and a claim that could not be verified marked as such.

**Read twice.** The first pass, 2026-08-16, read abstracts and landing pages and left six figures
marked unverified. The second pass the same day read **sixteen sources in full**, including four
implementations, and it **corrected nine claims and withdrew two**. What that pass cost is the
argument for the standard: three of the corrections were in sentences the first pass had marked
as confirmed. S5.4 lists every one.

#### S5.1 By kind

| Kind | Source, read in full | What it supplies, and what it does not |
|---|---|---|
| A2, B1 | **AmbigQA**, Min et al., arXiv:2004.10645, EMNLP 2020. 14,042 annotated examples over all three splits of NQ-open | The premise. *"Over half of the questions in NQ-OPEN are ambiguous"*, and the paper gives no single figure: per split it is 47% train, 51% dev, 56% test, so **across the whole set it is about 49%**. Scoring is an F1 over question-answer **pairs**, in three instantiations. **2.1 distinct answers per question is the average over all questions, not over the ambiguous ones**, and no ambiguous-only figure is reported |
| A2, B1 | **Answer equivalence**, Si, Zhao & Boyd-Graber, arXiv:2109.05289, EMNLP 2021 | Aliases mined from Freebase's `common.topic.alias` as additional gold answers. Expansion raises exact match by **+4.8 on TriviaQA, +1.5 on NQ, +0.7 on SQuAD**, tracking how often an answer has a KB alias at all (88%, 72%, 32%). Human validation of the expansion: **96%, 94% and 100% valid** on the test answers it flips |
| B1 | **TriviaQA's evaluation code**, `metric_max_over_ground_truths` | The pattern in its plainest form: score against every gold and take the maximum. Its normalisation **replaces punctuation with a space rather than deleting it**, so `well-known` becomes `well known`, and it strips `a`, `an`, `the`. Read as code |
| A3, D1, J2 | **ExtractBench**, Ferguson et al., arXiv:2602.12247, Feb 2026. Paper CC BY 4.0, **artifact MIT**. 35 PDFs over 5 schemas, 441 keys, **12,867 gold leaf values** | **The design worth the most here**: *"the evaluation framework treats the schema as an executable specification: each field declares its scoring metric"*, resolved from the JSON Schema node at traversal time. Twelve presets ship, including `number_tolerance`, `string_fuzzy` and `string_semantic` |
| D1 | **VAREX**, arXiv:2603.15118, Mar 2026. Paper CC BY 4.0, code Apache 2.0. 1,777 documents, 1,771 schemas, 21,084 fields | The deterministic counterpart: normalised exact match as the headline with ANLS beside it for partial credit, **zero model calls**, and **order-invariant array alignment by the Hungarian algorithm**. Its normalisation is deliberately shallow and the cases it does not cover are documented as characteristics |
| C1, C2 | **BEIR**, Thakur et al., arXiv:2104.08663, NeurIPS 2021. 18 datasets | Graded relevance per item rather than one right answer, and the argument for the metric: precision and recall are rank-unaware, MRR and MAP *"fail to evaluate tasks with graded relevance judgements"*, so it standardises on **nDCG@10**. Relevance is **binary in 12 of 18 datasets, three-level in 5, five-level in 1** |
| E1, E2 | **IFEval**, Zhou et al., arXiv:2311.07911, Nov 2023. 25 verifiable instruction types, **541 prompts** | The cleanest statement of E1: satisfaction checked by code. Worth more than the count is that it reports **four numbers, not one** — prompt-level and instruction-level, each strict and loose — where loose accepts any of eight text transformations, and the paper says so: *"it is likely to introduce false positives"* |
| E1, E2, H2 | **τ-Rec**, Narasimhan & Narasimhan, arXiv:2606.10156, RecSys 2026 Resource Track. Code MIT, **data CC BY 4.0**. 60 tasks, 153-title catalogue, movies only | S4.2, which is where the detail is. Reveal-tagged elicitation, typed predicates, deterministic scoring. **The user simulator is GPT-5 mini at temperature 1.0 and holds every hidden constraint in its system prompt**, so the reveal barrier is a prompt instruction and its leak rate is unmeasured |
| E3, E4 | **τ-bench**, Yao et al., arXiv:2406.12045, Jun 2024. 165 tasks over two domains, code MIT | Reward is **`r = r_action × r_output ∈ {0,1}`**: the final database against a unique goal state, **and** whether required values appear as substrings in what the agent said. Not the database alone. `pass^k` is *"the chance that all k i.i.d. task trials are successful, averaged across tasks"*. gpt-4o is **61.2 retail, 35.2 airline, 48.2 averaged**, and `pass^8` under 25% in retail |
| F1 | **HealthBench**, Arora et al., arXiv:2505.08775, May 2025. Code MIT. **5,000 conversations, mean 2.6 turns and a median of 1**, 262 physicians, 48,562 unique criteria over 57,237 instances | The largest instance of "the label is a list of statements". Each criterion is **binary and all-or-nothing**, carrying a signed weight from −10 to 10, and the score is `Σ met·p / Σ max(0,p)`, so **a per-example score can be negative** and only the mean is clipped. GPT-4.1 grades it at macro-F1 0.709 against a **physician-to-physician range of 0.569 to 0.730** |
| F1 | **InFoBench**, Qin et al., arXiv:2401.03601, Jan 2024. 500 instructions, 2,250 decomposed questions | DRFR, an **unweighted** `Σr / Σm` over binary criteria, which is the other half of the weighting fork HealthBench takes. **Its strongest result is about people, not models**: decomposing the question raised inter-annotator kappa from **0.284 to 0.532** on the same responses. GPT-4 as annotator reaches 89% against an expert label, over the 50 of 500 instructions that were annotated at all |
| H1 | **SemEval-2023 Task 11, LeWiDi**, Leonardelli et al., ACL Anthology 2023.semeval-1.314. **Four** datasets | The label as a distribution: a soft label is *"the proportion of annotations in favour of one or the other label"*, with no aggregation step. **Micro-F1 for the hard label and cross-entropy for the soft one, and the soft one is primary** because *"the existence of a 'truth' cannot be assumed"*. Two constraints it documents: soft values are **quantised by annotator count**, and cross-entropy *"is not directly comparable across different datasets"* |
| J1 | **AbstentionBench**, Kirichenko et al., arXiv:2506.09038, Jun 2025. 20 datasets, 20 models. Paper CC BY 4.0, **code and data CC BY-NC 4.0** | Abstention as its own measurement over **six** scenarios: answer unknown, false premise, stale, subjective, underspecified context, underspecified intent. Scaling does not help, and reasoning fine-tuning costs **24 percentage points** of abstention recall, averaged over two model pairs. Judged by Llama 3.1 8B at 88% accuracy against a 300-pair human set |

#### S5.2 The technique axis, which is where Thilina's three starting points sit

| Technique | Source, read in full | What it is worth here |
|---|---|---|
| Panels of judges | **PoLL**, Verga et al., arXiv:2404.18796, Apr 2024. Three judges: Command R 35B, Claude 3 Haiku, GPT-3.5 | A panel from disjoint families beats one large judge with less intra-model bias, at **seven to eight times less cost** than GPT-4 Turbo, over six settings of five datasets. **It is not best everywhere**: Haiku alone beats it on HotpotQA single-hop and on Bamboogle, Command R on multi-hop. Its own limitation is that one hand-picked panel was tested |
| Judge bias | **Self-preference bias**, Wataoka et al., arXiv:2410.21819 | A metric for the bias, and the claim that it tracks perplexity rather than authorship. **GPT-4 has the largest measured bias at 0.520 and is excluded from the perplexity analysis** that explains it, because its perplexities could not be obtained |
| Judge bias | **MT-Bench**, Zheng et al., arXiv:2306.05685 | Position bias measured: Claude-v1 favours the first position in **75.0%** of swapped pairs, GPT-3.5 in 50%, GPT-4 in 30%, and renaming the assistants moves Claude-v1 from 23.8% to 56.2% consistent. Verbosity bias: a repetitive-list attack fools Claude-v1 and GPT-3.5 91.3% of the time and GPT-4 8.7%. **It does not establish self-enhancement bias**, and says so: *"our study cannot determine whether the models exhibit a self-enhancement bias"* |
| Reward models | **RewardBench**, Lambert et al., arXiv:2403.13787, Mar 2024. **Five** sections, about 2,985 core prompts | G1's shape scored as a binary classification: a win when the chosen completion outscores the rejected one. **A v1 score and a v2 score are not comparable**, since v2 reweights the sections |

**Four of seventeen entries are on the technique axis, and every one of them is scored on a shape
that already exists on the other axis.** That is the note's constraint holding: a survey that
returned judges, panels and reward models would have returned S5.2 and none of S5.1.

#### S5.3 What was searched for and not found

- **No taxonomy of answer shapes exists.** The same result [`example-projects.md`
  §19.6](../items/example-projects.md#L1481) reached for task shapes: classifications are by occupation,
  business function, audience, interface or architecture, and nobody publishes one by what the
  answer looks like. **S1's derivation is ours and has no external convergence behind it.**
- **Nothing was found for I1** beyond calibration, which is its own literature and was not
  surveyed here.
- **Nothing was found for C3**, a set with a target composition, outside recommender-system
  diversity metrics, which were not surveyed.
- **Nothing was found for partial credit on partially elicited knowledge.** τ-Rec and τ-bench
  both multiply gates so that any single miss zeroes the episode, and neither reports a graded
  variant.

#### S5.4 What the second pass corrected, and two claims it withdrew

Recorded rather than quietly fixed, because the pattern is the finding: **an abstract states the
design and the implementation states what shipped, and where they disagree the implementation is
what a benchmark's numbers were computed by.**

| Claim in the first pass | What the full text says |
|---|---|
| ExtractBench "explicitly distinguishes omission from hallucination", read as FT-10 per field | **Withdrawn as stated.** The paper does distinguish them, and the shipped code scores both `0.0`: the difference survives only as a `reason` label, no breakdown is reported, and the paper's three states (present, null, MISSING) are collapsed to two by `apply_missing_null_policy` |
| ExtractBench: exact for identifiers, tolerance for quantities, semantic for names | An illustration in the abstract rather than the metric list. **Twelve presets ship** against eight in the paper's own table and nine in its appendix, and the paper itself assigns `string_semantic` to free text and `string_fuzzy` to entity names, contradicting the illustration |
| ExtractBench scores deterministically | **Wrong, and it is the cost warning.** Defaults are `string_semantic` for every string field and `array_llm` for every array, each an LLM call, judged by Gemini 2.5 Flash at a 0.7 threshold. Scoring is itself nondeterministic and would need its own replay story |
| DocILE supplies per-field extraction scoring | **Withdrawn.** Its primary metric never compares two values: it is object detection, scored by average precision over bounding boxes under a character-centre containment rule, with value read-out in a separate secondary evaluation. What it supplies is the negative result |
| Answer equivalence measures how often exact match is wrong | **Not the paper's measurement.** The "nearly a third" figure it carries is quoted from the EfficientQA competition, and the paper states outright that *"there is neither a clear measurement of its magnitude nor a consistent best practice solution"* |
| τ-bench compares the final database state | Half of it. The reward is `r_action × r_output`, and `r_output` is a substring check over what the agent said to the user |
| τ-bench: agents under 50% | Domain-averaged, and the caption warns the average is weighted by domain. gpt-4o is **61.2 in retail** |
| AbstentionBench has five scenario categories | **Six.** The five-item list comes from the paper's own Table 3 key, which omits `Subjective` and overloads `S` |
| AbstentionBench: 24% | 24 **percentage points**, over two model pairs. The relative figure would be about 35% |
| IFEval: about 500 prompts | **541.** The abstract rounds |
| PoLL: six datasets | Six settings of **five** datasets; HotpotQA is counted twice |
| RewardBench: four categories | **Five.** `Prior Sets` is a real fifth section |
| HealthBench: 5,000 multi-turn conversations | The count is right and the descriptor is not: mean 2.6 turns, **median 1** |
| LeWiDi | Four datasets, and its own account of the 2021 edition as six datasets is wrong: that edition had five, scored by class-weighted F1 rather than micro-F1 |

### S6. Corrections this survey makes to records already written

**Applied here. Two need Thilina's approval before they are applied where they belong.**

1. **This file's own evidence bullet**, that dogfood #1 is the exception with a single right
   answer. **Corrected above**, in place, with the measurement in S3.4.
2. **This survey's own first pass**, which attributed one matcher to dogfood #4 and drew a
   headline from it. **Corrected in S3.4**, with what was withdrawn stated there.
3. **[`example-projects.md` §19.6](../items/example-projects.md#L1481) mis-states τ-Rec's numbers.** It
   reads *"performance falls 84.6% → 58.6% → 20% across the three [tags]"*. Table 3's rows are
   **volunteer, mixed and hidden**, not `volunteer`, `on_ask`, `hidden`, at 13, 32 and 15 tasks,
   and the strata are **presence-based**, so a mixed task still carries volunteer constraints.
   The three figures are **one column of nine**, DeepSeek V4 Flash with no thinking, rather than
   a general result. The finding survives and the framing of it does not.
4. **[`example-projects.md` §19.6](../items/example-projects.md#L1481) also lists DocILE as scoring
   extraction "per-field, with the field's declared type choosing the rule and absence carried as
   `null`".** That is ExtractBench's design and not DocILE's: DocILE's primary metric is average
   precision over bounding boxes and never compares two values, with value read-out in a separate
   secondary benchmark. The row's verdict, that the contract alone gives the matcher, does not
   rest on DocILE.
5. **Not applied**: items 3 and 4 are in another item's record and `CLAUDE.md` requires approval
   before editing `dev-docs/`.
6. **No correction was needed to `docs/`.** Everything S3 names is accurately described in
   `docs/evaluation.md`; the assumption is in the design, not in the prose about it.

## What has to be decided

The sitting's agenda, each carrying what the survey found for it. The roadmap below stages them;
this says what each one is.

**All eight are settled.** 1, 2 and 3 on 2026-08-17 at the first sitting, and "What was decided,
2026-08-17" below is the record of it. 4, 7 and 8 the same day at the second, recorded under
"What was decided at the second sitting". 5 is stage 4 and was settled by being scheduled as its
own item rather than by being designed here. 6 is P3-9's.

1. **What an `Example` carries when there is more than one right answer.** A declared reading on
   a plural label, a second field, or a typed label object. Seam 1, and it is what makes four
   existing example sets mean something definite. **Evidence**: S3.4, and AmbigQA measuring about
   half of an ordinary QA benchmark as having more than one right answer.
2. **Whether a comparison may return a grade**, and if so what the six rates do with it. Today
   an imperfect answer is `false_confidence`, which S3.5 measures as reporting a working
   recommender as confidently wrong on 94% of rollouts of its certified evaluation. Options: a
   threshold, a third outcome, or leaving the rates binary and changing what the report leads
   with. **Evidence cuts both ways.** τ-Rec and τ-bench both keep the reward binary on purpose
   and multiply gates. InFoBench says the fix for an unstable single judgement is **decomposing
   the question rather than widening the scale**, and measures it: inter-annotator kappa 0.284 on
   a graded score against 0.532 on decomposed binary criteria, over the same responses. That is
   an argument for F1 over a graded `matches`.
3. **What `matches` is given.** Adding the example is a signature change; adding the rollout too
   makes it the same shape as `ProjectMetric.score`. Four kinds need it and E2 cannot be written
   without it.
4. **Settled 2026-08-17 at the second sitting, and built the same day**, as stage 3. It asked
   whether absence is per field. D1 was already closed by P3-10, so what was left was J2, and
   what shipped is a criterion's check returning `Unknown` for a condition the answer said
   nothing about, an answer whose unmet conditions are all of that kind sorting as `missed`
   rather than `false_confidence`, and `Criterion(expects_absence=True)` putting the key's side
   of absence on the condition. `Over` stays whole-answer; **FT-04 does not**, and reads the
   declaration. **ExtractBench's warning was the test the design had to pass**: it names
   omission and hallucination as different errors and scores both `0.0`, so the distinction
   survives as a label and no breakdown is reported. Here the outcome differs, the rate differs,
   and `results.criteria[id].absent` is the breakdown.
   [`build-logs/per-field-absence-build-log.md`](../build-logs/per-field-absence-build-log.md#L1).
5. **Whether a scoring rule may cost a model call.** F1, F2 and G1 need it and nothing supports
   it. **The evidence is unusually complete here.** ExtractBench's defaults make every string
   field and every array an LLM call, so scoring is itself nondeterministic and needs a replay
   story. HealthBench shows what a defensible judge looks like: measured against experts, and
   reported as a **percentile of the human spread** rather than against an implied ceiling, since
   physician-to-physician macro-F1 is itself 0.569 to 0.730. PoLL shows a panel of three small
   judges at a seventh of the cost of one large one. MT-Bench measures the biases. **If it lands,
   it goes through the envelope with `role="labelling"`, is priced, replays from the cassette,
   and joins `source_version`** — the library already has every one of those and routes no
   scoring call through them.
6. **Settled 2026-08-17 by `P3-9`, and not by this item.** It asked what an example carries
   about its end user, which is P3-9's decisions 1 and 2 with S4's narrowing: state plus a
   reveal rule, rather than persona prose or a second label. What shipped is `EndUser` with a
   `Fact` per thing that person knows, each carrying `disclose`. **The correction this entry
   asked for was taken**: the reveal barrier is structural rather than a prompt instruction,
   because a `hidden` fact is never given to the model and is read by the answer key instead.
   [`build-logs/end-user-in-an-evaluation-build-log.md`](../build-logs/end-user-in-an-evaluation-build-log.md#L1)
   §2.1.
7. **Settled 2026-08-17 at the second sitting: `Label` is the seam, and the join is designed
   once with the judge**, which is `P3-12`. It asked whether `Label` is the seam for criteria or
   whether a new one is designed beside it. **The route was run rather than reasoned about**,
   and it works today with no library change: a criterion check reading `read_labels(path)[key]`
   scores identically on a live run and on `rescore`, and a report prints the judged condition
   beside the coded one. Four edges decided against documenting it as it stands, two of them
   silent. They are `P3-12`'s to close and are in its record.
   LeWiDi stays the case for keeping raw judgements rather than a collapsed label, which
   `read_labels` does not: on items where annotators agreed only 40 to 60%, a hard label is
   wrong 46% of the time.
8. **Settled 2026-08-17 at the second sitting.** It asked what of this is v0.1 at all. Fifteen
   of the twenty-four kinds are shipped or expressible, J2 shipped as stage 3, two are `P3-12`'s,
   two are parked with a stated reason, and the remaining six are one deferred entry naming what
   would decide each. "Where every kind stands" below is the table, and it is what closes the
   survey rather than the enumeration.

**One word, from 2026-08-17 at the P3-10 build.** This record said *requirements* in decision 2
and `Criteria([Criterion(...)])` in option 2D, and used both within three sentences under "What the
build has to solve". The shipped names are `Criteria` and `Criterion`, and this record now uses
them throughout. The count that decided it: `criteri*` appears nowhere in `src/` or `docs/`, and
`requirement` appears ten times, every one of them meaning a rule the library enforces on the
builder.

## The options, with shapes

**Written 2026-08-16 so the sitting is a choice rather than a design from cold**, covering
decisions 1, 2 and 3, which is what "How the four group into sittings" below puts in one sitting.
Every option is a concrete diff against a site S3.2 already named. **None is recommended by being
listed**, and each carries what it costs.

### Decision 1 — what an `Example` carries when there is more than one right answer

**The site.** [`Example`](../../src/simple_agents/evaluation/examples.py#L53) holds
`expected: Any`, untyped, and nothing says what a non-scalar means. S3.4 measured two readings in
use and nothing recording which: **B1**, the label is plural and the answer is one thing, and
**C1**, the label is one thing and the answer is plural.

**1A. A declared reading beside the value.**

    Example(id="q1", inputs={"question": "Which retailer ships from Leeds?"},
            expected=["Kirkwall", "Kirkwall Retail Ltd"],
            expected_is=Admissible.ANY_OF, split="dev")

*For:* the smallest diff of the four. One field on `Example`, carried through `to_json` and
`from_json`, so `content_hash` covers it and a results file records the reading. `classify`,
`matches` and the six rates are untouched.
*Against:* the reading sits beside the value rather than in it, so nothing prevents
`expected="Kirkwall"` with `ANY_OF`, and the check for that is a new refusal. It needs a second
member for C1, and a third for A3, so the enum grows once per kind.

**1B. A second field, `expected` staying canonical.**

    Example(id="q1", inputs={...}, expected="Kirkwall",
            also_correct=["Kirkwall Retail Ltd", "Kirkwall Ltd"], split="dev")

*For:* **every existing surface keeps working unchanged**, because `expected` still means one
value: `expects_absence`, `Over`, `score_of` and every project metric that compares against it.
Every example set on disk stays valid. It is what TriviaQA's own evaluation does, with
`NormalizedAliases` beside the answer and a maximum taken over all of them.
*Against:* it cannot express a label with no canonical member. Dogfood #3's thirty-title shelf has
no primary and picking one is an invention. Nothing for C1.

**1C. A typed label.**

    Example(id="q1", inputs={...}, expected=AnyOf(["Kirkwall", "Kirkwall Retail Ltd"]))
    Example(id="q4", inputs={...}, expected=Contains("The Left Hand of Darkness"))
    Example(id="s7", inputs={...}, expected=WithinTolerance(52.0, relative=0.02))

*For:* the reading travels **with** the value, so a mismatch between them cannot be written. It is
the only option covering both measured readings and it extends to A3, A4 and later F1 without a
new field each time. **The library already has this shape**: `Unknown` is a tagged object in the
label position, encoded by `encode_answer` and read back by `decode_answer`, and this is the same
move for the other kinds.
*Against:* the largest diff. `encode_answer` and `decode_answer` gain a case per type;
[`expects_absence`](../../src/simple_agents/evaluation/examples.py#L156) and
[`score_of`](../../src/simple_agents/evaluation/metrics.py#L476) read the label and must see
through the wrapper; and every project metric doing `token_f1(predicted, expected)` breaks unless
the wrapper exposes its values. **It also invites a shipped matcher**, which the library refuses
on a stated argument, so it needs a rule at the front: *a label type says what the label is and
never how to compare it.*

**1D. Change nothing and write the convention down.** Say in `docs/evaluation.md` that a
non-scalar `expected` means whatever `matches` says, and make the brief record which.

*For:* no code, no format move.
*Against:* it is what happens today, and S3.4 is the measurement of the result.

**What would decide it.** 1B if backward compatibility is the binding constraint; 1C if more than
one further kind is ever going to land, because 1A and 1B both grow a field per kind and 1C does
not. **1C is the one that does not have to be redone under stage 3.**

### Decision 2 — whether a comparison may return a grade

**The site.** [`matches`](../../src/simple_agents/evaluation/runner.py#L261) returns `bool`,
[`classify`](../../src/simple_agents/evaluation/outcomes.py#L170) sorts on it, and
[`_scored`](../../src/simple_agents/evaluation/metrics.py#L511) refuses a `bool` from a metric,
so the split is enforced one way only. S3.5 is what that costs: `false_confidence_rate` **0.939**
on dogfood #3's certified evaluation.

**2A. Keep it binary; change what the report leads with.** A project declaring metrics gets them
printed above the six rates.

*For:* no format moves, no rule moves, one afternoon.
*Against:* the number is not misplaced, it is wrong. FT-10 defines `false_confidence` as asserting
a wrong value, and "none of five picks was on a thirty-book shelf" is not that.

**2B. `matches` may return a float, with a declared threshold.**

    EvalSuite(pipeline, examples, answer="answer",
              matches=lambda predicted, expected: overlap(predicted, expected),
              correct_at=0.6)

*For:* one keyword. The six rates keep their definitions, and the grade is available to a project
metric without the rule being written twice.
*Against:* `correct_at` is a task decision compressed into one number that the report does not
show, and it makes `accuracy` a function of a knob a reader cannot see. **It is S3.6's tolerance
problem in a new place**: a threshold passed as an argument is not in `source_version`, so moving
it moves every rate with nothing recording that the rule changed.

**2C. A third outcome.** `Outcome.PARTIAL`, for an answer that is neither right nor a confident
wrong value.

*For:* the honest shape. It says what actually happened rather than rounding it to one of two.
*Against:* the largest blast radius of anything in this item. `Outcome`, `asserted`, `succeeded`,
`measured`, all six entries of [`_SPECS`](../../src/simple_agents/evaluation/metrics.py#L102),
FT-10's stated definition, the results format, and `compare()`. It also reopens what
`precision_when_asserting` is over. **FT-10's argument is that two failure modes must not be
averaged; a third bucket needs its own argument and does not inherit that one.**

**2D. Decomposition: the label is criteria, each judged binary.**

    Example(id="q4", inputs={...}, split="held_out", expected=Criteria([
        Criterion("a book the reader has not already read"),
        Criterion("under 400 pages"),
        Criterion("shares a subject with the to-read shelf", weight=2),
    ]))

*For:* **the only option with a measurement behind it.** InFoBench reports inter-annotator kappa
of 0.284 on a graded score against 0.532 on decomposed binary criteria over the same responses,
which is the argument that an unstable judgement is fixed by decomposing the question rather than
by widening the scale. Every atomic judgement stays binary, so `matches` keeps its type and
`classify` keeps its five outcomes. **It subsumes stage 3**, since a per-field verdict is a
criteria list over a record. HealthBench and InFoBench are both this at scale.
*Against:* it changes what a label is, which is decision 1's territory, and that is why the two
are one sitting. Somebody writes the criteria per example. And it carries a fork of its own:
**InFoBench weights every criterion equally** (`Σr / Σm`), **HealthBench signs them** from −10 to
10 with the denominator `Σ max(0, p)`, which lets a criterion penalise and lets a per-example
score go negative, clipped only at the mean.

**What would decide it.** Whether the project's answer decomposes. Dogfood #3's does — "not
already read", "under 400 pages", "right kind of book" are three criteria it scored as one
number. Dogfood #1's does not: a span either is one of the gold spans or it is not.

### Decision 3 — what `matches` is given

**The site.** `matches: Callable[[Any, Any], bool]`. Not the example, not the rollout. E2, E3, C3
and H2 all need more, and E2 cannot be written at all.

**3A. Leave it.** Projects close over module-level state, which is what dogfood #4's
`_load_labels()` already does, reading a file from inside the metric on every call.

**3B. Add the example.**

    def matches(predicted, expected, example):
        return predicted.cost_centre == example.metadata["cost_centre"]

*For:* makes E2 and H2 writable, and `Example` already carries `inputs`, `metadata`, `memory` and
`end_user`, so nothing new has to be recorded to make it useful.
*Against:* it breaks every existing matcher unless the arity is inspected.

**3C. The same shape as `ProjectMetric.score`.**

    def matches(predicted, expected, rollout):
        return predicted.source in retrieved_in(rollout.trajectory)

*For:* one shape for both scoring seams, which is one fewer thing to learn, and it makes E3
writable in `matches` rather than only in a metric.
*Against:* `rollout` does not carry the example, so E2 still needs a lookup; and reading a
trajectory inside `matches` costs n×k file reads on the path every rate depends on.

**3D. Both, resolved by arity.** The library inspects the signature and passes what the function
takes, so a two-argument matcher keeps working unchanged.

*For:* no break, and both 3B and 3C become available.
*Against:* a signature that silently decides what a callable receives is a thing to document
carefully, and a typo in a parameter name becomes a different call rather than an error.
**Precedent exists**: [`_schema_from_signature`](../../src/simple_agents/tools.py#L1179) already
builds a tool's argument schema by inspecting one.

**What would decide it.** Whether the break is acceptable. 3D costs nothing to any project on
disk; 3B and 3C each cost every matcher in every dogfood a rewrite.

## What was decided, 2026-08-17

**The sitting settled decisions 1, 2 and 3, and did not touch 4 to 8.** It produced four
decisions rather than three, because decision 2 was two questions written as one.

| Decided | Rejected, and why |
|---|---|
| **1. A typed answer key.** `AnyOf([...])`, `Contains(...)`, `WithinTolerance(...)` and `Criteria([...])` sit in the `expected` position and are encoded the way [`Unknown`](../../src/simple_agents/schema.py#L41) already is. Option **1C** | **1A**, an enum naming the reading, closes the measured ambiguity for a fraction of the cost, and a name cannot carry contents. The slot now has to hold a tolerance and a list of criteria, and only a type holds those. **1B** cannot express a label with no canonical member. **1D** is what runs today |
| **2. Criteria are a legal answer key.** A list of conditions, each judged yes or no. Option **2D**, on the label axis | A sliding scale (**2B**) puts the burden on a single graded judgement, which InFoBench measured as roughly half as reproducible as decomposed binary criteria over the same responses |
| **3. A partly-right answer gets its own outcome**, rather than being rounded into `correct` or `false_confidence` | All-or-nothing and a declared pass mark both record "met 2 of 3" and "met none" in one bucket. FT-10 separates outcomes so a dangerous failure is not hidden behind a harmless one; rounding a partial into either bucket is that same averaging one level down. **The record's own position was that a third bucket does not inherit FT-10's argument. The sitting found that it does** |
| **4. One context object for every scoring seam**, carrying the answer, the answer key, the example and the rollout. Neither 3A, 3B, 3C nor 3D | Three shapes collapse to one, and nothing is revisited when a fifth field is needed. It costs [`ProjectMetric.score`](../../src/simple_agents/evaluation/metrics.py#L428) its signature as well, which is a larger diff than any option the record listed |

**The rule stated at the front of decision 1, and it is what keeps 1C from becoming a matcher
library**: *a type says what the right answer is, never how to compare it.* `AnyOf` declares that
the label stands for a set of admissible values and `Contains` that the answer is a collection;
neither says what equality means. The project still writes the comparison.

**Three corrections the sitting made to how the options were written.**

1. **Decision 2's four options are not on one axis.** 2D changes what a label is, 2C changes the
   outcome vocabulary, 2A changes the report, and only 2B does both. The reason the record gives
   for putting decisions 1 and 2 in one sitting reaches the label half and nothing else, so the
   two halves were taken separately and both were settled.
2. **Decision 3's options were obsoleted by decisions 1 and 2.** Once the answer key is typed and
   can hold criteria, comparing two values and checking a criterion are different seams:
   the first needs the answer, a value and sometimes the example, and the second has no value to
   compare against and needs the rollout. Every option in the record was about the arity of the
   first seam. **3D also cannot work as written**: 3B and 3C both produce a three-argument
   function, so arity cannot separate them and parameter names have to be read, which is the
   hazard the record lists as 3D's cost.
3. **The objection to 2B was overstated.** `correct_at` is an argument the library holds, so
   unlike S3.6's closure constant it is recordable beside
   [`_config`](../../src/simple_agents/evaluation/runner.py#L2401). The
   argument that decided against a sliding scale is the annotator-agreement one, not the
   recording one.

**Nothing in `simple-agents.md` §9 moves.** All four were checked against it. The nearest entries
are #6, `unknown` as a first-class return value, which is untouched because absence stays its own
outcome, and #10, conformance graded rather than binary, which a third outcome runs with. What
does move is FT-10's written definition in `docs/failure-taxonomy.md` and the results file format,
and neither is protected.

**A chatbot was put to the decisions as a test, and it changed none of them.** A conversation has
no enumerable right answer at any point, so criteria are not a better answer key for it but
the only one, and a canonical-plus-alternatives label has nothing to hold. What it raised that
none of the three decisions answers is below.

### What the build has to solve, and none of it is a decision anyone still owes

- **A criterion written as code cannot sit in a JSONL example file.** `expected` round-trips
  through [`encode_answer`](../../src/simple_agents/schema.py#L162) and a function does not, so a
  criterion is either named in the file and resolved against something the project registers, or
  the answer key stops being fully file-storable.
- **A criterion has to be versioned** the way `matches` already is at
  [`_config`](../../src/simple_agents/evaluation/runner.py#L2401), or editing one moves every
  number with nothing recording that the rule changed. This is S3.6's tolerance finding arriving
  in a third place.
- **What counts as "the answer" when the product is a conversation.** The library reads one answer
  off the final output through [`_answer_of`](../../src/simple_agents/evaluation/runner.py#L1864),
  by name or by a function. A project can therefore make the transcript the answer, and then
  criteria about the conversation are checked against a plain value. Whether that is the
  design or whether the run's record is needed instead is open, and it is what decides whether
  path criteria and content criteria live in one place.
- **How the third outcome changes each of the six rates' denominators**, and what
  `precision_when_asserting` is over once `asserted` has three members rather than two.
- **Whether per-field verdicts are now a special case of criteria.** A record with a verdict
  per field is a criteria list over that record. See the roadmap below.

## What was decided at the second sitting, 2026-08-17

**Decisions 4, 7 and 8, in that order, with 8 answered last because it needed the other two
priced.** Stage 3 was built the same day.

| Decided | Rejected, and why |
|---|---|
| **4. A criterion's check may report absence**, returning `Unknown` where the answer asserted nothing about that condition, and `Criterion(expects_absence=True)` declaring that silence is the right answer there | **Doing nothing** leaves a project writing two criteria per field, which puts that field twice in the grade and still cannot separate the two failures. **A `Record` answer key** gives the library two ways to decompose an answer key with two reporting surfaces and two roll-up rules |
| **7. `Label` is the seam for a judgement the scoring code did not compute, and the join is designed once at stage 4** with the judge | **Owning the join now** builds the recording half twice: [`plan.md` §2.1](../plan.md#L59) already accepted a judge that reads what an end user answered and says one design settles both, and a criterion judged by a person is the third consumer of it. **Documenting the working route as it stands** teaches a path with two silent failures |
| **8. `P3-5` closes with stage 3.** Stage 4 merges into the judge entry, which becomes `P3-12` at the top of `plan.md` §1 | **Leaving it in §2.1** is what that section's own rule refuses: the entry said it waits on "a decision about where a scored model call is recorded and priced", which is the item's own content. Its second half, the outcome for a rollout that consulted and got nothing back, genuinely waits on a project and stays there. *(It left §2.1 for `P3-22` on 2026-08-19, which settled it from the rule `no_response` already follows rather than from a project.)* |

**The argument that decided 4, and it is the library's own rather than the survey's.** FT-04
rewards an agent that reports absence and FT-10 separates the value it invented from the value
it failed to find. Both stop working at the first answer with two fields: `expects_absence` is
`isinstance(expected, Unknown)` over the whole answer, and a criterion returning `False` covers
"wrong", "omitted" and "correctly empty" alike. Measured at the build, on the same twelve real
rollouts: an agent that invented nothing was reported as asserting a confident wrong value on
25% of them.

**What the build then changed about decision 4.** The sitting agreed `expects_absence` as a
declaration read by FT-04 alone. The first live run scored a correct answer as partly right
because of it, so the fold reads it too and silence meets a condition declaring it.
[`build-logs/per-field-absence-build-log.md`](../build-logs/per-field-absence-build-log.md#L1)
§2.3.

## Where every kind stands

**Decision 8's answer, and what closes this survey.** S1's twenty-four kinds, by what a project
can do about each today.

| | Kinds | Where |
|---|---|---|
| **Shipped or expressible** | A1, A2, A3, A4, B1, C1, C3, D1, E1, E2, E3, F1 where code decides a condition, H2, J1 | `matches`, the four answer keys, a criteria list, `EndUser`, `Unknown` |
| **Shipped as stage 3** | J2 | [`build-logs/per-field-absence-build-log.md`](../build-logs/per-field-absence-build-log.md#L1) |
| **`P3-12`** | F1 where code cannot decide a condition, and J3's outcome | A judgement the scoring code did not compute |
| **Parked with a reason** | E4 | [`plan.md` §2.2](../plan.md#L101) |
| **Expressible, found so by a project** | C2 | Below, and it left the entry on 2026-08-27 |
| **Built** | G1, I1, B2, F2, G2, H1 | **All six on 2026-08-28**, `P3-48`. [`build-logs/a-figure-that-is-not-a-mean-build-log.md`](../build-logs/a-figure-that-is-not-a-mean-build-log.md#L1) §3 |

**The four, and how each came out.** *Settled 2026-08-28 by `P3-48`'s decider pass, which wrote
each against what ships rather than reading it. **B2 and G2 came out expressible** and **F2 and H1
needed one named thing each**, both built the same day. G2 is the surprise: the k rollouts of one
example are pairs, so the pair seam expressed it without having been designed for it.*

**The four, and where each stood before that.** *Deciders until 2026-08-28, when `P3-48`'s sitting pulled all
four in on Thilina's call: "I would prefer to do this properly rather than leave hanging threads."
`plan.md` §2.2's entry is deleted and this table is what is left of it.* The deciding work is the
entry's own afternoon, and **it runs before any of the four is built**: G1 and H1 both carried a
blocker a read produced and only a worked example would have caught. **What that afternoon is**,
carried over from the deleted entry: write each shape against what ships. `AnyOf`, `Contains`,
`WithinTolerance`, `Criteria` with its registered checks, a project metric and `compare_variants`
are the whole surface, and four worked examples say for each shape whether it is already
expressible or name the one thing that is missing. A shape that comes out expressible gains a line
here; a shape that does not has a scoped cost, and whether that cost belongs inside `P3-48` is
Thilina's call rather than the build's.

| Id | What it is | What would decide it |
|---|---|---|
| **B2** | Several right answers not worth the same. "Kirkwall Retail Ltd" fully right, "Kirkwall" half | A project whose acceptable answers differ in quality |
| **F2** | A rubric with named axes, so one answer scores accurate and badly written and both show | A project needing the axes inside the answer key rather than as separate project metrics |
| **G2** | No label at all: whether the agent agrees with itself across its own rollouts | A project measuring self-consistency. The resampling unit becomes the score's input, which nothing supports |
| **H1** | The annotators disagreed and the disagreement is the signal. The label is the spread | A labelling pass with several annotators, which no run has done. **The material is not lost**, corrected 2026-08-28: [`read_labels`](../../src/simple_agents/evaluation/labels.py#L133) returns `dict[str, Label]` with last-line-wins, and the file keeps every line, so collapsing is the reader's choice and a sibling returning `dict[str, list[Label]]` is what is missing. What "right" means against a distribution is then a project declaration |

**C2 is expressible today, found so by dogfood #5 on 2026-08-27.** A ranked list where position
counts is a `ProjectMetric` whose `score` reads the ordering, and the project wrote it in seven
lines::

    def reciprocal_rank(scoring) -> float:
        want, got = _hits(scoring)
        for position, name in enumerate(got, start=1):
            if name in want:
                return 1.0 / position
        return 0.0

    ranked = ProjectMetric(name="reciprocal_rank", score=reciprocal_rank, definition=(
        "1/rank of the first surfaced show they went on to watch, 0 where none"))

It carried an interval and an n like any other figure. **What is not expressible is the answer
key.** `want` came out of `example.metadata`, and `matches` cannot say that rank 1 is worth more
than rank 5, so a project scoring this way gets no `accuracy`, `graded_accuracy` or
`false_confidence_rate` over the ranked answer. That is the shape of every entry in the row above:
the scoring is expressible and the key is not.

**G1 is `plan.md` §1 `P3-48` since 2026-08-27**, taken with the count-or-total seam because a win
rate is that seam's hardest case. *(This table said "It needs `P3-12` as well" until then, and
`P3-12` and `P3-13` both closed on 2026-08-18. The correction is `DF5-X13`.)* **It is not that
seam's hardest case, it is that seam**, found at the item's own sitting on 2026-08-28: a win rate
is a ratio of two totals whose unit is a pair, and the four figures four dogfoods built by hand are
the same ratio over candidates, pages, picks and citations. **And a pair of arms is the narrowest
of three pairings**: this project paired two items from one ordering, and a bracket pairs winners
with winners, so the library takes the pairs a project declares rather than forming them. Dogfood #5 needed it
and built the whole instrument outside the library: 40 pairwise comparisons between two bands of
its own ordering, `prefer_this` 7, `prefer_that` 7, `prefer_neither` 26, never entering
`EvalSuite`.

## The roadmap

**Recommended, not agreed**, when it was written. **Corrected 2026-08-17 by the sitting above:
stages 1 and 2 are one agreed block, built as `P3-10`, and stage 3 is in question.** Stages 3 and
4 are still recommended and not agreed. Four stages, and each one's gate is what makes the next
worth starting. The argument for the ordering is that stage 1 costs one field and one signature and
turns four projects' undeclared conventions into declared ones, and every later stage is a
design that stage 1 would otherwise have to be redone underneath.

**What the sitting changed about the table below.** Stage 1's "what lands" is no longer a
declared reading and a signature: it is a typed answer key, criteria, a third outcome and one
context object, which is stage 2's content built with it rather than after it. **The grouping note
predicted this and it held**: it said stage 3 cannot be settled unless stage 2 lands on
decomposition, "where a per-field verdict is a corollary of it". Decomposition landed, so stage 3
is now either a corollary of criteria or nothing, and that is the build's to establish rather
than a sitting's.

| Stage | What lands | Decisions it settles | Why here |
|---|---|---|---|
| **1. Say what the label means** | A declared reading for a plural label, and `matches` given the example | 1, 3 | The cheapest change with the widest reach: it is a field and a signature, it makes B1, C1 and E2 expressible, and it is the only stage that changes what an existing results file means. **It forecloses nothing below it** |
| **2. Say what a partly-right answer is** | Whichever of a threshold, a third outcome, or a decomposed criteria list survives the argument in decision 2 | 2, and 7 if criteria win | Blocked by stage 1, because a grade over a plural label needs the reading first. This is where S3.5's 94% is answered |
| **3. Per-field absence** | Absence per field, with a roll-up | 4 | **Built 2026-08-17.** Narrowed by P3-10, which established that per-field *correctness* is a `Criteria` list over the record and needs nothing new, so what was left was J2: an `Unknown` in one field was a criterion returning `False`, indistinguishable from a wrong value, which is ExtractBench's own failure |
| **4. A scorer that costs something** | A judge seam through the envelope, or a decision not to have one | 5 | Last, and separable. It moves no existing rule and every earlier stage works without it. **`P3-12` since 2026-08-17**, carrying two consumers this record does not: a judge that reads what an end user answered, and a criterion decided by a person. **Designed 2026-08-18**, and "it moves no existing rule" held: a scoring rule reads judgements and never makes one, which `simple-agents.md` §10 gained rather than lost. [`archive/a-recorded-judgement.md`](../archive/a-recorded-judgement.md#L1) |

**How the four group into sittings, and it is not one.** *Added 2026-08-16 on Thilina's question,
and it corrects the row above for stage 2.*

- **Stages 1 and 2 are one sitting, decided together and built in order.** The row above says
  stage 2 is blocked by stage 1, which is true of the graded-matcher option and false of the
  decomposition option: a criteria list is not a plural label, it is a different axis, so
  choosing it changes what stage 1's label has to be. **Deciding stage 1 without knowing which
  way stage 2 goes risks designing the label twice.** Build stage 1 first regardless; the
  ordering of the build is not the ordering of the decision.
- **Stage 3 cannot be settled in that sitting unless stage 2 lands on decomposition**, where a
  per-field verdict is a corollary of it. Under either other option stage 3 is its own design,
  touching `expects_absence`, `Over`, FT-04, the six rates and the results format, and **no
  dogfood has produced a structured-record answer**, so it would be decided on external evidence
  and none of our own.
- **Stage 4 is its own sitting**, and not because of its size. A scoring call that spends money
  and does not repeat runs into `simple-agents.md` §10's hard requirement that the whole suite
  run in CI with no network and no spend, and into `source_version`, cassette replay and
  `max_spend`. That argument deserves a sitting rather than the tail of a long one.
- **The general reason not to settle four at once** is this project's own repeated finding:
  a decision made about code that does not exist yet gets revised when it does. Item 5 found two
  defects in items 3 and 4 within minutes of the first live run, after 236 tests had passed over
  both. Stages 3 and 4 would be agreed on top of an unbuilt stage 1.

**Not in the roadmap, and each says why.**

- **P3-9 runs after stage 1 and does not wait for stages 2 to 4.** Its decisions 1 and 2 need the
  label's reading settled and nothing more, so the ordering in
  [`plan.md`](../plan.md#L17) §1 holds as it stands.
- **I1, the figure that is not a mean over examples**, was
  [`plan.md` §2.1](../plan.md#L46) and stayed there while this survey added a second instance to it.
  *(**Scheduled as `P3-48` on 2026-08-27** with G1, and the two turned out to be one aggregation.)*
- **E4, a scorer that executes a reference computation**, stays unscheduled. It runs into
  [`plan.md` §2.2](../plan.md#L101)'s irreversible-tool entry from the other side, and no dogfood
  has one.
- **H1** is enumerated and not scheduled. It needs a labelling pass with several annotators that
  no run has done. *(This read "G1 and H1" until 2026-08-27, when dogfood #5's sitting 4 scheduled
  G1 as `P3-48`. `DF5-X13`. **H1 followed it on 2026-08-28** with B2, F2 and G2, when that item's
  sitting pulled all four in. What no run has done still holds; what the entry got wrong is that
  the material is lost, and it is not.)*

**What would change this ordering**: a dogfood whose answer is a structured record, which would
raise stage 3 above stage 2, or a project that cannot state a correct answer at all without a
judge, which would raise stage 4.

## What it waits on

**Nothing, and nothing waits on it. `P3-5` closed on 2026-08-17.** Stages 1 and 2 shipped that
day as `P3-10` ([`build-logs/answer-key-build-log.md`](../build-logs/answer-key-build-log.md#L1))
and stage 3 the same day
([`build-logs/per-field-absence-build-log.md`](../build-logs/per-field-absence-build-log.md#L1)).
Stage 4 is `P3-12`. *(Until the first sitting this section read "It is `plan.md` §1's top row and
the survey is done", and the top row was then the build.)*

**What waited on it**: P3-9, on stage 1 alone, and P3-2, because an example project that consults
meets P3-9's first assumption on its first run. Both gates were met by stage 1.

**The stages are not `P3-n` ids and are not queue positions.** They are sections of this record,
cited as `P3-5 stage 1` the way any section is cited, and until a stage joins `plan.md` §1 nothing
about it is scheduled.

**When a stage becomes work and takes a `P3-n`, say here which supersedes which.** A closed item
keeps its id, so `P3-5` does not disappear when a stage of it ships, and a session that cites
`P3-5 stage 1` after it has a queue id would otherwise be citing the record and the queue for one
thing with no line saying they are the same thing.

| Stage | Superseded by | Since |
|---|---|---|
| 1 and 2, which the sitting of 2026-08-17 made one block | `P3-10`, **built 2026-08-17** | 2026-08-17 |
| 3 | `P3-5` itself, **built 2026-08-17** under its own id | 2026-08-17 |
| 4 | `P3-12`, which carries two consumers beyond it | 2026-08-17 |
