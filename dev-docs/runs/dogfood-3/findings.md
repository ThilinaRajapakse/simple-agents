# Dogfood #3 — findings and the v0.1 changelog

`items/example-projects.md` §17's task, a book recommendation agent, against the wheel at
`runs/dogfood-3/wheels/`. **`runs/dogfood-1/findings.md`, `runs/dogfood-1/run2-findings.md` and
`runs/dogfood-2/findings.md` are the earlier records and are not restated here**; this document
cites them. Findings numbered `DF3-Dn` and `DF3-Pn` are this run's. `DF2-` prefixed ones are
dogfood #2's, `R2-` prefixed ones dogfood #1 run 2's, and bare `D4`, `P1` and so on run 1's.

**The run finished 2026-08-11 and this record was written the same day**, after it ended
rather than while it ran. **A finding that has since been closed says so on its first line and
is otherwise left as written.** §9 is the ledger: what landed, what was decided against, and
what is still open.

**No build log was asked for.** `runs/dogfood-protocol.md` §1 names one figure that is on disk nowhere else —
how long the coding agent spent waiting on the builder — and for this run **that figure is
gone**. It is not reconstructed below. Everything else in §1 that carries a time is either a
timestamp the run itself wrote, which is a measurement, or is **marked inferred**, which means
it was read off file modification times and is evidence about when a file last changed rather
than about when a stage began.

**Project:** `/home/thilina/Projects/dogfood-3`. Fresh coding-agent session. The prompt was
`runs/dogfood-3/setup.md` §3's two sentences and nothing else. Nothing in this document was written
into the project. `recovered/` is the one thing this analysis added to it, and §1.1 says what
it is.

Final totals across 187 run directories: **1,722 model calls, 4,029 tool calls, 152
consultations, and $6.6002 of recorded cost** — $5.4624 of it real money at Mistral, $1.1378 of
it device time under a `ComputeBasis` on a local Qwen3. `simple-agents check`: **0 failed, 10
passed at tier `evaluated`**, and §4's `DF3-D1` is what that number is worth.

| | dogfood #2 | dogfood #3 |
|---|---|---|
| Elapsed | 232 min, unfinished | ~15h50m *(inferred)* |
| Runs in the envelope | 16 | **187** — 161 on disk, 26 recovered |
| Model calls | 587 | 1,722 |
| Tool calls | 631 | 4,029 |
| Consultations | 0 | 152, every one of them `declined` |
| Recorded cost | $0.4785 | $6.6002 |
| Nodes, and kinds | 11 (7 D, 3 LLM, 1 Agent) | 10 (5 D, 4 LLM, 1 Agent) |
| Built-in tools used | `http_fetch`, `web_search` | `consult` |
| Project tools written | 3 | 4 |
| Tier | `prototype` | **`evaluated`** |
| `simple-agents check` | 3 of 3 | **10 of 10** |
| Brief entries | 9 | 30 — 29 the library ships, 1 the project added |
| Evaluations attempted | 0 | **8** |

---

## 1. Method, and what the artifacts could and could not answer

**The artifacts are the instrument**, which is `runs/dogfood-protocol.md` §1's own measured lesson, and this
run is the strongest case for it so far: every finding below except the two in §7 came from
reading files, and the builder's notes served as claims to check rather than as findings to
write up. Three of the six notes were sharpened by the artifacts, one was corrected, and one
turned out to be aimed a stage too early. §3 and §7 say which.

**Eight evaluations were attempted and five survive on disk.**

| Evaluation | Backend | Rollouts | How it ended | Results file |
|---|---|---|---|---|
| `eval_beaf691105b2` | Mistral | 2 | completed, a smoke run at k=1 | `held_out-k1.json` |
| `eval_20704a88aab5` | Mistral | 17 of 33 | **killed at two hours by the coding agent's own `timeout 7200`** | none. Recovered |
| `eval_122354f1ece4` | Mistral | 33 | 8 completed, then HTTP **402** from Mistral ended the other 25 in about 1.3 seconds | `held_out-k3-mistral.json` |
| `vllm/eval_befebfa2b97c` | vLLM | 3 | failed start | none. Recovered |
| `vllm/eval_b193efc82fec` | vLLM | 6 | failed start | none. Recovered |
| `vllm/eval_6a79bc29e72b` | vLLM | 33 | every rollout ran, then **a project metric raised in the scoring pass** and the evaluation was lost at the last step | **overwritten.** Recovered |
| `vllm/eval_c956458fe71a` | vLLM | 33 | completed | `held_out-k3-vllm-c956458fe71a.json` |
| `vllm/eval_59edbb664358` | vLLM | 39 | completed | `held_out-k3-vllm-59edbb664358.json`, then rescored |

**Three of the eight, and one results file, were deleted during the run.** They exist because
of §1.1 and for no other reason.

**Inferred stage marks, from file modification times.** Not measurements of a stage, and not
the waiting figure.

