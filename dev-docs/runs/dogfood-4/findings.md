# Dogfood #4 — findings

Dogfood #3's task again, a book recommendation agent, against the wheel at `runs/dogfood-4/wheels/`.
`runs/dogfood-4/setup.md` is how it was set up and its §3.1 is what re-using the task costs.
**`runs/dogfood-1/findings.md`, `runs/dogfood-1/run2-findings.md`, `runs/dogfood-2/findings.md` and
`runs/dogfood-3/findings.md` are the earlier records and are not restated here**; this document cites
them. Findings numbered `DF4-Dn` and `DF4-Pn` are this run's. `DF3-` prefixed ones are dogfood
#3's, `DF2-` dogfood #2's, `R2-` dogfood #1 run 2's, and bare `D4`, `P1` run 1's.

**The run ran 2026-08-11 to 08-13 and this record was written 2026-08-14**, after it ended.

**The condition from `RULINGS.md` D5, and it governs every finding below.** The library moved
under this run. A full-test QA pass ran on 2026-08-13 against `2f4db4c`, and everything it found
is fixed and pushed: five blockers, fourteen major findings, and roughly forty false documentation
statements. **Every issue this run hit is checked against what has since been fixed.** §4.14 is
that check, blocker by blocker, and a finding that is already closed says so on its first line and
names the commit rather than being reported as open.

