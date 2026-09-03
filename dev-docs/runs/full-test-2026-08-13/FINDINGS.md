# Findings, ranked

Every entry is backed by an executed reproduction. The area file named on each carries the fuller
evidence, and `runs/*.jsonl` carries the raw rows.

**Severity.** **Blocker** stops a release. **Major** misleads a builder about something that costs
money or correctness. **Minor** is wrong but bounded. **Cosmetic** is prose.

**Status, 2026-08-14: every finding below has been fixed.** This file is kept as it was written,
as the record of what the pass found and how it was measured, so a later reader can check the
reasoning rather than take the fix on trust. Corrections made after a fix challenged a finding are
marked inline, and `B1` carries one that reverses a claim this file originally made.

Thilina ruled on the five decisions in `SITTING-BRIEF.md` on 2026-08-13; `RULINGS.md` records them.
Five streams implemented them, one per group of files, with `fixes/` holding a build log each and
`fixes/RECONCILIATION.md` settling three points where two streams reported the same thing
differently. `PENDING-SIGNOFF.md` is what still needs Thilina.

After the fixes: **2089 tests pass**, `prose_check` is clean, and every changed surface was
verified live on Gemini and on a self-hosted vLLM from the installed wheel rather than from source.

---

## The shape of it

**Fifty-one checks did not pass, and they are not fifty-one separate defects.** They resolve into
the findings named below, which fall into four clusters and a tail. The clusters are worth more
attention than any count suggests, because each is one cause producing several symptoms across
several areas.

| Cluster | What is common to it | Worst severity |
|---|---|---|
| **Budget containment** | `max_steps` is documented as exact and is not, on two paths | Blocker |
| **Evaluation identity** | what an evaluation is filed under omits sampling, tools and budget, so different agents share it | Blocker |
| **Resume** | a refusal raised after the claim is discarded destroys the run; a `Deterministic` node never receives its answer; the documented `resume_from` path is refused | Blocker |
| **Retrieval defaults** | the shipped default ranking loses the query shape the feature exists for | Major |
| The tail | roughly forty documentation statements that are false, and a handful of narrow code defects | Major down |

**The statistics are sound, and that is worth stating first because it was the largest open
question.** `wilson_ci` matches `scipy.stats.binomtest(...).proportion_ci(method="wilson")` to
within 1e-12 at every one of 60 tested `(successes, n)` pairs including `n=1`, `0/n` and `n/n`,
and the bootstrap provably resamples examples rather than rollouts as §4 states: the interval is
byte-identical at k=1, 5 and 20 while a flat bootstrap over the same values narrows. What is wrong
sits around the arithmetic rather than in it.

**All 17 evaluation flags were reproduced and confirmed; none was dismissed.**

---

## Blockers

### B1. `max_steps` does not bound a run that branches, or one that searches

`area-a-pipeline-graph.md` A-1, `area-de-retrieval-memory.md` D-1.

