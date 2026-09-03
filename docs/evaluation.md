# Evaluation

The labeled example set, the k-rollout runner, the intervals, the per-node metrics, and the
comparison between two versions.

**The library ships the machinery. The project holds the content.** What counts as ground truth,
where the split falls, and whether an answer is correct are decisions about the task. No dataset
ships with the library, and no scoring rule is assumed.

## What to reach for

| To | Call | Covered in |
|---|---|---|
| Measure one pipeline | `EvalSuite(...).run(...)` | §6 |
| Read what a measurement says, per metric and per node | `print(results.report())` | §8.1 |
| Show a builder what one measured, and what it left alone | `simple-agents view` | `docs/view.md` §7 |
| Read the same figures over runs an evaluation did not make | `node_metrics("runs/")` | §5.5 |
| Print what every node did over the runs on disk, without writing code | `simple-agents report runs/` | §5.5 |
| Try a change and see whether it moved anything | `compare_variants(suite, {"name": other}, ...)` | §10 |
| Try the standard downgrades of a pipeline | `compare_variants(suite, ablate(pipeline), ...)` | §10.2 |
| Compare two measurements already on disk | `compare(before, after)` | §9 |
| Score rollouts again without running them | `EvalSuite(...).rescore(...)` | §6.4 |
| Continue an evaluation that stopped | `EvalSuite(...).run(..., resume_from=...)` | §6.5 |
| Watch one that is running, from another terminal | `simple-agents watch runs/eval/eval_a1226bc495df --expected 165` | §6.6 |

**`compare_variants` is how a change to the pipeline is measured**, and it is the one most often
reimplemented by hand. It runs the baseline and every named arm against the same backend in one
session, pays for only the nodes the change can reach, and reports the paired difference:

```python
from simple_agents.evaluation import compare_variants

comparison = compare_variants(
    suite,
    {"hunt as one call": flattened, "verify removed": shorter},
    envelope=envelope, model=client, split="held_out", k=5,
)
comparison.comparisons["hunt as one call"].moved      # ['accuracy']
```

Running the arms on two different days instead measures the backend's day as well as the
change, and running them by hand pays for every node rather than the ones that differ.

---

## 1. The example set

```python
from simple_agents import Unknown
from simple_agents.evaluation import Example, ExampleSet

examples = ExampleSet([
    Example(id="q1", inputs={"question": "Which retailer ships from Leeds?"},
            expected="Kirkwall", split="dev"),
    Example(id="q2", inputs={"question": "When did Kirkwall open the Leeds depot?"},
            expected=Unknown(reason="the collection gives no date"),
            split="held_out", source="doc:kirkwall-history"),
])
```

`inputs` is what the pipeline is run on, so it is whatever that pipeline's first node takes.
`expected` is the correct answer, or `Unknown` where the information is genuinely absent.

**`memory` is what the agent already remembers when the example starts**, for a pipeline that
reads a memory store. Each rollout gets its own store holding exactly this and nothing another
rollout wrote, so what an agent remembers is part of the example rather than a leftover
(`docs/memory.md` §3):

```python
Example(id="q4", inputs={"question": "Find me something to read"},
        expected="The Left Hand of Darkness", split="held_out",
        memory={"preferred_length": "prefers books under 300 pages"})
```

**`expected_by_node` labels a single node's output**, for the nodes a project holds ground truth
about. It is keyed by `node_id` and needs no entry for every node:

```python
Example(id="q1", inputs={"question": "Which retailer ships from Leeds?"},
        expected="Kirkwall", split="dev",
        expected_by_node={"hunt": "Kirkwall"})
```

§5 covers what is reported from it.

### 1.1 Splits

`split` is a name the project chooses. Two conventions make the rest of the tooling read
naturally: `dev` for examples that may be inspected freely, and `held_out` for the ones that may
not, with the reported number coming from `held_out` alone (FT-02).

**The set names which split is the held-out one**, defaulting to `held_out`. A project whose
splits are called something else says so once, and the name is recorded in the results file so a
conformance check reads it rather than guessing:

```python
examples = ExampleSet(examples, held_out="test")
examples = ExampleSet.from_jsonl("evals/examples.jsonl", held_out="test")
```

```python
examples.splits()                       # {'dev': 20, 'held_out': 20}
examples.in_split("held_out")           # the examples, in declaration order
examples.absent_proportion("held_out")  # 0.375
```

A held-out split with no absent-answer examples scores a careful agent and one that always
guesses identically, because no example exists where guessing is wrong and abstaining is right
(FT-04). `absent_proportion` is what reports that, and it counts a whole answer that is absent.
An absent case living in one condition of an answer key is `Example.absent_parts`, which FT-04
reads as well (§1.6).

### 1.2 Contamination

Two examples cannot share an identifier: `ExampleSet` refuses that at construction, so the same
example appearing in two splits is impossible rather than checked for. What is left is the same
example under two identifiers.

```python
report = examples.contamination(threshold=0.8)
report.clean          # False when anything was flagged
report.pairs          # each with both ids, both splits, the kind, and the similarity
```

`threshold` is the word overlap at or above which two examples count as near-duplicates, and
has no default. A pair at the threshold is flagged, so `threshold=1.0` flags identical
wording rather than nothing. What counts as too similar depends on the task, so it is a decision
the project records rather than one the library makes (FT-03). Start at 0.8 and read what it
flags.

Two kinds are reported. `near_duplicate` compares every pair of examples in different splits on
the words in their inputs, using the same tokeniser the shipped search index uses.
`shared_source` flags a pair drawn from one `source` however differently they are worded,
because what was learned from one applies to the other.

A pair can be flagged for both reasons, and is then reported once per reason, so a count by kind
counts each reason a split has to be redrawn for. The fixes differ: one side of a
`near_duplicate` goes, and a `shared_source` pair needs its whole source on one side of the
split.

Examples inside a single split are not compared. A repeated dev example is waste rather than
contamination.

**`shared_source` is the one that decides how a split is drawn.** Assign whole sources to a
side, rather than drawing examples independently and letting two questions from one document
land on opposite sides. Stratifying on absence survives that: assign each source to whichever
side sits further below target on both the total count and the absent count.

#### 1.2.1 The pairs a builder is shown

`contamination` answers whether anything crosses a threshold, and a set that is clean at every
threshold returns no pairs. `nearest_cross_split` returns the closest pairs whatever their
similarity, with both examples' text, which is what the `too_similar` question puts in front of
the builder.

```python
for pair in examples.nearest_cross_split(n=5):
    print(pair.describe())
```

Each carries both ids, both splits, both texts, the similarity, and `shared_source` where the two
came from one source. Ranked closest first. A set with one split returns nothing.

The builder judges the pairs, and `contamination_threshold=` records where they drew the line.
Asking them for the threshold first asks for a number about material they have not seen.

### 1.3 The file

One JSON object per line. `id`, `inputs`, `expected` and `split` are required; `source`,
`expected_by_node`, `memory`, `end_user` and `metadata` are optional.

```jsonl
{"id":"q1","split":"dev","inputs":{"question":"Which retailer ships from Leeds?"},"expected":"Kirkwall"}
{"id":"q2","split":"held_out","inputs":{"question":"When did it open?"},"expected":{"type":"unknown","reason":"no date given"},"source":"doc:kirkwall-history"}
```

Absence is the tagged object `docs/trajectory-format.md` §5.1 defines. `null`, `""` and a missing
field never mean `unknown`, in a file as on a record.

`end_user` is a string where it is a description alone, and a tagged object where that person
holds something the agent has to obtain (§5.4). A pipeline that asks more than one person
carries one entry per answerer instead, keyed by the name each `consult` tool declares in
`reaches`:

```jsonl
{"id":"q3","split":"held_out","inputs":{},"expected":"CC-4471","end_user":"An operations manager, brusque and short of time."}
{"id":"q4","split":"held_out","inputs":{},"expected":"CC-4471","end_user":{"type":"end_user","description":"An operations manager.","knows":{"cost_centre":{"text":"the cost centre is CC-4471","disclose":"on_ask","value":"CC-4471"}}}}
{"id":"q5","split":"held_out","inputs":{},"expected":"CC-4471","end_user":{"requester":"A junior analyst.","approver":"Her director."}}
```

`disclose` is `volunteer`, `on_ask` or `hidden`, and defaults to `on_ask`. `value` is what a
scoring rule compares an answer against, and is absent for a fact nothing scores against.

```python
examples = ExampleSet.from_jsonl("evals/examples.jsonl")
examples.to_jsonl("evals/examples.jsonl")
```

`content_hash()` identifies exactly this set of examples and labels. It is recorded in a results
file, so a comparison between two evaluations can tell whether they were computed over the same
examples. Changing any example changes it; reordering the set does not.

### 1.4 A label a model wrote

Some projects label by hand and some do not. Where a model writes or checks a label, that pass
decides what every later number is measured against, so it runs inside the envelope like any
other work. A one-node `Pipeline` fanning out over the candidates gives the whole pass one
manifest, one trajectory, one cost, a model pin and a cassette.

```python
def build_label_prompt(inputs, ctx):
    candidate = inputs["candidates"]
    return f"Question: {candidate['question']}\n\nPassages:\n{candidate['passages']}"

label = Pipeline(
    [LLMNode(build_label_prompt, output_schema=Verdict, node_id="label",
             over="candidates", temperature=0.0)],
    budget=Budget(max_steps=len(candidates), max_tokens=400_000,
                  max_cost=1.00, max_wall_clock_ms=1_800_000),
)
env = RunEnvelope(run_dir="runs/", cost_basis=PRICES, role="labelling",
                  cassette=Cassette.record("evals/cassettes/labels.jsonl"))
result = label.run({"candidates": candidates}, model=client, envelope=env)
```

**The budget bounds the pass.** `over=` makes one call per item inside one run, so `max_cost`
is what the whole pass may spend and `max_steps` counts every item. Running the pipeline once
per candidate instead makes each candidate its own run with its own budget, and a `max_cost` of
`1.00` over 60 candidates then permits `$60`.

**`role="labelling"` keeps the pass out of the checks that read the agent.** Every conformance
check that reads a run reads the newest run whose role is `agent`, so a labelling pass written
into `runs/` alongside them is found by `runs()` and is never mistaken for one
(`docs/run-envelope.md` §2.1). Without it, FT-13 and FT-14 report on the labelling run.

**A fan-out collects a failed item rather than ending the pass** (`docs/pipeline.md` §2.2), so
read `result.output.failures` before treating the verdicts as complete.

`MistralClient.complete` with a hand-built `ModelRequest` runs the same calls and records none
of it. FT-14 pins the model the agent ran on; without this nothing pins the model that wrote the
labels the agent is graded against, and a labelling pass that turns out to have been wrong
leaves no artifact saying what it did.

### 1.5 Where a judgement is kept

A label is a judgement about something that already exists: a candidate example a verification
pass ruled on, or an answer from a finished run that a person read. `evals/labels.jsonl` is
where they go, one JSON object per line.

```python
from simple_agents.evaluation import Label, read_labels, write_labels

write_labels("evals/labels.jsonl", [
    Label(id=outcome.item["id"], verdict=outcome.value.answerable,
          reason=outcome.value.reasoning,
          decided_by=result.manifest["models"]["configured"]["request_model"],
          run_id=result.run_id)
    for outcome in result.output.outcomes if outcome.error is None
])
```

```jsonl
{"id":"q29","verdict":true,"decided_by":"mistral-medium-2604","decided_at":"2026-08-07T14:03:12.481Z","reason":"Black_Death#11 puts Marseille in France","run_id":"run_20260807T140312Z_a1b3"}
{"id":"q30","verdict":"drop","decided_by":"human","decided_at":"2026-08-07T16:11:40.002Z","reason":"two judges disagree, so the label is not safe"}
```

**`decided_by` is required, and `run_id` is what makes a model's judgement recoverable.** A
label that names a run points at the manifest holding the model, the prompt and the cost, and
at the trajectory holding the exchange. A label decided by a person carries `"human"` and the
reason. A judgement whose basis is a source file or a conversation cannot be weighed when it
is questioned later.

`read_labels` returns them keyed by id, and the last line wins where an id appears twice, so
re-labelling appends a line and the earlier judgement stays in the file. `write_labels(...,
append=True)` is how a second session keeps the first one's work; without it the file is
replaced.

**No check reads this file.** Whether a label is right is not checkable and the library does not
claim otherwise (`docs/failure-taxonomy.md` §10). What the file buys is that the judgement, its
reason and its decider survive the session that made them.

**A verification pass produces labels; the example set is what the project builds from them.**
`evals/examples.jsonl` holds the inputs an evaluation runs the pipeline over, and §1.3 is its
schema.

**Where several people judged one thing, `read_every_label` keeps all of them.** `read_labels`
takes the last line for an id, which is a correction replacing an earlier judgement;
`read_every_label` returns every label under that id, in file order, which is several judgements
standing together:

```python
from simple_agents.evaluation import read_every_label

by_id = read_every_label("evals/labels.jsonl")
[label.verdict for label in by_id["q29"]]      # ['spam', 'spam', 'not_spam']
```

The disagreement is then a number the project puts in `Example.metadata` and scores against with
a `ProjectMetric`, so a label that is a spread rather than a value needs nothing further.

### 1.6 When there is more than one right answer

`expected` takes a plain value where the answer is one thing. Where it is not, it takes an
answer key, and the key says what the right answer is. It never says how to compare two
values: that stays in `matches`, which the project writes. What the builder was asked about
this is the brief's `answer_form` entry (`docs/procedure.md`, stage 2).

| Key | What it says | Grades |
|---|---|---|
| `AnyOf([...])` | The answer is one thing, drawn from this set | no |
| `Contains(...)` | The answer is a collection, and these have to appear in it | with more than one value |
| `WithinTolerance(v, ...)` | A quantity, right where it is close enough | no |
| `Criteria([...])` | A list of conditions, each judged yes or no | yes |

```python
from simple_agents.evaluation import AnyOf, Contains, Criteria, Criterion, WithinTolerance

Example(id="q1", inputs={"question": "Which retailer ships from Leeds?"},
        expected=AnyOf(["Kirkwall", "Kirkwall Retail Ltd"]), split="dev")

Example(id="q4", inputs={"question": "Find me something to read"},
        expected=Contains("The Left Hand of Darkness"), split="held_out")

Example(id="s7", inputs={"garment": "..."},
        expected=WithinTolerance(52.0, relative=0.02), split="dev")
```

**The key decides how many comparisons there are; `matches` decides each one.** `AnyOf` calls it
once per admissible value and is right where any of them matches. `Contains` calls it once per
value the answer has to hold, giving it the whole answer and one value, and grades on how many
were found. `WithinTolerance` calls nothing: the tolerance is the whole of what close enough
means, and it is declared in the key so that it travels into the example file and into
`content_hash`. A tolerance written into `matches` instead lives in a closure, which
`source_version` does not read, so widening it from 2% to 5% would move every rate with nothing
recording that the rule changed (§11.6).

#### A key that is a list of conditions

Where nothing enumerates the right answers, conditions recognise one. Each is judged yes or no,
and the grade is the weight met over the weight declared.

```python
Example(id="q4", inputs={"question": "Find me something to read"},
        split="held_out", expected=Criteria([
            Criterion(id="not_read", text="a book the reader has not read", required=True),
            Criterion(id="subject", text="shares a subject with the to-read shelf", weight=2),
            Criterion(id="length", text="under 400 pages"),
        ]))

suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    criteria={
        "not_read": lambda s: s.answer.title not in s.example.metadata["read"],
        "subject": lambda s: s.answer.subject in s.example.metadata["subjects"],
        "length": lambda s: s.answer.pages < 400,
    },
)
```

**The criterion is data and its check is code.** The criterion carries an id, its text, a weight
and whether it is required, so it sits in a JSONL file and in `content_hash`. The check is
registered once on the suite under that id and serves every example naming it, and its version
is recorded beside `matches` (§11.6). Construction is refused for a criterion nothing registers,
and for a registered check no example names.

`required` makes an unmet condition wrong rather than partly right, so a failure that matters is
not reported as an answer that was mostly right. `weight` is how much a condition counts toward
the grade relative to the others in the same list, and is positive. A condition the answer must
not meet is a criterion whose check returns true when the thing is absent.

**A check is given the whole `Scoring`** (§11.1), so a condition that depends on who is being
served reads it off `s.example` and is written once rather than once per person. The example
above scores every reader in the set from three registered checks. A condition about what the
run did rather than what it answered reads `s.trajectory`. `s.criterion_id` is the id of the
condition being decided, for one function registered under several.

#### A condition the answer said nothing about

A check returns `True`, `False`, or `Unknown` where the answer asserted nothing about that
condition. The three are what an answer with parts can do to any one of them: meet it, get it
wrong, or leave it alone.

```python
def po_number(s):
    if isinstance(s.answer.po_number, Unknown):
        return Unknown()
    return s.answer.po_number == s.example.metadata.get("po")
```

An absent condition is unmet. It earns no credit and its weight stays in the denominator, so
leaving a condition alone does not raise the grade. What changes is which failure it is: an
answer that met none of its key that way invented nothing, so it is `missed` rather than
`false_confidence` (§2). An answer that met part of its key and was silent on the rest is still
`partially_correct`. How often each condition was left alone is reported beside that condition's
figure (§3.1).

```python
results.rollouts[0].verdict.parts    # {'vendor': True, 'total': False, 'po_number': None}
results.rollouts[0].verdict.wrong    # ('total',)
results.rollouts[0].verdict.absent   # ('po_number',)
```

**Where the right answer to a condition is that the value is not there, the criterion says so**,
as `expected=Unknown(...)` does for a whole answer, and silence meets it.

```python
Criteria([
    Criterion(id="vendor", text="the vendor"),
    Criterion(id="po_number", text="the PO number, or that none is stated",
              expects_absence=True),
])
```