| Inferred | What the mtime is |
|---|---|
| 2026-08-10T08:16Z | `AGENTS.md` and `.agents/` — the project as `simple-agents init` left it |
| 2026-08-10T09:01:11Z | the first run manifest, which is a measurement. **45 minutes from setup to the first live run of a pipeline**, covering `brainstorm`, `shape` and a first build |
| 2026-08-10T12:37:57Z | the first evaluation rollout |
| 2026-08-11T00:06Z | `shelf.html`, the last file the run wrote |

### 1.1 The build log that was not asked for, and what stood in for it

**The project is a git repository with no commits and 639 objects.** `git init` ran at setup
(`runs/dogfood-3/setup.md` §1.1) and nothing was ever committed, so `git log` is empty and the build
order cannot be read off it. The object store nonetheless holds **261 trajectory blobs and 226
manifest blobs** written across the run, reachable from no ref. They are working-tree snapshots
taken while the build went on.

**This is not a replacement for the build log and does not carry its figure.** A snapshot says
what a file held; it does not say when the snapshot was taken in any way that survives, and it
says nothing at all about what the builder was doing. What it does carry is **the artifacts a
run destroyed**, which `runs/dogfood-protocol.md` §1 calls a finding in its own right and which no previous run
could produce evidence for.

Recovered, and written to `runs/dogfood-3/recovered/` on 2026-08-11 because a `git gc` would have
removed them:

- **26 rollout directories** across the three deleted evaluations, with manifests and
  trajectories: 202 node executions, 224 model calls, 572 tool calls, **$3.2619 of measured
  spend**.
- **One results file**, `eval_6a79bc29e72b`, written 20:30:58Z and overwritten. `DF3-D5`.
- **Seven successive versions of `idea.md`**, 1,179 to 3,349 words. §3 and §6 read them.

Every figure below drawn from this source says so. `recovered/README.md` records how each file
was matched back to its path.

### 1.2 What the library was when this ran

**The wheel is seven items behind the library that exists now**, and the artifacts have to be
read against what produced them. Manifest `0.16`, trajectory `0.18`, results `0.6`, 29
elicitation questions, 10 conformance checks.

Landed after it: per-node model selection, the `ablate()` fix, pipeline-as-a-tool, memory, paid
evaluation, rescore, and the recording default. So `LLMNode` had no `model=`, manifests carried
no `containers` and no `nodes[].model`, there was no `delegation` record, no `MemoryStore`, no
`max_spend`, no `EvalSuite.rescore`, and `Cassette` did not default to recording.

**Two of those seven were built off this run while it was still going** — rescore, and the
recording default — which is why §9.1 is longer than a findings record's usually is.

---

## 2. The ship criterion — `archive/plan-history.md` §3.3

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

**Met, at 10 of 10.** The bar has risen since dogfood #1 met it at 9 of 9: FT-29 is a check now
and this is the first project to face it.

```
simple-agents check: .
tier evaluated, declared in brief.toml
  pass  FT-13  FT-14  FT-24  FT-29  FT-01  FT-02  FT-03  FT-04  FT-06  FT-07
0 failed, 10 passed
```

**The criterion says nothing about the agent being good, and it was never meant to.** What this
run adds is that it also says nothing about the *measurement* being able to tell. `DF3-D1` is
that finding, and it is the most important thing in this record.

---

## 3. The `brainstorm` stage, first contact

**This is the first project ever to meet it**, which is what `runs/dogfood-3/setup.md` §2 set the run
up to test. Its five watch items, answered:

| Watched | What happened |
|---|---|
| Does `one_real_input` produce an actual file, or a description of one? | **An actual file, read before any node was designed.** `brief.toml` records 346 rows and 23 columns, and `idea.md` §"What it works on" carries a column-by-column table with fill rates. Three findings from it changed the design |
| Is `idea.md` five real sections or five headings with a line each? | **Five real sections, 1,179 words** at `brainstorm`. Recovered, §1.1 |
| Is `understanding_confirmed_at` ever updated, or set once and left? | **Updated.** It reads `measure` |
| Does the coding agent ask `what_it_does` first and read the answer? | **Not establishable.** Nothing in the artifacts records the order questions were asked in, and this is exactly the kind of thing the build log existed to carry |
| Do six required questions at one stage read as thorough, or as an interrogation? | **Neither. The builder's verdict is that it moved too fast**, which is the opposite failure to the one this question anticipated |

**The stage worked, and the failure is downstream of it.** The recovered `brainstorm` `idea.md`
lists, under *What is still open*:

> **Where the books get looked up.** The export has no content, so an external source has to
> supply it. Which one, and whether it is a search tool over the open web or a specific
> catalogue API, is not settled. **This is the project's main dependency**, and the answer
> decides how much of the recommendation quality is even reachable — see the abandon condition
> below.

That is the stage doing its job precisely. It named the project's largest unknown, called it the
main dependency, and tied it to the abandon condition.

**Nothing ever closed it with the builder.** The `shape` section that follows settles the answer
form, the split unit, the abstention rule, the three agentic decisions and the consultation
policy — all of them quoted from the builder — and says nothing about the source. Open Library,
Google Books and a Wikidata award list appear as settled fact in **`What the build settled`**,
one stage later. The `build` stage's nine questions are `backend`, `budget`, `tool_effects`,
`unproven_answer`, `unknown_literal`, `context_limit`, `rerun_cost`, `reproduce` and
`who_labels`. **None of them touches which external service the project will rest on.**

