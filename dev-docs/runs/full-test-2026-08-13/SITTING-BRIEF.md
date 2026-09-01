# Sitting brief: five decisions out of the full-test checkpoint

Prepared 2026-08-13 from the QA pass in this directory. `FINDINGS.md` is the ranked list of what
was found; this file carries only the parts that cannot be closed without a ruling.

**Each decision is self-contained.** Everything needed to decide it sits under its own heading:
what happened, what it costs, the options with their prices, a worked example, and a
recommendation. Nothing here requires reading another section first.

Five decisions:

1. Whether `max_steps` is a guarantee, and on which paths
2. What identity separates two evaluations, and what separates two graphs
3. What an evaluation does with a run that failed for a reason that is not the agent's
4. What ranking a project gets when it passes `embeddings=`
5. How this checkpoint's findings enter the schedule

Everything else found by the pass is either a plain defect with an obvious correct behaviour, or a
documentation correction. Those need no sitting and are listed at the end so the scope of this one
is visible.

---

# Decision 1. Is `max_steps` a guarantee, and on which paths?

## What happened

A pipeline whose route returns eight successors, under `Budget(max_steps=1, ...)`, made **eight**
model calls and then reported `BudgetExceeded`. A one-node pipeline that ran four semantic searches
under `max_steps=1, max_tokens=10` made **eight** model calls and reported `completed`.

Measured at `concurrency` 1, 2, 4 and 8 with identical results, so this is not about the
concurrency item that landed on 2026-08-13. Branch arms have behaved this way since branching
shipped.

| Path | Is `max_steps` honoured? |
|---|---|
| A chain of `LLMNode` | yes, exactly |
| A fan-out with `over=` | yes, at every concurrency |
| **Branch arms from a route** | **no.** All arms run at any limit, including `max_steps=1` |
| **Embedding and rerank calls inside a search** | **no.** Charged after the call returns |

## In plain language

`max_steps` is the one budget knob the library describes as a hard stop rather than an
approximation, which makes it the one a builder reaches for when they want a guarantee. On two of
the four ways work reaches a model, it is not a stop at all. It is a report, delivered after the
money is spent.

## The technical shape