So the check answers one question, whether the answer gave a value and whether it was right, and
absence on both sides is read by the library as it is for a whole answer (§2). The example whose
invoice states no PO number declares `expects_absence` and the example whose invoice states one
does not, and the same registered check serves both.

Where the condition declares `expects_absence`, reporting absence meets it and **an asserted
value is wrong whatever the check returns**, because the right answer there is that the value is
not there. That is why the check above reads `metadata.get("po")`: on the declaring example there
is no value to compare against, and the library decides the condition rather than the check.
Reporting absence where a value existed is unmet.

FT-04 reads the declaration too. A project whose absent cases are single empty fields satisfies
that gate with the examples it has, where before it needed an example whose whole answer was
absent.

#### The encoded form

Each key encodes as a tagged object, the way `Unknown` does, so an example file holds it and a
comparison between two evaluations can see it move.

```json
{"id": "q1", "split": "dev", "inputs": {"question": "..."},
 "expected": {"type": "any_of", "values": ["Kirkwall", "Kirkwall Retail Ltd"]}}
{"id": "s7", "split": "dev", "inputs": {"garment": "..."},
 "expected": {"type": "within_tolerance", "value": 52.0, "absolute": null, "relative": 0.02}}
{"id": "q4", "split": "held_out", "inputs": {"question": "..."},
 "expected": {"type": "criteria", "criteria": [
   {"id": "length", "text": "under 400 pages", "weight": 1.0, "required": false,
    "expects_absence": false}]}}
```

`{"type": "contains", "values": [...]}` is the fourth. Widening an admissible set changes
`content_hash`, so `compare()` declines to attribute the resulting difference to the agent
(§9).

---

## 2. What one rollout produced

Each rollout falls into one of seven outcomes. The library sorts them by reading absence on both
sides, so the project supplies only the comparison between two asserted answers.

| | `expected` is a value | `expected` is `Unknown` |
|---|---|---|
| asserted, met the answer key | `correct` | not reachable |
| asserted, met part of it | `partially_correct` | not reachable |
| asserted, met none of it | `false_confidence` | `false_confidence` |
| met none of it, asserting nothing wrong | `missed` | not reachable |
| reported `unknown` | `missed` | `correct_abstention` |
| produced nothing | `failed` | `failed` |
| never got an answer | `no_response` | `no_response` |

An asserted value where the correct answer is absence is `false_confidence` whatever it says,
because there was nothing to be right about, and the comparison function is not called.

A rollout that raised, or whose pipeline produced no output, is `failed`. That is separate from
`missed`: one is the agent reporting that it found nothing, the other is the run not finishing.

**`partially_correct` needs an answer key whose parts can be met separately** (§1.6): `Criteria`,
and `Contains` with more than one value. A plain label, an `AnyOf` and a `WithinTolerance` each
admit one answer or none, so a rollout scored against one of those is `correct` or
`false_confidence`. What was met is on the rollout:

```python
results.rollouts[0].verdict.grade    # 0.75
results.rollouts[0].verdict.met      # 2
results.rollouts[0].verdict.total    # 3
results.rollouts[0].verdict.parts    # {'not_read': True, 'subject': True, 'length': False}
```

`verdict` is `None` where no comparison happened: a failure, and either side reporting absence
end to end.

An answer that missed a criterion declared `required` is not partly right whatever else it met,
and its grade is recorded beside it. A recommendation that meets two conditions out of three and
fails the one saying the reader has not already read the book is a wrong answer, not a mostly
right one.

**The same separation runs inside the answer.** An answer that is not partly right is sorted the
way a whole answer is: `false_confidence` where it asserted something wrong, and `missed` where
every condition it did not meet is one it said nothing about (§1.6). So an agent that leaves a
field alone rather than inventing a value is not measured as one that invented it. A record whose
fields are all empty is `missed` where every condition asked for a value, and `partially_correct`
where one of them declared `expects_absence` and was met by the silence.

### 2.1 `no_response`, which measures nothing

`no_response` is the one outcome that is not a way the agent can be wrong. The rollout stopped on
a model call that recorded an error and returned no response, or on a replay that held no answer
for a call the run made. Nothing the agent did was measured, so the rollout is **outside every
rate's denominator**, and the count of what was left out is reported beside every rate (§8.1).

```python
[r for r in results.rollouts if r.outcome.value == "no_response"]
results.metrics["accuracy"].left_out         # {'no_response': 9}
```

**It is one of three things that put a rollout outside a denominator**, and §2.2 covers the rule
they share.

Two things put a rollout here:

- **A model call that never returned.** The backend was unreachable, rejected the request,
  rate-limited past its retries, or answered with a status the adapter could not use. A suite
  left running against a model id the backend no longer serves would otherwise report
  `failure_rate` 1.0 with complete intervals, which reads as an agent that answers nothing.
- **A replay with no entry** for a call the run made. §7.7 refuses the commonest case before the
  first rollout; this is what the rest sort as.

A response that arrived and could not be used is `failed`, not this: a tool that raised, an answer
that did not validate against the declared schema, a run that passed its budget, a request the
node's own context built and the backend refused as too long. The backend answered in each of
those, and what the agent did with the answer is the measurement.

Every rollout records its `seed`, its `run_id` and the path to its trajectory, so a surprising
result in the report is findable rather than gone (FT-07).

### 2.2 What a rate is over, and what leaves it

**A rollout is inside a rate's denominator when what it returned is attributable to the agent.**
Three things break that, and `RolloutOutcome.left_out` names whichever applied:

| Cause | What happened |
|---|---|
| `no_response` | The backend never answered, so there is nothing to score (§2.1) |
| `unanswered_consultation` | The agent asked a question of a channel that was meant to answer it, and the answer never arrived |
| `unreached_items` | A fan-out item died on a call the backend never answered (§5.4) |

```python
[r for r in results.rollouts if r.left_out]
results.metrics["accuracy"].left_out
# {'no_response': 9, 'unanswered_consultation': 5}
```

**A question with no intended answerer is not one of these.** A channel declaring `nobody`,
which `unattended()` does, is the designed path: a project that ships unattended is measured on
how the agent behaves when there is no one to ask, and a rate that dropped those rollouts would
measure nothing it cares about. `docs/tools.md` §4.6.2 lists the six kinds of answerer.

**Both figures are reported.** The headline rate is over the rollouts that measured the agent,
and under it the same rate with the left-out ones counted as they scored, so the narrower number
cannot be read without the wider one:

```
  accuracy   94.7%  [88.2%, 97.7%]  n=95 over all rollouts, less 5 whose question went unanswered
             90.0%  [82.4%, 94.7%]  n=100, with the 5 left out above counted as scored
```

`Metric.including_left_out` is the second figure and is `None` where nothing was left out for a
reason that leaves an answer to score. A `no_response` rollout has no answer to count either way,
so it is in neither.

---

## 3. The eight rates

Reported together, each over its own denominator, each with its own interval.

| Metric | Over |
|---|---|
| `accuracy` | right answers, counting a right report of absence, over all rollouts |
| `graded_accuracy` | right answers with partial credit, counting a right report of absence, over all rollouts |
| `false_confidence_rate` | rollouts that asserted a wrong answer, meeting none of its answer key or missing a condition the key declared required, over all rollouts. An answer that fell short only by saying nothing is not one of these |
| `partially_correct_rate` | rollouts that asserted an answer meeting part of its answer key, over all rollouts |
| `recall` | rollouts that found the right value, over rollouts of examples where a value exists |
| `abstention_rate` | rollouts that reported absence, over all rollouts |
| `failure_rate` | rollouts that produced no answer at all, over all rollouts |
| `precision_when_asserting` | rollouts that asserted the right value, over rollouts that asserted anything |

**`false_confidence_rate` and `recall` are the pair that matters.** An agent returning `unknown`
when it does not know is usable; one returning a confident wrong value is worse than nothing,
because whatever consumes it acts on it. One accuracy number covering both hides the dangerous
failure behind the harmless one, and optimizing against the average trades the harmless one away
(FT-10).

**`partially_correct_rate` is that separation applied to a decomposed answer key.** An answer
meeting two conditions of three is neither right nor a confident wrong value, and reporting it as
either puts two different results in one bucket. A project whose answer key is a plain value
reports `0.0` here and `graded_accuracy` equal to `accuracy`.

**`accuracy` and `graded_accuracy` differ only where a rollout was partly right.** A partly right
answer scores `0.0` in the first and its grade in the second, so the two figures are the same
number on an evaluation with no `partially_correct` rollout.

A partly right answer is in `precision_when_asserting`'s denominator and not in its numerator: it
asserted something and that something was not right. Leaving it out would raise the figure as the
agent produced more partly right answers.

**What separates an answer given from an answer withheld is what the answer put forward, not the
outcome it was sorted into.** A record naming a vendor and leaving a `required` PO number alone is
`missed`, because an unmet `required` condition means it is not partly right. It still asserted
something, so it is inside `precision_when_asserting`, where it scores `0.0`, and outside
`abstention_rate`, which is over rollouts that reported absence. A record silent on every condition
asserted nothing and is inside `abstention_rate`; so is one whose silence met a condition declaring
`expects_absence`, which meets part of its key without putting anything forward.

```python
results.rollouts[0].verdict.parts     # {'vendor': True, 'po_number': None}
results.rollouts[0].verdict.asserted  # True
results.rollouts[0].asserted          # True, read off the verdict where there is one
```

A metric whose denominator is empty reports `value` as `None` with a `reason`, not `0`. Recall
over a split where every answer is absent is undefined; reporting zero would read as the agent
finding nothing.

**A rollout that did not measure the agent is in none of these eight** (§2.2), and each metric
carries what it left out in `left_out`, keyed by cause. The counts are over the examples that
metric's figure is over, so `recall` counts only the examples where a value exists.

```python
results.metrics["failure_rate"].rollouts      # 24, the denominator
results.metrics["failure_rate"].left_out      # {'no_response': 6}, outside it
```

These eight are functions of the rollout and of whether the example expects absence. A figure
computed from the answer itself, such as token overlap against a labelled span or a measurement
within tolerance, is a `ProjectMetric` (§11), reported beside these with the same interval and
the same exclusion.

### 3.1 A figure per criterion

An example set whose answer keys are `Criteria` (§1.6) also reports one figure per condition:
how often it was met, over the rollouts judged against it, with its own interval and its own n.
The criterion's text is the figure's definition.

```python
results.criteria["not_read"].interval.point   # 0.61
results.criteria["not_read"].interval.n       # 87
results.criteria["not_read"].definition       # 'a book the reader has not read'
```

A criterion two examples both name is one figure over both of them, so a set of 200 examples
with three shared conditions reports three figures. That is what tells a project which part of
its answer key the agent keeps missing, rather than only how much of it was met on average.

A rollout that reported absence end to end, failed, or never got an answer out of the backend
was judged against no criterion and is outside every one of these.
`results.criteria[id].left_out` carries the causes of the last of those, over the examples
naming that criterion. A rollout that reported absence one condition at a time was judged, so it
is inside them.

`absent` carries how many rollouts inside the figure did not meet the condition because they
asserted nothing about it (§1.6). They are unmet and inside the denominator, so the figure and
the count together say how much of the shortfall was the agent being wrong and how much was the
agent being silent. Silence that met a condition declaring `expects_absence` is not a shortfall
and is not counted here.

```python
results.criteria["po_number"].interval.point   # 0.61
results.criteria["po_number"].absent           # 12
```

`compare()` pairs these between two evaluations as it pairs the eight (§9), under
`comparison.criteria`, keyed by criterion id.

---

## 4. Intervals

```python
metric = results.metrics["false_confidence_rate"]
metric.interval.point    # 0.08
metric.interval.low      # 0.02
metric.interval.high     # 0.17
metric.interval.n        # 20 examples
metric.interval.k        # 5 rollouts each, or None when it varied
```

**The resampling unit is the example, not the rollout.** Two rollouts of one example are two
samples of the same question and move together, so resampling k×n rollouts as though they were
k×n independent observations produces an interval narrower than the data supports. The narrowing
grows with k and nothing about the reported number reveals it. `bootstrap_ci` takes the rollouts
grouped by example, and refuses a flat list:

```python
from simple_agents.evaluation import bootstrap_ci

bootstrap_ci([[1, 1, 0], [0, 0, 0], [1, 1, 1]], seed=41)
bootstrap_ci([[0.71], [0.33], [0.90]], seed=41)     # one score per example
bootstrap_ci([0.71, 0.33, 0.90], seed=41)           # refused, and says to group them
```

Every example counts once whatever k it ran at, so one example run a hundred times does not
outvote ninety-nine run once. `seed` makes the interval reproducible and is recorded on it.
`resamples` below 100 is refused: the endpoints are percentiles of the resampled estimates, and
too few of them makes the interval vary between runs more than the data does.

**A set where every example scored the same gives resampling nothing to read.** Every resample
draws the same value and both endpoints land on it, so the interval comes back zero width and
30 of 30 correct reports the true rate as certainly 100%. Where those identical scores are 0 or
1 the quantity is a proportion, so `bootstrap_ci` returns the Wilson interval instead and
`interval.method` says which calculation produced the endpoints. A set whose scores are all
identical and not 0 or 1, including a paired difference that is zero on every example, still
reports zero width, and that means the sample holds no variation rather than that the value is
certain.

**`wilson_ci` is for judgements made by hand, where there are no rollouts to resample.** A
labelling pass produces a count out of a count, and that is what it takes:

```python
from simple_agents.evaluation import wilson_ci

wilson_ci(4, 4)      # point 1.0, interval 0.51 to 1.0
wilson_ci(37, 50)    # point 0.74, interval 0.60 to 0.84
```

Four labels all correct is not evidence of a 100% rate, and the interval is what says so. It
never runs outside 0 to 1 and never reads as zero width. `bootstrap_ci` is the one an
`EvalSuite` reports and takes scores from rollouts the agent ran; this one takes two numbers.

A wide interval is a finding about the sample size. Widening the example set is the fix; dropping
the interval is not.

### 4.1 What moves when nothing changes

An interval resamples examples, holding each example's mean over its own rollouts fixed. It
answers what the figure would be on a different sample of examples. It says nothing about running
these same examples again, which also moves the figure, because the agent is stochastic and k
rollouts of one example do not agree.

```python
results.metrics["accuracy"].interval.width    # 0.14, over which examples were drawn
results.metrics["accuracy"].rollout_noise     # 0.017, over running these ones again
```

`rollout_noise` is that second quantity as a standard deviation, read off the k rollouts each
example already ran. It costs nothing: no repeat of the evaluation is needed. It is `None` at
k=1, where there is no within-example variation to read, and `0.0` where every example's rollouts
agreed with each other. `report()` prints it as `rerun ±x` beside the interval.

A comparison carries the two sides combined, since the runs are independent:

```python
change = compare(before, after).metrics["accuracy"]
change.rollout_noise      # 0.024
change.inside_the_noise   # True: the difference is what one configuration gives twice
change.moved              # None, and verdict_reason says why
```

**A difference whose interval excludes zero but which is inside the rollout noise carries no
verdict.** `moved` is `None` rather than `True`, because a difference that size is what running
the same thing twice produces. A difference whose interval already includes zero is `False`
whatever the noise: nothing moved, and the noise is why.

**To measure the same thing by repetition instead**, run one configuration into its own run
directory n times and read the spread of the point estimates. Each repeat needs its own
`run_dir`, because a rollout appends to the trajectory it finds. That costs n evaluations and
sees one thing `rollout_noise` cannot: a source of variation between runs rather than inside
one, such as a data source that changed underneath. `docs/evaluation.md` §6.8 is what catches
the most common of those, a prompt that varies with nothing declared.

### 4.2 What doing nothing would score

```python
suite = EvalSuite(pipeline, examples, answer="answer", matches=agreement,
                  baseline=lambda example: "shelve")

results.baseline_metrics()["accuracy"].interval.point   # 0.76
results.metrics["accuracy"].interval.point              # 0.82
```

`baseline` is what an agent that did nothing would answer, as a function of the example. It is
scored by this suite's own `matches` and its own conditions, over the examples that ran, and it
calls no model. Every figure the evaluation reports has one, and `report()` prints it
under the figure it belongs to:

```
  accuracy   82.0%  [68.0%, 94.0%]  n=29 over all rollouts, rerun ±4.9%
             75.9%  [59.0%, 88.0%]  doing nothing, over 29 example(s)  not separated from it
```

**A figure whose interval covers its floor is one this evaluation cannot separate from not
trying.** The line reads the same way for a
rate that is better low, such as `false_confidence_rate`: what it says is that this figure does
not tell the two apart. That is a finding about the measure
rather than about the agent: widen the example set, raise k, or score something the task actually
turns on.

Whether the agent beat it is a paired question, example by example, as a comparison between two
versions is:

```python
from simple_agents import against_baseline

for name, change in against_baseline(results).items():
    print(name, change.before, "->", change.after, change.delta, change.moved)
```

`before` is the floor and `after` is the agent, so a positive `delta` is the agent ahead.

Writing the floor into a metric's `definition` instead is what goes stale: the split gets
rebalanced and the sentence does not, and the figure is then read against a number that describes
a split that no longer exists. `config.baseline` records the version of the function, so an edit
to what doing nothing answers appears in a comparison the way an edit to `matches` does.

**An agent that never answers gives that as its answer.** `baseline` returning `None` is refused:
`None` is what a rollout produces when the pipeline returned nothing, so a floor built from it
reports an agent that did nothing as one that failed, and `failure_rate` reads 100% for an agent
that cannot fail. Say it instead:

```python
baseline=lambda example: Unknown(reason='did nothing')   # never answers
baseline=lambda example: "shelve"                        # the majority class
```

The baseline is called once per example before the first rollout, so a baseline that raises or
answers `None` costs nothing.

**A figure about what the agent refrained from is declared `over=Over.ALL`.** Under the default
`Over.VALUE_EXISTS` a rollout that asserted nothing is decided without the project's own function
(§11.2), and a do-nothing baseline asserts nothing on every example, so the floor describes the
declaration whatever the figure measures: 0.0 for a metric, and undefined for a ratio, whose two
totals are both zero. `report()` says so where the floor would be, and
`results.baseline_unscored` names them:

