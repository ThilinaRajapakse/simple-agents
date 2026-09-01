# Build log — what elicitation asks about the answer

`plan.md` §1 P3-11. Started 2026-08-17. Written while building, not afterwards.

`P3-11` is the elicitation half of `P3-10`: that build shipped four answer keys, a decomposed
one and a third outcome, and the questions a coding agent puts to the builder still asked for one
answer. The item's record was `items/eliciting-the-answer-shape.md` and its content is here now.

**Where it came from.** The read-and-verify pass after `P3-10` shipped, so it is that build's own
consequence rather than a new finding. It is also `P3-5`'s survey arriving from the other side:
[`answer-shapes.md` S3.2](../design/answer-shapes.md#L318) already listed `ground_truth` and
`answer_form` among the sites encoding the one-answer assumption and filed them as evidence rather
than as work. **`absence_vs_error` is not on that list and was found here.**

**One fact that governs how far this item could go.** `absence_vs_error`'s answer is read by no
code: nothing turns it into a threshold, and FT-24 reads whether it was answered rather than what
it says. So widening it moves a question rather than a number, and the same holds for both new
questions, whose answers reach the code only through what a builder then writes.

## 1. Before any design

| Checked | What it was |
|---|---|
| [`ground_truth`, `answer_form`, `absence_vs_error`](../../src/simple_agents/conformance/elicitation.py#L252) | The item's claim that nothing pins the wording, re-verified: the text appears in `elicitation.py` and in no test, no shipped document and no script. Every reference elsewhere is by `name` |
| [`presentation`](../../src/simple_agents/conformance/elicitation.py#L321) | *"What it needs from this answer is the shape of the output, which every node upstream is then built to produce"*, and [`procedure.md`](../../docs/procedure.md#L119) says the same. **So the output schema had two owners and the answer key had none** |
| [`Question`](../../src/simple_agents/conformance/elicitation.py#L32) | `ask` is *"the question in the words the builder reads"*; `scaffold` is *"what the coding agent does to make it answerable"*. Neither says whether the ask may be split |
| Scaffolds that already decompose | **6 of 38**, counted rather than estimated: `involvement`, `absence_vs_error`, `unproven_answer`, `improvement`, `watching_live`, `unevaluated_effects`. `absence_vs_error` issues four asks plus an offered scale |
| [`BriefEntry`](../../src/simple_agents/conformance/brief.py#L61) | `status`, `answer`, `deferred_to`. The answer is prose, and the glossary's design is prose values |
| [`_rules`](../../src/simple_agents/evaluation/compare.py#L696) | Reads `config["criteria"]` and compares each check's `version` alone. **The criterion text is recorded there and never compared**, so what catches an edited criterion today is `content_hash` over `expected` |
| `Example.expected_by_node`, `EvalSuite(node_matches=)`, `results.nodes[id].reach` | Three shipped seams, and **no elicitation question mentions any of them** |
| Per-node use across the dogfoods, measured | **49 results files, 4 to 10 nodes each, not one node accuracy and `node_metrics` empty in all 49.** `expected_by_node` appears in no example file and `node_matches=` in no evaluate script |
| `WORD_BUDGET` | 1750 in [`test_procedure.py`](../../tests/test_procedure.py#L73), against a file at 1749 words |

## 2. Design

The sitting of 2026-08-17 settled seven questions. The first is the one that changed shape under
Thilina's objection and is recorded in full.

### 2.1 Who owns "what makes an answer right"

**`answer_form` is re-scoped to the answer key, and `presentation` keeps the output form.** The
first proposal was a new `answer_key` question beside an unchanged `answer_form`; it was rejected
because it leaves two entries answering one thing. The measured case is
[`answer-shapes.md` S3.4](../design/answer-shapes.md#L351): dogfood #4's `answer_form` entry reads
*"A structured record per recommended book"*, which is the output and is true, while its
`expected` held one title compared by containment and nothing recorded that.

**The name stays.** `answer_key` was weighed and dropped: `docs/evaluation.md` §1.6 says a plain
value is not an answer key, so the name would be wrong for the answer most projects give.

### 2.2 The narrowness was wider than the item's record said

**Thilina's objection, which is what the item did not see**: three questions rewritten still
describe an evaluation where one run produces one answer, by one path, judged once. The
measurement in §1 is what it cost, and it is S3.4's mechanism a second time.

**Two questions were added rather than one.** The first draft was a single `what_is_judged`
asking about a step's own answer and about the path together. Thilina's objection was that one
question then has to ask for a lot at once and offer two selections, and it is the coding agent
that has to decompose it. Split into `judged_steps` and `judged_path`, each one yes-or-no with a
list behind it.

**The same test failed a draft of `absence_vs_error`**, which had three clauses in one sentence.
Its ask is one comparison over three points now, with the magnitude left to the scaffold that
already offers the graded scale.

### 2.3 The boundary, and it is a rule rather than a judgement call

**A question widens only as far as a surface that ships.** Two things the objection reaches are
past it, and both are recorded rather than answered:

- **A run whose right behaviour is to ask rather than answer** (the survey's J3). Nothing scores
  it; it is P3-9's.
- **A figure over the whole evaluation rather than per example** (I1). `plan.md` §2.1, accepted
  and unscheduled.

Asking a builder either produces an answer nothing can act on, which is the defect this item
exists to fix, one layer along.

### 2.4 What is not built, and why

**The brief does not record the key structurally and no gate reads it.** A `key = "criteria"`
field was weighed. `P3-10` already put the shape somewhere machine-readable that cannot drift
from what was scored: the key is a tagged object inside `expected`, in the JSONL file and in
`content_hash`, and `compare()` declines to attribute a difference to the agent when it moves. A
brief field is a second copy of that. A check reading brief against example set is FT-32's shape
and defensible, and it needs the copy to exist first.

### 2.5 A rule nobody had written down, found by Thilina asking whether it existed

Moving the magnitude from the ask into the scaffold raised the question of whether a coding agent
may decompose an elicitation question at all. **Nothing said.** `Question.ask` reads as verbatim,
6 of 38 scaffolds already run several exchanges, and the sentence that governs it in
[`procedure.md`](../../docs/procedure.md#L115) said *"Put each to the builder in their own
words"*, which can be read as the builder's vocabulary or the coding agent's paraphrase.

**Resolved toward the builder's vocabulary**, because `Question.ask` says the ask is the words the
builder reads, which leaves nothing to paraphrase. Stated in three places rather than one: the
`Question` docstring, `procedure.md` stage 2, and **the CLI header**, which carried the same
ambiguous sentence and is what a coding agent reads every time it runs the command.

## 3. Build

**No format moved and no check changed.** `elicitation.py` is data, so the only behavioural change
is that FT-24 now requires two more entries at `shape`.

**Surfaces touched.** `elicitation.py` (`Question`'s docstring, `ground_truth`, `answer_form`,
`absence_vs_error` rewritten, `judged_steps` and `judged_path` added, one sentence into
`who_labels`), `cli.py` (the `questions` header), `docs/procedure.md`, `docs/evaluation.md` §1.6,
`tests/test_procedure.py`, `scripts/build_conformance_fixtures.py`, and 15 fixture briefs.

**`shape` goes from 6 questions to 8, all required. 38 questions to 40.**

**The fixtures were hand-edited rather than regenerated**, and then checked against the generator.
Regenerating runs `suite.run` and writes results files, which would sweep all 15 from results
format `0.13` to `0.14`; `random-thoughts-questions.md` records that as its own change. The patch
updated `ANSWERS` in the generator and applied the same text to the checked-in briefs, and
`_brief()` was then diffed against each file: **identical for all five variants**, so a later
regeneration reproduces them.

**Tests: 2348 to 2361.** Two are new and both read their expectations off the library rather than
transcribing them, so a renamed key leaves them failing rather than passing against a stale list:
one asserts every shipped answer key is named somewhere in the `shape` questions, the other that
`expected_by_node` and `node_matches` are.

**`WORD_BUDGET` moved 1750 to 1775**, against a file now at 1774. The budget exists so the skill
does not restate the documents; both additions are pointers into `docs/evaluation.md`.

**One thing changed while building.** The CLI header was not in the plan. It was found by running
`simple-agents questions --stage shape` to read what a coding agent sees, and it carried the
sentence §2.5 had just disambiguated in `procedure.md`.

### 3.1 A gap in `check_docs.py`, found because this build moved an item into a build log

`check_shrinkage` follows a moved file before calling it a deletion, and it matched on the
**basename alone**. `CLAUDE.md` requires a build log to carry a `-build-log` suffix, so
`items/<name>.md` becoming `build-logs/<name>-build-log.md` never matched. **That is the move the
conventions mandate on every built item**, and it is the one the check could not follow.

The cost is not the spurious warning. A move read as a deletion **skips the size comparison**, so
an item whose text was lost on the way into its build log reported the same as one that moved
intact, which is the failure the check exists to catch. Confirmed against this build's own move: a
gutted build log now reports *"dev-docs/items/eliciting-the-answer-shape.md ->
dev-docs/build-logs/eliciting-the-answer-shape-build-log.md is 100% shorter than at HEAD (4856
to 16 chars)"*, where it used to report a deletion.

Fixed by extracting `_moved_to`, which tries the mandated rename first and the basename second.
**Two fixtures**, and the self-test grew a way to run this rule: `check_shrinkage` needs a git ref,
so a fixture may ask for the copy to be committed before it is mutated. Verified non-vacuous by
reverting the rename branch, which leaves the first fixture silent at 28/29.

## 4. Verification

**Two backends, and the thing verified is not the code.** Nothing in this item has a runtime path:
the questions are data. What can be wrong is the **advice**, and `judged_steps` now tells builders
to use a seam that §1 measured as having zero use across four projects. So the harness builds what
the two new questions describe and runs it.

The pipeline branches: `read` extracts a retailer or reports absence and routes to `say` or
`no_retailer`, which rejoin at `done`. Six examples, four with a retailer and two without, k=2.
`expected_by_node` labels `read`; the answer key is `Criteria` with one condition about the answer
and one about the run.

### 4.1 Gemini, `gemini-3.1-flash-lite`, 12 rollouts

```
  node        kind          reach                 runs  calls
  read        llm           100.0% [61%,100%]       12     12
              accuracy: 100.0%  [61.0%, 100.0%] over 6
  say         llm           50.0% [17%,83%]          6      6
              ended: skipped 6
  no_retailer deterministic 50.0% [17%,83%]          6      0
              ended: skipped 6
  done        deterministic 100.0% [61%,100%]       12      0

  criteria met
    names_retailer  100.0%  [43.9%, 100.0%]  n=3  names Kirkwall Retail Ltd
    read_first      100.0%  [43.9%, 100.0%]  n=3  read the notes before answering
```

Both claims hold. **`judged_steps`**: `read` carries its own accuracy over the rollouts that
reached it and carry a label, and the two branch nodes each report `reach` 0.50 with their figures
over the six that reached them, which is the "runs on some inputs and not others" the scaffold
names. **`judged_path`**: `read_first` opened `s.trajectory` per rollout and returned a verdict,
judged in the same criteria list as the condition about the answer.

### 4.2 What the live run found, and it was in the harness rather than the library

**The first run scored `abstention_rate` 100% and every criterion undefined.** In a list, a node's
successor defaults to the next node, so `no_retailer` was `say`'s successor and the only node with
no successors, which made it the final node and its `Unknown` the run's answer on every rollout.
`docs/pipeline.md` §1 line 78 states the rule that was broken. **The library reported it
faithfully** and the report is what showed it: `say` ended `skipped 6`, `no_retailer` reached
12/12.

Two smaller ones, both the harness: a criterion read `record.record_type` on a trajectory record,
which is a `dict` subclass, and the refusal named the criterion, the rollout and the example; and
the harness printed `metric.interval.point` for a criterion with no denominator.

### 4.3 vLLM, `Qwen/Qwen3-1.7B`, 12 rollouts

A model two orders of magnitude smaller, and **the arm that shows what `judged_steps` is for**:

```
  read        llm           100.0% [61%,100%]       12     12
              accuracy: 66.7%  [33.3%, 100.0%] over 6
  say         llm           100.0% [61%,100%]       12     12
  no_retailer deterministic  0.0% [0%,39%]           0      0
              ended: skipped 12

  correct 8, false_confidence 4
  criteria met: names_retailer 100.0% n=4, read_first 100.0% n=4
```

The end-to-end rates say `false_confidence 4` and nothing about where. The per-node line says
where: `read` named a retailer on both absence examples, so its own accuracy is 66.7% and the
absence branch was **never reached on any rollout**, at `reach` 0.00 with `skipped 12`. The two
arms therefore disagree about the outcome and agree about every mechanism, which is the stronger
result: the same labels and the same path criterion localised a failure on the arm that had one.

**Two things about getting it to run.** The local arm appends `/no_think`, since the reasoning
parser is on and a 1.7B model thinks at length, and its basis is `ComputeBasis` rather than a
price.

**And one correction to a record, now spent.** The server first failed on
`FileNotFoundError: 'ninja'`, which
[`answer-key-build-log.md` §4.3](answer-key-build-log.md#L280) records as fixed by installing that
package. It was already installed inside the vLLM environment, whose `bin` is not on `PATH`, so
what got the run going was launching with that directory prepended. Thilina then installed `ninja`
system-wide, and the plain serve command in `docs/model-clients/vllm.md` §2 starts clean, which is
why nothing about this is in `handoff.md`.

## 5. Doc consequences

- **`docs/procedure.md` stage 2** carries the ambiguity fix and one sentence naming which of
  `answer_form` and `presentation` owns what. `WORD_BUDGET` moved with it.
- **`docs/evaluation.md` §1.6** names the brief entry that records the choice, so the two surfaces
  cite each other.
- `CHANGELOG.md` records the two new required questions, since a project on disk fails FT-24 until
  it answers them.
- **No shipped statement stopped being true.** The three rewritten questions were accurate about a
  library that had fewer answer shapes; nothing in `docs/` described them.

## 6. Left open

- **A check reading the `answer_form` answer against the example set.** FT-32's shape: the brief
  says any-of and every `expected` is a plain label. **Destination: `nothing`.** It rests on the
  brief recording the key in a form a check can read, which §2.4 decided against, so filing it as
  deferred work would file the consequence of a decision that was not taken. It starts from that
  decision being reopened.
- **A run whose right behaviour is to ask rather than answer**, the survey's J3. **Destination:**
  P3-9, which took it as half of its decision 2 and shipped the count rather than an outcome:
  [`build-logs/end-user-in-an-evaluation-build-log.md`](end-user-in-an-evaluation-build-log.md#L1)
  §2.6, with the outcome itself at [`plan.md` §2.1](../plan.md#L59).
- **A figure over the whole evaluation rather than per example**, I1. No question asks about it.
  **Destination:** [`plan.md` §2.1](../plan.md#L65), where a line was added to the count-or-total
  entry.
- **Negative weights, and a criterion that penalises.** Owed to §2.2 by `P3-10` and approved here.
  **Destination:** [`plan.md` §2.2](../plan.md#L101).
- **A criteria set declared once and referenced.** Owed to §2.2 by `P3-10` and approved here.
  **Its deciding condition was asserted twice and measured once**, which is the reason the entry
  reads as it does: a dogfood is scoped small on purpose, so example-set size says nothing about a
  real project's scale, and a dataset is not kept as code, so file-against-code is not a fork. What
  is true is that the set is a file, the shipped layout names it, and every project that built one
  generated it with a script. So the duplication is in the artifact and not in the authoring.
  **Destination:** [`plan.md` §2.2](../plan.md#L101).
- **Whether `ground_truth` should be two questions**, provenance separate from what is acceptable.
  Left at two halves because splitting it lands on `who_labels` at `build`. **Destination:**
  nothing; raised at the sitting and settled there.