Documented as exact in four places, one of them the `Budget` docstring:
[pipeline.md:513](../../../docs/pipeline.md#L513), [pipeline.md:918](../../../docs/pipeline.md#L918)
("whether or not calls overlap"), [budget.py:129](../../../src/simple_agents/budget.py#L129), and the
CHANGELOG entry for the concurrency item.

**Corrected 2026-08-13, after Stream A challenged the reproduction and it was re-measured on a
worktree at the pre-fix commit `2f4db4c`. The original statement of the precondition was wrong.**
Corrected measurement, `max_steps=1`, eight nodes:

| Shape | `concurrent_nodes` | concurrency | Calls |
|---|---|---|---|
| chain of `LLMNode` | none | 1 and 4 | 1 |
| branch arms from a route | **none** | 1 and 4 | **1** |
| branch arms from a route | **all eight grouped** | 1 and 4 | **8** |
| fan-out with `over=` | either | any | bounded |
| embedding and rerank inside a search | none needed | 1 | **8**, run completed |

**The precondition is membership in a declared `concurrent_nodes` group, not branching.** The
reproduction published in this file omitted `concurrent_nodes` and does not reproduce as written.
The measurement behind the finding did declare a group, so the defect is real and the printed
repro was wrong.

**Two consequences, and the first reverses what this file previously said.**

- **The branch-arm half is a concurrency regression after all.** `concurrent_nodes` arrived with
  `2f4db4c`, so no node could have been in a group before it. This file previously said the defect
  "is not a concurrency regression" and "predates it". That was wrong for this half.
- **The retrieval half does predate it.** Area D's `RETR-057` is a one-node pipeline with no group
  at all, which made eight model calls under `max_steps=1` and reported `completed`.

`run.one_step` was called only from `LLMNode._fan_out`. Everything else charged the step after the
response returned, and the run budget was consulted between batches rather than inside one.

`max_steps` is the only axis documented as exact, which makes it the one a builder reaches for as a
hard stop. Forty arms under `max_steps=5` is forty billed calls, and the run then reports
`BudgetExceeded`, which reads as though the bound held.

### B2. A refused resume destroys the suspended run

`lead-verified.md` L-5, `area-hb-suspension-envelope.md` H-2, H-4.

One mistyped node id in `answers=` deletes `suspension.json`. The refusal names the correct id;
the corrected call then reports "There is no suspended run".

```
resume(answers={"ask_typo": ...})  ->  refused, naming 'ask' as the right id
                                   ->  suspension.json is gone
resume(answers={"ask": ...})       ->  "There is no suspended run in ..."
```

[core.py:610](../../../src/simple_agents/pipeline/core.py#L610) (`discard_claim`) calls `discard_claim(root)` and then
evaluates `codec.decode(...)` and `self._answers_for(...)` as arguments to `_drive(...)`. Python
evaluates arguments before the call, so every refusal those raise lands after the state is gone.
The restore block above it is protected by `try/except` with `release_claim`; this is not.

Area H recorded the same shape from three further directions: a version mismatch, an unreadable
value tag, and a refused resume generally. **The better the refusal message, the worse the
outcome**, because it invites a corrected retry that cannot succeed.

### B3. A resume into a pipeline used as a node discards the answer

`area-hb-suspension-envelope.md` H-1.

The nested case, which is what the new tree-shaped suspension state exists for.

### B4. An evaluation cannot tell a suspension, or a transport failure, from a crash

`area-f-evaluation.md` F-1, `area-j-docs-implementability.md` J-3.

`_rollout` catches bare `Exception` ([runner.py:1323](../../../src/simple_agents/evaluation/runner.py#L1323)).
`RunSuspended` subclasses it, so a rollout that stops to ask the end user is scored `failed`.
[evaluation.md §7.4](../../../docs/evaluation.md) says it raises `RunSuspended`. No field of the
results file distinguishes a suspension from a crash, and the suspension state is on disk and
resumable the whole time.

The glossary is explicit that consultation is a designed interaction, not a fault path. J2 measured
what a builder sees: `failure_rate 1.000 [0.610, 1.000]` for a working agent.

**A precision, from the fuller area F measurement.** No rate *hides* the suspension:
`failure_rate 1.0` is a correct reading of the outcomes as classified, and the six rates come back
internally consistent. What is absent is any statement that the runs are **resumable**. Running a
suspending pipeline and a crashing pipeline side by side produces the same `failed` and the same
`failure_rate 1.0`, and the only difference is free text inside `rollout.error`.

**The same swallow converts configuration errors into results.** J1 had fifteen misconfigured
rollouts reported as a complete six-rate result, and `pipeline.md` §2.4's "refused before the run
starts" does not hold inside `EvalSuite.run`.

**And it converts transport failures into results**, which this pass observed by accident and is
worth recording as the strongest form of the finding. When the lead restarted the shared vLLM
server mid-pass, an area F suite kept running against a model id that no longer existed. **Nine
consecutive 404s scored as an ordinary `failure_rate 1.0`**, with a complete, well-formed set of
rates and intervals and no refusal of any kind. The agent noticed, purged the contaminated rows and
re-ran them. Nothing in the library would have told it. An evaluation in which every single rollout
failed because the backend was gone is presented identically to one measuring a genuinely poor
agent.

### B5. Two pipelines differing only in sampling, tools or budget share one `eval_id`

`area-f-evaluation.md` finding 1. Three consequences, each independently reproduced.

`_eval_id` hashes `graph_fingerprint()`, which covers node ids, kinds, edges, loop bounds, error
edges, retry policies and output schemas. **Sampling parameters, tools, `allow_unknown` and budgets
are outside it**, and nothing else in `_eval_id` carries them. Four edits produce a byte-identical
`eval_id`: `temperature`, `max_output_tokens`, `allow_unknown`, and the pipeline budget. Adding or
removing a tool on an `AgentNode` does too.

[evaluation.md §6.1](../../../docs/evaluation.md#L478) says "two evaluations differing in any of those
write into different ones", and [§10](../../../docs/evaluation.md#L1136) names "a tool added or
removed ... a temperature moved" as variants `compare_variants` runs.

- **`compare_variants` cannot run the variant §10 leads with.** The baseline arm runs and is paid
  for, then the variant resolves to the same directory and is refused by `_refuse_a_used_directory`.
  The refusal names neither the variant nor the sweep, and arrives **after 40 rollouts have been
  spent**.
- **`resume_from` mixes rollouts across the change and the results file does not say so.** An
  evaluation run at `temperature=None`, resumed under a suite declaring `temperature=0.7`, is
  accepted; `config.nodes` records `0.7` for a set in which four of six rollouts ran at `None`. The
  client confirms both temperatures reached the backend. This is the case §6.5 says the `eval_id`
  check prevents, and FT-15 is the failure it names.
- **`rescore` accepts rollouts a different configuration produced**, which is exactly the FT-15
  case its refusal exists to prevent.

Same family as **M3** below: an identity that omits something a builder considers part of what was
measured.

### B6. `resume_from` is refused on the default recording path

`area-f-evaluation.md` finding 2.

An evaluation records by default into `<eval_dir>/cassette.jsonl`. On the resuming call
`_recording_by_default` reconstructs `Cassette.record` over that same path, and `Cassette.record`
refuses a file that already holds a recording. **The evaluation that stopped is the one that wrote
it**, so the refusal fires exactly when resuming is wanted, and its message is about recording and
never mentions `resume_from`.

The documented call in [§6.5](../../../docs/evaluation.md#L673) uses an ordinary envelope and does not
run. Resuming works only under `record=False`, `Cassette.off()`, or an explicit cassette path.
**The documented recovery path for a long evaluation that stopped is the one that fails.**

---

## Major

### M1. A tool parameter's `Field(description=...)` never reaches the model, and its constraints are dropped

`lead-verified.md` L-1, `area-c-tools.md` 1. **Patch written and verified:
`patches/L-1-tool-annotated-metadata.patch`.**

[tools.md:61](../../../docs/tools.md#L61) says "A description anywhere in that schema is prompt text
... The model reads it", with a worked `Annotated[int, Field(description=...)]` example, and warns
that without one the parameter reaches the model "as a bare integer with a default and nothing
saying what a good value is". That is exactly what happens **with** one.

`ge=1, le=10` is also dropped from the schema **and from the validator**: `top_k=400` is accepted.
Cause is one missing argument at [tools.py `_resolved_hints`](../../../src/simple_agents/tools.py#L1073):
`get_type_hints(fn)` strips `Annotated` metadata without `include_extras=True`. Adding it restores
both the description and the bound; verified.

### M2. `resume(answer=...)` delivers to an `AgentNode` and to nothing else, and the documented example uses the failing node kind

`area-j-docs-implementability.md` J-1, `area-c-tools.md` 3, `area-hb-suspension-envelope.md` H-3.

A `Deterministic` node holding `consult` re-runs on resume, calls the channel again and suspends
again. [tools.md §4.6.1](../../../docs/tools.md) shows the consultation on a `Deterministic` node, and
[pipeline.md §1.8](../../../docs/pipeline.md) says "a `Deterministic` node has nothing to lose". It has
the pending question to lose. Found independently by a test agent and by a coding agent building
from the docs.

### M3. `pipeline.md` overstates what the `graph_fingerprint` covers, and contradicts `run-envelope.md`

`area-a-pipeline-graph.md` A-3.

A contained pipeline's `tools=`, `budget` and `fetch_policy=` do not move the fingerprint;
`successors` does. [run-envelope.md:88](../../../docs/run-envelope.md#L88) is correct;
[pipeline.md:297](../../../docs/pipeline.md#L297) says "a change to any of it moves the
`graph_fingerprint`" and is not. The fingerprint gates a resume refusal and an evaluation's
recording refusal, so a replayed evaluation can be served from a recording made when a sub-pipeline
could reach a different tool set.

### M4. `on_reply(field=...)` is documented to work over a dict, does not, and silently takes the wrong branch

`area-j-docs-implementability.md` J-2.

`field=` is an attribute lookup. Over a dict it finds nothing, and a missing reply is
indistinguishable from a refusal, so the route takes `declined` without complaint. A field
annotated `str` coerces the `Reply` and drops `chose` with the same result. **A route that cannot
find the reply picks a branch rather than refusing**, which is the failure the typed consultation
answer was built to remove.

### M5. A redacted tool result stops a run replaying its own cassette

`area-hb-suspension-envelope.md` B-1.

### M6. `charged_cost` adds device-seconds to money

`area-hb-suspension-envelope.md` B-2. [run-envelope.md](../../../docs/run-envelope.md) says
device-seconds is a unit rather than a currency and that nothing adds it to a figure in money.

### M7. A run that stopped in several nodes records one of them in the manifest

`area-hb-suspension-envelope.md` H-5. The second stop's node and question are recorded nowhere,
in the feature that shipped hours earlier specifically to support stopping in more than one place.

### M8. A cached `web_search` is charged the full declared price

`lead-verified.md` L-3. `web_search` is `SPENDS_MONEY`, requires a `declared_cost`, returns early
on a cache hit, and takes no `SpendMeter`, so it has no way to report that a hit spent nothing.
`docs/tools.md` §1.5 says a call a cache answered pays nothing, and §4.5 recommends exactly this
composition. `max_cost` therefore stops a run earlier than it needs to.

### M9. The shipped default ranking loses the paraphrase on five of six queries

`area-de-retrieval-memory.md` D-2. **Measured across six queries and two corpus sizes**, after an
initial single-query sighting was widened specifically so the severity would be honest.

Six queries, each built so the answer shares no word with the query and one decoy holds most of
the query's words. Position of the correct document in the top five:

| Ranking | 18 documents | 318 documents |
|---|---|---|
| `Semantic()` alone | **5 of 6** | 4 of 6 |
| **Default `Hybrid(fuse=RRF(k=5))`** | **1 of 6** | **2 of 6** |
| `Hybrid(fuse=Interleave())` | 4 of 6 | 4 of 6 |
| `Hybrid(fuse=WeightedScore(lexical=0.3))` | 5 of 6 | 4 of 6 |
| Default plus a 33-word `stopwords` list | 5 of 6 | 4 of 6 |

Passing `embeddings=` is one line of change, and [retrieval.md §4](../../../docs/retrieval.md#L107)
records that it also silently selects `Hybrid(fuse=RRF(k=5))`. **On the query shape the feature
exists for, that default discards the retriever that answered.**

**The mechanism, which is what makes this fixable.** No stopword list ships
(`DocumentIndex.stopwords` defaults to `frozenset()`, and `tools.md` says "No list ships"), so BM25
hands a lexical vote to nearly every document through words like `the` and `does`. RRF compares
rank alone and cannot tell a BM25 score of 3.9 from one of 0.14, so two weak votes beat one strong
one. The paraphrase, absent from the lexical list by construction, has one vote and lands eighth
of ten.

Declaring stopwords, or `WeightedScore(lexical=0.3)`, restores parity. This is a defaults question
rather than a broken algorithm, and `build-logs/semantic-recall-build-log.md` records that the
defaults were chosen against real judgments, so the right next step is to re-run that evidence
against these six queries rather than to change a default on this alone.

### M10. `contains_normalised` does not fold accents

`area-c-tools.md` 2, `lead-verified.md` L-4. `contains_normalised("Beyoncé sang", "Beyonce")` is
`False`. A grounding check on any accented name returns a false negative.

### M11. `Reply`'s own example is the case the default matcher rejects

`area-c-tools.md` 4.

### M12. The README ships unresolved review comments and a placeholder in visible prose

`area-i-conformance-cli-packaging.md` 1. Six `<!-- Thilina: ... -->` notes, an empty
`## Cassettes and Replays` heading, and line 95, which renders to the reader as: *"Registration
without one is refused, to ensure \<what does this provide?\>."*

### M13. `simple-agents init --claude` writes an AGENTS.md pointing at a path that does not exist

`area-i-conformance-cli-packaging.md` 2 and 3. The note is one constant naming
`.agents/skills/simple-agents/SKILL.md` whatever `--claude` or `--to` actually did, so the coding
agent follows a dead path. Separately, `init` writes no note at all when AGENTS.md already contains
the substring `simple-agents` anywhere, which the README's own `uv add simple-agents` line supplies.

### M14. `Retry-After` loses to a longer backoff

`area-g-model-clients.md` G-1, `FLAG-4`. `_http._wait` takes `max(backoff, retry_after)`, so a
backend asking for a shorter wait is ignored and the run waits longer than required, charged to
`max_wall_clock_ms`. An HTTP-date `Retry-After` is ignored entirely rather than parsed.

---

## Minor and cosmetic, grouped

Full detail in the area files.

**Counts that disagree with the thing beside them.** The FT-13 failure message says "the four are"
and lists five record types. `brief.py` says "the three stages are" and lists four. The sample
conformance report shows four `pass` rows and counts "3 passed", and omits FT-30. The README says
28 characteristic failures where there are 30, and four record types where there are five.
`conformance.md` §4 counts five entries enforced by construction where six say they are.
`questions --stage` help omits `brainstorm`.
(`area-i` 7, 8, 9, 10; `area-g` FLAG-2, FLAG-3, FLAG-6, FLAG-8.)

**Documentation that names the wrong place or the wrong default.** FT-04's message sends the reader
to the manifest where the code reads the results file. The vLLM `report_concurrency` default is
documented inverted, and §3 calls it opt-in where it is opt-out.
`run-envelope.md` §3.1 documents the pre-`node_id` tool-call cassette key. `trajectory-format.md`
§4.1 and `run-envelope.md` §2.1 contradict each other on whether `max_wall_clock_ms` is charged for
waiting. `consultation_route` is written into every manifest node entry and documented nowhere.
`memory_search` is documented as returning "every key there is" and caps at 50.
(`area-g` FLAG-1/5/7/10; envelope inventory flags 1 to 6.)

**Narrow code defects.** `Manifest.restore` never restores `counts["delegation"]`, so a resumed run
undercounts. `consult()` produces a tool whose `version` is `None` where every decorated tool
derives one, so its cassette key carries a null version. `embeddings_openai` writes a literal
`input_cache_read=0` where an unmeasured count should be `Unknown`. `PacedClient.waits` counts loop
iterations rather than calls held back. An embedding's `model_call` is parented to the node
execution rather than the tool call when the search runs in a `Deterministic` node.
A `Join` placed in a pipeline's node list constructs without complaint and dies at run time with
`AttributeError: 'Join' object has no attribute 'node_kind'` rather than a refusal.
`to_mermaid()` draws neither `suspend_before` nor a declared stop.
(`lead-verified` L-2; `area-g` G-2, FLAG-9; `area-d` D-3; `area-a` A-2; envelope inventory.)

---

## What went right, and should be said

- **The interval arithmetic is correct.** `wilson_ci` matches scipy to within 1e-12 across 60
  `(successes, n)` pairs including the degenerate ones, and the bootstrap provably resamples
  examples rather than rollouts, exactly as §4 states. This was the largest open question in the
  pass and it is closed.
- **All eleven conformance checks work.** Each was made to fail by a single mutation of a passing
  project, each named the right FT-nn, and each printed the taxonomy's own string. Exit codes are
  as documented.
- **Memory has no defect**, over 36 checks. The store, the three tools, scoping, persistence,
  redaction, put semantics and concurrent writes all behave as documented. **`Example.memory`
  isolation holds**: 24 rollouts at concurrency 4 and at concurrency 1, each overwriting a seeded
  key with a marker no other rollout can produce, and every rollout saw exactly its own.
- **The `VectorScan` identifier fix holds** against adversarial ids (`Ω-14`, `doc 2`, `007`,
  `MX-4471-B`) across rebuilds, removals, re-adds, two save/load round trips and uneven batches. No
  hit ever named a document other than the one whose text matched.
- **The reasoning, overflow and tool-refusal paths all behave as documented**, verified after
  reconfiguring vLLM twice and restoring it.
- **Every documented count matches the code**: 33 questions, 13 at brainstorm with 8 required, 6
  decision kinds, 11 checks, 30 taxonomy entries, 15 documents, 13 built-in tools.
- **The concurrency feature holds up live.** Declared overlap reduces wall clock against a real
  backend, the three construction refusals fire and name the offending node or tool,
  non-transitivity holds, and a run recorded at `concurrency=4` replays against a client pointed at
  a dead address with an invalid key.
- **Delegation works.** A real model chose a three-way decomposition, node ids nested correctly,
  `max_calls=1` held, and the model reported the two it could not reach as unknown rather than
  inventing them.
- **Memory works end to end** across separate runs on a self-hosted backend, and 25 of 25 memory
  checks passed.
- **A coding agent built a complete, evaluated, replayable agent from the shipped documents
  alone**, in a sealed venv with the source forbidden. J1's own summary of the failure mode is the
  most useful sentence in this checkpoint: **"the library's error messages were consistently better
  than the docs at exactly the points where the docs were wrong."**