```
  avoided_share               0.0%  [0.0%, 49.0%]  n=4 over rollouts of examples where a value exists
                              0.0%  [0.0%, 49.0%]  doing nothing, over 4 example(s)  not separated from it
                            the baseline asserted nothing, so avoided_share was not called for it.
                            over=Over.ALL is what scores a figure about refraining.
```

---

## 5. Per-node metrics

One end-to-end score reports that the agent got worse and nothing about where, leaving hand
bisection through prompt edits as the way to localize a regression (FT-08).

```python
results.nodes["hunt"].model_calls      # including calls made inside this node's tools
results.nodes["hunt"].tokens           # the four classes, unmeasured ones left unmeasured
results.nodes["hunt"].cost             # derived against the envelope's basis
results.nodes["hunt"].terminations     # {'finish': 47, 'max_steps': 3}
results.nodes["hunt"].absent_outputs   # executions whose output reported an absence
results.nodes["hunt"].unfinished_executions  # ended without producing an output at all
results.nodes["hunt"].unfinished_model_calls # what those spent
results.nodes["hunt"].empty_responses        # calls that came back with nothing to act on
results.nodes["hunt"].tools_that_never_succeeded   # {'document_search': 7}
results.nodes["hunt"].delegations      # subtasks this node's model sent to a delegate
results.nodes["hunt"].consultations    # questions this node asked the end user
results.nodes["hunt"].consultation_resolutions   # {'answered': 5, 'declined': 28}
results.nodes["hunt"].consultation_answered_by   # {'simulated': 33}
results.nodes["hunt"].resource_reads   # {'catalogue': 41}, from ctx.record_access
results.nodes["hunt"].resource_writes  # the same, for accesses recorded as writes
```

**`resource_reads` and `resource_writes` count what a node's own code reached**, by resource
name, from the accesses it recorded (`docs/pipeline.md` §3). A resource reached through a tool
is in `tool_calls` instead, since the tool declares what it touches. A node that reaches a
store directly and records nothing is in neither, which is what makes recording the access
worth doing.

**`consultation_resolutions` is what says whether the questions were answered.** An evaluation
supplies the consultation channel, and one that returns nothing resolves every question
`declined`. The agent still runs, still answers, and every rate is computed as usual, so an
evaluation measured against silence and one measured against a person produce the same six
numbers. This is where they differ. A run of an agent that consults, whose resolutions are all
`declined`, measured something other than the agent the brief describes.

**`consultation_answered_by` is what says who answered them**, and it is the other half of the
same problem. A channel returning a fixed string produces `answered` as readily as a person
does, so `answered: 97` says nothing on its own about what was measured. This reports the
channel's own declaration beside it: `answered: 97` with `canned: 97` is a stub, and with
`simulated: 97` is a model playing the reader §5.4 describes. `docs/tools.md` §4.6.2 covers the
six values.

**`unfinished_executions` says what the node paid for and got nothing out of.** An
`AgentNode` produces its output from a `finish` call, so an execution that stopped on a budget
axis or on a `finish` its own check kept rejecting returns `None` to the node after it. The run
completes and records no error, so no other figure reports it. `unfinished_items` counts the
fan-out items that ended the same way, which is a separate unit of work: a fan-out whose items
all stopped that way completed normally and records no termination of its own.

**`unfinished_without_tool_calls` is the sharper of the two.** It counts the executions and
items that made no tool call, no consultation and no delegation, so the loop spent its whole
allowance without once acting. A cap that binds after real work is the cap doing its job, and
the remedy is the cap or the task; a loop that never acted is a prompt or a tool declaration the
model could not use, and the remedy is the wording. Read `unfinished_model_calls` against
`model_calls` for the share of this node's spend that bought nothing, and
`unfinished_model_calls_without_tool_calls` for the part of it that bought nothing at all:

```python
node = results.nodes["look_closer"]
node.unfinished_model_calls / node.model_calls              # 0.30
node.unfinished_model_calls_without_tool_calls              # 3384
```

The last figure is what `simple-agents check` fails a project for (FT-35), and
`AgentNode(..., allow_unfinished=True)` is what declares that a node is meant to work this way.

**Three more figures say where else the spend went and bought nothing.**
`empty_responses` counts model calls that came back with no content and no tool call, which is
what a reasoning model does when its whole output ceiling went on the chain of thought.
`delegations_out_of_budget` counts the subtasks that ran the delegated pipeline out of its own
budget, so the model got a report of failure rather than an answer.
`tools_that_never_succeeded` names the tools this node called where every call failed, with how
many calls each took: a declaration the model could not use, or a dependency that was down. A
tool that failed and later worked is absent.

```python
results.nodes["hunt"].empty_responses               # 3, of 40 calls
results.nodes["hunt"].delegations_out_of_budget     # 4, of 11 subtasks
results.nodes["hunt"].tools_that_never_succeeded    # {'document_search': 7}
```

**`unmatched` says the options did not fit.** It counts answers that were none of the choices the
node offered, so a node whose questions come back unmatched is asking the wrong question rather
than getting no answer. That is separate from `declined`, which is nobody answering, and it is
the figure to read before changing a question's wording. `docs/tools.md` §4.6.1.

A model call made inside a tool is attributed to the node whose tool spent it, because its
`parent_id` is the tool call and the tool call's parent is the node.

**A node inside a delegated pipeline keeps its own figures.** Its calls are its own rather than
the delegating node's, so `orchestrate.research.hunt` reports what the worker spent and
`orchestrate` reports how many subtasks it sent. `executions` counts every subtask the node ran
in, the way it counts every iteration of a cycle (§5.1).

### 5.1 Reach

**A node in a graph does not run on every rollout**, so every figure it carries is over the
rollouts that reached it, and how many that was is reported beside them:

```python
results.nodes["verify"].runs                    # 100: rollouts in the evaluation
results.nodes["verify"].reached                 # 42: rollouts that ran this node
results.nodes["verify"].reach.interval.point    # 0.42, with an interval like every rate
results.nodes["verify"].executions              # 42, or more if it sits inside a cycle
```

`executions` counts executions and `reached` counts rollouts, so the two differ for a node
inside a bounded cycle that ran three times in one rollout. A node that was skipped did not
execute, and is counted under `terminations["skipped"]`. **A node the run stopped inside is one
execution rather than two**: it writes a record when it suspends and another when it is
resumed, and both describe the same execution (`docs/trajectory-format.md` §3). The same holds
for the subtasks `delegations` counts.

**Read reach before comparing anything per node.** Halving the cost of a node that now runs on
40% of rollouts instead of 90% is a routing change, and a node whose accuracy rose on a third as
many runs may not have improved at all. §9 pairs the two so a moved number has its reach beside
it.

### 5.2 Per-node accuracy

Where an example set labels a node through `expected_by_node` (§1), the evaluation reports how
often that node was right:

```python
suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    node_matches={"hunt": lambda s: s.answer["answer"] == s.expected},
)

results.nodes["hunt"].accuracy.interval.point   # 0.71
results.nodes["hunt"].accuracy.denominator      # what it is a rate over
```

**The denominator is the rollouts that reached the node and carry a label for it.** An example
with no label for a node contributes nothing to that node's accuracy, and a node no example
labels reports `accuracy` as `None`.

**A node matcher is given the node's recorded output**, read back from the trajectory, so it
compares plain data rather than the object the node returned: `{"answer": "Kirkwall"}` rather
than an `Answer`. The same comparison can therefore be made again from a results file and a run
directory after the process that produced them is gone.

A node returns a schema object, so an absence usually sits in one of its fields rather than
being the whole output. Absence is the node matcher's to handle, which is the one place it
is, because the matcher is given a whole output rather than an answer. `matches` is never
called with an absence on either side (§2), and a `ProjectMetric` declared per node leaves out
the rollouts whose output holds one unless it declares `Over.ALL` (§11.5).

**A recorded absence reaches the matcher as `Unknown`**, wherever in the output it sits, and so
does the label it is compared against. The matcher still returns yes or no: reporting absence is
a criterion's to do (§1.6), and a node matcher returning anything but a bool is refused with the
node named. The tagged object `docs/trajectory-format.md` §5.1
defines is how the trajectory stores it and not what a matcher sees, so one test serves both
sides:

```python
node_matches={"chase": lambda s: s.answer["source"] == s.expected["source"]}
```

That is the same shape `runs()` hands back for a past run (`docs/run-envelope.md` §8.1).
`read_trajectory` is the exception and yields records as they are on disk.

Nothing requires a label. Ground truth for a node's own output is a fact about the task, and
most projects have it for none of their nodes or for one.

### 5.3 Per-node project metrics

A node also reports the figures a project declares for it through `node_metrics`, beside `reach`
and `accuracy`:

```python
results.nodes["hunt"].metrics["span_f1"].interval.point       # a mean over the rollouts
results.nodes["hunt"].metrics["unreadable_pages"].numerator   # a ratio's two totals
```

Both a `ProjectMetric` and a `ProjectRatio` may be declared for a node, and both land in
`metrics`. §11.5 covers declaring one.

### 5.4 The end user an evaluation answers with

An agent that consults is measured against whoever answers it. The channel the project
registered reaches a terminal, a chat window or a queue, and none of those has anyone behind it
during k×n rollouts, so an evaluation says who answers instead:

**An evaluation is refused over a channel that reaches a person**, before the first rollout.
`consult` is declared `read_only` because of this refusal: one rollout asks once, and n examples
at k rollouts would put every question n×k times for real, with the answers deciding what the
rollouts measured. The refusal reads the `answered_by` the channel already declares
(`docs/tools.md` §4.6.2): `end_user`, `builder` and `coding_agent` are refused, and `simulated`,
`canned` and `nobody` run. A replay reaches no channel and is exempt.

Passing `end_user=` is what says who does answer:

```python
from simple_agents.evaluation import SimulatedEndUser

results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
                    end_user=SimulatedEndUser(model=cheap))
```

**The example describes the person and a model plays them.** The questions cannot be written in
advance, because the agent writes them during the run out of what that run happened to find, so
what an example carries is the person rather than the answers:

```python
Example(id="q4", inputs={"question": "Find me something to read"},
        expected="The Left Hand of Darkness", split="held_out",
        end_user="Reads a lot of grimdark, has read all of Abercrombie, wants something "
                 "under 400 pages, and finds questions about difficulty useless and says so.")
```

**Where the questions are meant to reach somebody**, pass that channel here rather than a
stand-in, with its own declaration on it: `ask_in_chat.answered_by = "end_user"`, then
`suite.run(..., end_user=ask_in_chat)`. Passing it is what says the n×k questions are intended.
`unattended()` is the other end: it answers `Unavailable` and blocks nothing, which is what a
project shipping unattended is measured on.

Write what would change an answer, including what the person will not put up with. An example
that says nothing about who the agent is answering is refused before the first rollout: a model
with nobody to play answers as an assistant would, which is more agreeable and more articulate
than any real reader, and every rate computed over that is a rate against an invention (FT-24).

**A model states what the description carries and nothing else.** Measured on 2026-08-17 against
`gemini-3.1-flash-lite`, five rollouts each: asked for a cost centre the description did not
mention, it deflected 5 times out of 5 and supplied no value; with the cost centre written into
the description it supplied it 5 times out of 5. So an example whose right answer depends on
something the agent has to obtain carries that value, and `EndUser` is where it goes:

```python
from simple_agents.evaluation import EndUser, Fact

Example(id="inv-12", inputs={"invoice": "4,200 GBP, Northgate Logistics"},
        expected="CC-4471", split="held_out",
        end_user=EndUser(
            "An operations manager. Brusque, short of time, and has no patience for questions "
            "she thinks the agent should answer itself.",
            knows={
                "deadline": Fact("this has to be filed today", disclose="volunteer"),
                "cost_centre": Fact("the cost centre for this project is CC-4471",
                                    value="CC-4471", disclose="on_ask"),
                "cap": Fact("anything over 5,000 pounds needs her director", value=5000,
                            disclose="hidden"),
            },
        ))
```

`text` is what the model playing them is told. `value` is the same thing as data, which is what
a scoring rule compares an answer against. Both in one place is what keeps them from
disagreeing: a value written into the description and repeated in `metadata` is two values
nothing compares, so an example whose description says `CC-4471` and whose metadata says
`CC-9000` passes every check.

**`disclose` decides what the run does with a fact**, and the three are three different
mechanisms rather than three strengths of the same one:

| | What the model is told | What the agent can do |
|---|---|---|
| `volunteer` | it, and to state it unasked | receive it without asking |
| `on_ask` | it, and to state it only when asked about that thing | obtain it by asking |
| `hidden` | nothing | never obtain it |

A `hidden` fact is never put in front of the model, so the barrier is that it was not given
rather than that the model was asked to withhold it. It reaches a run through the answer key,
whose criterion reads it off the example:

```python
from simple_agents.evaluation import Criteria, Criterion

Example(id="inv-12", inputs={"invoice": "4,200 GBP, Northgate Logistics"},
        expected=Criteria([
            Criterion(id="right_cost_centre", text="filed against CC-4471", required=True),
            Criterion(id="under_her_limit", text="within the amount she can sign off"),
        ]),
        split="held_out", end_user=manager)

EvalSuite(pipeline, examples, answer="answer", matches=exact, criteria={
    "right_cost_centre": lambda s: s.answer.cost_centre == "CC-4471",
    "under_her_limit": lambda s: s.answer.total <= s.example.end_user.knows["cap"].value,
})
```

A criterion is registered against an id an example carries, so the answer key is what makes the
check reachable: `criteria=` naming an id no example holds is refused at construction.

An example carrying one is asking whether the answer respects something the agent was never
told. What the split measures is what a benchmark of this shape reports: τ-Rec's pass^1 over 60
tasks runs 0.846 where every constraint is volunteered and 0.200 where any is hidden, on one
configuration of nine. An evaluation that does not separate them reports a mixture whose
composition it does not record.

A plain string means an `EndUser` with that description and no facts, and it is what the field
holds after construction whichever form it was given. An example file stores it as that plain
string when there are no facts, so a set written before `knows` existed hashes to what it always
did.

**What the person knows is part of the example set's `content_hash`.** Widening it is a change a
comparison between two evaluations declines to attribute to the agent.

**What it costs is stated rather than argued away.** The number is now partly a measurement of
the stand-in. A model playing a person is more agreeable than the person, so an agent that
consults will score better here than in front of its readers. Every consultation records
`answered_by: "simulated"` with the model that wrote it, in the same file as the figure, and
holding one stand-in fixed across two arms keeps the comparison between them fair whatever the
absolute number is worth.

**Each rollout gets its own**, bound to that example's description and that rollout's seed, so
two rollouts of one example ask their own questions and get their own answers. The answers are
stored in the cassette with the rest of the run, so replaying a rollout replays its reader. The
stand-in's calls go to its own model rather than the one being measured: they are charged to no
budget of the agent's, and they stay out of `results.nodes[...].model_calls` and its tokens.
What each call spent is on the consultation record it produced.

**Each question is answered with what that person already said in front of it.** Without it a
stand-in has no record of its own replies, and a run measured against one agrees with whatever
the agent claims: asked to confirm a title the person never picked, a stand-in that cannot see
its own replies approved it 3 times out of 3, and one that can see them and is told the record
is complete refused 3 times out of 3 (`gemini-3.1-flash-lite`, 2026-08-17). Seeing the replies
is what makes the rule checkable and neither alone changed the outcome.

The seed for one answer derives from the question rather than from how many came before it, so
two runs at one seed answer the same question the same way whatever order the questions arrived
in. Where two nodes of one rollout consult at the same time, which answers are in front of the
later one depends on which finished first; a replay is served from the cassette and is not
affected.

**Where the other end is not a person**, replace the prompt. `{end_user}` is filled in with the
example's description and whichever of its facts that person would state:

```python
SimulatedEndUser(model=cheap, instructions=(
    "Reply as the system described below, which an agent has queried.\n\n"
    "The system:\n{end_user}\n\n"
    "Answer with a value or an error, in the fewest words that carry it."))
```

The reply format and the rule about what this person has already said are appended by the
library, so a replaced prompt keeps both. The prompt is part of the evaluation's identity, so
two evaluations differing only in it resolve to different directories rather than the second
being refused as a re-run of the first.

**A pipeline that asks more than one person takes one stand-in per answerer**, keyed by the name
each `consult` tool declares in `reaches` (`docs/tools.md` §4.6.2), with the example describing
each of them:

```python
Example(id="inv-12", inputs={"invoice": "..."}, expected="CC-4471", split="held_out",
        end_user={"requester": EndUser("A junior analyst filing the invoice."),
                  "approver": EndUser("Her director. Signs off, asks one question, never two.")})

results = suite.run(envelope=env, model=client, split="held_out", k=3,
                    end_user={"requester": SimulatedEndUser(model=cheap),
                              "approver": SimulatedEndUser(model=cheap)})
```

An example that describes nobody for one of the names is refused before the first rollout, as is
a consult tool that does not say which of them it asks. Each answerer is part of the
evaluation's identity.

**Which model played the end user is part of the evaluation's identity.** Two evaluations
differing only in that resolve to different directories, so the second is not refused as a
re-run of the first (§6). Comparing readers is then an ordinary comparison: same agent, same
examples, three stand-ins, three arms, with `noise_floor` underneath them (§9).

**`record` takes the same argument and has to be given the same one**, since the answers go into
the cassette the rollouts replay.

**An evaluation given no `end_user` uses the project's own channel**, whatever that is. Nothing
refuses that; `consultation_answered_by` in the results file is what reports it (§5).

**Two figures say whether the consultations measured the agent.**