The builder learned about it by volunteering, unprompted, that a Google Books API key was
obtainable — after the coding agent had checked, found a key was needed, and dismissed the
source. That is `runs/dogfood-protocol.md` §1 step 5's first category, and §7 has it.

**The builder's note says the `brainstorm` stage moves too quickly. The artifacts say the stage
raised the right question and no later stage has a place to answer it.** Those are different
repairs, and `DF3-D8` is the second one.

---

## 4. Library defects

### DF3-D1 — A project reaches full conformance with an evaluation that cannot detect its own effect

**Open, and narrowed 2026-08-11.** `DF3-D8` ships a `measurement` decision kind that asks what
an agent doing nothing would score, so the answer can no longer be absent. Nothing checks the
answer and nothing can: the library cannot compute a project's chance rate. **Dogfood #4 is what
measures whether asking is enough.** The highest-value finding in the run, and it is about the
conformance ceiling
(`simple-agents.md` §3.2).

`simple-agents check` passes 10 of 10 at tier `evaluated`. The file it certifies is
`evals/results/held_out-k3-vllm-c956458fe71a.json`, named by `brief.toml`'s `results` key:

| | |
|---|---|
| accuracy | **0.0** over 33 rollouts, 11 examples, interval [0, 0.259] |
| the design | one author is held out of the reader's library and the agent scores a hit by naming them |
| the chance of a hit | **about 0.5%**, by the project's own arithmetic: five picks against the 969 authors in its award list, and the real universe it searches is millions of works |

A measured 0% is consistent with a broken agent and with an excellent one that recommended five
other good books, and **nothing in the number separates them**. The project reached this
conclusion itself, in `build_examples.py`, after the measurement had been paid for three times.
The coding agent's own account of it:

> You approved "the right held-out author is fine" as the definition of correct, but you were
> answering what counts as a hit, not auditing whether the measurement could detect anything.
> Working out that chance was 0.5% was my job and I didn't do it.

**The replacement does not fix it, and the artifacts say so more sharply than the narrative
does.** The example set was rebuilt around the reader's own to-read shelf: 30 valid answers
instead of one, ground truth the builder declared rather than one inferred for them. It is a
better design by every argument in `docs/evaluation.md`. `build_examples.py` prints its own
chance rate on the way past — 30 targets, 969 authors, five picks, **14.6%**. Measured over 39
rollouts:

| | |
|---|---|
| accuracy | **0.0256**, interval **[0, 0.0769]** |

**The whole interval sits below the chance rate the project computed for itself.** Either the
agent is worse than random or the chance model is wrong, and nothing on disk decides which. Two
successive evaluation designs, both uninterpretable, both green.