`run.one_step`, the reservation that makes the axis exact, is called from one place in the
library: [`calls.py:35`](../../../src/simple_agents/runtime/calls.py#L35), inside `_call_model` *(at the record's writing, inside `LLMNode._fan_out`)*.
Everything else charges after the response returns.
[`handles.py:131`](../../../src/simple_agents/runtime/handles.py#L131), `_call_retrieval_model`, charges after
the fact and reserves nothing. The run-level budget is consulted between nodes, so a node that
issues many calls is unbounded within itself.

Four shipped statements say the axis is exact, one of them a docstring a builder reads in their
editor:

- [`pipeline.md:513`](../../../docs/pipeline.md#L513), §1.11: "`max_steps` is exact: one call is one
  step, the step is taken before the call, and a call does not start unless one remains."
- [`pipeline.md:918`](../../../docs/pipeline.md#L918), §5: "The step is taken before the call and a
  call does not start unless one remains, **whether or not calls overlap**."
- [`budget.py:129`](../../../src/simple_agents/budget.py#L129), `Budget`: "``max_steps`` is exact: the
  step is taken before the call."
- `CHANGELOG.md`, on the concurrency item: "`max_steps` is exact under it, because a step is taken
  before its call."

## What it costs a builder, concretely

A builder writes a research agent that fans a question across forty sources by returning forty ids
from a route. They set `max_steps=5` while developing, because they are on a paid backend and want
to be sure a mistake cannot run away. They run it once. Forty calls are made and billed. The run
then tells them the budget was exceeded, which reads as though the bound held and they simply
asked for too much.

## The options

**Option A. Make the axis exact everywhere.** Both paths reserve before dispatching, the way
`_fan_out` already does.

- The documented guarantee becomes true, and stays true for any path added later.
- A branching pipeline under a tight `max_steps` now stops partway through its arms rather than
  completing them, so some existing pipelines change behaviour. Nothing outside this repository
  depends on that yet.
- The reservation has to be taken under the same lock the concurrency item introduced, or two arms
  starting together each see the last remaining step. That is the only part with real difficulty.

**Option B. Correct the four statements.** `max_steps` is described as exact for a chain and a
fan-out, and approximate across branch arms and retrieval calls.

- Cheap, and truthful.
- It removes the only hard bound the library offers. `max_tokens`, `max_cost` and
  `max_wall_clock_ms` are already documented as approximate, so a builder who wants a guarantee is
  left with nothing to reach for, and the honest answer to "how do I make sure this cannot run
  away" becomes "you cannot".

**Option C. Reserve on branch arms, document the retrieval case.** Branch arms take the step
before dispatching. Embedding and rerank calls keep charging after, and the documentation says a
search's own calls are charged rather than bounded.

- Closes the case that costs the most, since branch arms are how a builder fans out deliberately.
- Leaves a second class of call outside the guarantee, which is the kind of exception that is
  forgotten and rediscovered.

## Recommendation

**Option A.** The reason is what the axis is for. A budget that reports rather than bounds is not
a budget, and this library's whole argument is that the unglamorous parts are the product. The
concurrency item already built the lock this needs, so the difficulty is smaller now than it was a
week ago.

The behaviour change is real and I would not soften it: pipelines that currently complete their
arms will stop partway. That is the correct behaviour under a bound the builder set, and nothing
outside this repository is running yet.

**If A is rejected, I would argue for B over C.** A guarantee with one remembered exception is
worse than a documented approximation, because the exception is what a builder finds out the
expensive way.

---

# Decision 2. What identity separates two evaluations, and what separates two graphs?

## What happened

Two pipelines that differ only in `temperature` produce a byte-identical `eval_id`. So do two that
differ only in `max_output_tokens`, in `allow_unknown`, in the pipeline budget, or in whether an
`AgentNode` offers a tool.

Three consequences, each reproduced:

- **`compare_variants` cannot run the variant `evaluation.md` §10 leads with.** The baseline arm
  runs and is paid for. The variant arm then resolves to the same directory and is refused by
  `_refuse_a_used_directory` ([`runner.py:1254`](../../../src/simple_agents/evaluation/runner.py#L1254)).
  The refusal names neither the variant nor the sweep, and arrives after forty rollouts have been
  spent.
- **`resume_from` mixes rollouts across the change.** An evaluation run at `temperature=None`,
  resumed under a suite declaring `temperature=0.7`, is accepted. `config.nodes` records `0.7` for
  a set in which four of six rollouts ran at `None`. Both temperatures were confirmed to reach the
  backend.
- **`rescore` accepts rollouts a different configuration produced**, which is the FT-15 case its
  refusal exists to prevent.

Separately, the same omission appears one level down: a contained pipeline's `tools=`, `budget` and
`fetch_policy=` do not move the `graph_fingerprint`, and `successors` does.

## In plain language

The library files an evaluation under a name derived from what it considers "the same evaluation".
That name currently ignores the sampling settings, the tools, and the budget. So two runs of
materially different agents are filed as one, and the three places that read rollouts back off disk
accept a mixture without noticing.

For a library whose stated purpose is that a number about an agent can be audited later, this is
the number quietly describing a set that never ran together.

## The technical shape

`_eval_id` ([`runner.py:1162`](../../../src/simple_agents/evaluation/runner.py#L1162)) hashes
`graph_fingerprint()` ([`core.py:2117`](../../../src/simple_agents/pipeline/core.py#L2117)), which
covers node ids, kinds, edges, loop bounds, error edges, retry policies and output schemas.
Sampling parameters, tools, `allow_unknown` and budgets are outside it, and nothing else in
`_eval_id` carries them.

**Two shipped documents already disagree about the fingerprint**, which is worth settling in the
same decision:

- [`run-envelope.md:88`](../../../docs/run-envelope.md#L88) describes it as a digest of shape and adds
  "Budgets are outside it and are compared separately." This matches the code.
- [`pipeline.md:297`](../../../docs/pipeline.md#L297) says a contained pipeline "takes `tools=` and
  `fetch_policy=` the way the outer pipeline does ... and a change to any of it moves the
  `graph_fingerprint`." This is true of none of them.

And the claim the identity is supposed to support:
[`evaluation.md:478`](../../../docs/evaluation.md#L478), §6.1: "two evaluations differing in any of
those write into different ones."

## What it costs a builder, concretely

A builder is deciding whether `temperature=0.0` beats `temperature=0.7` on their task. They run the
baseline, it takes twenty minutes and costs a few dollars. They then run `compare_variants` with
the temperature variant, which is the first example `evaluation.md` §10 gives. The baseline arm
runs again, in full, and then the sweep dies with a message about a directory already holding
rollouts. Nothing in it mentions temperature, variants, or what to do.

The worse version: they instead resume an interrupted run after changing the temperature, and get a
single accuracy figure over six rollouts, four of which ran at the old setting. The results file
says `0.7`. Nothing anywhere records that this happened.

## The options

**Option A. Widen both identities.** `graph_fingerprint` gains a contained pipeline's `tools=`,
`fetch_policy=` and budget; `_eval_id` additionally gains sampling parameters and `allow_unknown`.

- Every claim currently made becomes true, and the three refusals start firing where they are
  documented to.
- Recordings invalidate more often. A builder who changes a budget must re-record. Per the standing
  note that re-recording is cheap at this stage, that is a small price now and a larger one later.
- One fingerprint then serves two questions that are not quite the same question, which is the
  substance of Option C.

**Option B. Narrow the documentation.** The identities stay as they are, and `evaluation.md` §6.1
and `pipeline.md:297` are corrected to say what is actually separated.

- Cheapest, and makes the documents honest.
- Leaves `resume_from` and `rescore` silently mixing configurations, which is a wrong number rather
  than a wrong sentence. I would not ship this on its own.

**Option C. Split the two questions.** `graph_fingerprint` stays a digest of **shape**, which is
what a resume needs: can this stored state still be walked? `_eval_id` becomes a digest of
**everything that decides what was measured**, which is shape plus sampling plus tools plus budget
plus `allow_unknown`.

- Each identity answers one question, and the answer is right for that question.
- A resumed run keeps tolerating a budget change, which is the behaviour `run-envelope.md` already
  documents as deliberate.
- `pipeline.md:297` still needs correcting, since `tools=` genuinely is not shape.
- Slightly more code than A: two digests rather than one.

## Recommendation

**Option C, plus the `pipeline.md:297` correction.** A suspended run and a comparable measurement
are different questions, and the current design fails partly because one digest is being asked
both. A resume cares whether the graph can still be walked; an evaluation cares whether two numbers
are about the same thing. Tools and sampling belong in the second and not the first.

I would also make the `compare_variants` refusal name the variant and the sweep whatever is
decided, because "already holds an evaluation's rollouts" after a paid baseline arm is a message
that tells the builder nothing they can act on.

---

# Decision 3. What does an evaluation do with a run that failed for a reason that is not the agent's?

## What happened

`_rollout` catches bare `Exception`
([`runner.py:1323`](../../../src/simple_agents/evaluation/runner.py#L1323), `_rollout`) and scores the rollout
`failed`. Three different things therefore arrive at the same place:

- **A consultation.** `RunSuspended` subclasses `CallerFacingError` and so `Exception`. An agent
  that stops to ask its end user a question is scored as an agent that failed.
  [`evaluation.md:845`](../../../docs/evaluation.md#L845), §7.4, says it raises `RunSuspended`. It does
  not. The suspension state is written and every run is resumable the whole time, and nothing says
  so.
- **A configuration error.** The J1 docs-implementability run had fifteen misconfigured rollouts
  reported as a complete six-rate result.
- **A transport failure.** This pass observed it by accident. When the shared vLLM server was
  restarted mid-pass, a suite kept running against a model id that no longer existed. **Nine
  consecutive 404s scored as an ordinary `failure_rate` 1.0**, with a complete, well-formed set of
  rates and intervals, and no refusal of any kind.

Running a suspending pipeline and a crashing pipeline side by side produces the same `failed`, the
same `failure_rate` 1.0, and identical results files. The only difference is free text inside
`rollout.error`.

## In plain language

The evaluation answers "how good is this agent" with a number, and that number currently absorbs
"the agent asked a question", "the builder wired it up wrong" and "the backend was switched off".
All three come out looking like an agent that gets everything wrong.

The transport case is the sharpest, because it happened here, to a careful agent, and was caught by
noticing rather than by anything the library said.

## The technical shape

The classification is in `Outcome`, and everything that is not a scored answer becomes
`Outcome.FAILED`. The six rates are then computed over those outcomes and are, on their own terms,
correct: `failure_rate` 1.0 is a true statement about outcomes as classified. Nothing is hidden.
What is missing is any distinction between a failure the agent produced and a failure it was
handed.

Note that the glossary in [`CLAUDE.md`](../../../CLAUDE.md) is explicit on one of the three:
"Consultation is a designed interaction, not a fault path. The builder plans for it. It is not an
error, an escalation, or a fallback."

## What it costs a builder, concretely

A builder's agent asks the end user one clarifying question before answering. They run their first
evaluation. It reports `failure_rate 1.000 [0.610, 1.000]` and `accuracy 0.000`. Every rollout is
sitting on disk, suspended, waiting for an answer, fully resumable. The builder's reasonable
conclusion is that their agent is broken.

The transport version: an evaluation runs overnight against a backend that goes down at 2am. In the
morning there is a complete results file with intervals, reporting that the agent answers nothing
correctly.

## The options

**Option A. A separate outcome class for a failure that is not the agent's.** `Outcome` gains a
member, the rates exclude it from their denominators, and the results file reports how many there
were.

- The six rates become statements about the agent again.
- A denominator that silently shrinks is its own hazard, so the count has to be reported beside
  every rate rather than only in a corner of the file.
- Requires deciding which exceptions are the agent's, which is a judgement the library has to make
  on the project's behalf.

**Option B. Refuse rather than score.** `RunSuspended` propagates as §7.4 already says. A
transport-class failure above some threshold ends the evaluation with a refusal rather than a
results file.

- Matches what the documentation already claims for suspension.
- An evaluation is a long, expensive thing, and ending it on the first failure of a class that may
  be transient is its own cost. A threshold turns one decision into two.

**Option C. Keep scoring, record the distinction.** Outcomes stay as they are, and the results file
gains a breakdown of what the failures were: agent, suspended, configuration, transport.

- Smallest change. Nothing about the rates moves, so no existing number changes meaning.
- The headline figure a builder reads still says the agent failed. It moves the problem from
  invisible to findable, which is not the same as fixed.

**Option D. A and B together, by class.** Suspension propagates (B, and it is what §7.4 already
promises). Configuration errors end the evaluation, since they fail identically on every rollout
and one is enough to know. Transport failures get the separate outcome class (A) with the count
reported, since they are genuinely transient and a run that hits a few should still produce a
number.

## Recommendation

**Option D.** The three cases look alike in the code and are not alike in what a builder should do
about them. A suspension means "go and answer the question, then resume", and §7.4 already says it
raises. A configuration error means "fix the wiring", and failing fast on the first one saves the
other k×n rollouts. A transport failure means "some of this did not get measured", which is exactly
what a separate outcome class with a reported count says.

The one thing I would not do is Option C alone. A results file that reports `failure_rate 1.0` with
a footnote explaining that the backend was down is still a results file whose headline number is
wrong, and headline numbers are what get copied into a report.

---

# Decision 4. What ranking does a project get when it passes `embeddings=`?

## What happened

Six queries, each built so the correct answer shares no word with the query and one decoy holds
most of the query's words. This is the shape `docs/retrieval.md` exists for. Position of the
correct document in the top five:

| Ranking | 18 documents | 318 documents |
|---|---|---|
| `Semantic()` alone | **5 of 6** | 4 of 6 |
| **Default `Hybrid(fuse=RRF(k=5))`** | **1 of 6** | **2 of 6** |
| `Hybrid(fuse=Interleave())` | 4 of 6 | 4 of 6 |
| `Hybrid(fuse=WeightedScore(lexical=0.3))` | 5 of 6 | 4 of 6 |
| Default plus a 33-word `stopwords` list | 5 of 6 | 4 of 6 |

Passing `embeddings=` is the one line of change the feature is sold on, and it also silently
selects the ranking: [`retrieval.md:107`](../../../docs/retrieval.md#L107), §4, "It defaults to
`Lexical()` without `embeddings` and `Hybrid(fuse=RRF(k=5))` with it."

## In plain language

A builder adds semantic search because a question phrased differently from the document should
still find it. On exactly that kind of question, the default they get is worse than either of the
two things it combines, and much worse than the semantic search they added.

## The technical shape

Two mechanisms compound, and both are visible in the numbers:

- **No stopword list ships.** `DocumentIndex.stopwords` defaults to `frozenset()`
  ([`search.py:176`](../../../src/simple_agents/builtins/search.py#L176)), and
  [`tools.md:459`](../../../docs/tools.md#L459) states "No list ships". A natural-language question
  therefore hands a BM25 vote to nearly every document in the corpus, through words like `the` and
  `does`.
- **RRF compares rank alone.** `RRF.combine` ([`ranking.py:127`](../../../src/simple_agents/builtins/ranking.py#L127))
  cannot tell a BM25 score of 3.904 from one of 0.141, so two weak lexical votes outweigh one
  strong semantic one.

Worked, on the query `does the reader finish long books`:

```
lexical   1. library-hours 3.904   2. extension-form 0.248   3. bearing 0.213 ...
semantic  1. reader-note   0.472   2. library-hours  0.320    <- reader-note is the answer

RRF(k=5)  1. library-hours  0.3095   (lexical 1, semantic 2)
          2. extension-form 0.2679   (lexical 2, semantic 3)
          ...
          8. reader-note    0.1667   (lexical absent, semantic 1)
```

The answer is ranked first by the retriever that understood the question, and eighth of ten by the
default that combines it with one that did not.

## The evidence that argues against acting on this alone

[`build-logs/semantic-recall-build-log.md`](../../../dev-docs/build-logs/semantic-recall-build-log.md) records
that these defaults were chosen against three corpora and real judgments, and that a recommendation
inverted once it met them. Six queries built by a QA agent to exhibit a property are not that. They
demonstrate the failure exists and is mechanical; they do not measure how often it happens on
realistic queries.

## The options

**Option A. Ship a stopword list by default.** The default gains a small English stopword list, and
`stopwords=` overrides it.

- Restores parity in the measurement above (5 of 6, matching `Semantic()`), and treats the cause
  rather than the symptom.
- A stopword list is language-specific, and the library currently makes no language assumption. A
  default list is an assumption that a non-English corpus silently pays for.

**Option B. Change the default fusion** to `WeightedScore(lexical=0.3)`.

- Also restores parity (5 of 6), and keeps score information that RRF discards.
- A weight is a number with no principled value, and the right one is corpus-dependent. It replaces
  a defensible default with a tuned one.

**Option C. Default to `Semantic()` when `embeddings=` is passed**, and make `Hybrid` explicit.

- The builder gets what they asked for. Passing an embedding client and receiving a ranking mostly
  decided by word overlap is the surprise at the root of this.
- Gives up the lexical arm's genuine strength on exact terms, names and codes, which is what hybrid
  is for.

**Option D. Leave the default and document the failure**, with the mechanism and the remedies.

- Honest, cheap, and consistent with the build log's evidence.
- The default stays the one that loses the query shape the feature is sold on, and documentation is
  a weak instrument against a default.

## Recommendation

**Re-run the build log's evidence against these six queries before choosing, then Option A.**

I am recommending a measurement rather than a change because the two bodies of evidence disagree
and one of them was built to exhibit the effect. That is worth an hour, and it is the same
discipline the build log itself applied when a recommendation inverted.

My expectation, stated so it can be checked rather than trusted: Option A will hold up, because the
mechanism is not subtle. A query that is a natural-language sentence gives BM25 a vote on every
document containing `the`, and no amount of corpus realism removes that. If the re-run shows
otherwise, Option D is the honest fallback.

---

# Decision 5. How do this checkpoint's findings enter the schedule?

## What happened

This pass produced nineteen named findings, of which five are blockers, plus roughly forty
documentation statements that are false. Separately, **dogfood #4 finished overnight** and has no
findings record. It is [`plan.md`](../../../dev-docs/plan.md) §1.2 item 2, and it is the run that measures whether
the decision surface worked.

Three bodies of work now exist and none of them is scheduled anywhere:

- The four decisions above, and whatever they imply.
- The plain defects and documentation corrections from this checkpoint, listed below.
- Dogfood #4's findings record, and whatever that produces.

## In plain language

The queue in `plan.md` §1.2 does not know any of this happened. Something has to put it there, and
the order matters because the items interact: two of the decisions above change what the correct
documentation correction is, so writing those corrections first means writing sentences that then
get reversed.

## What I am asking

Three things, and they are separable:

- **Whether I update [`plan.md`](../../../dev-docs/plan.md) §1.2 and [`handoff.md`](../../../dev-docs/handoff.md)** with what
  came out of this, and in what shape. Both are files I have not touched, per the rule that
  `dev-docs` changes are presented before they are made. My proposal is one new §1.2 item for
  the decisions above, one for the mechanical fixes, and a §1.7 entry for this checkpoint.
- **Whether the ~40 documentation corrections go in as one item or per document.** One item is
  easier to schedule and harder to review. Per document matches the shipped-document review already
  in flight at §1.2 item 4, and `evaluation.md` is next in that review and is also the document
  with the most corrections pending, so the two could be merged.
- **Whether dogfood #4's findings record comes before or after this work.** It is a cold read of a
  library that this pass has just found five blockers in. Writing it first means it is written
  against the library as the dogfood met it, which is the honest thing. Writing it second means the
  fixes land sooner.

## Recommendation

**Decisions first, then dogfood #4's record, then the corrections.**

The decisions unblock everything else and two of them change what the corrections say. Dogfood #4's
record should be written against the library as that run met it, and it will read differently once
these blockers are fixed, so it is worth doing before the tree moves. The corrections are the
largest body of work and the least urgent, and merging them into the shipped-document review that
is already running is cheaper than scheduling them twice.

On the mechanical fixes: **the resume claim ordering and the `include_extras` one-liner should not
wait for any of this.** The first is data loss with no design question in it, and the second is one
argument with a verified patch already written.

---

# What is not in this sitting

Recorded so the scope above is legible, and so nothing here is mistaken for an open question.

**Plain defects with an obvious correct behaviour**, needing a fix and no ruling:

- The resume claim is discarded before the validation that can refuse
  ([`core.py:610`](../../../src/simple_agents/pipeline/core.py#L610) (`discard_claim`)), so a typo in `answers=` destroys
  a suspended run.
- `get_type_hints(fn)` without `include_extras=True`
  ([`tools.py` `_resolved_hints`](../../../src/simple_agents/tools.py#L1069)) discards every tool parameter's
  description and constraints. Patch in `patches/`, verified, unapplied.
- `resume_from` is refused on the default recording path.
- `resume(answer=...)` reaches an `AgentNode` and no other node kind.
- `on_reply(field=...)` over a dict silently takes the `declined` branch.
- A redacted tool result stops a run replaying its own cassette.
- `charged_cost` adds device-seconds to money.
- A multi-node stop records one node in the manifest.
- `simple-agents init --claude` writes an AGENTS.md naming a path that layout does not have.
- `Manifest.restore` never restores `counts["delegation"]`.
- `consult()` produces a tool whose `version` is `None`.
- A cached `web_search` is charged the full declared price.
- `contains_normalised` does not fold accents.
- `embeddings_openai` writes a literal `input_cache_read=0` for a count it did not measure.
- `PacedClient.waits` counts loop iterations rather than calls held back.
- `Retry-After` loses to a longer backoff, and an HTTP-date form is ignored.

**Documentation corrections**, about forty, listed per area in `findings/`. The largest groups are
counts that disagree with the list beside them (FT-13's "four" listing five, `brief.py`'s "three
stages" listing four, the sample report's "3 passed" beside four rows, the README's 28-versus-30),
and the README's six unresolved review comments and one placeholder that renders to the reader.