`consultation_misreadings`, per node, counts the answers where the stand-in said which option it
had picked and the tool's own rule read a different one, or none. The rule that routes the run
is the project's own, and the stand-in's account of what it meant never routes anything, so this
figure is what says whether that rule reads the answers a run actually produces. A figure equal
to the node's consultations means it read none of them, and the branches the route names were
never taken. Whole-answer equality, which is the rule where none is passed, reads no option out
of prose (`docs/tools.md` §4.6.1).

**The stand-in and the reader are different jobs and both run here.** The stand-in writes the
answer, playing the person the example describes, and its cost stays off the node's figures. A
reader registered with `consult(read=...)` decides which option that answer was, and its cost is
the agent's, because it ships with the agent. The reader reads the text, and the stand-in's
declared choice is what its verdict is compared against. A reader that took that declaration
would report zero misreadings for every project.

It is a floor rather than a count of every misreading: a stand-in whose reply is composite,
`"I've already read Crossroads of Ravens. Pick The Will of the Many."`, declines to call it one
option, and the disagreement with a rule that also read none is not counted.

`unanswered_consultations`, per rollout, counts the questions the end user declined or was not
there for:

```python
[r for r in results.rollouts if r.unanswered_consultations]
```

A rollout that had to ask and got nothing back was scored against an answer it had no way to
reach, so a rate over it is partly a measurement of whoever was answering rather than of the
agent. Where the channel was meant to answer, the rollout leaves every denominator and
`left_out` says so (§2.2); where the channel declares `nobody`, the rollout stays inside, because
behaving well with no one to ask is what such a project is measured on. Nothing reclassifies the
rollout either way: it keeps the outcome it earned, and this is the number that says how many
questions went unanswered.

`unreached_items`, per rollout, counts the fan-out items that died on a call the backend never
answered:

```python
[r for r in results.rollouts if r.unreached_items]
```

A fan-out collects a failed item rather than raising, so a rollout whose items were rate-limited
or refused completes and is scored on whatever the rest produced. Where the fan-out is what
produces the answer, that reads as the agent declining. The rollout leaves every denominator
for the same reason a `no_response` one does: the backend never answered, and this is that at
item granularity (§2.2). An item that failed on a reply it was given, such as one that did not
validate, is not counted here: that is the agent producing no answer from an answer, which is
what `failed` covers. Nothing reclassifies the rollout, which keeps the outcome it earned.

### 5.5 The same figures over runs an evaluation did not make

`results.nodes` covers the rollouts of one evaluation. `node_metrics` reads the same figures out
of any directory of runs, which is how a project reads what its agent has been doing rather than
what one measurement found:

```python
from simple_agents import node_metrics

found = node_metrics("runs/", role="agent")
found["look_closer"].runs                        # how many runs were read
found["look_closer"].unfinished_executions       # what produced nothing
found["look_closer"].unfinished_model_calls      # what those spent
```

Nothing here imports the project's pipeline, so this reads runs from another process or another
terminal. Every run at any depth is read, so a directory holding evaluations is read as the
rollouts inside them.

**Reading fewer runs reports figures over fewer runs**, and `runs` on each result says how many
were read. `role` and `live` filter the way `runs()` does, `since` takes runs that started at or
after an ISO timestamp, and `last` keeps the newest that many:

```python
node_metrics("runs/", since="2026-08-14", last=500)
```

**Cost needs the basis the runs were written with.** Pass `cost_basis=` as the envelope declared
it; without one each node's `cost` reports unknown and every other figure is unaffected.

Each run's manifest also carries the unfinished figures for that run alone, under `unfinished`,
so a reader that only wants those opens one small file per run rather than every record they
wrote (`docs/run-envelope.md` §2.8).

**`simple-agents report` prints the same figures without writing any code**, over a directory of
runs, one run, an evaluation's rollouts, or a results file:

```
simple-agents report runs/ --since 2026-08-14
simple-agents report evals/results/held-out-v3.json
```

`docs/run-envelope.md` §8.4 covers what it prints and what narrows it.

### 5.6 Scoring one step at a time, back to front

Per-node accuracy scores a step on the inputs it actually received, which is the thing under
suspicion when the end-to-end number is low. A judge that scores 0.9 on ideal candidates while
the pipeline scores 0.4 has lost the number upstream, and no figure over the real rollouts says
so.

**Back-to-front evaluation runs the last step alone on ideal inputs, then the last two, and so
on.** The rung where the number falls is the step that lost it. `Pipeline.slice` returns each
rung as a real pipeline:

```python
rung = pipeline.slice(start="judge")             # judge to the end of the pipeline
suite = EvalSuite(rung, examples.entering(rung), answer="answer", matches=exact)
results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41)
```

A rung runs, writes a trajectory and a manifest, and reports the eight rates like any other
pipeline. `start` and `end` are inclusive and either may be left out:

```python
pipeline.slice(start="judge")                    # the tail from a node
pipeline.slice(end="select")                     # the head up to one
pipeline.slice(start="select", end="judge")      # the span between two
pipeline.slice(start="judge", end="judge")       # one node alone
```

`nodes` names the set instead, for a branching graph where two bounds cannot say which arm is
wanted. It cannot be combined with `start` or `end`:

```python
pipeline.slice(nodes=["select", "judge", "present"])
```

#### What a rung is run on

`ExampleSet.entering` derives it. The ideal input to a step is the correct output of the step
before it, and `Example.expected_by_node` (§1) already carries that:

```python
examples.entering(pipeline.slice(start="judge"))   # inputs become the label for `select`
```

An example with no label for the node that was cut off is left out, the way one with no label
for a node is left out of that node's accuracy. Where the first node of the rung has more than
one predecessor, `inputs` is a `Join` of their labels, which is what that node receives in the
whole pipeline.

An example set built by hand works too, and is what to reach for where the ideal input is not
the label for a step: `Example(inputs=<what the step is handed>, expected=<what it should
produce>)`, evaluated against the rung. It is an ordinary example set, with its own splits,
contamination report and `content_hash`.

#### What the slice does at its edges

**An edge whose other end is outside the slice stays declared.** It is not removed, so the
nodes that remain see the graph they saw before.

A node that took a `Join` still receives one, with the arm that was cut in `Join.absent`. That
is what it receives in the whole pipeline whenever the route sent the run the other way, so the
rung measures the same path rather than an approximation of it.

A route may still select an arm the rung does not hold. The run ends there rather than being
sent down a surviving arm:

```python
results.metrics["accuracy"].left_out       # {'left_the_slice': 7}
results.nodes["select"].terminations       # {'left_the_slice': 7, 'finish': 43}
```

Those rollouts are outside every figure and the count is reported beside each one, the same way
a rollout whose question went unanswered is (§2.2). The run's manifest records `outcome` as
`stopped_early` and `stopped_early` as `left_the_slice`, and `Pipeline.run` on a rung raises
`LeftTheSlice` rather than returning a result.

A slice is refused for a node id the pipeline does not hold, for a set whose nodes are not all
reachable from the earliest of them, and for a set with more than one node that ends it. A
dotted id names a node inside a pipeline used as a node, which is a different graph: slice that
one.

#### Reading the rungs together

Every figure is over the rung's own examples, so the numbers are not comparable rung to rung
the way two evaluations of one pipeline are. What is comparable is where the loss appears.

Each rung's results file says which rung it is. `config.slice` carries the source pipeline's
`graph_fingerprint` under `of`, the node set, the bounds, what was dropped and every cut edge,
so rungs of one pipeline are joined on `of` rather than read as unrelated evaluations:

```python
results.config["slice"]["of"]        # the pipeline this is a rung of
results.config["slice"]["nodes"]     # ['judge', 'present']
```

**`reach` inside a rung is not `reach` in the pipeline.** The rung's first node runs on every
rollout, where the whole pipeline may reach it on 40% of them. Read the rung for whether the
step works on ideal inputs, and the whole pipeline's per-node `reach` (§5.1) for how often it
runs at all.

---

## 6. Running it

```python
from simple_agents.evaluation import EvalSuite

suite = EvalSuite(
    pipeline,
    ExampleSet.from_jsonl("evals/examples.jsonl"),
    answer="answer",
    matches=lambda s: s.answer.strip() == s.expected.strip(),
    contamination_threshold=0.8,
)
results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)
results.write()
```

`write()` with no path names the file after the evaluation, under `evals/results/`. Pass a path
to choose the name. A path that already holds a results file is refused, because a results
file is the only durable record of a measurement and the rollouts behind an overwritten one may
not be scoreable again: the pipeline moves, and `rescore` refuses a graph that has changed.
Pass `overwrite=True` to replace one.

`answer` names the field of the pipeline's output holding the answer, or is a function
returning it.

**`matches` has no default.** What counts as a correct answer is a decision about the task:
whether case matters, whether a longer span containing the answer counts, whether a date may be
written either way. A library default would decide it silently, and the project would score
against a rule nobody chose.

### 6.1 Rollouts and seeds

One rollout is one `Pipeline.run`, with its own run directory under `<run_dir>/eval/<eval_id>/`, its
own trajectory and its own seed. Each rollout's seed derives from the evaluation's seed, the
example's id and the rollout index, so one integer reconstructs the whole evaluation (FT-07).
Leaving `seed` unset generates one and records it.

Run directories are named for the example: `q29-3` is the fourth rollout of example `q29`. Two
example ids that would name the same directory are refused rather than overwriting each other.

**`eval_id` is derived from everything that decides what was measured.** The example set's
content hash, the seed, the split, `k`, the model, and everything the manifest records about the
pipeline: its `graph_fingerprint()`, the version of every prompt in it, and per node the sampling
parameters, the tools, `allow_unknown`, the context builder, the route, the finish check, the
fan-out, the declared model and the node's own budget, plus the budget of the pipeline and of
every pipeline used as a node.

So the same evaluation resolves to the same directory twice, and the second run is refused with
`UsedRunDirectory` rather than writing into it: a rollout appends to the trajectory it finds, so
a second evaluation there would produce trajectories holding two runs, in which every per-node
count doubles and the earlier run's calls are read into this one's cost. `resume_from=` is what
writes into a directory that already holds rollouts (§6.5), and `rescore` reads one without
running anything (§6.4). Two evaluations differing in any of those write into different
directories. A committed evaluation's directory names are stable across rebuilds.

`graph_fingerprint()` is narrower and answers a different question: whether stored state can
still be walked (`docs/run-envelope.md` §2.1). It is a digest of shape alone, so two pipelines
differing only in a temperature share one fingerprint and never share an `eval_id`.

`k=1` runs. Agents are stochastic and run-to-run variance on agent tasks is routinely larger than
the effect being measured, so a single rollout cannot tell a real improvement from noise (FT-05),
but k=1 can be legitimate at temperature 0 over fixed documents. The results file records `k`
beside an interval that will be wide, so the number carries its own qualification.

### 6.2 In parallel

`concurrency` runs that many rollouts at once, and defaults to 4. Rollouts are independent runs
and one cassette is shared across them, guarded by a lock.

**A hosted backend with a per-minute quota needs a pacing client in front of the adapter**, which
`docs/model-clients.md` §4 covers. Retries wait 31 seconds at the shipped defaults and each
rollout backs off on its own, so k rollouts wake into the same closed window.

Results do not depend on how many ran at once. Each rollout's seed comes from the example and the
index rather than from the order it happened to start in.

**That covers what the library holds, and not what a tool holds.** A rollout gets its own seed,
its own run directory and its own memory store. Anything else a tool reaches is the project's, and
rollouts running at once reach it together: a cache at module level, a connection, a counter, a
file the tool writes. A tool holding state across calls serves one rollout a value another rollout
put there, and the figure that comes out describes neither. Give such a tool state scoped to the
run, or set `concurrency=1` and say in the results why.

**A write that outlives the run is the sharpest case, and `concurrency=1` does not touch it.**
Rollouts execute real tools, so a pipeline ending in a write to the product's artifact writes
seeded results into what the end user reads, examples × k times. During an evaluation such a
write goes to the run's own directory: a `Deterministic` body writes under `ctx.workspace`, and
a tool writes through a `Workspace` handle (`docs/product.md` §5, `docs/tools.md` §3.2).

**`run_concurrency` is what each rollout's own run may overlap** (`docs/pipeline.md` §1.10), and
defaults to 1. An evaluation issues `concurrency × run_concurrency` calls at once, which is what
a pacing client is told, so an evaluation of a pipeline that fans out concurrently paces for the
calls it actually makes rather than for the rollout count:

```python
results = suite.run(envelope=env, model=client, split="held_out", k=5,
                    concurrency=4, run_concurrency=8)
```

Both are recorded in the results file's `config`.

### 6.3 An evaluation records its rollouts

**`suite.run` writes a cassette into `<run_dir>/eval/<eval_id>/cassette.jsonl`.** The rollouts are
what the money and the wall clock buy, and scoring is where the mistakes are: a metric that
raises, a `matches` that turns out to be wrong, a figure nobody thought to declare. With the
rollouts on file, each of those is applied again with `suite.rescore` (§6.4) or replayed for
free, rather than paid for twice.

An envelope that names a cassette of its own is left alone, so `Cassette.replay(path)` still
replays, `Cassette.off()` still records nothing, and a project that chooses its own path still
gets it.

**One file holds every rollout**, rather than one per rollout as a run outside an evaluation
writes (`docs/run-envelope.md` §3). A tool call is keyed on its arguments and not on which
rollout made it, so a replay of this file serves one recorded answer to all k rollouts of an
example. While `suite.run` records, each of those calls runs live and is written for the
replay. The recording that serves while it records is `suite.record` (§6.3.1), whose rollouts
buy one answer between them (FT-20).

```python
results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)
# runs/eval/eval_a1226bc495df/cassette.jsonl now holds every call the rollouts made
```

**What lands on disk, and the one reason to turn it off.** A cassette holds the request and the
response of every model and tool call, redacted under the run's rules before it is written, the
same rules and the same path as a trajectory record (`docs/run-envelope.md` §6). Redaction
matches known credential formats, field names that look sensitive, values named in `secret_env`,
and anything typed `SecretStr`. It does not know about a credential in a format it has no rule
for.

`record=False` is for an evaluation whose responses must not reach disk on those terms:

```python
results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41, record=False)
```

That evaluation cannot be replayed, so a mistake in the pipeline costs every rollout again. It
can still be re-scored: `rescore` reads each rollout's trajectory rather than the cassette, so a
`matches` that turned out to be wrong or a metric added afterwards is applied to the rollouts
already paid for (§6.4). Turning recording off removes the second copy and not the first: a
`model_call` record in each rollout's trajectory still carries the whole prompt and the whole
response. `Trajectory.sampled(0.0)` is
what keeps payloads off disk, and an evaluation refuses a sampled envelope (§7.8), so an
evaluation over material that may not be written is one the library will not run.

### 6.3.1 Recording without scoring

`suite.record` makes the live runs a replayed evaluation is served from: one run per rollout, at
the seed that rollout will use, all into one cassette, and returns what they cost. It separates
the runs from the number, which is what a `spends_money` tool needs (§7.2).

```python
from simple_agents import Cassette

made = suite.record(
    envelope=env.with_cassette(Cassette.record("evals/cassettes/held-out.jsonl")),
    model=client,
    split="held_out",
    k=5,
    max_spend=0.50,
)
results = suite.run(
    envelope=env.with_cassette(Cassette.replay(made.cassette)),
    model=client,
    split="held_out",
    k=5,
    seed=made.seed,
)
```

`split`, `k` and `seed` have to be the same on both calls, because a rollout's seed derives from
all three. `seed` comes back on the `Recording` for that reason: leave it unset on `record` and
pass what it returns to `run`.

**A call already on file is served rather than made again**, which is what makes this cost less
than the same rollouts run live. A tool call is keyed on its name, version, arguments and
occurrence with no seed in it, so the k rollouts of one example that make the same call buy one
answer between them. Model calls carry the seed, so each is made live and the variance across
rollouts is the real one.

`Recording` says what it cost:

| Field | |
|---|---|
| `cassette`, `seed` | What to pass to `run` |
| `examples`, `k`, `runs` | What was recorded |
| `paid_calls` | Tool calls that were charged for. Model calls are not counted here; each run's manifest carries its own |
| `spend`, `currency` | What the whole recording was charged, model calls and paid tool calls together, in the currency the paid tool calls were priced in. Measured, not declared, so a call a tool answered from its own cache counts in neither |
| `entries` | Distinct calls on file |
| `failed` | Runs that ended in an error |

A run that fails is named in `failed` rather than raising, so one bad example does not discard
the calls the others paid for. A recording with any entry in `failed` is incomplete, and the
rollouts replaying those examples will miss. A run that stopped to ask a person is not in
`failed`: `RunSuspended` reaches the caller (§7.4).

The envelope's cassette is `Cassette.record(path)` for a new recording or `Cassette.update(path)`
to fill in the calls an earlier one does not hold. `max_spend` means what it does on `run` (§7.2)
and is required wherever a `spends_money` tool is reachable.

### 6.4 Scoring rollouts that already ran

`suite.rescore` scores rollouts from their run directories. Nothing executes a pipeline, calls a
model or spends anything.

```python
results = suite.rescore(run_dir="runs/eval/eval_a1226bc495df", split="held_out")
results.write("evals/results/held-out-v3-rescored.json")
```

A rescore carries the `eval_id` of the rollouts it read, so `write()` with no path would land on
the file the original run wrote and be refused. Name a rescored file, or pass `overwrite=True`
where replacing the earlier number is the point.

`run_dir` is the evaluation's own directory, the one holding a directory per rollout, not the
`run_dir` the envelope declared. Each rollout's answer is read back from its trajectory and
compared with `matches` as it was live, so this is the path for three cases:

- **A metric raised.** A metric's `score` is called once per rollout, and one that cannot read
  what the agent produced ends the evaluation. The rollouts that ran are on disk and are scored
  from there once the metric is fixed.
- **`matches` was wrong.** What counts as a correct answer is a decision that gets revised, and
  revising it does not need the agent run again.