**What the library does and does not ask.** FT-01 asks whether an evaluation exists, FT-02
whether a split is held out, FT-04 whether absent cases are represented, FT-06 whether an
interval is reported, FT-07 whether seeds are controlled. Every one passed. Across the 29
elicitation questions this run faced, and the 30 the library shipped when this was written,
**none asks what an
agent that does nothing would score**, and the taxonomy's §10 —
the list of what is deliberately not checkable — names the neighbour ("whether the metric
measures what the builder cares about → elicitation") but not this.

**The `measure` stage's scaffold puts the measurement before the question.** `improvement`
([elicitation.py:406](../../../src/simple_agents/conformance/elicitation.py#L406)) reads *"Run the
first evaluation and print the six rates with this project's own numbers beside them. Ask which
one the builder would act on."* So the builder is asked which number to act on **after** it has
been paid for, which is the order this run followed and the order that cost it two designs.

**Why this is not one missing question.** Decided at the 2026-08-11 sitting: a builder cannot
answer "what is your chance rate" cold, and asking it as a question would produce an invented
number. It is the same shape as `DF3-D8` and is folded into it, §9.3.

### DF3-D2 — An argument the model invents ends the run, and the schema check is what lets it through

**Closed 2026-08-11**, `build-logs/dogfood-3-fixes-build-log.md`. An invented argument is
refused as `ModelFacingError` on both declaration paths, and a live Qwen3-30B was seen inventing
`find_book(year=...)`, being told, and correcting itself with the run completing. Reproduced
against the project's own wheel, and against the source as it then was, which was
unchanged in this path.

```
find_book.call({"title": "Piranesi", "year": 2020})
→ TypeError: find_book() got an unexpected keyword argument 'year'
```

`Tool.call` ([`tools.py` `Tool.call`](../../../src/simple_agents/tools.py#L815)) validates the model's arguments
against a schema, then splats them into the function. The validator is a pydantic model built by
`_schema_from_signature` ([tools.py:1175](../../../src/simple_agents/tools.py#L1175)) with no config
passed, so pydantic's default applies and **an unknown key is ignored rather than refused**.
Validation passes, the function raises `TypeError`, the agent loop's catch-all treats an
undeclared exception as caller-facing and re-raises it as a `CallerFacingError`
([consultation.py:544](../../../src/simple_agents/runtime/consultation.py#L544), `except Exception as exc`), and the run ends.

**The one mechanism that could catch this is configured to let it through**, and the failure
then arrives somewhere that cannot report it usefully.

**It happened twice**, on `year` and then on `subjects`. Each cost a rollout — thrown away
rather than the model being told "that is not an argument of this tool", which is a correction
it can make in one step. The coding agent added `year` as a real parameter, hit the same thing
on `subjects`, and then built a general guard by hand.

**The two ways to declare a tool behave differently, and nothing says so.** A schema derived
from the signature gets validated. A schema passed as `parameters=` gets **no validation at
all**, because `_validator` is `None`. This project declared every tool explicitly, for reasons
of its own, and thereby opted out of argument checking without knowing it. That asymmetry is a
trap independent of the invented argument.

**Was ignoring extras ever decided?** No. The commit that introduced the derived schema
(`b02d2ac`) carries no rationale, and nothing in `dev-docs/`, `docs/tools.md` or
`simple-agents.md` mentions extra tool arguments. It is pydantic's default, inherited. **The
library already made the opposite decision one level over**: `R2-D1` put
`additionalProperties: false` on the output schema deliberately, with a measurement behind it,
and `strict_schema` ([`strict_schema`](../../../src/simple_agents/adapters/_openai_wire.py#L300))
is applied to the output schema only. So the model is told "no extra fields" for its final
answer and told nothing for its tool calls.

**Correcting the builder's note.** It reads *"The tool decorator refuses `**kwargs`, so there is
no general guard available — this is a standing fragility, not a fixed bug."* True of the
derived path only. The coding agent **found the general guard and shipped it**: every tool in
`booksource.py` declares `parameters=` explicitly, takes `**extra`, and names the ignored
arguments back to the model rather than swallowing them.

> This tool does not take ['subjects']; those were ignored and the result is unfiltered by
> them. Use only the documented arguments.

Its own reasoning, which is the absorption case: *"a fix that adds each invented argument as it
appears is a fix that keeps losing runs"*, and *"an ignored `subjects=[...]` means it asked for
a filter it did not get and should know that."*

**What this constrains.** Forbidding extras on the explicit path would break exactly this
pattern, which is the one working guard the run produced. §9.3 carries the shape that does not.

### DF3-D3 — A killed evaluation loses every rollout it paid for, and the retry deletes them

**Closed 2026-08-11.** `EvalSuite.run(resume_from=...)` runs the rollouts a stopped evaluation
still owes and scores the rest from disk, and `progress_of()` shows a run overrunning while it
still can be stopped. **Largely closed when this was written**: `EvalSuite.run` records rollouts
by default and `EvalSuite.rescore`
([`rescore`](../../../src/simple_agents/evaluation/runner.py#L794)) scores what is on disk with
nothing executed. What remains open is the resume half.

**Measured, from `recovered/runs/eval_20704a88aab5/`:** 17 rollouts, 15 completed and 2 in
flight, **$3.2266**, first start 13:02:24Z and last start 14:53:43Z. A `timeout 7200` the coding
agent set on its own command fired at about 15:02Z. Its own account:

> I killed the Mistral baseline with my own timeout 7200. Throttled at ~7 min/rollout, 33
> rollouts needs ~4 hours; I'd capped it at 2. Cost: 17 rollouts, ~$3.60, two hours.

The count and the duration check out exactly. The cost recoverable from the manifests is
$3.2266 over the 15 that finished; the 2 in flight never priced, which is `DF3-D4`.

**Nothing resumed, and the directory was deleted.** The re-run got a new `eval_id`
(`eval_122354f1ece4`) because the graph had moved, so the library refused nothing and overwrote
nothing — the 17 rollouts were removed by hand. `rescore` would not have helped at the time
(it did not exist) and would not fully help now either: it scores the 17 that ran, and there is
no way to run the 16 that did not and combine them.

**The second Mistral evaluation then died differently**, and the artifacts say how: 8 rollouts
completed over 55 minutes, and the remaining 25 errored inside 1.3 seconds on

> `https://api.mistral.ai/v1/chat/completions returned 402 after 1 attempt(s): Check your
> subscription`

A results file was written anyway, reporting `accuracy 0.0` over 33 rollouts with an interval
beside it. `failure_rate` reads **0.7576**, so the artifact does say what happened — in a
different metric from the headline, and only to a reader who reads all six.

### DF3-D4 — One unmeasured call makes a whole evaluation's spend unknown

**Closed 2026-08-11.** `totals.cost` gains `measured` and `unpriced_nodes`, results file `0.10`.

`held_out-k3-mistral.json` reports `cost.value: null` and all four token counts as
`{"type": "unknown", "reason": "the call raised before the backend returned a response"}`. Its
own eight completed rollout manifests carry **$1.5627** between them.

The propagation is right: an unmeasured token count is not zero, and `simple-agents.md` is
explicit that an unknown must not be rendered as a number. **What is missing is the figure
beside it.** The totals object has one slot, so an evaluation that spent real money and then hit
a payment failure reports nothing at all about what it spent — and it is exactly the evaluation
whose bill the builder most needs to see. The per-rollout manifests hold it; nothing aggregates
them once one is unknown.

Every vLLM evaluation shows the same shape under a `ComputeBasis`, with
`"the call has no ended_at, and compute cost is duration times a rate"`.

### DF3-D5 — `EvalResults.write` overwrites silently, and it destroyed the project's baseline

**Closed 2026-08-11.** `write` refuses an existing results file and names one after the
`eval_id` when given no path.

`write` ([results.py:566](../../../src/simple_agents/evaluation/results.py#L566)) calls `write_text` on
whatever path it is given.

`brief.toml`'s `improvement` entry — the entry recording which number the builder would act on —
quotes this project's baseline as **accuracy 6.1%, "two hits in 33 rollouts, both James S.A.
Corey"**, with all six rates beside it. **No file on disk carries that number.** Recovered from
the object store: `eval_6a79bc29e72b`, written 20:30:58Z, overwritten by the next evaluation
under the same deterministic filename.

So the brief's most consequential entry quotes a measurement that no longer exists, and it
cannot be rebuilt: the 33 rollouts are still on disk, but the pipeline moved afterwards and
rescoring them under a new graph is refused for good reason (FT-15).

**The project diagnosed this itself and worked around it**, in a comment worth reading in full:

> The path used to be derived from the split, k and the backend alone, which is the same for
> every re-run: a second evaluation wrote over the first, and the first could not be rebuilt
> because the pipeline had moved on and `rescore.py` rightly refuses to score old rollouts under
> a new graph. **A results file is the only durable record of a measurement, and a deterministic
> name makes it a temporary one.**

`Cassette.record` already refuses a path that holds a recording, for the same reason. `write`
does not.

### DF3-D6 — The conformance report reads two different measurements at once

**Closed 2026-08-11.** The report carries a note when the two describe different measurements.
A cousin of `DF2-D4` and `R2-D5`, and the mechanism is new.

`discover` ([artifacts.py:119](../../../src/simple_agents/conformance/artifacts.py#L119))
reads `results` from the brief where it is set, and otherwise takes the most recent results
file. It finds the run directory separately, by recency. In this project the two disagree:

| Checks | Read |
|---|---|
| FT-01, 02, 03, 04, 06, 07 | `evals/results/held_out-k3-vllm-c956458fe71a.json` — the author-hiding design, superseded twice |
| FT-13, FT-14 | `runs/vllm/eval_59edbb664358/starved-01-1/` — a different evaluation, a different example set, a different graph |

**The report certifies a measurement and a run that were never the same measurement.** The brief
key is what makes it possible to be stale rather than merely old: it was last written before the
final two results files existed, and nothing re-reads it. A project that measures, then improves,
then measures again gets a green report describing the version it abandoned.

### DF3-D7 — An evaluation measured an agent whose consultation was declined in every rollout

**Closed 2026-08-11.** `per_node.consultation_resolutions` records how each ended, and the
counter no longer double-counts a question answered in a later process.

`consult` is the one built-in tool this project used, and consultation is a designed part of the
agent: the builder specified what it may ask about ("content, never logistics"), rejected the
obvious questions outright, and the brief's `consultation` entry records it.

`evaluate.py` supplies `channel=lambda question, options: None`. Every consultation in every
rollout therefore resolves `declined`: **31 of 31** in `eval_c956458fe71a`, **152 across the
run**. The trajectory records it faithfully, with `resolution: "declined"` and
`blocking: true`.

**The results file counts them and does not say how they ended.** *(Corrected in place: this
first read "the results file has no count of it", which is wrong. `per_node` has a
`consultations` field and it is populated — `hunt` 28, `apply` 3 — and the correction makes the
finding narrower and sharper rather than weaker.)* The counter increments on the record type
alone, so **nothing anywhere distinguishes a consultation that was answered from one that was
refused**; the word `declined` appears nowhere in any results file, and no metric's denominator
changes when the channel goes silent.

**So the measured agent is not the agent the builder designed, and the artifact that reports the
measurement cannot show the difference.** A project that ran its evaluation with a live channel
and one that ran it with a dead one produce the same numbers here. FT-25 covers the shape of
this in the taxonomy and is not one of the ten checks.

### DF3-D8 — The library asks the builder about their world and never asks the coding agent to propose

**Closed 2026-08-11**, `build-logs/decision-surface-build-log.md`: six decision kinds,
`[decisions]` in the brief, **FT-30**, and three questions (`how_far`, `involvement`,
`presentation`). **Dogfood #3 passed 10 of 10 and fails 2 of 11 against what it produced**, on
FT-24 and FT-30. A design item rather than a fix. `DF3-D1` and §3's finding are both
instances of it.

Every one of the 29 questions asks the builder about **their own world**: their data, their end
users, whether a wrong answer beats no answer, what they would act on. Those went well, and §6
says how well. **Not one asks the coding agent to put its own decision in front of the builder
before making it.** So every decision that was the coding agent's got made alone:

| Decided alone | Evidence |
|---|---|
| Which catalogue supplies book content | §3. Named at `brainstorm` as the main dependency, settled at `build` |
| The pipeline: ten nodes, four of them LLM, one agentic | Never shown to the builder |
| `MAX_ENRICH = 12` — how many of 346 books are read before any opinion is formed | Chosen alone. The coding agent's own later comment: *"the limit was in the wrong place: it was defending per-run network round-trips, which caching already handles, while the context window it appeared to protect was never close to full"* |
| "not another 10-book series" | Invented as a test prompt, written into the code as a builder constraint, and cited back at the builder as a requirement |
| Whether the measurement could move | `DF3-D1` |
| `shelf.html`, 174KB of presentation | Built, never discussed |

**More questions cannot close this.** The decisions that hurt were project-specific and
unenumerable: no shipped question can say "which catalogue API" to a project that has no
catalogue, or "how many books to enrich" to one that enriches nothing. What *is* enumerable is
the **kinds**, and all six rows above fall into six of them: an external dependency the project
will rest on; the shape of the machine; a number written into code that changes behaviour;
prompt text stating a requirement; how results are presented; whether the measurement can move.

**Decided 2026-08-11**: the repair is a recorded surface for decisions the coding agent made and
the builder did not, gated so a stage cannot close while one is unreviewed, driven by a shipped
taxonomy of those kinds — plus a question asked before any of it about how involved the builder
wants to be, which is the only part that makes the volume shrink for a builder who wants it to.
§9.3 carries it, and it needs its own sitting. **It is not scheduled by this record.**

---

## 5. Documentation bugs

### DF3-P1 — `docs/trajectory-format.md` never gives the join, and a wrong reading failed silently

**Closed 2026-08-11.** §4.2 states the join and shows it.

The document is correct. §2's common-fields table carries `parent_id` with the note "the
`node_execution` for a call the node made itself"; §3 puts `node_id` under `node_execution`;
§4.2's `tool_call` table does not list it. Verified against this run's trajectories:
`node_execution` carries both, and `model_call`, `tool_call` and `consultation` carry
`parent_id` alone.

**No sentence anywhere in the document says how to attribute a tool call to a node.** That
sentence exists in exactly one place in the library —

> Records for one node are found by matching ``parent_id`` to the node's ``record_id``.

— in `read_trajectory`'s docstring
([trajectory.py:857](../../../src/simple_agents/records/trajectory.py#L857)). This project read its
trajectories with `json.loads(line)` in a loop, as `evaluate.py` and `rescore.py` both do, and
so never saw it.

**What it cost.** The coding agent filtered `tool_call` records by `node_id`, got nothing, and
diagnosed the agent as making zero tool calls. Its own correction:

> `tool_call` records carry `parent_id`, not `node_id` — my filter was wrong, and it's been
> wrong since I introduced it. That means my "zero tool calls" diagnosis may itself have been
> wrong. Let me redo it properly across all runs.

**A wrong filter over a trajectory returns an empty set rather than an error**, so the failure
mode of a reader that gets this wrong is a confident wrong conclusion. The run made **4,029**
tool calls.

---

## 6. What did not go wrong

**FT-29 worked, and this is the first evidence of it anywhere.** Seven successive versions of
`idea.md` are recoverable, and they grow by exactly one section per stage:

| Version | Words | Sections |
|---|---|---|
| 1 | 1,179 | the five required |
| 2 | 1,694 | + *What is settled about the shape* |
| 3 | 2,262 | + *What the build settled* |
| 4–6 | 2,669 → 3,165 | same seven, filled in |
| 7 | 3,349 | + *What measuring it is for* |

`understanding_confirmed_at` reads `measure`, not `brainstorm`. The document is the project's own
account of itself, rewritten as the project changed, which is what the stage was designed to
produce and what no check can verify.

**`one_real_input` did the thing it exists for.** A real 346-row export was obtained and read
before a single node was designed, and the reading changed the design: no content signal at all
in the format, a rating column where 82% of books sit at 4–5★ and so barely discriminates, and
`Date Read` present on 30% of rows. Each is recorded as a consequence the pipeline was built
around rather than discovered later.

**Agency was justified per node and the builder chose it.** Ten nodes, one `AgentNode`. The
`agency_boundary` entry records all three open decisions as the builder's picks, and that the
builder declined the "keep it fixed" option. This is the third dogfood in a row to land on
structured-data-first with the agentic node late.

**The brief took a question the library does not ship.** The coding agent needed a number only
the builder had — what proportion of recommendations may be bestsellers — and **created its own
brief entry, `bestseller_share`**, recording the builder's "about half", where it went in the
code, and the builder's later correction of how it should be used. Thirty entries against 29
questions. The brief format is doing more than the questionnaire behind it.

**FT-04 was met properly.** The `starved-NN` examples hide almost the whole library and expect
`unknown`, measuring the price of the builder's never-abstain decision rather than leaving it
invisible.

**The library's refusals held where they fired.** `Cassette.record` refused a path already
holding a recording and the project routed around it correctly. The refusal of a used evaluation
directory did what it was for, and the project separated its two backends into their own run
directories with a comment explaining why.

**`rescore` was invented here before the library had it.** `eval_6a79bc29e72b` ran 33 rollouts,
its scoring pass raised, and the project wrote `rescore.py` and recovered the measurement from
the rollouts on disk two hours later. §9.1.

---

## 7. `runs/dogfood-protocol.md` §1 step 5 — the three categories

**Interventions the builder was forced into.** Four, and the first is the one the protocol
exists to catch.

1. **The Google Books API key.** The coding agent checked, found a key was needed, and dismissed
   the source. The builder volunteered, unprompted, that a key was obtainable. Nothing asked.
2. **The evaluation design.** The builder's *"That sounds like a stupid evaluation setup. It has
   to pick one author out of a virtually infinite set."* `DF3-D1`.
3. **The invented constraint.** The builder caught "not another 10-book series" being cited back
   as their own requirement. The coding agent's reply: *"that's my error to own... I invented it
   as a sample request and then started citing it back to you as a requirement — and worse,
   wrote it into the code as a builder constraint."*
4. **The bestseller share.** The builder had to correct how their own answer was implemented:
   *"I didn't mean that you should toss half of bestsellers. I meant that the recommendations I
   get should be a roughly even split."*

**Questions the library should have answered itself.** None found. Across 30 brief entries and
every artifact, nothing was put to the builder that the documentation already covers. This is
the third run in a row where over-asking did not appear.

**Things the builder wanted to volunteer and was never asked for.** This is the category
`runs/dogfood-protocol.md` §1 calls the highest-value entry and the easiest to miss, and this run filled it:
**six decisions, all of them the coding agent's, none of them surfaced.** They are the table in
`DF3-D8`, and the finding is that category becoming a structural one rather than a list.

**The categories produced two of this record's ten findings**, which continues §4.1's own
measured pattern: the artifacts are the instrument and the categories are a checklist. What is
new is that this time the missing-question category produced the largest finding in the record
rather than nothing at all.

---

## 8. Prior questions this run answers

**`runs/dogfood-3/setup.md` §2's five watch items.** §3 has all five.

**`plan.md` §2.1, a seam for a project-supplied count or total.** The entry's
test is whether a project reaches for one and finds `failure_rate` and `absent_outputs`
insufficient. **This project reached for one and put it through the metric seam as a rate
instead.** `backlist_share` is a proportion computed inside the `present` node, which prints
both the count and the rate for a human reading a single run, and the `ProjectMetric` reports
only the rate. The count the builder asked for by name — how many of the picks are backlist —
reaches the trajectory and no results file. Two of two dogfoods that got as far as caring have
now reached for a count. The entry stays open; the evidence for it is stronger.

**`archive/plan-history.md` §1.8, semantic recall.** *"What decides how far it goes: whether a project reaches
for recall the lexical path misses."* **This run says nothing about it.** The wheel predates
memory entirely, so the project never had a store to recall from. The question is still
unanswered by any dogfood.

**`runs/dogfood-2/findings.md` §1.1, on timestamps.** Still open, and this run adds nothing: it had no
build log to check timestamps against.

**`items/example-projects.md` §17.** The worked candidate ran, and §17.9's account of what the
real export contains held up against the coding agent's own reading of it.

---

## 9. What landed, what was decided against, and what is open

### 9.1 Landed off this run while it was still going

Two Phase 3 items were built from this run before the record was written, which is why their
evidence is here rather than only in their build logs.

- **Scoring rollouts that already ran**, 2026-08-10. `EvalSuite.run` records its rollouts by
  default, a project metric that raises now fails on the first rollout and cancels the rest
  rather than after every rollout is paid for, and `EvalSuite.rescore(run_dir=...)` scores what
  is on disk with nothing executed. Results file `0.9`.
  `build-logs/rescore-build-log.md`.

  **The measured case for it is in this run's artifacts.** `eval_59edbb664358`'s `neighbourhood`
  metric was wrong on the first pass — a Jaccard against the union of thirty books' subjects,
  which measures set sizes rather than similarity. Rescored over the same 39 rollouts, with
  nothing re-executed:

  | | first pass | rescored |
  |---|---|---|
  | `neighbourhood` | 0.00254 [0, 0.0076] | **0.2380 [0.127, 0.344]** |

  A 94× move in the project's own headline graded metric, for free. Every other metric is
  identical, which is what a rescore should look like.

- **`config.incomplete` came from this project verbatim.** `rescore.py` invented it — *"a partial
  set is scored and says so"*, with `examples_in_split`, `examples_scored`, `rollouts_expected`
  and `rollouts_scored` — and `_rescored_config`
  ([runner.py:2464](../../../src/simple_agents/evaluation/runner.py#L2464)) now carries the same four
  counts. The clearest absorption in three dogfoods.

- **A run records by default**, 2026-08-11. `RunEnvelope.cassette` defaults to
  `Cassette.into_run()`, and a recording is kept or dropped with its trajectory's payloads.
  Manifest `0.20`. `build-logs/recording-default-build-log.md`.

### 9.2 Decided at the sitting on 2026-08-11

- **`DF3-D1` is not repaired by adding a question.** A builder cannot answer "what would an
  agent that does nothing score" cold at the point the question would fire, and a required
  question a builder cannot answer produces an invented answer. It is folded into `DF3-D8`.

- **`plan.md` §1 and `handoff.md` say the wheel is six items behind; it is seven.** Left as
  written. The correction is here and nowhere else.

- **The recovered artifacts are kept as files.** `runs/dogfood-3/recovered/`, §1.1. Written 2026-08-11
  because a `git gc` would have destroyed the only evidence for `DF3-D3` and `DF3-D5`.

### 9.3 What the sitting decided, and where each went

**Everything below was decided at the sitting and all of it is now built**, the same day, in
`runs/dogfood-protocol.md`'s two newest entries. Where the sitting chose between options, the one not taken
is kept, because the reason it was not taken is the part worth having later. **Dogfood #4 is
what remains**, and it is what measures whether any of this worked.

**The mechanical fixes**, `build-logs/dogfood-3-fixes-build-log.md`.

| # | Finding | Decided |
|---|---|---|
| `DF3-D2` | An invented tool argument ends the run | **Both paths, signature-aware.** `extra='forbid'` on the derived path, where `Tool.call` already turns a validation failure into a `ModelFacingError` the loop hands back. On the explicit `parameters=` path, pass extras through to a function taking `**kwargs` and refuse where it does not, so the guard this project built by hand keeps working. **Not taken: sending tool schemas through `strict_schema`.** It stops the guess at the source, and `R2-D1` only ever measured a strict *output* schema against Mistral. Nobody has measured a strict *tool* schema against any backend, and Mistral is out of credits, so it would ship an unverified claim about hosted backends. Revisit when credits return |
| `DF3-D4` | One unmeasured call makes a whole evaluation's spend unknown | Report the measured part beside the honest unknown: what the priced rollouts cost and how many did not price. The propagation itself is right and does not change |
| `DF3-D5` | `EvalResults.write` overwrites silently | **Both**: a default filename derived from `eval_id`, and a refusal when an explicit path already holds a results file, as `Cassette.record` already does |
| `DF3-D6` | The report certifies a results file and a run from different measurements | The report says so when the two come from different evaluations. **Not taken: refusing.** It blocks legitimate cases — rescoring, comparing arms — and the failure here is silence rather than permission |
| `DF3-D7` | Consultations are counted and never resolved | Record how a consultation ended, not only that it happened. **Not taken, for now: refusing an evaluation whose channel declines every consultation.** A project may want the declined arm as a baseline. Make the number visible first and see whether anyone reaches for the refusal |
| `DF3-P1` | The trajectory doc never gives the node join | One sentence and a two-line example in `docs/trajectory-format.md` §4.2 |

**An evaluation that can be watched and re-entered**, in the same build log.

| # | Finding | Decided |
|---|---|---|
| `DF3-D3` | No way to resume a partial evaluation | `EvalSuite.run(resume_from=run_dir)` skips rollouts already on disk whose graph fingerprint matches and runs the rest. The pieces exist: `_rollouts_on_disk`, the fingerprint refusal, and `config.incomplete` |
| — | Nothing reports progress while an evaluation runs | **Both a callback and a reader**: `on_rollout=` for a project that wants to react, and a reader over a partly-populated evaluation directory so a human or a second terminal can watch. **The reader first**, because that is what would have saved this run — the coding agent was watching from another shell, not from inside its own process. Absorbed from the project's `watch_eval.py`, and the absence is what cost `DF3-D3` its $3.2266 |

**`DF3-D8`**, `build-logs/decision-surface-build-log.md`. The design surface: a recorded decision surface with a
gate, driven by a shipped taxonomy of the six kinds in §4, plus the involvement question asked
before any of it. `DF3-D1` and §3's finding close with it. **Two more decisions fold into its
brief rather than being scheduled separately**, because all three edit the elicitation and
procedure surface and `docs/procedure.md` is also the shipped skill:

- **Presentation is elicited and not shipped.** The builder is asked what the output has to look
  like and who reads it; the library ships no rendering. The decision has consequences the
  library cares about — this project's output schema was shaped by it, at `shape`, before any
  page existed — and the rendering does not. **Not taken: out of scope**, which throws away a
  real elicitation signal, and **not taken: shipping a shape**, which is a large surface on the
  evidence of one page.
- **The procedure asks for a build log.** **Not taken: the library writing one**, because the
  library cannot see the conversation and the conversation is the only thing a build log holds
  that the artifacts do not. It is nearly free once a decision record with statuses exists,
  which is why it goes here rather than on its own.

**And a dogfood.** `DF3-D8` can only be tested by another run. **Dogfood #4 comes before Phase
5**, decided at the sitting, and `runs/dogfood-4/setup.md` is how it was set up.