**Two questions were carried into this record specifically and are answered from what the run
shows.** §8.1 is consultation and the `Reply` matcher (`PENDING-SIGNOFF.md` item 6), and it
reports that the matcher cannot be decided from this run and why. §8.2 is whether
`compare_variants` fails on its own leading example (`RULINGS.md` D2's third cause).

**Project:** `/home/thilina/Projects/dogfood-4`. Fresh coding-agent session. The prompt was
`runs/dogfood-4/setup.md` §3's two sentences and nothing else. Nothing in this document was written
into the project.

Final totals across **3,293 run directories**: **22,475 model calls, 12,582 tool calls, 104
consultations, and $2.7055 of recorded cost** — $1.0057 of device time on a local Qwen3, $1.4356
under a per-model basis mixing that with Gemini, and $0.2643 of real money at Google.
`simple-agents check`: **0 failed, 11 passed at tier `evaluated`**.

| | dogfood #3 | dogfood #4 |
|---|---|---|
| Elapsed | ~15h50m *(inferred)* | **~47h13m** *(setup commit to last artifact write, with two overnight gaps)* |
| Runs in the envelope | 187 | **3,293** |
| Model calls | 1,722 | **22,475** |
| Tool calls | 4,029 | 12,582 |
| Consultations | 152, every one `declined` | 104, **97 recorded `answered`** and none answered by a person (`DF4-D12`) |
| Recorded cost | $6.6002 | $2.7055 |
| Nodes, and kinds | 10 (5 D, 4 LLM, 1 Agent) | 11 (7 D, 3 LLM, 1 Agent) in the last full run, after two whole pipelines; the evaluation harness is an 8-node subset of it |
| Model identities | 1 | **3** — Qwen3-30B, `gemini-3.1-flash-lite` and `gemini-3.6-flash`, at 20,531, 1,769 and 102 manifest-observed calls |
| Project tools written | 4 | 6 |
| Tier | `evaluated` | `evaluated` |
| `simple-agents check` | 10 of 10 | **11 of 11** |
| Brief entries | 30 | 26, all `answered` |
| Decisions recorded | none — the surface did not exist | **16**, across all six kinds; 10 `agreed`, 6 `changed` |
| Evaluations attempted | 8 | **33**, every one of which survives on disk |
| Build log | not asked for, not written | **not asked for, and written: 265KB** |

---

## 1. Method, and what the artifacts could and could not answer

**This run produced a build log without being asked**, so for the first time the artifacts and the
coding agent's own account of the work can be read against each other. They mostly agree. Where
they do not, §8.3 says which the artifacts corrected.

Every figure below is measured from the project's own artifacts unless it says otherwise. Where a
library defect is claimed, it is reproduced — against the project's wheel where the question is
what this run met, and against the current source where the question is whether it is still open.

### 1.1 The build log, which was not asked for and appeared

`runs/dogfood-4/setup.md` §4 removed the build log from the prompt deliberately: `docs/procedure.md`
line 38 tells the coding agent to keep one, and whether it does so unprompted is the measurement.

**It did.** `BUILD-LOG.md` is 265KB and 4,478 lines, written as the work happened, and it is the
best artifact any dogfood has produced. It records what was tried, what broke, what was measured
rather than assumed, two claims the coding agent retracted, and the builder's own words at every
turn.

**Three things qualify that.**

**It was not kept live without repeated intervention.** The log itself records a second reminder
at line 761 ("Both were warranted"), `handoff.md` says "the builder has asked five times and the
last two were not polite", `UI-KICKOFF.md` says six and "the last two were angry", and at line
2295 the builder had to write *"in case you've somehow switched to writing to the claude artifact
instead of the build log, stop doing that."* One shipped instruction, followed on the sixth ask.

**It does not carry the one figure `runs/dogfood-protocol.md` §1 wanted from it.** §4.1 names how long the coding
agent spent waiting on the builder as the figure that is on disk nowhere else.
`docs/procedure.md` asks for "each exchange with the builder as it happens" and says nothing about
timings, so the log records the exchanges and not their clock. **The waiting figure is gone for
the third run running**, and this time the log existed.

**It stops before the run does.** Its last write is 2026-08-13 13:35Z. The single most
consequential methodological finding of the run — a prompt that varied between processes at one
`prompt_version`, `DF4-D10` — is recorded only in `handoff.md` and in `noise_floor.py`'s module
docstring.

### 1.2 What the library was when this ran

**The wheel is `9dbe71b`, the commit that closed dogfood #3 and shipped the decision surface.
Fifteen commits landed after it while the run went on**, and the isolation held: the project's
wheel is still sha256 `7e35779…`, the figure `runs/dogfood-4/setup.md` §1.2 recorded, and the installed
copy carries no `Reply`, no `GeminiClient` and no `concurrent_nodes`.

Manifest `0.20`, trajectory `0.19`, results file `0.10`, 33 elicitation questions, 11 conformance
checks, 6 decision kinds.

What landed after it, and did not reach the run:

| | |
|---|---|
| `afffc88`, 2026-08-12 | the Gemini adapter, and `ToolCall.provider` to carry what its tool calls require back. **§6 is what this run then spent a session rediscovering** |
| `1178695`, 2026-08-12 | the typed consultation answer: `Reply`, `chose`, `on_reply`. **§8.1 is what the run says about it instead** |
| `2f4db4c`, 2026-08-13 | concurrency, `concurrent_nodes`, suspension format `0.4` |
| `d13e46e` onward, 2026-08-14 | the full-test QA fixes. §4.14 |

### 1.3 What this run destroyed, which is nothing

`runs/dogfood-protocol.md` §1 calls what a run destroys a finding in its own right, and dogfood #3 filled that
category with three deleted evaluations recovered from unreachable objects.

**This run destroyed nothing.** All 29 evaluations named by their `eval_id` have their rollouts on
disk, and every rollout directory has its results file; the two sets match exactly in both
directions. The three noise repeats are there too. The 26 rollouts whose cost never priced are
still there. The void `held-out-v2.json` is kept and marked rather than deleted.

It was asked to tidy up and argued against it, in its own words:

> They are the evidence behind every figure in this log, `simple-agents check` reads `runs/`, and
> **two conclusions today were overturned by going back and reading a trajectory** that a tidy-up
> would have removed.

Both overturned conclusions are in §8.3.

The project was committed once, at setup, and never again. `git log` therefore says nothing about
build order, and everything in §1 that carries a time is either a timestamp a run wrote, which is
a measurement, or a file modification time, which is marked as one.

### 1.4 One thing this analysis did to the project

Writing this record ran `uv run` once inside `dogfood-4`, which re-synced its virtual environment
from its own `wheels/` copy. The wheel's sha256 is unchanged, and the installed package still
carries none of the four features listed in §1.2 as absent. Nothing else in the project was
written to, and the store was read through `mode=ro&immutable=1`.

---

## 2. The ship criterion — `archive/plan-history.md` §3.3

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

**Met, at 11 of 11.** FT-30 is a check now and this is the first project to face it.

```
simple-agents check: .
tier evaluated, declared in brief.toml
  pass  FT-13  FT-14  FT-24  FT-29  FT-30  FT-01  FT-02  FT-03  FT-04  FT-06  FT-07
0 failed, 11 passed
```

**The report also carried `DF3-D6`'s note, which is that fix firing in the wild for the first
time**, and it is correct: the checks that read a results file are describing
`evals/results/eval_5680e78cdcfc.json`, and the checks that read a run are describing a noise-floor
rollout from a different evaluation nine hours later. §6 has it.

**What the criterion says nothing about, this time.** Dogfood #3's record said the criterion says
nothing about the agent being good, and added that it says nothing about the measurement being
able to tell. This run adds a third: **it says nothing about the artifact the end user sees.**
Eleven checks read a results file and a run directory. The product is a queue in a SQLite store
that no check, and no evaluation, ever looked at. `DF4-D1`.

---

## 3. The decision surface, first contact

`runs/dogfood-4/setup.md` §2 set six things to watch. All six are answered.

| Watched | What happened |
|---|---|
| **Does FT-30 change what the builder is shown?** The measure is not whether the gate passes; it is whether the builder still finds a decision in the code that they never saw | **Both.** Sixteen decisions were recorded across all six kinds and six came back `changed`, which is the mechanism working and is new. **And the builder still found two.** `DF4-D2` is the one that cost two days; `DF4-D6` is the one that cost 1,584 model calls |
| **Does `how_far` get asked before the design, and does its answer hold?** | Asked in the first round of elicitation, answered `measure` / tier `evaluated`, and it held: the tier never moved and the project reported a rate with an interval over a held-out split. **What did not hold is the scope**, and `DF4-D7` is that: 60% of the run happened after the last stage the procedure defines |
| **Does `involvement` do anything at all?** | **Yes, for as long as there were gates.** It was answered "a batch at each stage gate", and stages 1 to 3 each carry a batched elicitation table and a gate in the build log. After stage 4 opened there is no further gate, and every decision from then on was put to the builder because he was in the conversation. `DF4-D7` |
| **`DF3-D1`: if this run again reaches a green gate with a measurement that cannot move, the elicitation answer was not enough** | **The answer was enough.** §6 has it: the project computed a do-nothing baseline, found its first stage-4 measure uninformative *before* reporting it, replaced the measure, and then caught a split-prevalence artifact because the baseline was recorded per split. It is the clearest thing `DF3-D8` bought |
| **Is the `BUILD-LOG.md` line enough?** | **Enough to produce a log, not enough to keep it live.** §1.1 |
| **Does the decision record read as bureaucracy?** | **No, and the artifacts are unusually clear on it.** Sixteen entries, each carrying `considered` and a `because` that argues from measurement. Not one is a formality: the six `changed` ones record the builder overriding a recommendation, and `behavioural_constants` records a superseded value rather than deleting it. `involvement` shrank nothing, because the builder chose the middle option and then worked continuously anyway |

**The elicitation itself.** All 23 required questions are answered and 3 of the 10 optional ones
(`existing_solution`, `not_building`, `abandon_condition`). The two brainstorm optionals were
skipped for a stated reason — the opening statement carried what the agent receives, what it
produces and who receives it, which is what `what_it_does`'s scaffold says makes the exploratory
questions unnecessary. That is the scaffold being read and followed.

`one_real_input` did the thing it exists for, again: a 346-row export was obtained and read in
full before any node was designed, and three findings from it changed the design. `idea.md` is
current at `measure` and its "What is still open" section carries eleven live questions with
figures against each.

---

## 4. Library defects

### DF4-D1 — The artifact the end user sees is not what any evaluation measured

**Acted on:** `DF4-I06`, `DF4-I02`, `DF4-I20`.

**Open, and the largest finding in the run.** It was found by a second coding-agent session
working on a different task, reading the store rather than a results file, two days after the
project's own measurement first read green.

**What an evaluation measures here.** `EvalSuite` runs the pipeline once per rollout against a
seeded example and scores what it returns. **What the project produces** is a queue in
`library.gemini.db`, written by every version of the pipeline that ever ran, read by the
interface, and shown to the builder.

The two had drifted a long way apart, and the numbers are the finding:

| | empty `supports` |
|---|---|
| the store's judgements, which the queue reads | **22 of 26 — 85%** |
| a fresh evaluation at the same prompt version, the same day | **5 of 102 — 5%** |

Every empty one was dated 2026-08-12, written before prompt version 6 — the version that exists
*because* `supports` was coming back empty. The queue was showing the output of a pipeline that
had been fixed and re-measured twice since.

**And the defect the project had most carefully chased was live in it.** *Ninefox Gambit*'s only
support read *"Yoon Ha Lee's other works, including Revenants of the Liminal and The Raven
Tower"* — the first book does not exist, the second is Ann Leckie's. `Support`'s own docstring in
`recommender.py` names that exact string as the fabrication that motivated splitting `book` into
its own field, and the split does not catch it: `_verify_citations` checks `item.book`, this
judgement set `book` to unknown and put the titles in the prose, and nothing scanned the sentence.
So it carried no `[unverified: …]` marker, and the builder's `unproven_answer` decision — report a
weak case *marked* — silently did not apply to the one case it was written for.

**Nothing in the library or in the checks looks at this artifact.** FT-01 to FT-07 read a results
file; FT-13 and FT-14 read a run directory. `simple-agents check` read 11 of 11 throughout. The
evaluation cannot see it either: a rollout starts from a seeded example, so no rollout ever reads
the queue.

**What the project had to invent.** A `judgement.pipeline` column stamped from a single constant,
so "stale" is a query rather than a guess; and `rejudge.py`, because `load_work` selects books
with **no** current judgement, so a book judged once is never revisited however far the judging
step moves. Its own correction is the sentence worth keeping:

> An identifier for staleness is only useful with something that refreshes what it identifies.

**Closed inside the run, and the finding stands anyway.** The store today holds 19 judgements at
pipeline `10` with real citable arguments, `Ninefox Gambit` among them, and 13 caseless ones that
reach no queue: twelve rejects, and `Grass`, which carries the store's one and only verdict. What is not closed is that a project can reach full
conformance, on a sound measurement, while shipping an artifact assembled from every superseded
version of itself, and that nothing in the library gives it a way to notice.

This is the sharpest form of the builder's own note: *"there is no separation between the
evaluation and testing runs and the more 'production' level data the UI would need. And nothing
guides the coding agent to make this separation."*

### DF4-D2 — The narrowing that cost this project two days was recorded in the brief as an answer, and FT-30 passed over it

**Acted on:** `DF4-I03`.

**Open, and it is `DF3-D8`'s successor.** The decision surface was built to catch decisions the
coding agent made alone. This one it did not make alone: it asked, got an answer, and then read a
scope answer as a design.

Two brief entries, both answered at the brainstorm gate, both in the builder's own words:

> **`finished_version`** — "It replaces Goodreads outright, tracking shelves, progress and ratings
> locally. And it learns from the builder's verdicts, recording which recommendations were taken,
> dismissed or abandoned."

> **`not_building`** — "The browsing and shelving interface is out of scope until the output schema
> has settled — recommender first, UI after."

The coding agent read the second as *a recommender is a stateless run over a CSV*, and built that.
Every narrow decision downstream followed: a fixed eight-node pipeline that re-reads the export on
every run, holds nothing between runs, and ends in a node named `argue` whose schema carries
`argument`, `risk` and `fit` and **no field meaning no**.

Two stages, seven builds and a measurement later, the builder:

> "This sounds like you designed a stupid system. How is it agentic if it just finds some
> candidates and argues FOR them? The agentic part of the recommender should also look at my
> tastes, reading history, anything fucking else that helps, and judge the books based on that."

The coding agent then framed the queue architecture as *superseding* the shape decisions, and was
corrected again:

> "Then you asked the wrong questions or misunderstood my answers, because this is what I was
> trying to tell you to build."

**He is right, and the brief proves it.** The answer that made the built design wrong was recorded
on day one, one entry away from the answer that made it look right.

**What the checks read, and what they do not.** FT-29 reads whether `idea.md` has five sections
and whether `understanding_confirmed_at` names the current stage. FT-30 reads whether each of six
kinds has an entry and whether any is still `proposed`. **Neither reads one entry against
another.** `pipeline_shape` is recorded properly — `kind = "shape"`, `status = "changed"`, four
alternatives under `considered` — and the alternative that was right is not among the four,
because it is in `finished_version`, one stage up.

`docs/failure-taxonomy.md` §10 already names the neighbouring limit: *"Whether the record of
decisions is complete → a decision the coding agent did not notice making is one it did not write
down."* This is a different one and it is not in the list. The decision was noticed, recorded,
argued and agreed. What was never checked is whether it contradicted an answer the builder had
already given.

**What it cost:** the first pipeline entire, its evaluation, and the two days of build behind
them. The builder's own note is *"The design stage is still subpar."*

### DF4-D3 — A transport failure inside a fan-out is scored as an abstention, and the arm it broke reported the run's highest number

**Acted on:** `DF4-I10`.

**Open. This is `B4`'s family arriving through a path `D3`'s fix does not reach**, and §4.14 is
the check.

**Measured, from `evals/results/eval_6607cccf8b32.json`** — the Gemini arm at prompt version 3, on
`dev`, k=3:

| | |
|---|---|
| rollouts that produced no verdict | **15 of 102** |
| ...because the backend never answered | **14 of them**, free-tier 429s |
| `failure_rate` | **0.00 [0.00, 0.10]** |
| rollouts carrying an `error` in the results file | **0** |
| rollout `outcome` on all 15 | `missed` |
| `would_shelve_agreement` | **0.939 [0.85, 1.00]** — the highest figure the project ever produced |

The evidence is in the trajectory and nowhere else. `runs/eval_6607cccf8b32/sunbringer-1/`
carries a `model_call` record with

> `CallerFacingError`: `…/chat/completions rate-limited the run and 6 attempt(s) did not clear it
> (429: You exceeded your current quota…)`

and the `judge_each` node execution beside it carries no error at all.

**The mechanism, reproduced against the current source.** An `over=` fan-out collects an item
failure rather than raising ([`_Failures.saw`](../../../src/simple_agents/nodes/fanout.py#L481)), and at the
default `max_failures=None` ([`LLMNode.__init__`](../../../src/simple_agents/nodes/llm.py#L94)) it never
raises at all. A one-item fan-out whose model call raises `CallerFacingError` therefore produces:

```
run outcome: completed, no exception reached the caller
manifest outcome: completed
model_call error class: caller_facing
  node judge    termination=None     error=no
```

**So `D3`'s classification never fires.**
[`_outcome_for`](../../../src/simple_agents/evaluation/runner.py#L2728) is reached only when the run
raises, and this run did not. **And its second guard does not reach it either**:
[`_ended_on_an_unanswered_call`](../../../src/simple_agents/evaluation/runner.py#L2758) reads the *last*
model call, and `look_closer` called successfully afterwards, so even a raising version would have
been classified `failed` rather than `no_response`.

**Why it flatters rather than deflates.** `would_shelve_agreement` is declared `Over.ASSERTED`, so
the 15 rollouts that never reached a backend leave the denominator entirely, and answering 15%
less of the split at 0.91 precision on the rest reads as the best arm in the comparison. The
project caught it by reading trajectories at the builder's instruction, not from any number.

**And the cause was one of its own fixes.** Removing the `look_closer` spin (`DF4-D5`) took an
evaluation from 25 minutes to 2, which compressed 102 Gemini calls into a window the free key
would not carry. The build log's own summary is worth keeping: *"A performance fix turned a latent
infrastructure limit into a measurement artifact, and the artifact raised the headline rather than
lowering it."*

### DF4-D4 — `RetryPolicy` on a fan-out node is inert at the default, and the fix added to close a 2.3% loss did nothing

**Acted on:** `DF4-I09`.

**Open, and the same root as `DF4-D3`.**

**The loss it was meant to close, measured by the project across every recorded run:** **28 of
1,233 `judge_each` fan-out items — 2.3% — died on schema validation**, and only 2 of those were
Gemini's. Qwen had been losing about one book in fifty this way for the whole project, silently,
as an abstention.

`retry=RetryPolicy(attempts=2)` was added to close it and the build log claimed it had. It had
not, and the artifacts say so: `twilight-1` failed on `Invalid JSON: EOF while parsing a string`,
has **one** `judge_each` `node_execution` record rather than two, and became that arm's single
abstention.

**Reproduced against the current source.** A two-item fan-out with `retry=RetryPolicy(attempts=2)`,
one item failing its schema:

| `max_failures` | `judge_each` node executions | model calls |
|---|---|---|
| **`None`, the default** | **1** | 2 |
| `0` | 2 | 4 |

[`_Failures.saw`](../../../src/simple_agents/nodes/fanout.py#L481) returns without raising while the count is
within the limit, and [`RetryPolicy`](../../../src/simple_agents/graph.py#L92) re-executes a node only
when the node raises. Collecting is what makes retrying impossible, and the two are configured
independently.

**Neither surface says so.** `RetryPolicy`'s docstring is *"How many times a node is executed
before its failure is final"* and names two exceptions it never retries, both about the run rather
than the item. [`docs/pipeline.md` §2.2](../../../docs/pipeline.md#L633) says *"Without it, every item is
attempted and every failure is collected"*, which is true and reads as reassurance.

**What the workaround costs, stated by the project and worth keeping:** `max_failures=0` makes a
production batch of six re-run whole on one bad book, and turns a quietly dropped book into a run
that ends loudly.

### DF4-D5 — A node that spun to its step cap and did nothing spent 15% of the run's model calls, and nothing says so

**Acted on:** `DF4-I21`, `DF4-I22`.

**Open.** This answers the builder's own note — *"Can the library check for stupid shit that
happens? Like a node that just spins in the air doing nothing until it hits max steps?"* — with a
measurement.

Across all 3,293 run directories:

| | |
|---|---|
| node executions terminating on `max_steps` | **276** |
| ...of which made **zero** tool calls | **188** |
| model calls those 188 spent | **3,384** — median 18 each, which is exactly the node's cap |
| share of the run's 22,475 model calls | **15%** |
| the node responsible for 257 of the 276 | `look_closer` |

**The cause was three defects stacked**, and the project found all three:

1. A two-rollout FT-07 failure was patched by running the node on **every** rollout (`DF4-D6`).
2. The cost of the empty case was asserted as "one short call per batch" and never measured. It is
   18 calls, so the estimate was 18× wrong, and it was asserted in the same sentence that accepted
   the trade.
3. **The empty case could not finish.** Told *"Finish, reporting 0 judged"*, Qwen answered with a
   Hermes `<tool_call>` block one closing brace short, so the server's parser would not take it as
   a call and the node would not take it as an answer. Measured live, six samples each: the old
   wording parsed **0 of 6** at the default temperature and **0 of 6** at `temperature=0.0`, and
   naming the tool and its arguments outright parsed **5 of 5**. The wording, not the sampling.

**Everything needed to see this is already recorded and nothing aggregates it.** The
`node_execution` carries `termination: "max_steps"`; the tool calls carry `parent_id`. An agentic
node that reached its step cap having called no tool did nothing, at full price, and both facts
are in the file. `simple-agents check` read 11 of 11 through all of it.

### DF4-D6 — A routed-around node records no seed, so FT-07's cheapest fix is to run it on every rollout

**Acted on:** `DF4-I08`.

**Open. Reproduced against the current source**, and it is what produced `DF4-D5`.

[`_emit_skip`](../../../src/simple_agents/pipeline/core.py#L1912) writes `seed=None` for a node every edge
into which was absent. [`_unseeded`](../../../src/simple_agents/conformance/checks.py#L1552) exempts only
`deterministic` nodes, so a routed-around `LLMNode` or `AgentNode` reads to FT-07 as a node that
sampled without recording its seed:

```
  start      kind=deterministic seed=None      termination=None
  sometimes  kind=llm           seed=None      termination=skipped
  always     kind=llm           seed=7         termination=None
_unseeded(records) -> True
```

**What it cost here.** FT-07 failed on 2 rollouts of 108 because `look_closer` was routed around
when no book asked for a second look. The route was made unconditional, and the node then burned
its whole 18-step budget on 30 of 102 rollouts in one arm and **88 of 100 in another** — 1,584
calls in that arm alone, the largest single line item in the evaluation, buying nothing because
there was nothing to buy.

**The FT-07 objection is right and was re-verified rather than inherited**, both by the project and
above: a skipped agentic node is genuinely indistinguishable from an unseeded one in the record.
What the library offers is two options, and the cheap one is wrong.

**And the change was the coding agent's own, made alone to clear a gate.** The build log entry that
introduced it records no consultation, and no `[decisions]` entry covers it. It altered what the
agent does on every run. The builder found it two days later by asking what `look_closer` was for,
and the coding agent's own account is the right one:

> a two-rollout conformance failure was fixed by making an agentic node run on every rollout, the
> cost was estimated at one call without being measured, and the real cost is the largest single
> line item in an evaluation.

FT-30 passed at every gate through all of it. This is the second half of `DF4-D2`, and it is the
half the taxonomy's §10 already anticipates.

### DF4-D7 — The procedure ends at `measure`, and most of this project was built after it

**Acted on:** `DF4-I05`, `DF4-I01`.

**Open.**

| Day | Runs |
|---|---|
| 2026-08-11 | 106 |
| 2026-08-12 | 1,198 |
| **2026-08-13, after the last gate** | **1,989 — 60% of the run** |

Stage 4 opened on 2026-08-12 and `brief.toml`'s `stage` has read `measure` ever since. What
happened after the last gate the procedure defines: the judging node was redesigned into two
nodes, the store was rebuilt with 929 model-written characterisations, four model arms were run
against three model identities, a native Gemini adapter was written, a second session built an
interface, and the reported measurement moved from 0.41 to 0.89.

**`involvement` sets when decisions are surfaced at a gate.** With no gate after `measure`, the
answer stops governing exactly when the project starts moving fastest. Every decision recorded
after 2026-08-12 was put to the builder because he was in the conversation; the one that was not
is `DF4-D6`.

**This is not an argument for a fifth stage**, and the run does not supply one. What it supplies is
the measurement that four stages describe the smaller part of a real project's life, and that
every gate-driven mechanism the library has — `involvement`, FT-24, FT-30, the elicitation sets —
is inert across the larger part.

### DF4-D8 — Nothing reads the brief against the code, and it was wrong for a day

**Acted on:** `DF4-I03`, `DF4-I24`.

**Open.** This is the builder's note *"We need a go back and verify the code against the
brief/plan/whatever step"*, and the artifacts support it exactly.

Four entries described a pipeline that no longer existed:

| Entry | Said | Was |
|---|---|---|
| `behavioural_constants` | 12 candidates kept, 5 recommendations | 120 collected, 6 judged |
| `tool_effects` | three tools, all `read_only` | six tools, two of them `writes` |
| `agency_boundary` | discovery is deterministic | agentic, for a session |
| `results` | `held-out-v2.json` | a file the project had itself marked void |

All four were corrected only when the builder said *"Update the brief."* `simple-agents check`
read 11 of 11 before and after, "which continues to mean the artifacts are well-formed" — the
coding agent's own phrase, twice.

**FT-24 reads whether entries exist. FT-30 reads whether decisions are settled. Nothing reads
whether either is still true.** `docs/failure-taxonomy.md` §10 names the neighbour — whether an
entry records the builder's answer or the coding agent's summary of it — and not this. The
difference matters: whether a `because` is honest is a claim about prose, and whether
`tool_effects` lists three tools where the code declares six is a claim a check can make.

### DF4-D9 — A capability the builder asked for left the graph, and every check passed over it

**Acted on:** `DF4-I03`, `DF4-I26`, `DF4-I01`.

**Open, and it is the sharpest instance of `DF4-D8`.** `DF4-D8` is four brief entries whose text
went stale. This is a whole capability the builder was elicited on, agreed to, and never got.

`consultation` is the entry he was most expansive about, at the shape gate, in his own words, and
the record notes that he exceeded the options offered rather than picking one:

> "Disambiguating is good. But I would also say that it should be able to ask at points where it
> can't decide, has questions about taste, etc. etc. **I would give the agent quite a bit of agency
> on this.**"

It was built. `consult` went on the `hunt` node, the answer widened `agency_boundary`, and
**all 104 of this run's consultations came from that one node, on one day, 2026-08-11**.

**Then the back half was redesigned and consultation left the design.** The shipped queue pipeline
declares six tools across two agentic nodes and `consult` is not among them. Nothing marked it,
nothing missed it, and no later entry records the capability being dropped.

**Every surface the library has kept passing.** The `consultation` entry still reads `answered`
with his words in it. FT-24 reads whether the entries exist. FT-30 reads whether the decisions are
settled. **Nothing reads whether an elicited capability is still in the graph** — and the graph is
in the manifest, node by node, with the tools each node declares.

**The check that would have caught it is already specified, and is not built.**
[`docs/failure-taxonomy.md` FT-25](../../../docs/failure-taxonomy.md#L483) is
*"Consultation treated as a fault path"*, surface *"elicitation-only, **with a static occurrence
check**"*, and its check reads in full:

> The brief must answer "what must the agent ask the end user, and when?". If the answer is
> non-empty, **a consultation tool must be registered and reachable from the relevant nodes.**
> Whether the consultation points are the *right* ones is not checkable.

That is this project exactly: a non-empty answer, in the builder's own words, and no consultation
tool registered anywhere in the shipped graph. **FT-25 is not one of the eleven checks that ship**
— `checks.py` registers FT-01, 02, 03, 04, 06, 07, 13, 14, 24, 29 and 30 — and the only place it
appears in the source is as a citation inside an elicitation question's guidance
([`elicitation.py`](../../../src/simple_agents/conformance/elicitation.py#L287)) and in `consult`'s
own module docstring.

So the question this finding raises is narrower than it first looks. It is not whether an elicited
capability leaving the graph is checkable. **The taxonomy already says it is, and says how.**

**Why this is not the same finding as `DF4-D8`.** A stale `tool_effects` entry misdescribes what
was built. This is the builder answering a question, the answer shaping a decision, the decision
being superseded by a different decision, and the answer being silently orphaned by the
supersession. `queue_architecture` supersedes `pipeline_shape` explicitly and correctly, and it
carries no account of what the superseded shape was holding.

**The proposed shape of a repair, and it is deliberately not a design.** A point at which the
coding agent is prompted to re-check what has drifted: the brief against the code, an entry
against the entries that superseded it, and `idea.md` against both. FT-29 already asks for
`understanding_confirmed_at` to be re-set at every stage after re-reading `idea.md`, which is the
same instinct aimed at one file. What is missing is the pass that reads the rest, and where in the
procedure it fires. `DF4-D7` is why "at a stage gate" is not on its own sufficient: 60% of this
project happened after the last one.

### DF4-D10 — Nothing checks that one prompt version sent one prompt

**Acted on:** `DF4-I19`, `DF4-I23`.

**Open, and it qualifies most of the numbers this run produced.**

`_overlaps` sorted the shared-subject list by frequency alone, so ties fell back to **set iteration
order, which Python randomises per process**. The same book produced a different prompt in every
process, at one `prompt_version`.

**15 of 102 rollouts differed between two evaluations for this reason and nothing else.** Part of
the spread across the four model arms — 0.88, 0.89, 0.90, 0.91, 0.92 — is this rather than the
changes each was attributed to.

**It was found only because the project built a noise-floor harness by hand.** Three identical
`dev` runs of one configuration, nothing changed between them, returned **0.929, 0.889 and 0.899 —
a range of 0.04**, and the project adopted a standing rule that no difference smaller than that is
read as a difference. That rule then killed one of its own proposals: a work-identity node was
rejected partly because "the noise floor on this project is 0.04, so an improvement of that size
could never be shown".

**The library has everything needed to catch it.** Every prompt is in the trajectory, with the
declared `prompt_version` beside it in the manifest, and k rollouts of one example send
byte-identical prompts to a node whose prompt is a function of the example. Nothing compares them.
FT-15 is the taxonomy entry for this class and the check that exists reads the version rather than
the text.

**The library's own refusal fired correctly on the neighbouring case** and is worth recording
beside it: re-running with a changed prompt at the same declared version was refused, because the
evaluation directory derives from the version. What it cannot see is a prompt that changes without
anyone changing it.

### DF4-D11 — An evaluation's identity does not include the data the pipeline reads

**Acted on:** `DF4-I07`.

**Open, and it is the eval-identity family from a direction `D2`'s widening does not cover.**

The project rebuilt its store — 929 model-written characterisations replacing catalogue jacket
copy — and needed the same pipeline re-measured over it, which is the only way to separate the
characterisation effect from the model effect. Same graph, same prompts, same model, same
examples, different data: **the same `eval_id`**, and `_refuse_a_used_directory` would have
refused the re-baseline as a second write into the first measurement's directory.

**It was avoided by accident.** `retry=RetryPolicy(attempts=2)` landed in the same change and moved
the graph fingerprint, and the build log records the escape as incidental: *"That incidentally
solves the collision noted earlier."*

[`_eval_id`](../../../src/simple_agents/evaluation/runner.py#L1162) now covers everything the *pipeline
declares* — shape, prompts, sampling, tools, `allow_unknown`, budgets, per-node model. What decides
what was measured here is a SQLite file the pipeline opens, and `LIBRARY_DB` selects which one.

The library cannot hash a project's data source and should not try. What it has no surface for is a
project declaring one.

### DF4-D12 — A declined consultation is asked again, and answering the refusal records it as an answer

**Acted on:** `DF4-I01`.

**Open. A cousin of `DF3-D7`**, and the mechanism is new.

Run 2 of the build stage: **three of the hunt's twelve steps went on consultations nobody
answered.** A decline returns `None`, the model reads that as "not answered" and asks again, and
the node budget is what decides whether the run produces anything at all. That run crashed with a
null output.

**The project's fix was to make the channel answer the refusal**, in prose:

> "Nobody is available to answer right now. Do not ask again during this run: decide from the
> reading history on your own judgement, and note the uncertainty in your answer."

That is an answer as far as the library is concerned. **97 of this run's 104 consultations are
recorded `resolution: "answered"`, and not one was answered by a person.** `DF3-D7` shipped
`per_node.consultation_resolutions` precisely so a declined consultation would be visible in the
results, and this run defeats it honestly, by answering.

The two halves are separable and both are real: a decline that reads to the model as "ask again"
is a budget leak in the node least able to afford one, and there is nowhere to say "declined, and
do not ask again" without saying it as an answer.

### DF4-D13 — A tool parameter's `Field(description=...)` reached nobody

**Closed 2026-08-14 in `d13e46e`** (full-test `M1`), before this inventory existed, so it produced
no candidate and needs none. Met, and recorded because this run found it independently and its
evidence is the strongest anywhere.

The judging node's `record_judgement` took bare `list[str]` for `supports` and `weakens`, and
**every call came back `supports=[] weakens=[]`** — the model filling the fields, with nothing. The
rich guidance — *"0.5 means genuinely uncertain — use it, because the uncertain ones are what the
reader is shown to learn from"* — sat on a `Judgement` class no node used.

The project confirmed the cause by printing the wire schema, which is not something anyone does
unprompted:

```
without include_extras: {'tag': <class 'str'>}
with include_extras   : {'tag': Annotated[str, FieldInfo(..., description='hello')]}
```

[`_resolved_hints`](../../../src/simple_agents/tools.py#L1069) called `get_type_hints(fn)` without
`include_extras=True`, so `Annotated` metadata was stripped before the schema was derived, exactly
as the QA pass found. **The sentence the coding agent wrote about it is the one worth keeping:**

> had they been moved onto the tool as `Annotated` — the obvious fix, and the documented one —
> they would still have had no effect, and the failure would have looked like the model ignoring
> instructions rather than never receiving them.

**What it cost, and what it settled once worked around.** A day of attributing the empty reasoning
to the model, and a diagnosis that nearly ran an ablation with a broken instrument. Writing the
schema out by hand as `parameters=` — the documented escape hatch, which does work — moved
confidence from 0.90 on every book to a 0.4–0.9 spread within a single batch, immediately.

### DF4-D14 — Two evaluations differing only in a temperature or a tool share one `eval_id`

**Closed 2026-08-14 in `d13e46e`** (full-test `B5`), before this inventory existed, so it produced
no candidate and needs none. Met as a mechanism; **not met live**, and §8.2 is what that means for
`RULINGS.md` D2's third cause.

Reproduced against the project's own wheel, on the two variants
[`docs/evaluation.md` §10](../../../docs/evaluation.md#L1323) leads with:

| | `eval_id` |
|---|---|
| baseline | `eval_7c1cd1268d76` |
| `temperature=0.7` | `eval_7c1cd1268d76` — **same** |
| an `AgentNode` with no tool | `eval_649729af21eb` |
| the same node with one tool | `eval_649729af21eb` — **same** |

Against the current source both move it, so the fix holds.

**The run never met it**, because the wheel already folded each node's declared model into
`_eval_id`, with a comment naming the collision it prevents, and a per-node model is what this
run's arms differed by. Arms A and B wrote to `eval_eb44a057cb52` and `eval_1bd4d0b7c852`.

### 4.14 The five blockers, checked against what this run met

`RULINGS.md` D5 requires this and it is the reason it is a table rather than a sentence.

| Blocker | Met? | Evidence |
|---|---|---|
| **B1** `max_steps` does not bound a run that branches, or one that searches | **No** | The precondition is membership in a declared `concurrent_nodes` group, and `concurrent_nodes` shipped in `2f4db4c`, two days after this wheel; the installed copy has none. The retrieval half needs an embedding or rerank call inside a search node, and this project dropped both at the shape gate when the builder removed the `cut` node |
| **B2** A refused resume destroys the suspended run | **No** | **0 of 3,293 manifests carry a suspension.** No node declares `suspend_before`; the consult tool answers in-process |
| **B3** A resume into a pipeline used as a node discards the answer | **No** | Same. No pipeline was used as a node either |
| **B4** An evaluation cannot tell a suspension, or a transport failure, from a crash | **The transport half, and D3's fix does not reach it** | `DF4-D3`. 15 rollouts, 14 of them 429s, `failure_rate` 0.00, and the arm reported the run's highest figure. The suspension half was not met, for B2's reason |
| **B5** Two pipelines differing only in sampling, tools or budget share one `eval_id` | **As a mechanism, not live** | `DF4-D14` |
| **B6** `resume_from` is refused on the default recording path | **No** | The project never resumed an evaluation. It ran 33 of them and re-ran rather than resuming, which is its own small finding: `DF3-D3`'s resume half shipped and was never reached for |

**Of the fourteen major findings, one was met**: `M1`, which is `DF4-D13`. `M11` — `Reply`'s own
example being the case the default matcher rejects — is §8.1's subject and could not be met,
because `Reply` is not in this wheel.

---

## 5. Documentation bugs

### DF4-P1 — Nothing says a tool holding state is shared across rollouts, and one measurement was destroyed by it

**Acted on:** `DF4-I11`.

**Open.** The most expensive documentation gap in the run.

`check_candidates` kept accepted candidates in a module-level list. `EvalSuite` runs rollouts on a
`ThreadPoolExecutor`, so four rollouts shared it and each rollout's `read_library` cleared it while
the others were mid-hunt. Measured by the project over the 200 `check_candidates` results in the
recorded evaluation:

- **81 results contained books the rollout never proposed.** One `absent2` rollout was told it had
  accepted *The Broken Earth Trilogy*; an `absent5` rollout was told it held *The Left Hand of
  Darkness*, *Solaris* and *Hyperion*.
- **21 times the running count went backwards**, once from 22 to 4.

`still_needed` — the hunt's only stopping signal — was therefore computed from other rollouts'
progress. That is a corrupted control loop, and it invalidated `held-out-v2.json`, the
`would_shelve` 0.41 that `brief.toml` named as the reported measurement for the next two days.

**What the documentation says.** [`docs/evaluation.md` §6.2](../../../docs/evaluation.md#L572):
*"Rollouts are independent runs and one cassette is shared across them, guarded by a lock"*, and
*"Results do not depend on how many ran at once."* Both sentences are true of the library and both
read as reassurance about the project. **The word "thread" appears once in all of `docs/`**, in
`run-envelope.md` §6 about the cassette.

`Example.memory` isolates the store per rollout, which the full-test pass verified holds at
concurrency 4. Nothing isolates a tool, and nothing says so.

### DF4-P2 — `docs/pipeline.md` §2.2 never says what a fanned-out prompt receives

**Acted on:** `DF4-I12`.

**Open.** Every item of the first fan-out failed with `KeyError: 'description'`, and it was found
on a fake run rather than a paid one only because `docs/pipeline.md` §6 told the project to do that
first.

[`_fan_out`](../../../src/simple_agents/nodes/fanout.py#L216) calls the prompt with
`item_inputs = {**inputs, self.over: item}` — the whole input dict, with the `over` key holding one
item. [§2.2](../../../docs/pipeline.md#L612) documents `over=`, `FanOutResult`, `ItemOutcome`,
`max_failures`, `keep=` and `kept`, in that order, and never says what the prompt function is
called with. [`docs/context.md`](../../../docs/context.md#L16) says a fan-out sends *"that item's prompt
alone, once per item"*, which is about the conversation and reads as though the item is what
arrives.

### DF4-P3 — `docs/pipeline.md` §6 does not say that a fake run may not reach a node with its own model

**Acted on:** `DF4-I13`.

**Open**, and it made a test a lie.

The project declared `model=client` on every node — the technique
[`docs/model-clients.md`](../../../docs/model-clients.md#L24) recommends for running a cheap model on a
reduction step — and the run scripted against `FakeModelClient` went to the GPU and spent real
device time. A node's own client beats the run's, correctly and by design.

[§6](../../../docs/pipeline.md#L952) is careful about what a fake run cannot show: *"It cannot show what
a backend accepts."* It does not say that it may not be the thing that runs.

**And the cost did not stop there.** The project drew the wrong rule from its own bug and wrote it
into its handoff — "no node declares its own client, and it must stay that way" — which would have
blocked the per-node model swap that `docs/model-clients.md` recommends two lines later. The
builder caught it before it cost a session. The coding agent's own correction: *"The lesson was do
not blanket-declare, not never declare."*

### DF4-P4 — `too_similar` asks the builder for a number, and the scaffold that would have made it answerable was skipped

**Acted on:** `DF4-I14`.

**Open**, and it is the builder's first dogfood-4 note: *"It asked me a question about
contamination or something going from 0.8 to 0.4 or whatever. No context given, no defining the
terms. A random builder would have no idea what it was talking about."*

The shipped question is in two parts and only the second reached him:

> **ask:** What makes two examples the same example twice, and what threshold encodes that?
>
> **scaffold:** Run `examples.contamination(threshold=0.8)` and **show the builder the most similar
> cross-split pairs with their overlap. Ask which of them are the same example twice.** Record the
> threshold that encodes the answer.

The scaffold says to show pairs and ask a question about books. The `ask` ends by naming a
threshold. `brief.toml`'s answer records the number and the pairs — *"0.8, and the set is clean at
it. It is clean at 0.6 and 0.4 as well"* — and the builder's experience was of being asked for a
number in a vocabulary he had not been given.

**Nothing records or checks which half was used.** This is the same shape as `involvement`: the
library ships the right instruction and cannot tell whether it was followed.

---

## 6. What did not go wrong

**`DF3-D1` is answered, and the answer is that asking was enough.** This is the most important
entry in the section, because `runs/dogfood-4/setup.md` §2 named it as the open one.

The `measurement` decision kind asks what an agent that did nothing would score, and this project
answered it four times over:

- At stage 4 it computed a do-nothing baseline before reporting anything: **0 of 12 on exact
  recall, never abstaining**, and recorded the conclusion that *"that contest is uninformative
  rather than lost"* — the `DF3-D1` failure, caught before it was reported rather than after three
  paid measurements.
- It replaced the measure and put the new baseline **inside the metric definition**, so the figure
  cannot be quoted without it: *"the held-out split is 20 shelve, 14 skip and 2 absent, so always
  answering 'shelve' scores 0.56."*
- It then caught a defect the baseline made visible and nothing else would have: the two splits
  had baselines of 0.61 and 0.81, so *"reading one against the other nearly produced 'the agent
  has no skill' when a large part of the gap was the denominator."* The splits were rebalanced and
  per-class recall was reported beside the headline because that does not move with the mix.
- And it reported a regression against the baseline rather than tidying it away: the inferred-taste
  version scored **0.68 [0.52, 0.82]**, whose lower bound sits below 0.56, and the entry says
  *"recorded as a regression rather than tidied away, because it is the clearest thing this project
  has measured about its own prompts."*

**`DF3-D6`'s fix fired, on a real project, and was right.** Running `simple-agents check` today
prints the note: the checks that read a results file and the checks that read a run are describing
different measurements. They are — the brief names an evaluation from 02:54Z and the newest run is
a noise-floor rollout from 12:55Z. That is exactly the case the fix was built for, and it is the
first time it has fired anywhere.

**`DF3-D5`'s fix held.** 29 results files named by their `eval_id`, none overwritten, and 33
evaluations all still readable. Dogfood #3 lost its baseline to a deterministic filename.

**`DF3-D4`'s fix held.** 26 manifests never priced their cost, and the totals still carried the
measured part rather than collapsing to a single unknown.

**FT-09 fired three times and each was a real absence, not bureaucracy.** A judge's batch schema
with no way to say a book could not be assessed, so a dropped book would vanish silently
(`could_not_judge`); an ordering schema with the same hole (`left_out`); and `already_has_it` as a
bare `bool`, where a model that cannot tell would have had to guess, which became `Maybe[bool]`
with `unknown` *keeping* the book — the behaviour the builder had chosen at the build gate.

**FT-04 failed usefully.** A results artifact over the `dev` split contains no held-out examples,
so nothing in it has absence as the right answer, and the check said so. The methodology it forced
is the right one: the version was chosen on `dev` and confirmed on `held_out`.

**The mixed-basis refusal fired before the first call.** A run whose nodes call different models
is refused unless `cost_basis` is a mapping keyed by `request_model`, which is what made a run
priced across a self-hosted Qwen and a hosted Gemini produce **one figure — $0.0012, not an upper
bound and not null.** 759 manifests carry that basis. Per-node model selection and the cost basis
behind it work end to end, on a real project, which is their first exercise anywhere.

**`ablate()` ran on a real pipeline and answered the right question.** It generated three
downgrades — `look_closer as one call`, `ensure_characterised removed`, `report removed` — and
refused the rest **by name**, because removing them would hand a node a value of the wrong declared
shape. This is the first evidence since the `ablate()` fix that it walks a real graph. The project
also read it correctly: *"It generates downgrades, not swaps… it does not compare models."*

**FT-14 read a hosted identity correctly.** `gemini-3.1-flash-lite` passes on the model id alone;
`gemini-flash-lite-latest` would have failed on the floating marker. The project noticed and
recorded why.

**The library's own Gemini design was independently confirmed, at the cost of a session.** The
project hit `thought_signature` as a hard 400 that killed **102 of 102** `look_closer` node
executions through an OpenAI-compatible endpoint, wrote a native adapter, and carried the signature
in a process-local memo keyed on ids it minted itself, evicted past 20,000 entries and refusing any
conversation begun on another client. `afffc88` had shipped the same fix the day before, in the
place the project could not reach: `ToolCall.provider`, which reaches the trajectory as
`outputs.tool_calls[].provider`, so — in [`docs/model-clients/gemini.md`](../../../docs/model-clients/gemini.md#L80)'s
own words — *"a run resumed in another process rebuilds a conversation this backend still
accepts."* **This is the isolation working as `runs/dogfood-4/setup.md` §1.2 intended**: a coding agent
that needed the thing built it, arrived at a strictly weaker version, and confirmed the design
without ever seeing it.

**Three defects were found by the fake run before a backend was paid for**, which is
`docs/pipeline.md` §6 doing exactly what it claims: a context overflow at 16,385 tokens against a
16,384 window, a fan-out prompt reading the wrong key (`DF4-P2`), and the fake client not being
reached at all (`DF4-P3`).

**The refusals held where they fired.** `Cassette.record` refused a path already holding a
recording. `EvalSuite` refused a mixed cassette and named `allow_mixed_cassette=True` as the opt-in,
which the project took knowingly and recorded as an experiment rather than a measurement. A changed
prompt at an unchanged `prompt_version` was refused, and the project's own note is *"worth knowing
before a long run rather than at the end of one."* A fan-out node given two in-edges was refused
by name — *"Node 'judge_each' fans out over 'unjudged' and takes input from 2 nodes, so it receives
a Join rather than a dict"* — and the refusal is what decided the shape of the fix.

**The `brainstorm` stage held up on its second contact.** `idea.md` is current at `measure`, its
five sections are real, and its "What is still open" carries eleven questions each with a figure
against it. `one_real_input` again produced a file read before a node was designed.

**Nothing was destroyed.** §1.3.

---

## 7. `runs/dogfood-protocol.md` §1 step 5 — the three categories

**Interventions the builder was forced into.** The single largest count any dogfood has produced,
and they fall into three shapes.

*Corrections of a coding-agent claim the artifacts should have caught, five of them, and every one
was right:*

1. **The null result.** *"This is impossible unless something is getting hidden under the hood."*
   It was: the characterisation pass moved 9 of 34 examples, improving `shelve` and damaging
   `skip`, and the split's 70/30 prevalence cancelled them in the headline. Reported as a null
   result anyway, against the project's own recorded warning about prevalence.
2. **The `look_closer` overreach.** *"This is bullshit. The most it can say is that a Qwen look
   closer doesn't help a Gemini judge."* Conceded, and the retraction produced `DF4-D5`.
3. **"Empty is the correct answer" was wrong.** *"If it only works for books that are essentially
   the same as the stuff I've read, then that's not useful."* Three pipeline defects were behind
   it, and fixing them took judgements carrying a supporting case from 48% to 94%.
4. **The handoff's per-node client claim.** `DF4-P3`.
5. **The model-size framing.** *"I think 3.1-flash-lite is still a bigger model than 30B, is it
   not?"* Withdrawn: `Qwen3-30B-A3B` activates about 3B parameters per token, and "cheapest tier"
   had been reached for as an explanation of a gap the data did not show.

*Process interventions about the build log:* at least six, the last two angry, plus one about
writing a summary to an artifact instead of the log. `DF4-D13`'s cousin: a shipped instruction that
needs a person to enforce it.

*Requirements and sources the elicitation never asked for, and he supplied:* the post-cutoff
release gap; `awesome-` lists and then `awesome-fantasy` by name; editions and repackagings;
tracking every refresh so a threshold can be argued from data later; recording the queue context a
pick was made in; user control over detected subjects; and the whole queue architecture.

**Questions asked that the library should have answered itself.** One: `DF4-P4`, where the
threshold reached him without the pairs the scaffold said to show first. This is the fourth run in
a row where over-asking did not appear.

**Things the builder wanted to volunteer and was never asked for.** `runs/dogfood-protocol.md` §1 calls this the
highest-value entry and the easiest to miss, and dogfood #3 filled it with six decisions.

**This run fills it with one, and it is structural rather than a list.** The builder's own note:

> The agent rarely, if ever, volunteers sources that could be used. It certainly does not use its
> own web search capabilities to find sources. E.g. see if book award websites have lists that
> could be used to find candidates.

The artifacts confirm it precisely. Awards were investigated once, at his prompting, on a wrong
premise — that they could ride the Listopia tag mechanism — and the correction is in the log:
*"Listopia ranks by accumulated votes, so a 2026 release can never reach the top of an established
list… **awards are not sourced at all**. Recorded as open."* And they stayed open. `web_search` was
called **7 times in the entire run**, all of them inside `look_closer` on a taste question, never
once to find a source.

**Where dogfood #3's six decisions went.** All six kinds now have a brief entry and the builder
saw them, which is the decision surface working. What replaced them is one decision he was never
asked about because it was never framed as one (`DF4-D2`), and one he was never asked about at all
(`DF4-D6`).

---

## 8. Prior questions this run answers

### 8.1 Consultation, and why the `Reply` matcher cannot be decided from this run

**The question carried here, from `PENDING-SIGNOFF.md` item 6:** the default matcher compares the
whole answer against the whole option, so `"Yes."` matches the option `yes` and `"Yes, go ahead"`
does not. Whether a natural-language affirmative should match was left to *"a real model and a
real person against it."*

**No real person was ever against it, and the run explains why.** That is the answer this section
reports, because it is larger than the matcher and it decides the order the two questions have to
be taken in.

#### The library has a production answer for consultation and no development answer

**The production answer exists, is documented where a coding agent would find it, and was
found.** [`docs/tools.md` §4.6](../../../docs/tools.md#L800) carries a subsection headed *"When nobody is
at a terminal, the channel stops the run instead of blocking"*: the channel raises `Suspend`, the
question is recorded with `resolution: "pending"`, and `Pipeline.resume` continues from the same
point with the conversation and the spend intact.
[`docs/pipeline.md` §1.8](../../../docs/pipeline.md#L326) leads its three examples with the same one.
**The coding agent read it and cited it by section number** in `agent.py`.

**It chose against it, and the reason is the library's own.** An evaluation cannot suspend — the
library says so, and serves the recorded answer from the cassette instead. But the recording has
to come from a live run with a person in it, and during development there is no such person: the
builder is not at the terminal, the coding agent is running the pipeline, and nothing in the
procedure says who the channel is. This project ran **33 evaluations and 3,293 runs**, none of
which a human could sit through.

**So it stubbed, and the library ships no stub.** Both of the two available stubs are wrong, and
two dogfoods picked one each without conferring:

| Stub | What the library records | What it costs |
|---|---|---|
| return `None`, the documented decline | `resolution: "declined"` | The model reads it as a question worth asking again. **Measured here: three of the hunt's twelve steps**, on the run that then ended with a null output |
| return prose saying nobody is there | **`resolution: "answered"`** | Every number downstream describes an agent whose consultation never happened. `DF3-D7` shipped `consultation_resolutions` so a refusal would be visible in the results, and this defeats it honestly, by answering |

Dogfood #3 took the first: **152 consultations, every one `declined`**. Dogfood #4 took the second
after measuring what the first cost, and its own docstring is the clearest statement of the hole
anywhere:

> A declined consultation reads to the agent as a question worth trying again, and on the second
> real run it spent three of its twelve steps re-asking questions no one was going to answer, then
> ran out of budget with nothing to show. Telling it the truth about availability is what stops
> the loop.

**There is no way to say "declined, and do not ask again" without saying it as an answer.**

#### And the library has no concept of after

The primitives are there — suspend and resume, `Trajectory.sampled(rate)` for what a production
project accumulates, `runs()`, memory scoped to one end user. What is absent is any account of a
project going live: no stage after `measure`, no document about it, and the word "production"
appears four times in all of `docs/`, every one incidental. `DF4-D7` is the same absence measured
from the other side, and the two should be read together.

#### The consultations this run produced, and what they can and cannot support

**All 104 came from one node, `hunt`, on one day, 2026-08-11**, in the pipeline the builder later
called a stupid system. **The shipped pipeline does not consult at all** (`DF4-D9`). 28 of the 104
were asked after that run had already been told nobody was available. So these are one draft
node's questions, asked into a void, from a design that was abandoned.

**They are not evidence about what a real agent asks**, and any conclusion drawn from their shape
inherits that confound. What they are is the only sample anyone has, so it is recorded, with the
confound attached:

| | |
|---|---|
| offered no options at all | **73 — 70%** |
| offered options | 31, of which 23 were the first consultation of their run |
| binary whose first option begins "Yes" and second "No" | 8 |
| **options that are the bare string `yes` or `no`** | **4, of 125 options** |
| median words per option | **6**; longest 20; two words or fewer, 16 of 125 |

Two shapes appear, and they want opposite matching rules. A binary written as prose —

```
["Yes, I'd like to proceed with that title as a candidate",
 "No, I'd like to search for a real celebrity autobiography, ghostwritten and published this year"]
```

— where nothing a person would type matches the offered string, so whole-answer equality makes
`chose` unreachable rather than strict. And a pick from a list —

```
['Crossroads of Ravens', 'The Will of the Many', 'The Witch of Whispervale',
 'The Wolf and the Crown of Blood', 'Secrets of the Bees']
```

— where whole-string equality is close to right, and reading an answer more liberally risks
matching *The Will of the Many* against *The Witch of Whispervale*.

#### What this decides

**Not the matcher.** A rule for reading an answer is worth nothing while nothing can answer, the
sample comes from an abandoned node, and no answer in it was written by a person.
`PENDING-SIGNOFF.md` item 6 should stay open and **should not be taken before the consultation
design is**.

**What it does decide** is that the question underneath it is not "should `yes` match a sentence
beginning with yes". It is what answers a consultation during the life of a project the library
owns, and what the library ships for the case where nobody can. Everything else, the matcher
included, is downstream of that.

**One thing is settled.** `M11` said `Reply`'s own docstring example is the case the matcher
rejects, and Stream C corrected the example rather than the rule. `options=["yes", "no"]` appears
**4 times in 125 options** in a real run, so the docstring is now honest about a case a model
rarely produces.


### 8.2 `compare_variants` on its own leading example — `RULINGS.md` D2's third cause

**The claim to confirm or refute:** *"It fails on its own leading example, after paying for a
baseline arm, with a refusal about directories."*

**Confirmed as a mechanism, refuted as an explanation.** Three findings, in order of what they
change.

**1. The mechanism is real in the wheel this run used.** `DF4-D14` reproduces it: a temperature
moved and a tool added both leave `eval_id` byte-identical, so a second arm resolves to the
baseline's directory and is refused by `_refuse_a_used_directory` after the baseline has run.

**2. The run never met it, and the reason matters.** `compare_variants` was **never called.** No
baseline arm was ever paid for and thrown away, and no refusal about directories was ever seen. The
project ran its four arms as four separate `suite.run()` calls.

**3. The reason it was not called is not discoverability**, which is what D2's follow-up assumes
across its three causes. The coding agent found the feature, read it, checked it against its own
case, and judged it the right tool — and then did not use it, for a reason about this pipeline:

> **`compare_variants()` is the right tool for the model comparison, and it was not used.** Checked
> rather than assumed: `plan_variant` accepts a model-only change and marks `judge_each` as
> `changed`, so the arms are comparable in its terms.
>
> **Its main advantage is mostly unavailable in this particular pipeline, which is worth stating
> rather than overselling the tool.** The cassette only helps for calls the change cannot have
> touched, and `judge_each` is the first model-calling node with anything to do… so changing it
> taints `look_closer`, which is 741 of the 843 calls. The replay saving here is close to nil.

**So the run is evidence for D2's follow-up ruling and against its third cause as a diagnosis.**
Promoting the evaluation surface to the top level and giving variant comparison its own `index.md`
row are both right, and neither would have changed this outcome: the feature was found, understood,
and correctly judged to buy little on this graph. What would have changed it is `max_live_calls`
being the headline rather than the replay, which is the one advantage the project did identify as
applying — and it is the last thing named in the paragraph.

**One further datum for cause 1.** The run reached for `progress_of`, which is `DF3-D3`'s shipped
reader, and did not find it: `watch.py` imports nothing from `simple_agents` and re-implements it
by globbing manifests, wrongly twice. D2's follow-up promoted `EvalSuite`, `Example`, `ExampleSet`,
`compare`, `compare_variants`, `ablate` and `EvalResults` to the top level. **`progress_of` was not
promoted**, and it is the one this run went looking for.

### 8.3 The builder's own notes, checked against the artifacts

`random-thoughts-questions.md` "Dogfood 4 notes" is his list from the run. Following `runs/dogfood-protocol.md`
§1's method, each is a claim to check rather than a finding to write up.

| His note | What the artifacts say |
|---|---|
| The contamination question had no context | **Confirmed and sharpened.** `DF4-P4`: the scaffold said to show the pairs first, and only the threshold reached him |
| It rarely volunteers sources; awards were never used | **Confirmed.** §7. Awards were investigated once, on a premise the project itself later refuted, and remain unsourced. `web_search` fired 7 times in the run and never to find a source |
| It struggles to keep the build log live | **Confirmed.** §1.1: six asks |
| The design stage is subpar; decisions not run past him | **Confirmed, and it is the run's second-largest finding.** `DF4-D2` and `DF4-D6` |
| The coding agent seems dumber here than in the library | **Not establishable.** Nothing in the artifacts separates task difficulty from agent quality, and this is exactly what `runs/dogfood-4/setup.md` §3.1 warned the repeated task would confound |
| `LLMNode` has `over=` and no `tools=`; `AgentNode` the reverse | **True, and the constraint produced the better shape.** It forced judging into a fan-out with a fixed evidence floor and an optional second pass, which took per-book agreement from 0.867 to 1.0 and made batch length stop mattering. Worth a look as a documented consequence rather than as a defect |
| "The store step only writes at the end of the fan-out" — is this library-side? | **True, and library-side.** A fan-out returns `FanOutResult` to one successor, so a project whose side effect is in that successor writes once, at the end. A serial pass over 929 books had run five minutes and written nothing. **The library does not lose the items** — a suspended or budget-stopped run continues at the item it stopped on — but a killed process does, and there is no per-item seam. The project's fix, chunks of 40 written as they complete, is the right one and it had to invent it |
| Gemini's `thought_signature` is dropped — is that true? | **It was true of this wheel and is not true of the library.** `ToolCall.provider` and the native adapter shipped in `afffc88` on 2026-08-12. §6, and the consequence the run measured is a hard 400 killing 102 of 102 node executions, not a soft degradation |
| Versioning for pipelines to make evaluations easier — or is that ablation? | **Neither, and the run answers it.** `graph_fingerprint` and `_eval_id` version a pipeline; `ablate()` generates downgrades; `compare_variants` runs named arms. §8.2 has the project's own reading, which is correct |
| We need progress bars | **Confirmed, and it is a discoverability finding rather than a missing feature.** `progress_of` shipped off `DF3-D3` and the project rebuilt it by hand. §8.2 |
| It says it ran something when it did not | **Confirmed twice.** A "regenerated" claim made against a stale file because `show_prompts.py` needs `--md` to write; and a smoke-test print truncated at 105 characters that hid the `[unverified: …]` suffix the test existed to show |
| Can the library check for a node spinning until max steps? | **`DF4-D5`, with the measurement.** 188 executions, 3,384 calls, 15% of the run |
| It scatters files everywhere | **Confirmed.** 30 Python files, four Markdown documents and three SQLite stores at the project root, with no directory structure. The procedure says nothing about layout |
| No separation between evaluation data and production data | **`DF4-D1`, and it is the run's largest finding** |
| We need a verify-the-code-against-the-brief step | **`DF4-D8`, with four entries that were wrong for a day** |

**Two claims of the coding agent's that the artifacts overturned**, both found by the builder
pushing and both worth keeping as method: an apparent model advantage that was a defect in the
harness measuring it, three separate times, each flattering the same arm; and "the characterisation
pass did not move Qwen", which moved nine examples in two opposing directions that the split's
prevalence cancelled.

### 8.4 Other standing questions

**`archive/plan-history.md` §1.8, semantic recall.** *"What decides how far it goes: whether a project reaches for
recall the lexical path misses."* **This run reached for it, specified it, and built something
else.** `queue_architecture` names `MemoryStore` as the cache mechanism, with `memory_search`
matching by meaning as the stated attraction — and **`memory` is `None` in all 3,293 manifests.**
The project built SQLite instead, because what it needed was three tables separated by how fast
each goes stale, an append-only judgement history, a taste fingerprint to invalidate against,
migrations, WAL, and queries. A store scoped per end user and reached through `remember`, `recall`
and `memory_search` answers none of that. **This is the first evidence from any dogfood about the
memory item, and it says the shape was wrong for the one project that specified it by name.** The
retrieval question is still unanswered, because the store was never reached.

**`plan.md` §2.1, a seam for a project-supplied count or total.** **Reached for
again, and built by hand again.** The project counts `citation_unverified` events, unverified
citations per judgement, per-class recall, confidence separation between right and wrong answers,
and the noise floor — none of them expressible as a mean over examples with an interval, all of
them computed in `compare_arms.py` and printed outside the results file. Three of three dogfoods
that got as far as caring have now reached for one. The entry stays open; the evidence is stronger
than it was.

**`runs/dogfood-4/inventory.md` DF4-Q3, whether `brainstorm` should have room to wander.** Its own
test was *"a dogfood run where the coding agent is told to explore before asking, against one where
it is not"*, and this run was not told, so it does not settle it. What it adds is that the stage's
*output* was again good and the failure was again downstream: `idea.md` named the project's
dependencies and open questions honestly, and the decision that broke the design was made two
stages later out of an answer given at `brainstorm`. `DF4-D2`.

**`runs/dogfood-2/findings.md` §1.1, on timestamps.** Still open. This run has a build log and it
carries no timings, so it adds nothing.

---

## 9. Where the project ended, and what is open

**The project ended with its reported measurement deliberately one version stale.** `brief.toml`
names `eval_5680e78cdcfc.json`, `would_shelve_agreement` **0.82 [0.68, 0.94]** on `held_out`
against an always-shelve baseline of 0.76, with 0.00 abstention and 0.00 failure. Four later
evaluations exist and none of them is a `held_out` run at the version the code is at. The project's
own account is that this is on purpose: the later figures were measured with the non-deterministic
prompt of `DF4-D10`, and *"repoint it at a `held_out` run made at v10 or later."* That run was never
made.

**The last thing the run measured about itself is its own noise floor**, and it is the right note
to end on: three identical `dev` runs, nothing changed, returning 0.929, 0.889 and 0.899. **The
entire model comparison this project spent a day on — four arms, three model identities, twenty
times the cost at the top end — spans less than that range.**

**What is open, and what a sitting has to decide.**

| # | Finding | Shape of the decision |
|---|---|---|
| `DF4-D1` | The artifact the end user sees is not what any evaluation measured | The largest one, and it is a design question rather than a fix. The conformance suite reads a results file and a run directory, and a project that owns state has a third artifact nothing looks at |
| `DF4-D2` | A narrowing recorded in the brief as an answer, which FT-30 passed over | `DF3-D8`'s successor. Whether anything can read one brief entry against another, or whether this is the builder's job and the taxonomy's §10 should say so |
| `DF4-D3` | A transport failure inside a fan-out scored as an abstention | Narrower than it looks, and it reopens `D3`: the classification is at the wrong boundary, because a fan-out never raises |
| `DF4-D4` | `RetryPolicy` inert on a fan-out at the default | A documentation fix at minimum; possibly a refusal, since the two settings are configured independently and one silently disables the other |
| `DF4-D5` | A node spinning to its cap having called no tool, unreported | Cheap: everything needed is recorded. A check or a line in the report |
| `DF4-D6` | A routed-around node fails FT-07 | Needs a third option. The check's objection is right and the workaround is expensive |
| `DF4-D7` | The procedure ends at `measure` | Not an argument for a fifth stage. What is open is whether any gate-driven mechanism should govern after the last gate |
| `DF4-D8` | Nothing reads the brief against the code | Partly checkable: `tool_effects` against the declared tools, `behavioural_constants` against the manifest |
| `DF4-D9` | A capability the builder asked for left the graph | Sharper than `DF4-D8` and decided with it. The proposed shape is a prompted re-check of what has drifted, and `DF4-D7` is why a stage gate is not on its own the place for it |
| `DF4-D10` | Nothing checks that one prompt version sent one prompt | Cheap and high value: k rollouts of one example already carry their prompts |
| `DF4-D11` | An evaluation's identity does not cover the data it reads | A declaration surface, not a hash |
| `DF4-D12` | A declined consultation is asked again, and answering it records an answer | Small, and it defeats `DF3-D7`'s fix in the field |
| `DF4-P1` to `DF4-P4` | Four documentation bugs, one of which destroyed a measurement | `DF4-P1` is the one worth doing first |
| §8.1 | **Consultation, and whether the library has a concept of after** | The largest thing in the record after `DF4-D1`. There is a production answer, no development answer, and no stub. `DF4-D12` and the `Reply` matcher are both downstream of it and should not be taken first |
| §8.4 | `MemoryStore` was specified by name and not used | The first evidence about the memory item from any dogfood |

**`DF4-D13` and `DF4-D14` are closed** by `d13e46e`, and §4.14 is the check that the other four
blockers were not met.