- **A metric was added afterwards.** A figure nobody thought to declare before the run is
  computed from the same rollouts.

**The answer read back is the output of the pipeline's terminal node**, rebuilt through the
schema that node declares, so `answer` reads it exactly as it did live whether it names a field
or is a function. A pipeline with two nodes that have no successor is refused at construction, so
which node that is never depends on which path ran.

**A re-score is refused when the rollouts came from a different pipeline.** Each run records the
digest of the graph it walked, and scoring rollouts from one shape under a suite holding another
reports a number for code that never ran (FT-15):

```
The rollouts in 'runs/eval/eval_a1226bc495df' were produced by a different pipeline: they record
graph_fingerprint sha256:92fd65fc295ccc2f, and this suite's pipeline is
sha256:6c9a99763bc5176c. A number scored from them would describe a shape that never ran, and
the results file would not say so (FT-15).
```

**And when they came from the same shape under a different configuration.** Each run also
records the sampling parameters, tools, `allow_unknown` and budgets it ran under, and the
refusal names the fields that differ rather than two digests:

```
The rollouts in 'runs/eval/eval_a1226bc495df' ran under a different configuration. The graph is the
same shape, and 2 field(s) that decide what was measured are not. A number scored from them
would describe a configuration that never ran, and the results file would carry this suite's
rather than theirs (FT-15).
  budget.max_steps: 12 -> 20
  nodes.hunt.sampling.temperature: 0.0 -> 0.7
```

A run directory written by an earlier version of the library records none of that, and is
scored rather than refused: nothing is concluded from an absent record.

**A partial set is scored and says so.** An evaluation that stopped leaves fewer rollouts than
the split has, and every figure is then over what ran:

```
2 example(s) x 3 rollout(s) on split 'held_out', seed 1308420538
  INCOMPLETE: scored 6 of 33 rollout(s), over 2 of 11 example(s) in this split. Every figure
  below is over what ran, not over the split.
```

`config.incomplete` carries the same counts, and `config.scored_from` is `"run_directory"`
rather than `"rollouts"`, so a reader of the file can tell without being told. **The floor is
over what ran too** (§4.2), so it sits under a figure computed at the same n and
`against_baseline` pairs the examples the agent answered.

**Three fields do not survive the round trip.** `concurrency`, `run_concurrency` and `max_spend`
describe running an evaluation and are `null`, since nothing ran. `seed` is one rollout's rather
than the evaluation's, because a rollout's seed derives from it and the derivation does not
invert; `config.seed_source` says `"rollout"` where that is what it is. Pass `cost_basis=` to get
per-node cost figures, since a basis is not recoverable from a run directory.

### 6.5 Resuming an evaluation that stopped part way

`rescore` scores the rollouts that ran. `resume_from` runs the ones that did not.

```python
suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
          resume_from="runs/eval/eval_a1226bc495df")
```

The rollouts already on disk are scored from their trajectories without running, and only the
missing ones are run. What comes back is the evaluation, with the same `eval_id` and the same
numbers a single uninterrupted run would have produced.

**The directory has to be this evaluation's own.** Its name is checked against the `eval_id`
these arguments produce. A rollout's seed derives from the evaluation's, so rollouts from
another evaluation answer different questions under different seeds, and mixing them would
report a number over a set that never ran together. A changed pipeline, prompt, split, k, seed,
model, sampling parameter, tool, budget or `allow_unknown` already produces a different
`eval_id` (§6.1), so it is refused here with a message pointing at `rescore`, which is the tool
for rollouts the pipeline has moved past.

**A rollout that never finished is run again**, and its directory is removed first. A kill
leaves a manifest with no `ended_at` and a trajectory holding part of a run; a rollout appends
to the trajectory it finds, so resuming into that one would produce a file holding two runs.

**The cassette the stopped evaluation wrote is continued rather than replaced.** The rollouts
that already ran keep the calls they bought, and the ones being run now are recorded beside
them. A call already on file is served rather than bought again, so a rollout that was killed
part-way replays what it had already paid for and buys only the rest. A model call carries the
seed it was sent with and a rollout's seed is its own, so a resumed rollout is never served
another rollout's response. An envelope naming its own cassette is left alone here as it is
everywhere else (§6.3).

### 6.6 Watching one while it runs

An evaluation writes its results file at the end and nothing before it, so a long one is silent
for its whole duration. Two ways to see into it.

**From inside**, as each rollout finishes:

```python
from simple_agents import ProgressBar

with ProgressBar() as bar:
    suite.run(envelope=env, model=client, split="held_out", k=3, seed=41, on_rollout=bar)
# eval_a1226bc495df:  36%|###6      | 12/33 [18:20<32:05, 8 correct, 3 missed, 1 failed, 0.0412 USD]
```

The number of rollouts is known before the first one starts, so this carries a proportion and a time remaining. A resumed evaluation starts where it left off, because `finished` counts what was read back from disk. Nothing is written where the stream is not a terminal. `ProgressBar` also takes the `on_progress=` of a single run (`docs/pipeline.md` §1.7).

`on_rollout=` takes any callback, and `RolloutProgress.describe()` is one line of the same figures:

```python
suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
          on_rollout=lambda progress: print(progress.describe()))
# 12/33 rollouts, 8 correct, 3 missed, 1 failed, ~18m left
```

`RolloutProgress` carries `finished`, `total`, `resumed`, the outcomes so far, `elapsed_s` and
`remaining_s`. `remaining_s` extrapolates from the rate so far and is `None` until there is one.
A callback that raises is reported as a warning and the evaluation carries on, because a bug in
a progress printer is not worth losing the rollouts to.

**On disk, while it runs.** The evaluation keeps `progress.json` beside its rollouts under
`runs/eval/<eval_id>/`, replaced whole after every rollout lands: the total it declared, how
many have finished, the outcomes scored so far, what they cost, and its estimate of the time
left. `simple-agents view --serve` reads it to follow the evaluation on the page
(`docs/view.md` §6), so a reader elsewhere gets the runner's own denominator rather than one
it guessed.

**From outside**, over the directory, with nothing of the project imported:

```python
from simple_agents import progress_of

progress_of("runs/eval/eval_a1226bc495df", expected=33)
# {'finished': 12, 'running': 2, 'expected': 33, 'done': False,
#  'outcomes': {'completed': 11, 'error': 1}, 'cost': 0.0412, 'currency': 'USD',
#  'unpriced': 0, 'elapsed_s': 1840.2, 'remaining_s': 3220.4}
```

`simple-agents watch` is the same reading as a display, which is what a second terminal usually wants:

```
simple-agents watch runs/eval/eval_a1226bc495df --expected 33
```

It returns once every rollout expected has finished. `--interval` sets how often it reads, and `--once` reads a single time and returns.

This reads manifests, so it works from another terminal while the evaluation runs, and on a
directory an evaluation left behind. `expected` is examples times k, which the caller knows and
the directory does not; without it, `expected`, `done` and `remaining_s` are `null`, because a
directory holding 12 rollouts cannot say whether that is all of them.

**`running` counts rollouts with no `ended_at`.** While an evaluation runs that is a rollout in
flight. Once it has stopped, it is one the stop interrupted, and `resume_from` runs those again.

### 6.7 What the directory name covers, and what it cannot

**`<run_dir>/eval/<eval_id>/` is named after what decides what was measured**: the examples and their
labels, the seed, the split, k, the model, and everything the manifest records about the
pipeline. Two evaluations that measured different things cannot write into one directory, and
re-running one into a directory that already holds rollouts is refused, because a rollout appends
to the trajectory it finds.

**The name is built from what the pipeline declares.** An edited prompt, an edited tool body and
an edited `Deterministic` node body all move it, because each is read off the source. Three
things do not:

- **Data a node reads.** A store, a corpus or a table that is rebuilt underneath an unchanged
  pipeline. Nothing in the library can see it.
- **A prompt whose text is not a function of the example**, such as one reading the clock or a
  sequence that is not pinned.
- **Anything under a version the project declared and did not move.** Declaring a version is what
  stops a cosmetic edit renaming every directory, and it also means the source is no longer what
  the name is built from.

**Declare a version where a node or a tool reads data that changes underneath it**, and change it
when the data changes:

```python
Deterministic(read_library, node_id="read", version="characterised-2026-08")
```

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY, version="catalogue-2026-08")
def look_up(title: str) -> dict:
    """Look one title up in the catalogue. Returns what the catalogue holds."""
    return catalogue.get(title)
```

Without one, an evaluation over the rebuilt data resolves to the first measurement's directory
and is refused as a used directory, which names the wrong cause; and `resume_from` reads the
earlier rollouts as this evaluation's and reports one figure over two versions of the data.

**A declared version that stayed put while the source moved is reported.** The hash is recorded
beside the declaration either way (`docs/run-envelope.md` §2.3), so `resume_from` and `rescore`
warn rather than refuse:

```
1 declaration(s) in 'runs/eval/eval_da7c892c5e86' name a version that has not moved while the
source under it has. The rollouts being read ran the earlier source, so a figure that changes
is attributable to nothing (FT-15).
  node 'read': version 'v1' held, source sha256:f6141e7a80af -> sha256:d9d67fa322c4
```

### 6.8 Comparing the prompts that were actually sent

**Every prompt is in the trajectory.** `prompt_differences` reads them back and reports where one
example was sent more than one:

```python
from simple_agents import prompt_differences

prompt_differences("runs/eval/eval_a1226bc495df")
# {'run_dir': 'runs/eval/eval_a1226bc495df', 'against': None, 'rollouts': 96, 'compared': 33,
#  'unreadable': 0, 'declarations': [],
#  'differing': [{'example': 'q1', 'node': 'hunt', 'item': None, 'distinct': 2,
#                 'across_runs': False,
#                 'prompts': {'sha256:aa4d52b117e0': ['q1-0', 'q1-1'],
#                             'sha256:42608933a241': ['q1-2']}}]}
```

The k rollouts of one example send one prompt to a node whose prompt is a function of the
example, so a node listed here is one where something else decided what was sent. What is
compared is the first model call of each node execution, per fan-out item: a later call in an
`AgentNode`'s loop carries what the model said, and varies for a reason the example does not
decide.

**`against` reads two evaluations and compares one example across both**, which is what sees a
change no declaration covers:

```python
prompt_differences("runs/eval/eval_new", against="runs/eval/eval_old")
```

`across_runs` says the two directories disagree rather than the rollouts inside one, and
`declarations` names each version declared alike in both whose source hash differs. Two
evaluations of one declared configuration produce one directory name, so pass the two
`run_dir`s their envelopes were given rather than one path twice.

**Pass one evaluation's directory, not the directory holding them.** A `run_dir` holding
`eval_*` directories carries no rollouts of its own, and an empty report over it would read as
agreement, so it is refused and names one of the evaluations under it.

**Nothing here decides whether a difference is a defect.** A prompt reading the clock, a tool
holding state across rollouts and memory that accumulates each produce one legitimately (§6.2).
A prompt that is a function of the example alone does not.

---

### 6.9 What each rollout runs against

A rollout executes the real code, so a step that writes a store writes it once per rollout.
§6.2 covers the case the workspace rule serves: a pipeline whose last step writes into the
product's artifact sends that write under `ctx.workspace`, and nothing reads it back.

**A pipeline that reads back what it writes is the case the workspace rule does not serve.**
Where excluding what a previous run already queued is production behaviour, an evaluation that
hid the write would measure a pipeline the product does not run. Sharing one store across
rollouts measures something else again: each rollout reads what the ones before it wrote. One
project ran 23 rollouts against a single database copy, and the count its exclusion step
blocked went from 45 to 279 across the run.

**`stores` says what happens to each store, one answer per store.** It is required on
`suite.run`, on `suite.record` and on `compare_variants` wherever a step declares one in
`touches=`. `record` runs the real code too, so a store its runs share is written once per
run before the evaluation that replays them has begun:

```python
from simple_agents.evaluation import CopyPerRollout, Shared

results = suite.run(
    envelope=env, model=client, split="held_out", k=5, seed=41,
    stores={
        "catalogue": CopyPerRollout("data/shows.db", as_input="db_path"),
        "embeddings": Shared("read-only; no step of this pipeline writes it"),
    },
)
```

`CopyPerRollout` copies the store before the rollout starts, puts the copy's path into that
rollout's inputs under `as_input`, and deletes it when the rollout ends, whether it passed,
failed or raised. A rollout that suspended keeps its copies, since the run is waiting and can
be continued; they sit inside that rollout's own directory, which `resume_from` removes before
running it again (§6.5). A step reads the path from `ctx.run_inputs["db_path"]`
(`docs/pipeline.md` §3.1). `Shared` says every rollout reaches the store as it is, and the
reason goes into the results file beside the figure.

**The path is added after the example set is hashed.** A copy that lands somewhere different
on each run therefore leaves `content_hash` and `eval_id` alone, and two evaluations still
compare. Putting the paths into the examples themselves is what stopped one project's
`compare()` from pairing two of its own runs.

**A step that declares no store is not covered by this.** `touches=` is what a node says about
the resources it reaches in its own code, so a step that reaches one and declares nothing is
invisible here, as it is on the drawings (`docs/view.md` §4). A tool's own `touches=` is not
read here either: a tool declaring `WRITES` has already said its writes stay inside the run
(§7.2).

**A copy is made per rollout, so a 51MB store over 23 rollouts is 1.1GB written and removed.**
`Shared` avoids that and reintroduces what the copies prevent, so it is the answer for a store
the pipeline reads and never writes.

**Two stores that would write over each other are refused before any rollout runs**: two
`as_input` keys the same, so only the last copy is reachable; and two resource names that file
their copy under the same path. A copy is filed under the resource name with anything but
letters, digits, `_`, `.` and `-` replaced, so `catalogue/v2` cannot nest a directory and
`../x` cannot write outside the rollout.

---

## 7. What an evaluation refuses to run

### 7.1 A split whose two sides overlap

The contamination check runs before the first rollout, and a split it flags is refused
(FT-03). Without that, the finding arrives in the results file the evaluation produced, and the
rollouts that produced it have already been paid for.

```
2 pair(s) of examples fall on both sides of this split at threshold 0.8, so a number
measured over it reports memorisation of material the dev side may be tuned against
(FT-03). This evaluation would be 200 rollout(s) producing that number.
  q7 (held_out) and q31 (dev) were both drawn from 'doc:kirkwall-history', so what was
  learned from one applies to the other.
  ...
```

Only pairs with one side in the split being evaluated are refused. An overlap between two other
splits cannot reach this number, so an evaluation of `held_out` runs while `dev` and `scratch`
share material. The results file records the whole report either way, so what was found is on
file whether or not it stopped the run.

`allow_contaminated_split=True` measures over it anyway. A suite given no
`contamination_threshold` runs no check and is not refused.

### 7.2 A tool whose effects reach outside the run

k rollouts over n examples repeat every action, and each rollout may repeat it several times.
The two classes that reach outside the run are separated by what a builder can do about it. A
`spends_money` tool runs under a declared `max_spend`. An `irreversible` tool does not run at
all. Neither is checked when the cassette is replaying, where the call is served from the file
and the body never executes (FT-20).

```
Evaluation refused to run: tool 'web_search' declared spends_money, and this evaluation is
200 rollout(s) (40 examples × 5), each of which may call it more than once. An evaluation
runs k rollouts over n examples, so every action a tool takes happens k×n times. Nothing
here says how much of that is acceptable, so the run would spend an amount decided by how
often the agent reaches for the tool: 'web_search' at up to 0.005 USD a call.

Say how much: suite.run(..., max_spend=0.50) is the most this evaluation may cost, model
calls and paid calls together, and it is checked before the first rollout. The cheaper path
is to buy each distinct call once: suite.record(...) makes the live runs and
suite.run(..., Cassette.replay(path)) replays them, and a repeated call is served from the
file rather than bought again.
```

**`examples × k` is the number of rollouts, not the number of calls.** One rollout can call a
paid tool as often as the agent reaches for it, so no figure derived from `DeclaredCost` bounds
what an evaluation costs.

#### `max_spend`

`max_spend` is the most the evaluation may cost, model calls and paid tool calls together. It is
checked before the first rollout and never binds part-way through one:

```python
results = suite.run(
    envelope=env, model=client, split="held_out", k=5, seed=41, max_spend=0.50
)
```

What makes it a bound is the pipeline's own budget. One rollout cannot pass `max_cost`, which
depletes on what a tool meters and on what a model call costs, inside a delegated pipeline as
well as outside one (`docs/pipeline.md` §2.5). So `examples × k × max_cost` bounds the
evaluation, and a `max_spend` under that figure is refused with both figures named:

```
Evaluation refused to run: 40 examples × 5 rollouts at max_cost=0.02 USD each can cost
4.000000 USD, and max_spend is 0.50 USD. The ceiling is checked here rather than during the
evaluation, so an evaluation that starts is one whose spend is already bounded.

Raise max_spend to 4.000000 USD, lower the pipeline's max_cost to 0.002500 USD, or run fewer
rollouts. A rollout can still pass max_cost by one model call, whose cost is known only
after it returns, and by whatever a tool meters above its own declared_cost.
```

A pipeline whose budget sets `max_cost=None` is refused for the same reason: one rollout is
unbounded, so k×n of them cannot be bounded either. `max_cost` needs a cost basis wherever a
model call is reachable (`docs/run-envelope.md` §4.4).

**Two things the ceiling does not cover**, both stated in the refusal rather than left to be
found. A rollout can pass `max_cost` by one model call, because a call's cost is known only
after it returns; bound one call with `max_output_tokens` on the node. And a tool that reports
spending more than its `DeclaredCost` declares passes it by that call's excess, because a tool
holding a `SpendMeter` is taken at its word (`docs/tools.md` §1.5). Declaring `max_per_call` is
what keeps the paid half exact, since the limit is checked against it before the call.

`irreversible` has no ceiling. An action that cannot be undone is not bounded by declaring how
many of them are acceptable, so the refusal names no way to permit it:

```
Evaluation refused to run: tool 'place_order' is declared irreversible and this evaluation
is 200 rollout(s) (40 examples × 5), each of which may call it more than once. An evaluation
runs k rollouts over n examples, so every action a tool takes happens k×n times. There is no
ceiling for this class, because an action that cannot be undone cannot be bounded by
declaring how many of them are acceptable.
```

The refusal covers the tools the pipeline can reach. A tool declared in a registry that no node
uses cannot run during a rollout, and refusing on it would refuse a project for a tool this
evaluation never touches.

A tool that takes a `ModelHandle` or a `Workspace` is re-run rather than served, so it could
repeat. It cannot be one of these two classes: declaring a handle beside `spends_money` or
`irreversible` is already refused at registration (`docs/tools.md` §3.2).

### 7.3 A cassette in `update` mode

An evaluation under `Cassette.update` would take some answers from the file and produce others
live, with nothing saying which rollouts were which. Use `Cassette.record` to measure against the
live backend and `Cassette.replay` to measure against a recording.

`allow_mixed_cassette=True` runs it anyway:

```python
suite.run(envelope=env, model=client, split="held_out", k=3, allow_mixed_cassette=True)
```

This is what `compare_variants` and `ablate` do. Their arms share one file so that the calls
common to two arms are made once, and the number they report compares the arms rather than
describing the backend. An evaluation whose number is read on its own wants `Cassette.record`
instead.

### 7.4 Suspension, and which evaluations meet it

An agent that consults can stop mid-run and wait for a person (`docs/pipeline.md` §1.8). That
does not happen during an evaluation replaying a recording: a consultation is served from the
cassette like any other tool call, so the channel is never reached and the recorded answer
stands in for the person. An evaluation given `end_user=` (§5.4) does not suspend either: the
stand-in answers in the call rather than stopping the run.

**A recorded answer is served to the rollout that recorded it.** A tool call is keyed on its
arguments, and a consultation's arguments hold the question the model wrote. Rollouts of one
example run at different seeds and ask different questions, so each one needs its own recorded
answer, and a prompt edit that changes the question is a cassette miss rather than a stale
answer. Recording an evaluation over a consulting agent therefore asks a person one question per
rollout.

An evaluation measuring against a live backend can stop. `RunSuspended` reaches the caller,
from `suite.run` and from `suite.record` alike, rather than being scored. The rollouts that
already finished are on disk with their trajectories, `suspension.json` holds what the stopped
one needs, and `resume_from` (§6.5) is what continues the evaluation once the person has
answered:

```python
try:
    results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41)
except RunSuspended as stop:
    queue.put({"run_id": stop.run_id, "question": stop.waiting_for})
```

Scoring it instead would report a total failure over a queue of runs that are waiting, with
`failure_rate` 1.0 and complete intervals around it.

### 7.4.1 A configuration error ends the evaluation

`ConfigurationError` fails identically on every rollout, so the first one is the whole of the
information and the other k×n are not paid for. `answer=` naming a field the output does not
carry is the commonest, and a client that reports no token counts on a streamed call
(`StreamUsageMissing`) ends the evaluation for the same reason.

Everything else a rollout raises is scored: `failed` where the backend answered and the agent
produced nothing usable, `no_response` where it did not answer at all (§2.1).

**A fan-out is no exception.** A `ConfigurationError` raised inside one item ends the
evaluation the way one raised anywhere else does, since it was wrong before the first rollout
started (`docs/pipeline.md` §1.5). `max_failures` ends that node's execution once the count of an
item's own failures passes it, which ends the rollout rather than the evaluation.

### 7.5 Streaming, which does not arise either

`EvalSuite.run` supplies no token sink, so a node declaring `stream=True` makes ordinary calls
during an evaluation (`docs/pipeline.md` §1.9). Nothing needs turning off, and a pipeline is
measured making the same requests whether or not the application renders its output live. A
recording made while streaming replays into an evaluation, since streaming is no part of a
cassette key.

A chain of thought is recorded during an evaluation whether or not anything streams, since it
comes off the response rather than off the stream (`docs/model-clients.md` §6).

### 7.6 A recording that answers one tool call two ways

A tool call is keyed on its name, its version, its arguments and how many times that same call
has been made in this run. It is not keyed on which rollout made it, which is what lets one
recorded answer serve all k rollouts that make the same call rather than the tool being
performed k times (FT-20).

Where the recording holds more than one response under one key, the tool answered the same
request differently, so replay would serve the first rollout's answer to every rollout and
report a number built on one rollout's value.

```
Evaluation refused to run: the recording answers one call to 'now' in more than one way,
under a single key. A tool call is keyed on its arguments and not on which rollout made it,
so replay would serve the first recorded answer to every rollout and report a number built
on one rollout's value.

A tool whose answer depends on anything but its arguments has to take a handle, which makes
it run again rather than be served: ModelHandle for a model call, Workspace for the run's
files, Memory for what the agent remembers, and Annotated[<type>, NodeInput()] for the node's
own input, which is what differs between one rollout and the next (docs/tools.md §3.2).
Record the cassette again once it does.
```

Model calls are not read this way. A hosted backend answering one request two ways is
ordinary, and the manifest's `cassette.diverged` count is what reports it (§5 of
`docs/run-envelope.md`).

### 7.7 A recording made at other seeds

A model call is recorded under the seed the request was sent with, and a rollout's seed derives
from the evaluation's seed, the example's id and the rollout index. A recording made at other
seeds misses on every model call of every rollout it does not hold.

**A missed rollout measured nothing.** Without this refusal the evaluation completes and every
rollout sorts as `no_response` (§2.1), so every rate has an empty denominator and reports
`undefined` with the count that was left out. The refusal arrives before the first rollout
instead, and names the recording as the reason.

```
Evaluation refused to run: the recording at 'evals/cassettes/held-out.jsonl' cannot serve
200 of 200 rollout(s). This evaluation runs at seed=41, and each rollout's seed derives from
it, the example's id and the rollout index; a model call is recorded under the seed it was
sent with. Those rollouts would miss on their first model call, fail, and be scored as
failures rather than raising, so the evaluation would report a rate measured over runs that
never happened.

Make the recording with suite.record(envelope=..., model=..., split=..., k=5), which runs
each rollout live at the seed it will replay at and returns the seed to pass here. Where the
recording already exists, pass the seed it was made at.
```

Recording at a larger `k` than the evaluation runs is fine: the seeds it does not need are
ignored. Recording at a smaller one is not, because the extra rollout indices name seeds the
file does not hold.

Two cases are not checked. A pipeline that makes no model call is served whatever seed its
rollouts run at, since a tool call's key carries no seed. And a cassette recorded before seeds
were stored names none, so nothing can be concluded from it either way.

### 7.8 A sampled trajectory

Per-node accuracy and `absent_outputs` are read back out of each rollout's trajectory, so an
envelope that drops payloads moves the numbers rather than the volume.

```
This evaluation runs through an envelope with Trajectory.sampled(0.01), which drops the
payload fields on most rollouts. Per-node accuracy and `absent_outputs` are read back out of
each rollout's trajectory, so a sampled evaluation reports numbers computed from records that
no longer hold what the nodes produced.

Pass an envelope with Trajectory.full() here, and keep the sampled one for production runs:
envelope.with_trajectory(Trajectory.full()).
```

The rate governs the rollouts' recordings too (`docs/run-envelope.md` §7), so this is also what
stops an evaluation recording rollouts it would then delete.

---

## 8. The results file

JSON, `eval_format_version` `0.30`. Each figure carries `population`, the sentence naming which rollouts it covers, and `over`, the same fact as the value that decided it, so a reader comparing two files does not parse a sentence. It carries what the number was and what produced it, so a
reader can tell what was measured without the code that measured it.

**`EvalResults.read` reads a file written at `0.28` or later.** The format is additive by
default, so a field a later version writes is absent from an older file rather than different in
it, and re-making a file costs k rollouts of real spend. A file below that floor is refused, and
the message says to re-run the evaluation. `simple-agents check` reads the JSON directly and goes
on reading an older file, reporting what it cannot join (FT-37).

**A figure the file predates is absent rather than empty, and the two are different answers.**
`format_version` is the version the file was read at, and `carries` says whether a named figure
was written in it, so a reader can tell a project that declared none from a file that predates
the field:

```python
results = EvalResults.read("evals/results/held-out-v2.json")
results.format_version                  # '0.28'
results.carries("node_ratios")          # False: written before per-node ratios existed
```

The names are `node_ratios`, a `ProjectRatio` reported per node (§11.5), and `slice`, what the
evaluated pipeline is a slice of (§5.6), both of which arrived in `0.29`; and `stores`, what
each store the pipeline reaches did during the rollouts (§6.9), which arrived in `0.30`.

| Field | Holds |
|---|---|
| `eval_id`, `created_at` | which evaluation this was |
| `config` | split, k, n, seed, concurrency, run_concurrency, the example set's content hash, its splits, which of them is held out, and its absent proportion, the version of the comparison that decided whether an answer was right, each criterion's text and the version of the check that decided it under `criteria` (§1.6), the declaration and version of every project metric under `metrics` and `node_metrics` (§11), `slice`: what the evaluated pipeline is a slice of, and `null` where it is a whole one (§5.6), the bootstrap parameters, the pipeline's nodes and the pipelines used as nodes, as the manifest records them (`docs/run-envelope.md` §2.1), a `graph_fingerprint` of the shape they were measured over, a `behaviour_fingerprint` of what produced them, which is `null` where a node takes the run's model and none was given (FT-37), the prompt versions, the tools every node can call and their side-effect classes, the model pin, the cost basis, the cassette mode and this evaluation's `hits`, `misses`, `recorded` and `diverged` counts, the budget, `max_spend`, `scored_from`, `seed_source`, and `stores`: what each store a step declares in `touches=` did during the rollouts, `copy_per_rollout` with its source and input key or `shared` with the reason (`docs/evaluation.md` §6.9) |

Three of those name how the number came to be rather than what it was measured over.
`max_spend` is the ceiling the evaluation ran under and is `null` where none was declared, so a
rate measured with a paid tool running live says what bounded it. `scored_from` is `"rollouts"`
for an evaluation that ran and `"run_directory"` for one scored from disk. `seed_source` is
`"evaluation"` or `"rollout"`, and a rescore adds `incomplete` where it scored fewer rollouts
than the split holds (§6.4).
| `examples` | per example: its split, whether its answer was absent, which conditions of its answer key expect absence under `absent_parts` (§1.6), its source, its `metadata`, any metadata key too large to write under `metadata_omitted`, and its `label` where the answer key is a single value. Every one of those is a key a figure can be grouped by (§8.2) |
| `metrics` | the eight rates and any project metric, each with its definition, its denominator, its unit, its interval, `left_out`: what it would have been over that did not measure the agent, keyed by cause, and `including_left_out`: the same figure with those counted as they scored (§2.2) |
| `criteria` | one figure per condition of a decomposed answer key, each with the criterion's text as its definition and `absent`: how many rollouts inside it left the condition unmet by asserting nothing about it (§3.1) |
| `nodes` | per-node metrics, including any project metric or ratio declared per node, what each node produced nothing with (§5), and the tools it called that never answered |
| `totals` | tokens, derived model cost, and `tool_spend` over the whole evaluation. Tool spend is what the tools were charged, over the calls that bought something, and is a sum rather than a rate, so it carries no interval. `cost.value` is `null` where any node's cost could not be measured; `cost.measured` is what the rest cost and `cost.unpriced_nodes` names the ones left out |
| `contamination` | what the near-duplicate check found, or `null` when no threshold was configured |
| `rollouts` | every rollout: its example, its index, its seed, its outcome, its answer, its `run_id`, its trajectory path, its project-metric scores, its `verdict` against the answer key, `left_out` where it is outside every rate's denominator (§2.2), and per node whether it was reached, whether it matched, and its per-node scores |
| `baseline` | one entry per example for what an agent that did nothing would have answered, in the same shape as a rollout, or empty where the suite declared no `baseline=` (§4.2) |
| `baseline_unscored` | the project figures whose own function no baseline answer reached, because `over` decided them without it. A figure over rollouts that asserted a value is one of these for a baseline that asserts nothing, and its floor describes the declaration rather than the answers (§4.2) |

```python
results = EvalResults.read("evals/results/held-out-v3.json")
[r.trajectory for r in results.rollouts if r.outcome.value == "false_confidence"]
```

The `run_id` and trajectory on every rollout are what make a surprising result findable. Without
them a failure noticed in the report cannot be re-opened.

`config.prompts` records the version of each prompt the runs used, and `config.nodes` each node
as the manifest records it, down to its sampling parameters and the tools it offered, so a metric
that moved between two evaluations has a candidate cause (FT-15). A change to a route moves which
nodes run at all. `config.matches` is versioned the same way: what counts as a correct answer
moves every rate, so an edit to it appears in `changed` beside a prompt edit.

`config.graph_fingerprint` is a digest of the pipeline's shape. A reader holding the results file
alone can ask whether the pipeline changed since the numbers were measured, without opening a run
directory. It is narrower than `eval_id` (§6.1), which digests the configuration as well, so two
results files sharing a fingerprint and differing in `eval_id` were measured over one shape under
two configurations.

Each project metric's score is on the rollout that produced it, so the numbers travel in the
file and a later comparison needs neither the labels nor the scoring functions (§11.6).

### 8.1 Reading it without parsing it

```python
print(results.report())
```

```
3 example(s) x 3 rollout(s) on split 'held_out', seed 41

  accuracy                   77.8%  [66.7%, 100.0%]  n=3 over all rollouts
  graded_accuracy            77.8%  [66.7%, 100.0%]  n=3 over all rollouts
  false_confidence_rate       0.0%  [0.0%, 56.1%]  n=3 over all rollouts
  partially_correct_rate      0.0%  [0.0%, 56.1%]  n=3 over all rollouts
  recall                     66.7%  [66.7%, 66.7%]  n=2 over rollouts of examples where a value exists
  abstention_rate            55.6%  [33.3%, 100.0%]  n=3 over all rollouts
  failure_rate                0.0%  [0.0%, 56.1%]  n=3 over all rollouts
  precision_when_asserting  100.0%  [34.2%, 100.0%]  n=2 over rollouts that asserted an answer
  span_f1                    66.7%  [66.7%, 66.7%]  n=2 over rollouts of examples where a value exists

  node        kind          reach                execs  calls  tools  model cost           tool spend
  hunt        agent         100.0% [44%,100%]        9     19     19  0.001038 USD         -
              span_f1: 100.0%  [34.2%, 100.0%] over 2
              ended: finish 9
  verify      llm           100.0% [44%,100%]        9      9      0  0.000338 USD         -

  correct 4, correct_abstention 3, missed 2
  intervals: Wilson score interval on a proportion
  intervals: percentile bootstrap, resampling examples, 2000 resamples
  contamination at threshold 0.8: clean
  calls: replay
```

`span_f1` is a project metric (§11), printed beside the eight and again under the node it was
declared for.

**A node that produced nothing carries it under its row**, with what it spent, so the figures of
§5 are read without opening the file:

```
  look_closer agent         100.0% [44%,100%]      102   1835    412  0.014204 USD         -
              produced nothing: 90 unit(s) of work, spending 1,689 of 1,835 model call(s)
              88 of those 90 made no tool call, consultation or delegation, spending 1,652 model call(s) (FT-35)
              3 call(s) came back with no content and no tool call
```

Every rate carries its interval and the n it was computed over, so no line of this can be quoted
as a bare percentage (FT-06). A rate with no denominator prints `undefined` and the reason rather
than `0.0%`. The per-node table carries `reach` for the same reason: `runs`, `calls`, `model cost` and
`tool spend` on that line are over the rollouts that reached the node, and reach says how many
that was. `tool spend` reads `-` where this node called no tool that cost anything. A
node with an accuracy prints it on its own line under the node.

**A rollout the backend never answered is named on every line it is missing from** (§2.1), so a
denominator that shrank says so where the figure is read:

```
3 example(s) x 3 rollout(s) on split 'held_out', seed 41

  accuracy                  100.0%  [34.2%, 100.0%]  n=2 over all rollouts, less 3 that got no response
  graded_accuracy           100.0%  [34.2%, 100.0%]  n=2 over all rollouts, less 3 that got no response
  false_confidence_rate       0.0%  [0.0%, 65.8%]  n=2 over all rollouts, less 3 that got no response
  partially_correct_rate      0.0%  [0.0%, 65.8%]  n=2 over all rollouts, less 3 that got no response
  recall                    100.0%  [20.7%, 100.0%]  n=1 over rollouts of examples where a value exists, less 3 that got no response
  abstention_rate            50.0%  [0.0%, 100.0%]  n=2 over all rollouts, less 3 that got no response
  failure_rate                0.0%  [0.0%, 65.8%]  n=2 over all rollouts, less 3 that got no response
  precision_when_asserting  100.0%  [20.7%, 100.0%]  n=1 over rollouts that asserted an answer, less 3 that got no response

  correct 3, correct_abstention 3, no_response 3
```

Where the backend answered nothing at all, every rate prints `undefined` with the count rather
than a rate over runs that never happened:

```
  accuracy                  undefined: No rollouts fall under all rollouts, so this figure has
                            no denominator. 9 rollout(s) got no answer out of the backend and
                            are outside it.
```

### 8.2 Every figure, grouped by a property of the example

A headline is a mean over whatever mix of examples the split holds, so it moves with the mix as
well as with the agent. A change that improved one kind of example and damaged another reports
no change at all where the prevalence cancels them.

```python
results.groupable()                 # ('genre', 'label', 'source', 'split')
results.grouped("label")["shelve"].metrics["accuracy"].interval.point
results.grouped("label")["shelve"].examples

print(results.report(group_by="label"))
```

The key is a field of the example entry or one of its `metadata` keys, and `groupable()` says
which this evaluation carries. `label` is there where the answer key is a single value. A key no
example carries is refused, and the refusal names what is groupable instead.

The cells come from the rollouts the file already holds, so a grouping can be chosen after the
evaluation ran. What has to be there before it runs is the key itself: a property put on the
examples afterwards changes the set's `content_hash`, and a comparison against evaluations made
before it then needs `allow_different_sets=True`.

A comparison groups the same way, and each cell is a full comparison over its own examples:

```python
comparison = compare(before, after, group_by="label")
comparison.metrics["accuracy"].moved              # False, pooled
comparison.groups["shelve"].metrics["accuracy"].delta
comparison.groups["skip"].metrics["accuracy"].delta
```

Every cell carries its own n, and one with fewer than 20 examples reports its figure and
withholds a verdict on the difference (§9). A thin cell is not a reason not to group: a figure
that cancelled in the pooled number was a measurement lost, and how many examples fall in a cell
is a property of the example set rather than of the library.

---

## 9. Between two versions

```python
from simple_agents.evaluation import EvalResults, compare

comparison = compare(
    EvalResults.read("evals/results/held-out-v2.json"),
    EvalResults.read("evals/results/held-out-v3.json"),
)
print(comparison.report())

comparison.moved                # ['false_confidence_rate']
comparison.undecided            # ['recall']: too few examples carry it
comparison.moved_nodes          # ['verify']
comparison.population_changed   # ['precision_when_asserting']: see below
comparison.changed              # {'nodes.hunt.sampling.temperature': [0.0, 0.7]}

change = comparison.metrics["false_confidence_rate"]
change.before, change.after      # 0.04, 0.16
change.difference.low            # 0.03, so the interval excludes no change
```

`report()` prints every metric with both point estimates, the paired difference and its
interval, and whether it moved, followed by the reason for any metric with no verdict and by
`population_note` for any whose denominator moved. A table written by hand from the attributes
above leaves those two out unless it asks for them.

**The interval is on the paired difference, example by example.** Two point estimates invite a
comparison the data does not support: 62% against 68% over twenty examples is a difference the
same agent produces twice in a row. Pairing cancels the fact that some examples are simply harder
than others and leaves the effect of the change, so `moved` is the question of whether the
interval excludes zero.

**A metric whose denominator depends on the agent covers different examples on each side.**
`precision_when_asserting` is over rollouts that asserted a value, and a change that makes the
agent abstain more takes examples out of it. Its two point estimates are then not two readings
of one quantity, and they can move while every example under the metric on both sides moves by
nothing. `comparison.population_changed` names those metrics and
`metrics[name].population_note` says how many examples each side carried. The paired
`difference` is the change.

`changed` names what differed in the two configurations, keyed down to the node and the field:
`nodes.hunt.tools`, `nodes.verify.sampling.temperature`, `prompts.hunt.version`. A metric that
moved with nothing in `changed` moved for a reason the results do not record, which is itself
worth knowing.

**A verdict needs 20 examples.** Below that `moved` is `None` rather than `True` or `False`, the
metric is named in `undecided`, and `metrics[name].verdict_reason` says how many examples carried
it. The delta and the interval are still reported; what is withheld is the claim that the
difference would hold on other examples.

```python
change = comparison.metrics["accuracy"]
change.delta                     # -1.0
change.moved                     # None
change.verdict_reason            # '3 example(s) carry this metric and a verdict needs 20. …'
```

Twenty is the count of examples, not of rollouts: k rollouts of one example move together and
resample together, so ten examples at k=20 is ten, not two hundred. Where every example moves the
same way the interval has zero width, which reads as certainty and is the sample having no
variation left to resample. One example produces that reliably.

**A changed scoring rule also withholds the verdict.** `matches` decides every outcome the eight
rates read, so two evaluations scored by different versions of it differ in the rule as much as
in the agent. Where `config.matches` differs, `moved` is `None` on all eight, `rule_moved` holds
both versions, and `verdict_reason` says so. §11.6 covers the same for a project metric.

```python
change = comparison.metrics["accuracy"]
change.rule_moved        # ['sha256:6b024a74f756', 'sha256:fc1dd6b639c8']
change.delta             # -0.44, and the rule moved, not necessarily the agent
```

**Project metrics are compared like the six**, on the scores each evaluation recorded (§11.6).

**Per node, reach and accuracy are compared the same way**, and reach is reported beside
accuracy:

```python
change = comparison.nodes["verify"]
change.reach.moved       # True: fewer rollouts reach it than before
change.accuracy.moved    # False: it is as right as it was, on fewer runs
```

Those are two different findings. A per-node number that moved because routing sent fewer
rollouts through the node is not the node getting worse, and reading accuracy alone does not
separate them. `accuracy` is `None` for a node no example labels. A node present in only one of
the two evaluations is left out of `nodes`, and its appearance or removal is in `changed`.

Two evaluations computed over different example sets are refused: the difference would mix a
change to the agent with a change to what it was asked, and a reader cannot tell which moved the
number. Pass `allow_different_sets=True` to compare the shared examples anyway.

---

## 10. Between two versions of the pipeline itself

`compare()` reads two results files that already exist. `compare_variants()` produces them: it
runs the baseline and every variant against the same backend in one session, and reports what
moved between each variant and the baseline.

```python
from simple_agents.evaluation import ablate, compare_variants

comparison = compare_variants(
    suite,
    {"hunt as one call": flattened_pipeline},
    envelope=envelope,
    model=client,
    split="held_out",
    k=5,
    max_live_calls=600,
    max_spend=5.00,
)
comparison.comparisons["hunt as one call"].moved      # ['accuracy']
comparison.plans["hunt as one call"].live_calls       # 2 per rollout, so 2 x 40 x 5 for the arm
comparison.write("evals/variants/hunt-as-one-call.json")
```

`max_spend` is the most any one arm may cost, checked before that arm's first rollout, and
is required wherever a `spends_money` tool is reachable, as it is for `suite.run`.

**A variant is another `Pipeline`.** Anything expressible as one is a variant: a different node
kind, a node added or removed, a tool added or removed, a prompt reworded, a temperature moved, a
rewired graph, a different model on one node. There is no separate edit language to learn, and a
variant the library cannot generate is one written by hand.

**`stores` is passed here rather than per arm**, and is checked against every arm's pipeline
before the baseline runs, so an arm whose steps reach a store the baseline's do not is refused
rather than raising once the baseline has been paid for (§6.9).

**`end_user` is passed here rather than per arm**, and every arm gets it, so an agent that
consults is compared against one reader rather than against whichever the arm happened to reach
(§5.4). Comparing the readers themselves is the other direction: one pipeline, one example set,
and a `SimulatedEndUser` per arm.

**Every arm but the baseline runs under `role="variant"`.** An arm is a pipeline the project
does not have, so its rollouts are not read as runs of the agent by anything that reads a run
(`docs/run-envelope.md` §2.1), and `runs("runs/", role="variant")` reads a sweep back. The
baseline keeps `agent`, because it is the pipeline the project has, run over the example set:
a project that has only ever swept still has runs to certify. `VARIANT_ROLE` is the value.

**Which step needs the expensive model is this measurement.** A node declares the client it
calls (`docs/pipeline.md` §2.4), so the variant that answers it is the baseline with one node
moved to a cheaper model:

```python
def build(reducer_model):
    return Pipeline(
        [
            Deterministic(load_docs),
            LLMNode(reduce_notes, output_schema=Notes, model=reducer_model),
            LLMNode(answer, output_schema=Answer),
        ],
        budget=Budget(max_steps=None, max_tokens=200_000, max_cost=None,
                      max_wall_clock_ms=300_000),
    )

comparison = compare_variants(suite, {"reduce_notes on the 1.7B": build(local)},
                              envelope=envelope, model=strong, split="held_out", k=5)
```

The baseline is `build(strong)` and the arm is `build(local)`, so the two differ at one node.

The plan marks that node `live` and everything it can reach `live` too, so the sweep pays for
the node under test and for whatever runs after it, and reads the rest off the baseline's
cassette. §10.1 covers which nodes those are. One arm may price in tokens and the other in
device-seconds, which needs a cost basis per model on the envelope (`docs/run-envelope.md` §4.1).

**Both arms run in one session.** The same pipeline run against a hosted backend on two different
days moves its own metrics, so a variant recorded today and compared against last month's results
file reports the difference between two days. Running the arms together removes that.

### 10.1 What the sweep will cost, before it runs

```python
from simple_agents.evaluation import plan_variant

plan = plan_variant(suite.pipeline, flattened_pipeline, name="hunt as one call")
plan.differs_at      # ('hunt',)
plan.changed         # {'nodes.hunt.node_kind': ['agent', 'llm'], 'nodes.hunt.tools': [['search'], []]}
plan.live_calls      # 2 per rollout
plan.replayed_calls  # 0 per rollout
```

A node whose own configuration is unchanged, and every node that can reach it too, issues the
requests it issued before at the same derived seeds. The baseline's recording answers them, and
the variant makes no call for that node at all. Everything else is called live.

So the cost of a variant depends on where it differs. Removing a terminal node changes no
request and runs entirely from the recording. Changing the first node of four re-runs all four.

`live_calls` is an upper bound: a changed node upstream can still produce the value it produced
before, in which case the request downstream is the one on file and it replays after all.
`replayed_calls` is a lower bound and is exact.

**`max_live_calls` refuses the sweep before the first call.**

```
This sweep would make at most 810 live model calls and max_live_calls is 400. Nothing has run yet.
  baseline: at most 630 live calls
  hunt as one call: at most 180 live calls, differing at hunt
  verify removed: at most 0 live calls, differing at hunt, verify
```

It counts live requests rather than money, because a project on a compute basis has no price per
call. Leaving it unset runs whatever the sweep costs.

### 10.2 `ablate()`

```python
comparison = compare_variants(suite, ablate(suite.pipeline), envelope=envelope,
                              model=client, split="held_out", k=5)
```

`ablate()` generates the standard downgrades: every `AgentNode` as an `LLMNode` with the same
prompt, schema and sampling and no tools, and every node whose removal leaves its successors a
value of the shape they had. It is a starting set, not the set of variants worth trying.

**Removing a node re-points every edge that named it at what it led to.** A node that ended the
run leaves its predecessor ending the run instead. A node inside a nested pipeline is removed
inside that pipeline, so it keeps its id and its container keeps its own budget, and the arm
pairs with the baseline node for node.

**`skipped` says which variants were not generated, and why**, so a node with no arm is
distinguishable from a node whose arm measured nothing:

```python
arms = ablate(suite.pipeline)
sorted(arms)     # ['hunt as one call', 'report removed', 'verify removed']
arms.skipped
# {'hunt removed': "no edge reaches it, so it is where the run starts and its input is what
#                   run() was passed rather than another node's output."}
```

The reason is a sentence rather than a code, and it comes from one of two places.

**Three are decided before the graph is built**, by asking whether removing the node could
measure anything:

- **No edge reaches it**, so it is where the run starts and its input is what `run()` was passed
  rather than another node's output.
- **It is the only node in the pipeline**, so removing it would leave nothing to run.
- **The node feeding it declares a different `output_schema`**, so the removal would hand its
  successors a value of a different declared shape and every rollout would fail there.

**The rest are the graph's own refusals**, in the graph's own words, because removing a node
re-points every edge that named it and the result has to be a pipeline. A predecessor left
holding two successors and no route, a `Loop(then=...)` whose target now leads to more than one
node, and an `on_error` pointing at the removed node all arrive this way. There are as many of
them as there are ways to declare a graph the library will not walk, so read `skipped[name]`
rather than matching on a fixed set.

A skipped variant is one to write by hand and pass to `compare_variants`.

### 10.3 What a variant arm's numbers are made of

A variant arm serves the calls the recording answers and makes the rest live, so its results file
carries `config.cassette.mode` of `update` and `nodes[].replayed_calls` beside
`nodes[].model_calls`. Read them together: an arm whose numbers are entirely replayed measured no
new backend behaviour, which is what makes it free.

The comparison itself is a paired difference, and the calls the two arms share are byte-identical
rather than two samples of the same request, so nothing the backend did between them enters it.

### 10.4 The written comparison

JSON, `variant_format_version` `0.3`. Per variant: the plan with what differed and where, the
`eval_id`, `graph_fingerprint` and `behaviour_fingerprint` of both arms, the full comparison
record, and the cost and tokens of each arm.

Read the two fingerprints together. `graph_fingerprint` covers the shape of the pipeline and
cannot see a reworded prompt, a moved temperature or a swapped model, so two arms differing only
in a prompt record the same value for it. `behaviour_fingerprint` is what separates them, and it
is the blind spot FT-37 closes for a headline.

The comparison nested under each variant carries `comparison_format_version`, and holds every
figure `compare()` computed: the metric changes, the per-criterion changes, each node, and each
cell of a grouping.

Cost is what `compare()` does not report and what a downgrade is usually for. The two figures sit
beside the metric deltas so a variant that cost accuracy and saved half the money reads as one
finding rather than two.

---

## 11. A metric the project declares

`ProjectMetric` is a figure the project computes from the answer: token overlap against a
labelled span, a numeric measurement within tolerance, how many of a structured answer's fields
were right.

```python
from simple_agents.evaluation import EvalSuite, Over, ProjectMetric

span_f1 = ProjectMetric(
    name="span_f1",
    definition="token overlap between the asserted answer and the label",
    score=lambda s: token_f1(s.answer, s.expected),
)

suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    metrics=[span_f1],
)
results.metrics["span_f1"].interval.point      # 0.71
```

It is reported beside the eight, with the same interval over the same resampling unit, in the
same block of the results file, and compared the same way between two evaluations. A name one of
the eight already has is refused, since one entry per name means one of the two would be reported
and the other dropped.

### 11.1 What `score` is given

One `Scoring`, which is the object every scoring rule in an evaluation is given: `matches`,
`node_matches`, a criterion's check (§1.6), and this.

| | |
|---|---|
| `s.answer` | what the rollout produced, or the node's recorded output where the figure is per node |
| `s.expected` | the value this call is about, and the criterion's own text inside a criterion's check. `s.example.expected` is always the whole answer key |
| `s.example` | the example, with its `inputs`, `metadata`, `memory` and `end_user` |
| `s.trajectory` | the path to what the run recorded, or `None` |
| `s.outcome` | how the rollout was sorted. `None` inside `matches`, `node_matches` and a criterion's check, which are what decide it |
| `s.criterion_id` | the condition being decided inside a criterion's check, and `None` everywhere else |
| `s.rollout`, `s.seed`, `s.run_id`, `s.node_id` | which rollout this is, and where it ran |

```python
ProjectMetric(
    name="cited_a_retrieved_source",
    definition="asserted answers whose cited source appears in a tool result",
    score=lambda s: float(s.answer.source in retrieved_in(s.trajectory)),
)
```

Reading the trajectory opens a file per rollout, so a metric that does it costs n×k file reads.

A rule that depends on who is being served reads the example, and is written once for the whole
set rather than once per person:

```python
matches=lambda s: s.answer.cost_centre == s.example.metadata["cost_centre"]
```

**Inside a `ProjectMetric` the scoring carries the verdict**, which is what the comparison with
the answer key produced. A figure over a decomposed key reads its parts, so conditions grouped by
a naming convention roll up into a figure per axis:

```python
def axis(scoring, prefix):
    parts = {k: met for k, met in scoring.verdict.parts.items() if k.startswith(prefix)}
    return sum(1 for met in parts.values() if met) / len(parts)

accuracy = ProjectMetric(name="accuracy_axis", definition="share of the accuracy conditions met",
                         score=lambda s: axis(s, "accuracy."))
```

`verdict` is `None` inside `matches`, `node_matches` and a criterion's check, which are what
decide it, and `None` for a rollout no comparison happened for.

### 11.2 Which rollouts it is over

`over` says which rollouts fall in the denominator. Under the first two, `score` is only ever
handed two asserted values, and the library reads absence.

| `over=` | The denominator | A rollout that put no value forward |
|---|---|---|
| `Over.VALUE_EXISTS` (default) | every rollout of an example whose label is a value | scores 0.0, `score` not called |
| `Over.ASSERTED` | rollouts that put a value forward, of examples whose label is a value | leaves the denominator |
| `Over.ALL` | every rollout | is passed to `score`, which handles it |

The first reads as "how close was it, overall" and the second as "when it answered, how close
was it". They are the same distinction `recall` and `precision_when_asserting` draw, and which
one is wanted is a decision about the task.

**Examples whose label is absence are outside the first two**, since a score comparing two
values has nothing to compare against on them. `Over.ALL` covers them, and there `s.answer` may
be `Unknown` or `None` and `s.expected` may be `Unknown`.

**A figure measuring what the agent refrained from wants `Over.ALL`.** Under the first two the
figure is decided without the project's function for every rollout that asserted nothing, which
is the whole population such a figure is about. `ProjectRatio` reads the same rule and defaults
to `Over.ALL` for it (§11.7). The do-nothing baseline is where this shows:
`results.baseline_unscored` names the figures no baseline answer reached, and `report()` says so
where the floor would be (§4.2).

### 11.3 The shape of the figure

A project metric is a mean over examples: each example's mean over its rollouts, then the
mean over examples, then the percentile bootstrap on that. That is what the interval is over.

A ratio of two totals is a different quantity, and `ProjectRatio` is what reports one (§11.7).
Cost per correct answer is total spend divided by the count of correct answers, and the mean over
examples of each example's own ratio does not equal it. `results.totals` and `results.nodes` carry
counts, tokens and cost over the whole evaluation, so a ratio over those is arithmetic on the
results file.

A yes-or-no comparison belongs in `matches`, which decides whether the rollout was correct and
therefore what all eight rates report. A `score` returning `True` is refused, naming `matches`.

### 11.4 Units

```python
ProjectMetric(
    name="tokens_per_answer",
    definition="tokens one rollout consumed",
    score=..., over=Over.ALL, unit="tokens",
)
```

`unit` defaults to `RATE`, which a report prints as a percentage. Anything else prints as the
number with the unit after it, so a cost reads `0.000153 USD` rather than `0.0%`. `unit=None`
is a bare number.

### 11.5 Per node

`node_metrics` reports the same figures per node, for the nodes an example set labels through
`expected_by_node` (§1):

```python
suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    node_metrics={"hunt": [span_f1]},
)
results.nodes["hunt"].metrics["span_f1"].interval.point
```

`score` is given the node's recorded output, its label for that node, and the rollout. Both the
output and the label carry `Unknown` where a value was absent, as they do for a node matcher
(§5.2). The denominator is the `over` denominator narrowed to the rollouts that reached the
node and carry a label for it. A node put a value forward when its recorded output holds no
absence anywhere in it, which is the same reading `absent_outputs` counts (§5).

The same `ProjectMetric` can be declared end to end and per node. They are two figures over two
denominators and are recorded in two places.

**A `ProjectRatio` is declared per node the same way**, which is where a figure counting things
the step handled rather than scoring what it produced belongs:

```python
unreadable = ProjectRatio(
    name="unreadable_pages",
    definition="pages that could not be read, over pages fetched",
    numerator=lambda s: len(s.answer["unreadable"]),
    denominator=lambda s: len(s.answer["fetched"]),
)

suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    node_metrics={"fetch_pages": [unreadable]},
)
results.nodes["fetch_pages"].metrics["unreadable_pages"].numerator   # 118
results.nodes["fetch_pages"].metrics["unreadable_pages"].value       # 0.175
```

The two totals are summed over the rollouts that reached the node and carry a label for it,
rather than averaged (§11.7), and each rollout's contribution is written to
`rollouts[].nodes[].ratios` as a pair. A results file written before `0.29` holds none, which
`EvalResults.carries("node_ratios")` reports (§8).

### 11.6 What is written, and what a comparison does with it

Each rollout's score is written into the results file at `rollouts[].scores`, and each node's at
`rollouts[].nodes[].scores`. A ratio's two totals go to `rollouts[].ratios` and
`rollouts[].nodes[].ratios` as a pair, because a ratio is summed rather than averaged. So the number travels with the file: `compare()` pairs on project
metrics without the labels and without the scoring functions, and a reader of the file needs
neither.

```python
comparison.metrics["span_f1"].delta      # -0.08
comparison.nodes["hunt"].metrics["span_f1"].moved
```

**A metric only one of the two evaluations reports is left out**, and the declaration that added
or dropped it is in `changed` through `config.metrics`.

**A changed scoring rule withholds the verdict.** `score` is versioned by a hash of its source,
recorded in `config.metrics`, and where the two sides differ `moved` is `None` and
`verdict_reason` names both versions. The two sides were scored by different rules, so the
difference between them is between the rules as much as between the agents. The same holds for
`matches` and the eight rates it decides.

```python
change = comparison.metrics["span_f1"]
change.rule_moved        # ['sha256:6b024a74f756', 'sha256:fc1dd6b639c8']
change.moved             # None
```

A value the function closes over is in the hash, so a tolerance captured by the factory that
built `score` moves the version when it changes. A constant the function reads from module level
is not, and neither is what a file it opens holds, so a rule whose threshold lives in either
changes without its version changing. Put the value in the function or in what it closes over, or
re-run both sides.

### 11.7 A figure that is one total over another

`ProjectRatio` reports a ratio of two totals, for a figure where the thing being counted is not
the rollout: picks inside an answer, pages a run read, pairs a judge decided.

```python
from simple_agents.evaluation import ProjectRatio

backlist = ProjectRatio(
    name="backlist_share",
    definition="picks from the backlist, over all picks",
    numerator=lambda s: len([p for p in s.answer.picks if p.backlist]),
    denominator=lambda s: len(s.answer.picks),
)

suite = EvalSuite(pipeline, examples, answer="answer", matches=exact, metrics=[backlist])
results.metrics["backlist_share"].numerator     # 118
results.metrics["backlist_share"].denominator   # 673
results.metrics["backlist_share"].value         # 0.175
```

Both halves take a `Scoring` and return that rollout's contribution. The library sums each over
the figure's population and divides.

**This is not the mean of each example's own ratio, and the two differ.** An answer returning 10
picks with 1 from the backlist and one returning 2 picks with 1 have contributed 2 of 12, which
is 0.167. The mean over examples of 0.1 and 0.5 is 0.30. `ProjectMetric` reports the second and
`ProjectRatio` the first; which one is wanted is a question about what the figure counts.

The interval resamples examples, summing both totals inside each resample, so k rollouts of one
example travel together as they do for every other figure. A ratio sitting exactly on 0 or 1 gets
Wilson's interval on the pooled counts instead, because every resample would draw the same value
and a percentile interval would read as certainty.

`over` says which rollouts the figure covers, as it does for `ProjectMetric` (§11.2), and defaults
to all of them. Each rollout's two counts are written to `rollouts[].ratios`, so the number
travels with the file and a comparison needs neither the labels nor the functions.

### 11.8 A figure that is a count over this run

A count is a census of what happened in these runs. Where there is a
denominator, declare it. A figure with an interval can be compared between two versions, and one
without cannot:

```python
ProjectRatio(
    name="dropped_no_measurements",
    definition="candidates dropped for having no measurements",
    numerator=lambda s: s.answer.dropped,
    no_interval="a count over this run, not an estimate of a rate",
)
```

`no_interval` holds the reason printed in place of an interval. The figure reports its total,
prints in a form that cannot be read as a measurement, and has its verdict withheld by a
comparison, which reports both numbers and says why it has none.

A `ProjectRatio` declaring neither a `denominator` nor `no_interval` is refused: a total reported
as though it were a rate is the failure FT-06 exists for. Passing `denominator=lambda s: 1.0`
reports the count per rollout, which is a rate and carries an interval.

FT-06 reads the declaration rather than the text. A figure reporting a value passes the check by
carrying an interval, or by declaring `no_interval`; a reason written beside a reported value with
no such declaration does not pass.

### 11.9 A figure over pairs, where there is no correct answer

Some tasks have no answer key. Which of two shortlists is better, which of two summaries reads
well, whether a reordering helped: nothing can be written in `expected`. What a person can say
is which of the two they would rather have.

A pair is two things and what each of them is. The judge sees `this` and `that`; a counting rule
reads `this_is` and `that_is`, so the order somebody was shown can be randomised without the
figure changing meaning:

```python
from simple_agents.evaluation import Pair, paired_figure, pairs_from_arms, read_labels

pairs = pairs_from_arms(before, after, before_is="baseline", after_is="variant", seed=41)
```

**How the pairs are formed is where the instrument's quality comes from, and the library fixes
nothing about it.** Pairing across a wide quality gap produces mostly pairs where neither side is
wanted, which says little about either. A bracket, where winners meet winners and losers meet
losers, resolves that by position rather than by asking a person to express it. `pairs_from_arms`
builds the one pairing the library holds both sides of, two versions of a pipeline over one
example set; every other pairing is a list of `Pair` the project builds.

**Pass `seed` wherever a person or a model is judging.** A judge shown one arm first prefers it
more often than chance, so a figure built without randomising the order measures the order as
well as the arms.

**The library holds no opinion about what a verdict says.** A project decides its own set, and
both counting rules are given the pair and the verdict:

```python
def chose(pair, verdict):
    if verdict == "prefer_this":
        return pair.this_is
    if verdict == "prefer_that":
        return pair.that_is
    return verdict

win_rate = paired_figure(
    pairs, read_labels("evals/labels.jsonl"),
    name="win_rate",
    definition="times the variant was preferred, of pairs with a preference",
    numerator=lambda p, v: chose(p, v) == "variant",
    denominator=lambda p, v: chose(p, v) in ("variant", "baseline"),
)
```

**A third verdict is usually two.** "Neither of these was wanted" and "both were good and I could
not choose" are different findings, and one figure cannot separate them. Recording them apart
costs a fourth verdict and reports both:

```
win_rate         7 of 14 pairs    50.0% [23.1%, 77.8%]
nothing_wanted  26 of 40 pairs    65.0% [50.0%, 80.0%]
```

Read together, those say the two arms are indistinguishable and that two thirds of what was shown
held nothing anybody wanted. The first figure alone reads as a tie; the second is the finding.

The result is a `Metric`, so it carries an interval, a population and its two totals like every
other figure, and `no_interval` declares it a count as it does on a `ProjectRatio` (§11.8). The
interval resamples `pair.unit`, which is the example a pair came from where it has one, so pairs
from one example travel together.

**Verdicts are read, never made here.** A judging pass or a labelling surface records them, the
way every other judgement is recorded (§12), so a figure over pairs is computed with no network
and reproduces on replay. `unjudged_pairs(pairs, verdicts)` is what that pass is handed, and a
figure computed while some are outstanding counts them in `left_out` under `unjudged`.

---

## 12. A condition a model or a person decides

Some conditions on an answer cannot be decided by code. Whether a reply promised a refund,
whether a summary is faithful to what it summarised, whether a recommendation honoured what the
reader asked for. A model or a person decides those, and a scoring rule reads the decision.

**A scoring rule never calls a model.** The judgement is made first and written to
`evals/judgements.jsonl`; scoring reads the file. Scoring runs again on every `rescore` and in
CI, so a model call inside it would need credentials on a machine that has none, spend money
every time a number is recomputed, and give a different answer on each pass.

### 12.1 Declaring a condition as judged

`Judged()` is registered in place of a check, in the same `criteria=` map that says how every
other condition is decided.

```python
from simple_agents.evaluation import EvalSuite, Judged

suite = EvalSuite(
    pipeline, examples, answer="answer", matches=exact,
    criteria={"cites_policy": names_a_section, "no_refund_promise": Judged()},
)
```

The condition's text is the question the judge is asked and the answer is what it reads, so
nothing else is declared. Construction succeeds with nothing judged yet, because a judgement is
about an answer and no answer exists until its rollout has run.

A judgement that reads more than the answer, or a figure that is not a condition on the answer
key, calls `Scoring.judgement` instead. It is reachable from every scoring seam.

```python
node_matches={"retrieve": lambda s: s.judgement(
    "are these passages relevant to the question?", over=s.answer)}
```

### 12.2 Running it

`judge=` on `run` does the rollouts, the judging and the scoring in one call.

```python
results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
                    judge=judge_them)
```

`judge_them` is given the whole list of judgements waiting and returns a `Label` for each.
What it does in between is the project's: one model call per answer, one call judging twenty, a
panel of three voting, or a rule that resolves the clear cases cheaply and escalates the rest.

```python
def judge_them(wants):
    result = judging_pipeline.run(
        {"wants": [{"question": w.question, "answer": w.material} for w in wants]},
        model=judge, envelope=env.with_role("labelling"),
    )
    return [
        want.label(verdict.met, decided_by=judge.identity().request_model,
                   reason=verdict.reason, run_id=result.run_id)
        for want, verdict in zip(wants, result.output.verdicts)
    ]
```

**Running the pass as a `Pipeline` under an envelope is what makes it recoverable.** `run_id` on
each judgement names the run holding the model, the prompt, the cost and the whole exchange
(§1.4). A judgement decided by a person carries `decided_by="human"` and the reason.

Where a person judges, the steps are separate and there are days in the middle. `run` refuses
with `UnjudgedAnswers`, which carries the worklist and the directory the rollouts are in, so
nothing has to be run again and no path has to be repeated.

```python
from simple_agents.evaluation import UnjudgedAnswers

try:
    results = suite.run(envelope=env, model=client, split="held_out", k=3, seed=41)
except UnjudgedAnswers as waiting:
    for want in waiting.wanted:
        print(want.describe())
        write_labels("evals/judgements.jsonl",
                     [want.label(input("met? ") == "y", decided_by="human")], append=True)
    results = suite.rescore(run_dir=waiting.run_dir, split="held_out")
```

`suite.unjudged(run_dir=..., split=...)` is the same list, for a session that comes back to a
directory later rather than catching the refusal.

### 12.3 What a judgement is keyed on

A judgement is filed under a digest of the example, the question and the material. Not under the
rollout it was read for.

Two consequences follow, and both are the point.

**The k rollouts of one example that produced the same answer are judged once.** They are one
entry in the worklist and one line in the file.

**An answer that changed has no judgement rather than an old one.** A verdict made in March
against March's answer cannot be found by an April answer that differs, so it is never applied to
it. A refusal that names a slot judged before, against different material, says so.

### 12.4 What happens when a judgement is missing

`run` refuses between the rollouts and the numbers, with one message naming every answer waiting.

> 431 of 600 answers have no judgement, so nothing decides whether they met the condition and no
> number can be reported.

Every rollout has finished and is recorded by then, so a refusal costs the run and nothing that
was paid for. The directory holds the rollouts, and `rescore` scores them once the judgements
exist. An unjudged answer is never scored as an absence: nothing having decided is a different
state from a decision that the answer said nothing (§1.6).

**A judging pass returns a `Label` for every request it is given, and raises where it cannot
decide one.** A pass that drops an item leaves it unjudged, and the refusal says so rather than
asking again. `Unknown` as a verdict is not the way to report a judge that failed: it says the
answer asserted nothing about the condition, and it is counted in `results.criteria[id].absent`
beside the agent's own silences.

### 12.5 The two files

| File | What it holds | When it changes |
|---|---|---|
| `evals/judgements.jsonl` | Every judgement this project has made | Appended to by each judging pass |
| `runs/eval/eval_<id>/judgements.jsonl` | The judgements one evaluation's numbers rested on | Written once, when that evaluation scored |

The store is what stops an unchanged answer being judged twice. The copy is what pins a reported
number to what decided it: `rescore` on a run directory reads that copy, so it gives back the
numbers that evaluation reported however the store has moved since.

The store is append-only and the last line for a key wins. A verdict corrected by hand is a later
line, so the correction is what the next evaluation reads and the original stays in the file with
`decided_by` naming the model that made it.

### 12.6 What the results file records, and what a comparison does with it

`config.criteria` carries `decided: "judged"` for a judged condition, the deciders and their
counts, the judging runs, and a digest of the judgements the numbers rested on.

```json
"no_refund_promise": {
  "text": "does not promise a refund",
  "decided": "judged",
  "n": 600,
  "decided_by": {"gemini-3.1-flash-lite": 583, "human": 17},
  "run_ids": ["run_20260818T090412Z_c4a1"],
  "judgements": "sha256:9f4c1e0a7d22c318"
}
```

**A changed set of judgements withholds the verdict**, as a changed `matches` does (§11.6).
Re-judging, correcting a verdict by hand and swapping the judge all move the digest, so
`compare()` reports that the rule moved rather than attributing the difference to the agent.

```python
comparison.metrics["accuracy"].rule_moved   # ['sha256:9f4c1e0a7d22c318', 'sha256:2a71bb03e419']
comparison.metrics["accuracy"].moved        # None
```

**Rewording the condition moves the digest as well.** The text is the question the judge was
asked and is inside the key each judgement is filed under, so rewording it leaves every
judgement unfindable and the condition has to be judged again (§12.3).

The report says which figures rest on judgements and who made them.

```
  criteria met
    cites_policy       0.93  [0.89, 0.96]  n=600  names the policy section it relied on
    no_refund_promise  0.71  [0.64, 0.78]  n=600  does not promise a refund
                       judged: gemini-3.1-flash-lite 583, human 17
```

**No check reads whether a judgement is right.** Whether a judge agrees with a person is not
checkable by the library, and `docs/failure-taxonomy.md` §10 lists what handles that instead.
What the file buys is that the judgement, its reason and its decider survive the session that
made them, and that a number moving because the judge changed is visible.

## 13. An example that is a conversation

A pipeline that reads a conversation (`docs/conversation.md`) is evaluated in one of two shapes. Both need a store on the envelope, and each rollout gets its own, holding what its example declares and nothing another rollout wrote:

```python
from simple_agents import ConversationStore, RunEnvelope

env = RunEnvelope(run_dir="runs/", conversations=ConversationStore("conversations/"))
```

### 13.1 What the agent has already been told

`conversation` is what was said before this example starts. The rollout is one run, the resampling unit is unchanged, and every figure means what it meant:

```python
Example(
    id="q4",
    inputs={"question": "What else did she write?"},
    expected="The Left Hand of Darkness",
    split="held_out",
    conversation=[
        {"role": "user", "content": "Who wrote The Dispossessed?"},
        {"role": "assistant", "content": "Ursula K. Le Guin"},
    ],
)
```

This measures what the agent does given a conversation. It says nothing about whether the agent builds a good one.

### 13.2 A conversation the rollout runs through

`turns` is what the end user says next, in order. The rollout is one run per turn against one conversation, and what the example expects is what the last turn answered:

```python
Example(
    id="q9",
    inputs={"question": "I need a book"},
    expected="The Left Hand of Darkness",
    split="held_out",
    turns=["Something under 400 pages", "Not grimdark"],
)
```

`inputs` is the first turn and each entry of `turns` is a later one, so the example above is three runs. A later turn's inputs are the example's, with the one key holding a string replaced by what was said, so a pipeline taking `question` and one taking `message` both work without the example naming the key. An entry that is a dict is used as the run's inputs whole, which is how a turn that changes more than one key is written.

**The turns run in sequence whatever `concurrency` says**, since turn 3 is answered against what turn 2 left behind. Rollouts of different examples still overlap.

Each turn is its own run with its own manifest, trajectory and budget, under `runs/eval/<eval_id>/<example>-<k>-t<n>/`, and each one records which turn it was (`docs/run-envelope.md` §2.1). So a three-turn example at k=3 is nine runs of real spend, and `plan_variant` and the cost of a sweep are read against that.

`suite.rescore(run_dir=...)` scores the last turn of each rollout, read from what each run recorded rather than from its directory's name.

**What this measures that §13.1 does not** is how the conversation develops: whether the agent asks the same thing twice, whether it keeps what it was told on turn 1, whether it converges. A criterion reading the whole conversation is what scores those (§12).
