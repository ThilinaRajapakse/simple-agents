# Dogfood #1, run 2 — findings and the v0.1 changelog

The second run of `runs/dogfood-protocol.md` §1 against the same task and the same builder, on the wheel built
at `3ec0e5c` rather than at `e2b277c`. **`runs/dogfood-1/findings.md` is run 1's record and is not
restated here**; this document cites it. Findings numbered `R2-Dn` and `R2-Pn` are run 2's.
Bare `D4`, `D5`, `P1` and so on are run 1's.

**Every finding here landed at the sitting on 2026-08-07**, and §9 is the ledger: §9.3 names
the three things decided against, each with its ruling. The entries below are left as written,
so the figures are the run's rather than retrofitted.

**Project:** `/home/thilina/Projects/dogfood-1-run2`, one commit (`38543da`, `pyproject.toml`
and `.gitignore`, Simple Agents installed from the wheel into `.venv`). Fresh coding-agent
session, two-sentence prompt, `BUILD-LOG.md` requested with interactions recorded verbatim.
Thilina answered elicitation and volunteered nothing, per §4.1 step 3. A `.env` holding
`MISTRAL_API_KEY` was written by him during the run, in answer to an elicited question.

**Elapsed 13:44Z–16:53Z, about 3 hours 10 minutes.** 635 runs inside the envelope, 788 model
calls, 782 tool calls, **$0.1682** recorded. 120 further model calls defining the ground truth
ran outside the envelope and are unpriced, which is **R2-D7**.

| | run 1 | run 2 |
|---|---|---|
| Elapsed | ~90 min | ~190 min |
| Runs in the envelope | 470 | 635 |
| Model calls | 574 | 788 |
| Tool calls | 0 | 782 |
| Recorded cost | $0.1003 | $0.1682 |
| Examples | 59 (dev 30 / held-out 29) | 60 (dev 30 / held-out 30) |
| `absent_proportion` held out | 0.5172 | 0.5000 |
| k | 5 | 5 |
| Evaluations | 3 | 5 |
| Brief entries | 14 (12 required, 1 deferred) | 16 (12 required, 0 deferred) |
| `manifest.tools` | `[]` | `document_search` |
| Cassette | never recorded | recorded and replayed |
| `simple-agents check` | 7 of 7 (9 of 9 on re-run) | 9 of 9 |

---

## 1. Method, and what did not survive verification

`BUILD-LOG.md` is a coding agent's account of its own work, so it is a hypothesis. Run 1's log
survived this completely, which `runs/dogfood-1/findings.md` §1 recorded as the unusual outcome.
**Run 2's did not.** One claim is false, one is unverifiable because the project deleted the
evidence, and one diagnosis is wrong.

| Claim | Reproduced |
|---|---|
| Corpus 186 passages from 6 articles, dev 96 / held-out 90 | Exact. Oxygen 43, Packet_switching 23, Harvard 30; Black_Death 23, Amazon_rainforest 21, Steam_engine 46. |
| Example set 60, 30 per split, 15 answerable and 15 absent in each | Exact, from `evals/questions.jsonl`. |
| Verification pass 2: 60 checked, 2 flagged, 0 discarded for a bad quote | Exact, from `evals/verification.jsonl`. Both flags are the two the log names, with the doc ids it gives. |
| 3 examples removed, with reasons | Exact. `MANUAL` in `tools/build_examples.py` holds two drops and one overruled flag, verbatim as the log's table. |
| Held-out small k=5: accuracy 46.7%, false confidence 50.7%, `correct 50, correct_abstention 20, false_confidence 76, missed 4` | Exact, from `evals/results/held-out-small-k5.json`. |
| Held-out medium k=5: accuracy 58.7%, false confidence 3.3%, recall 22.7%, abstention 85.3% | Exact. |
| The `compare()` table, eight metrics | Re-ran `compare()` over the two shipped results files. Every figure and every verdict reproduces. |
| Small: 2 of 150 rollouts rejected by the grounding check, 22 model abstentions, 126 answered | Exact, recomputed from 150 trajectories. |
| Medium: 78 of 150 rejected by the grounding check, 48 model abstentions, 22 answered | 78 is the count rejected for an unresolvable `source_doc`. Two more were rejected for a missing span, so the true figure is 80 and the log's three columns sum to 148 rather than 150. Cosmetic. |
| The grounding check changed 0 of 24 asserted dev answers | Consistent: across all 94 ad-hoc single runs, **zero** finalize rejections. The specific 30-run subset cannot be isolated. |
| `simple-agents check`: 9 of 9, exit 0 | Re-run. Exact, but on a different results file than the log's — see **R2-D5**. |
| The backend returns mangled key names | Exact and worse than the log says. 104 of 114 parseable responses in the ad-hoc batch carried at least one, and `quote ` with a trailing space appears 22 times where the log names only `source_doc`. |

**The false claim.** The log says the parser change was checked against the reported number:
"replaying small's recorded cassette through the new parser gives bit-identical results — 48.0%
accuracy, 50.0% false confidence, 66.7% recall, 16.7% abstention ... matching the live run
exactly." The reported number is **46.7%** accuracy and 50.7% false confidence
(`evals/results/held-out-small-k5.json`, created 16:16:28Z). The figures the replay produced are
those of `held-out-small-k5-run1-nocost.json`, created 16:10:01Z, which is the run the project
had already set aside. Every metric and every outcome count in
`held-out-small-k5-replay-newparser.json` equals that file and none equals the reported one.
**The reported number was never replayed through the changed parser.** The mechanism is
**R2-D3**, and it is a library defect rather than carelessness: the coding agent recorded both
runs into one cassette path and the file serves the first.

**The wrong diagnosis.** The log attributes the malformed decoding to `Maybe[str]`: "most likely
because `Maybe[str]` compiles to an `anyOf`/`$ref` union", and proposes as a remedy "drop
`Maybe[str]`'s `anyOf`/`$ref` union from the schema ... The second would mean giving up the
library's `unknown` contract". A probe against the live backend says the union is not the cause
and the `unknown` contract does not have to be given up. See **R2-D1**.

**Three claims cannot be checked, because the fix deleted the evidence.** "Nine 429s on the
first dev evaluation", "the second dev evaluation reported 180 executions of a node that runs
once per rollout", and "101 of 150 medium rollouts rejected in `finalize`" all describe runs
whose directories were removed by the `shutil.rmtree` in `evals/run_eval.py:104`, which the
project added as the workaround for **R2-D4**. Nothing on disk contradicts them.

---

## 2. The ship criterion — `archive/plan-history.md` §3.3

> **v0 is done when a coding agent, given only the library and its docs, from a cold start,
> produces a trivial agent that passes `simple-agents check` at tier `evaluated`.**

**It passed, at nine checks.** Run directly against the project rather than read off the log:

```
simple-agents check: .
tier evaluated, declared in brief.toml

  pass  FT-13  No trajectory logging                              runs/held-out-medium-k5/.../trajectory.jsonl
  pass  FT-14  Model version unpinned                             runs/held-out-medium-k5/.../manifest.json
  pass  FT-24  Elicitation skipped                                brief.toml
  pass  FT-01  No evaluation at all                               evals/results/held-out-medium-k5.json
  pass  FT-02  No held-out split                                  evals/results/held-out-medium-k5.json
  pass  FT-03  Development examples leaked into the held-out set  evals/results/held-out-medium-k5.json
  pass  FT-04  Happy path only, no absent-data cases              evals/results/held-out-medium-k5.json
  pass  FT-06  Point estimate with no interval                    evals/results/held-out-medium-k5.json
  pass  FT-07  Seeds uncontrolled                                 evals/results/held-out-medium-k5.json and 150 more

0 failed, 9 passed          exit 0
```

**What it passed on**, and the two new checks are the ones worth naming, since a project passing
at seven could fail at nine:

- **FT-03** reads `contamination: {threshold: 0.8, compared: 900, clean: true, pairs: []}`. The
  split is by whole SQuAD article, so no two questions from one paragraph can straddle it. This
  is the check that run 1 failed in substance and discovered after paying for 150 rollouts.
- **FT-04** reads `absent_proportion: 0.5`, 15 of 30 held-out examples labelled absent.
- FT-13 and FT-14 read a trajectory and a manifest the envelope wrote, from real
  `Pipeline.run`s. 635 run directories, 788 model calls, 782 tool calls.
- FT-24 reads a `brief.toml` whose 12 required entries are all `answered`, **none deferred and
  none absent**, plus 4 of the 5 optional ones. Only `context_limit` has no entry.
- FT-01, FT-02, FT-06 and FT-07 read a results file `EvalSuite.run` wrote: 30 held-out
  examples, k=5, seed 41, bootstrap intervals on all eight metrics, per-rollout seeds recorded.

The gate reads `held-out-medium-k5.json`, which is the arm the project's own log declares is
not a valid measurement. That is **R2-D5**, and it did not change the outcome here.

---

## 3. The four predictions

Each was a run 1 finding whose fix is a claim about what a cold agent does next.

### D4 — the one to bet against. **The fix worked.**

Run 1 read past `builtins/search.py`, wrote BM25 by hand with the same `K1`, `B`, regex and
tie-break, and declared no tool, so `manifest.tools` was `[]` on all 470 runs.

**Run 2 used `document_search`.** `agent.py:57` imports it from
`simple_agents.builtins.search`; `corpus.py` builds a `DocumentIndex.from_texts` over the 186
pooled passages; `build_tools()` registers it in a `ToolRegistry`; and `retrieve` is
`Deterministic(retrieve, tools=tools)` calling `ctx.call_tool("document_search", ...)`. The
manifest records it with a version, a side-effect class and `offered: true`. 782 tool calls
across the run, and 173 of them replayed from a cassette.

The log names the route: "`document_search` from the library's built-ins ... which is the
library's shape for a tool the work requires at a known step rather than one the model chooses
(`tools.md` §2.1). Calling the function directly would run it and record nothing." The
`procedure.md` stage 2 sentence that landed off D4 is
[`docs/procedure.md:73`](../../../docs/procedure.md#L73): "**Read `docs/tools.md` §4 before writing
anything the library might already ship**: eight tools come with it, including `document_search`
over a `DocumentIndex` the project builds". Naming the tool before a node is written is what
changed.

**What this unblocks.** Item 7's registry, item 13's `Deterministic(fn, tools=[...])`,
`side_effect_class`, the finish check and the tool half of the cassette are dogfooded for the
first time. Two of them broke — **R2-D2**.

### D5 — contamination. **It drew the split correctly from the start.**

Three outcomes were passes. This is the third and strongest: the refusal was never met, the
standalone `ExampleSet.contamination` was never called, and no rollout was discarded, because
the split was drawn by whole article at Stage 1, before any example existed.

`BUILD-LOG.md`, immediately after the tier was chosen: "Also FT-03: whole sources go to one side
of a split, so two questions written from one SQuAD paragraph cannot straddle it." Q10 then put
the split to the builder as three options, all three grouping by article or paragraph rather
than by question. The sentence that landed off P4 is
[`docs/procedure.md:123`](../../../docs/procedure.md#L123), "**Assign whole sources to a split rather than
drawing examples one by one.**", with the same instruction at
[`docs/evaluation.md:90`](../../../docs/evaluation.md#L90).

`contamination` reports 900 pairs compared, 0 flagged. Run 1 flagged 22 and paid 150 rollouts to
find out.

### D3 — `Maybe[T]`'s replaced description. **The warning never fired, and did not need to.**

`warn_absence_undescribed` is silent on this project: constructing the pipeline under
`warnings.simplefilter("always")` produces nothing. The description was correct on the **first
model call of the run**, at 14:12:45Z — the schema recorded in that manifest already says `If no
passage states the answer, send {"type": "unknown", "reason": "..."}`.

The reason is P1, not the warning. `docs/pipeline.md` §4 now carries a worked replacement:

```python
answer: Maybe[str] = Field(
    description='The shortest span that answers the question. If the documents do not '
    'answer it, send {"type": "unknown", "reason": "..."}.'
)
```

The project's field is a near-verbatim copy of it. **Bare `"unknown"` literals: 0 of 450
rollouts across the three evaluations**, against run 1's 19 of 145. The prose fix did the work
and the code fix was not exercised.

### D9 — a cassette. **Recorded, replayed, and it exposed a defect.**

`cassette.mode` is `record` on 300 runs and `replay` on 150. `evals/cassettes/` holds two files.
`reproduce` is answered in the brief rather than absent. The `run_eval.py` interface offers
`--record` and `--replay`, and the replay served 173 model calls and 173 tool calls with zero
misses and no network.

The sentence that landed off D9 is at [`docs/procedure.md:127`](../../../docs/procedure.md#L127): "**A
recording makes the second evaluation free.** `Cassette.record(path)` on the envelope, then
`Cassette.replay(path)`". The project did exactly that and got a cassette that replays a run it
had discarded — **R2-D3**.

---

## 4. Library defects

Ranked by what they cost this project.

### R2-D1 — The library asks for strict schema-constrained decoding with a schema that does not satisfy the contract

**Design bug.** This is the root cause of most of what went wrong in the build, and the log
identified the symptom, mis-diagnosed the cause, and proposed giving up `Maybe[T]` as the
remedy.

`response_format_for` sends the Pydantic schema unchanged with `strict: True`
([`response_format_for`](../../../src/simple_agents/adapters/_openai_wire.py#L337)):

```python
return {
    "type": "json_schema",
    "json_schema": {"name": "output", "schema": dict(output_schema), "strict": True},
}
```

A Pydantic model whose optional fields carry `= None` produces `required: ["answer"]` and no
`additionalProperties`. The OpenAI-dialect strict contract that `strict: true` claims requires
every property in `required` and `additionalProperties: false` on every object. Mistral does not
reject the request. Its constrained decoder degrades instead, and emits key names padded with
punctuation:

```json
{"answer": "1775", "quote": "...", "source_doc ": "Oxygen#3"}
{"answer": "1650", "quote": "...", "source_doc: ": "Harvard_University#3"}
{"answer": "ten-horsepower", "quote": "...", "source_doc': "Steam_engine#7"}
{"answer": "steam turbines", "quote": "...", "source_doc': \"Steam_engine#10\"": "Steam_engine#10"}
```

One recorded key is `source_doc": null, "quote": null} }</INVALID_JSON> {`.

**Measured, not asserted.** 60 calls to `mistral-small-2603` at `temperature=0.0` over 10 real
prompts taken from the project's cassette, four arms:

| Schema sent | Clean | Mangled |
|---|---|---|
| The library's, unchanged (run twice) | **0 of 20** | 20 |
| Plus `additionalProperties: false` | 10 of 10 | 0 |
| Plus every property in `required` | 10 of 10 | 0 |
| Both, and `Maybe[str]` flattened to a plain string | 10 of 10 | 0 |

**The `anyOf`/`$ref` union is not the cause.** The flattened arm and the union arm both come
back clean once the schema is compliant, so the log's proposed remedy of dropping the `unknown`
contract would have cost the contract and fixed nothing that the compliance repair does not.

**Why run 1 did not see this.** Run 1's schema had no field defaults, so Pydantic put all four
properties in `required` and the request happened to be compliant on that axis. Its 580 model
calls carry **zero** mangled keys. The difference between the two runs is one Pydantic idiom —
`source_doc: str | None = None` — and nothing in the library or the docs says it changes what
the backend is being asked to guarantee.

**The library's own recordings cannot catch it.** `tests/fixtures/wire/mistral/json_schema.json`
is a hand-built schema with `required: ["answer", "found"]` and `additionalProperties: false`,
which is a shape `response_format_for` does not produce from `tests/schemas.py`'s `Answer`. The
twelve recorded backend cassettes are all short prompts and all come back clean. So the evidence
that a server accepted the request is evidence about a schema the library does not emit. This is
the failure class `handoff.md` names, one layer in: the suite did use a real backend, with the
wrong input.

**What it cost this project.** A hand-written `model_validator(mode="before")` repairing key
names, which is 30 lines of `agent.py` and is the only reason the small arm has a number at all;
17 of 23 supported dev answers reading as uncited before it was written; and the medium arm
being unmeasurable, with 78 of 150 rollouts converted to `unknown` by a grounding check reading
a citation the parser could not recover. The log's own summary: "The evaluation was measuring my
parser against medium's malformed output, not medium's ability to answer questions."

### R2-D2 — A tool on a `Deterministic` node is invisible to the evaluation, including to FT-20's refusal

**Design bug.** Item 13 shipped `Deterministic(fn, tools=[...])`; `_tools_of` was not updated for
it ([runner.py:2828](../../../src/simple_agents/evaluation/runner.py#L2828)):

```python
for _, node in pipeline.declared_nodes():
    if not isinstance(node, (AgentNode, LLMNode)):
        continue
    for tool in getattr(node, "tools", []):
```

`_tools_of(pipeline)` returns `[]` on this project while `retrieve` declares `document_search`.
Two consequences:

- **`config.tools` is `[]` in all five results files**, on a project that made 782 tool calls.
  The manifest records the tool correctly, so the run envelope and the evaluation disagree about
  whether this agent has any tools. `docs/evaluation.md:433` documents `config` as carrying "the
  tools and their side-effect classes".
- **`_refuse_unsafe_tools` cannot see it**
  ([runner.py:2129](../../../src/simple_agents/evaluation/runner.py#L2129)). FT-20's protection against
  executing something that reaches outside the run 150 times does not apply to a tool called at
  a fixed point. Here the tool is `read_only` and nothing was harmed. A project calling
  `http_fetch` or a `PURCHASES` tool from a `Deterministic` node gets no refusal.

`procedure.md` stage 2 sends a coding agent to exactly this construction: "A step that has to
call a tool but chooses nothing is `Deterministic(fn, tools=[...])`, not an `AgentNode`." The
documented shape is the one the refusal does not cover.

### R2-D3 — Recording into a cassette path that already holds one silently replays the earlier run

**Design bug**, with a prose half at **R2-P3**.

`Cassette.lookup` serves `group[0]`, documented as "the first response recorded, so a replay
returns the same answer every time and a later recording into the same file cannot change what
an earlier run replays" ([`lookup`](../../../src/simple_agents/records/cassette.py#L351)). That rule is
right in isolation. Its consequence when two evaluations record to one path is that **the second
run's responses are written into the file and are unreachable**.

`evals/cassettes/held-out-small-k5.jsonl` holds 400 entries under 246 keys: **154 keys carry two
variants**. The manifests count it — summed over the 150 runs of the reported evaluation,
`diverged` is 154 — and nothing surfaces it:

- `results.config.cassette` is `{mode, path}` with no counts, so the evaluation-level file
  cannot show it.
- Reading it requires summing a field across 150 manifests.
- `docs/run-envelope.md:85` frames a non-zero `diverged` as "the backend does not reproduce its
  own sampling", which is true here and is not the fact that mattered.

**What it cost.** The project's only check that its reported number survived a change to the
agent, and its `reproduce` answer in the brief. Both point at a recording of a run whose numbers
the project set aside. See §1.

A second, smaller consequence: `evals/cassettes/` is in `.gitignore`, so the `reproduce` entry's
"a rerun costs nothing and needs no credentials" does not hold for a clone. The project's own
comment on the ignore rule is honest about it; the brief entry is not.

### R2-D4 — `eval_id` ignores the model, and a re-run appends to its predecessor's trajectories

**Design bug**, two halves of one thing.

`held-out-small-k5`, `held-out-small-k5-run1-nocost`, `held-out-small-k5-replay-newparser` and
**`held-out-medium-k5`** all carry `eval_id: eval_457598b3c6f6`. The last is a different model.
Two arms of a model comparison are one evaluation as far as the identifier is concerned.

The second half is what the project actually hit, recorded in `evals/run_eval.py:97`:

> `eval_id` is derived from what defines the evaluation, so re-running an unchanged one lands in
> the same directory — and the rollout trajectories there are appended to rather than truncated.
> A second run of the dev evaluation then reported 180 executions of a node that runs once per
> rollout, over 90 rollouts, and inherited the first run's rate-limited calls, which have no
> token counts and so made the whole evaluation's cost unpriceable.

The workaround is `shutil.rmtree(run_dir)` before every evaluation, plus a hand-chosen `--name`
per arm. That workaround is why three of the log's claims are now unverifiable (§1): the fix for
a library defect destroyed the evidence for the others.

### R2-D5 — `simple-agents check` picks the newest results file, and the project has five

**Design bug.** `_latest_results` takes `max(files, key=_created_at)`
([artifacts.py:489](../../../src/simple_agents/conformance/artifacts.py#L489)). In this project that is
`held-out-medium-k5.json`, created 16:50:11Z.

The project's reported number is `held-out-small-k5.json`. The medium arm is a variant, and
`BUILD-LOG.md` states plainly that it "is not a valid measurement of medium, and is reported as
such". Nothing machine-readable says so: `brief.toml` records medium as a variant to compare and
does not record that the comparison did not come off, and the results file itself carries no
such flag. **The gate certified the arm the project disowns.**

It passed either way, so nothing is wrong with the numbers. What is wrong is that a project with
more than one results file has no way to say which one it stands behind, and the check picks by
timestamp. Run 1 had one results file and could not show this.

### R2-D6 — `PacedClient`'s default floor is 1 regardless of concurrency, and a held-out evaluation was re-run because of it

**Design bug**, with a prose half at **R2-P1**.

`min_remaining_requests` defaults to `1` ([pacing.py:72](../../../src/simple_agents/pacing.py#L72)). With
`concurrency=4`, a window reporting one request remaining is a window three in-flight rollouts
will overrun. `EvalSuite.run` knows the concurrency; the client is constructed separately and
nothing connects them.

The sequence on this project, from `BUILD-LOG.md` and `evals/run_eval.py:123`:

1. No pacing, concurrency 4. Nine 429s on the first dev evaluation, each consuming one of the
   answering node's three `RetryPolicy` attempts. `failure_rate` read 0%, and a rate-limited
   call records no token counts, so **the evaluation's cost was unknown**.
2. `PacedClient` at its default floor, concurrency 4. Two more 429s on the **held-out**
   evaluation. Cost unknown again.
3. Floor raised to `max(2, concurrency)`, concurrency dropped to 2. Cost derived.

**Step 2 is the expensive one: the held-out split had to be run twice.** The log says the right
thing about it — "Re-running the held-out split needs saying out loud, because it is exactly how
a held-out number gets quietly shopped for" — keeps both files and prints both sets of numbers.
It is still a re-run of a held-out evaluation forced by an infrastructure default, and it is
what put two recordings into one cassette (**R2-D3**).

Run 1's D2 was `PacedClient` blowing a wall-clock budget. That is fixed and held here: 635 runs,
zero `stopped_early`. Run 2's is the opposite failure, at the same seam.

### R2-D7 — A project-side model call still has no envelope

**Design bug, and this is run 1's D8 reproduced by an independent session.** D8 is the one
finding from run 1 with no disposition.

`tools/verify_unanswerable.py` defines the ground truth for every unanswerable example. It calls
`MistralClient.complete` with a hand-built `ModelRequest`, twice over 60 candidates, on two
different models. No trajectory, no manifest, no cost, no model pin, no cassette, no `replayed`
flag. Half the label set of the evaluation sits outside everything the library built, exactly as
in run 1.

**Run 2 makes the case sharper, because the pass that has no record is the one that was wrong.**
The first verification pass, on `mistral-small-2603` with the question's own source paragraph
included, judged **39 of 60** SQuAD unanswerables answerable. Had it shipped, the example set
would have been about 21 examples on a corrupted balance and every number the project reported
would have been measured against it. The evidence that this happened is four example lines in
`BUILD-LOG.md`. `evals/verification.jsonl` holds only pass 2.

A labelling pass, an ablation and a judge are all project-side model calls, and the library has
one envelope, reachable only through `Pipeline.run`.

### R2-D8 — `Comparison` has no report, so `population_changed` is printed only by a project that goes looking

**Design bug with a prose half at R2-P2.** The D6 fix works. Re-running `compare()` over the two
shipped results files:

```
population_changed: ['precision_when_asserting']
precision_when_asserting covered 28 of the shared examples in the earlier evaluation and 12 in
the later one, because its denominator depends on what the agent did. So `before` and `after`
are over different sets of examples and the gap between them is partly which examples fell
under the metric. `difference` is over the 12 in both, and is the change.
```

`EvalResults` has `report()`. `Comparison` does not, so a project that wants to see a comparison
writes the printer, and `evals/compare_runs.py` prints `before`, `after`, `delta`, the interval,
`moved`, `verdict_reason`, `shared` and `changed` — everything except the population note. The
log's comparison table reproduces that omission, and reports
`precision_when_asserting 0.386 → 0.750` beside a paired delta of `+0.100` with no statement
that the two point estimates are over 28 and 12 examples. That is run 1's D6 in the same shape,
one layer further out: the library now knows, and the project still did not print it.

### R2-D9 — `held_back_ms` never reaches the trajectory

**Design bug, small.** The D2 fix routes pacing and retry backoff into `ModelResponse` so
`max_wall_clock` is charged the call without it. The `model_call` record carries `params`,
`tokens`, `rate_limit`, `recorded_duration_ms` and the timestamps, and no `held_back_ms`. A
project asking "how much of this evaluation was waiting" has the aggregate wall clock and no
split. `docs/pipeline.md:616` says the timestamps bracket the whole call, which is true and is
not the same as reporting the wait.

---

## 5. Documentation bugs

Split as Thilina ruled at the item 14 sitting. `docs/procedure.md`, `docs/index.md` and
`docs/conformance.md` have never been reviewed, `docs/evaluation.md` carries unreviewed text
from items 9, 8a, 13 and 14 and from the run 1 fixes, and every document edited off run 1
carries text a week old that nobody has read.

### 5.1 In documents that were reviewed

**R2-P1 — `docs/model-clients.md` §-pacing shows the configuration that produced the 429s.**
`model-clients.md` is marked done in Thilina's Corner. Its worked example is:

```python
client = PacedClient(MistralClient(model="mistral-small-2603"))
results = suite.run(envelope=env, model=client, split="held_out", k=5, concurrency=4)
```

Default floor 1, concurrency 4. The paragraph below it defines `min_remaining_requests` as "the
request count at or below which the next call waits" and never relates it to how many callers
share the client. The project copied the example and took two 429s on its held-out evaluation.
See **R2-D6**.

### 5.2 In documents that have never been reviewed, or carry unreviewed text

**R2-P2 — `docs/evaluation.md` §9's code block omits `population_changed`.** The block lists
`comparison.moved`, `comparison.undecided`, `comparison.moved_nodes` and `comparison.changed`.
The paragraph two below spends five sentences on `population_changed` and `population_note`. A
coding agent writing a printer copies the block. `evals/compare_runs.py` prints exactly the four
in the block. See **R2-D8**.

**R2-P3 — `docs/procedure.md` stage 3 gives one cassette path and no rule about reusing it.**
"`Cassette.record(path)` on the envelope, then `Cassette.replay(path)`, where the same set will
be measured again against a changed prompt or scoring rule." Nothing says what recording twice
into one path does, and `docs/run-envelope.md` §3 covers what makes a recorded call *miss*
rather than what makes one shadow another. See **R2-D3**.

**R2-P4 — nothing says an optional field changes what the backend is asked to guarantee.**
`docs/pipeline.md` §4 covers what a schema must express and how descriptions reach the model.
`docs/model-clients.md` covers what an adapter sends. Neither says that `field: str | None =
None` leaves the field out of `required`, that the library still sends `strict: true`, or that
a backend may respond by not honouring the schema. The prose half of **R2-D1**.

**R2-P5 — `docs/evaluation.md:433` says `config` carries "the tools and their side-effect
classes" and it does not, for a tool on a `Deterministic` node.** The prose half of **R2-D2**;
the document describes the intended behaviour and the code has a hole under it.

---

## 6. What did not go wrong

Recorded because a findings document that lists only failures misreports the run.

- **The staged procedure was followed literally**, all three stages, all three gates, with the
  Stage 1 gate correctly reported as "FT-24 pass, everything else blocked, exit 1" and read as
  expected. `simple-agents init --claude` was run in the first minutes, before any code, and the
  skill symlink and `AGENTS.md` are on disk. The procedure itself was still reconstructed from
  `docs_path()` → `index.md` → `procedure.md`, as in run 1.
- **No elicitation question was answered on the builder's behalf.** 18 questions across five
  rounds, 16 brief entries, every one traceable to a numbered interaction.
- **Zero deferrals**, so run 1's D7 shape — a deferral naming a stage already reached — could
  not arise. All 12 required entries answered, and 4 of 5 optional ones.
- **FT-11 was applied without being prompted.** Three `Deterministic` and one `LLMNode`, no
  `AgentNode`, the absence argued in `brief.toml` under `agency_boundary` and in `agent.py`'s
  module docstring, both citing FT-11. The one run-time decision is a `Loop(max_iterations=2,
  then="finalize")` with the route on the pipeline.
- **The cycle and `Join` were used for what they are for.** The log records the reasoning: a
  reformulation node after `answer` would receive an `Attempt` and no longer have the question,
  and the three ways out were the model echoing the question back, the workspace as a side
  channel, or the cycle. It took the cycle, and named the workspace option as "hides the data
  flow from the manifest's declared edges, which is the thing this library exists to prevent".

  *Amended 2026-08-09, at the DF2-D1 sitting, on Thilina's approval. The routing decision above
  stands and the credit for it stands. What the run then did inside the cycle did not work, and
  nothing said so.* `retrieve` reads its working set from `inputs["prepare"]`
  (`agent.py:206` in the dogfood-1-run2 project's own repository), and the edge from outside a cycle stays
  resolved at the value that entered it. `prepare` returns `passages: []` and runs once, so
  `seen` starts empty on the retry and the union the code and its comment intend never happens.
  **Measured over all 95 runs: 20 went round the cycle twice, `inputs.prepare.passages` is 0 on
  both executions in every one, and 12 lost passages the first pass had retrieved, 29 in
  total.** It is not separable from the score, because those passages had already failed to
  produce an answer on the first pass. What it shows is the mechanism failing with nothing
  raised, nothing recorded, and no check firing, which is why the sitting's answer was
  documentation rather than a new mechanism. `docs/pipeline.md` §1.4 now states the frozen edge
  and shows the shape that accumulates.
- **The held-out split was held out.** Dev was inspected and debugged against, held-out was not
  read while the agent changed, and the log states the 14-point optimism the dev number carried
  as the argument for FT-02 "in this project rather than in the abstract".
- **`compare()` withheld a verdict, and the log accepted it.** `squad_f1` gained 12 points and
  `moved` is `False`. The log: "a point estimate alone would have read as a clear win for the
  10× model."
- **The degenerate-abstainer collapse was caught by the six rates.** The first medium arm scored
  50.7% accuracy by answering one question in 150 rollouts, higher than small's 46.7%, and
  `abstention_rate 98.7%` beside `recall 1.3%` is what made it unmistakable.
- **The medium arm was declared invalid rather than reported.** The log measured how much was
  recoverable (26 of 78) before deciding to stop, and refused to synthesise citations because
  "the check is only worth having if the citation is the model's".
- **The verification pass was checked rather than trusted.** A 65% flag rate was read as
  implausible, diagnosed to the judge seeing the adversarially-written source paragraph, and
  rebuilt. Every surviving flag was read by hand and the reasons are in the code.

---

## 7. `runs/dogfood-protocol.md` §1 step 5 — the three categories

**All three are empty, for the second time.** Answered by Thilina at the sitting, 2026-08-07,
asked directly rather than inferred from the transcript.

1. **Interventions he was forced to make: none.**
2. **Questions he was asked that the library should have answered itself: none.** "I think all
   the questions were fine." This run put 18 questions across five rounds against run 1's 14
   brief entries across five interactions, so the count rose and the reading did not change.
3. **Things he wanted to volunteer and was never asked for: none.**
4. **Where the transcript and the log disagree: nowhere.** Run 2's prompt asked for verbatim
   interactions specifically so this could be checked rather than trusted, and it checks. The
   one candidate the artifacts raised — `BUILD-LOG.md` Q14 claiming a real case was shown, where
   the case text may have reached only the log — he reads as a coding-agent confusion rather
   than a mismatch worth recording.

**§4.1 step 5 has now returned empty on both runs.** Two runs, a task the elicitation set covers
and a builder who answers what he is asked, and the instrument reports nothing either time.
**Every finding in §4 and §5 of both documents came from reading the artifacts.** §4.1 already
records that step 5's categories may not be the instrument they were expected to be; a second
empty run is the evidence for that rather than against it, and dogfood #2 is where the
categories get their last chance on a task whose shape they were designed for.

### 7.1 What the builder can and cannot review

Recorded at the sitting, on Thilina's statement, because it changes what §5's split is for.

> I can only review the language, ambiguity, and clear contradictions. It is your job to make
> sure the documentation is *correct*. My reviews would not have caught these because I can't
> run code inside my head.

**The split in §5 is therefore not "reviewed" against "not yet reviewed".** Run 1's §5 opened
with "a confusion caused by prose Thilina would have caught in the review is a different finding
from one caused by the design", and that framing does not survive. **R2-P1** sits in a document
marked done: `docs/model-clients.md` shows `PacedClient` at its default floor beside
`concurrency=4`, and reading it cannot reveal that the two numbers have to relate, because the
relationship is arithmetic about a running system. The same holds for **R2-P4** and **R2-P5**,
which are statements about what the library does that are wrong rather than unclear.

The useful split is **prose that is unclear, ambiguous or self-contradicting**, which the review
catches, against **prose that is clear and false**, which only running the code catches. The
second is a correctness defect that happens to live in a document, and it belongs to whoever
wrote the code.

---

## 8. Prior questions this run answers

- **`build-logs/item8c-build-log.md`, branching.** Met again, and used again. A cycle, a
  route over a validated output, a `Join` carrying the question round, and a bound on the node
  that closes the cycle. The log chose it over two alternatives and named why each was worse.
  Two dogfoods have now met the graph case and both used what shipped.
- **`plan.md` §2.1, no seam for a project-supplied count or total.** Two
  `ProjectMetric`s declared (`squad_em`, `squad_f1`), both means over examples, both took
  intervals, both `Over.ALL`. Nothing reached for a count. Same answer as run 1, and still open
  for dogfood #2.
- **`plan.md` §2.2, a payload stored by reference.** Not exercised. Passages are short and the
  largest trajectory is small.
- **`archive/plan-history.md` §4.2's pooling argument.** It held this time. The passages were pooled, the agent
  got a search tool over them, `side_effect_class` was declared, the finish check ran and the
  tool half of the cassette replayed 173 calls. The amendment recorded against §4.2 after run 1
  should say so.

---

## 9. What landed, decided at the sitting on 2026-08-07

Thilina's ruling, as on run 1, was that every fix lands now rather than as v0.1, so §4 and §5
are a record of what was built. **1169 tests pass**, up from 1147.

| Finding | What landed | Kind |
|---|---|---|
| **R2-D1** | `strict_schema` in `_openai_wire`, so both adapters send every property in `required`, `additionalProperties: false` on every object, and no `default` | code |
| **R2-D2** | `_tools_of` reads every node carrying tools, so `config.tools` and FT-20's refusal see a tool on a `Deterministic` node | code |
| **R2-D3** | `Cassette.record` refuses a file that already holds a recording; the evaluation's cassette counts are summed into `results.config.cassette` | code |
| **R2-D4** | `eval_id` includes the model, and running into a directory that already holds rollouts is refused | code |
| **R2-D5** | `results` in `brief.toml` names the evaluation the project reports, and the checks read that one | code |
| **R2-D6** | `PacedClient.expect_callers`, the request floor defaulting to the caller count, `EvalSuite.run` setting it from concurrency and warning on an unpaced hosted client | code |
| **R2-D7** | `who_labels`'s scaffold names the envelope, and `docs/evaluation.md` §1.4 shows the one-node `Pipeline` | prose |
| **R2-D8** | `Comparison.report()`, which prints `verdict_reason` and `population_note` without being asked | code |
| **R2-D9** | `held_back_ms` on the `model_call` record, trajectory format `0.16` | code |
| **R2-P1** | `docs/model-clients.md` relates the floor to the caller count, with the example | prose |
| **R2-P2** | `docs/evaluation.md` §9's code block carries `population_changed` and `report()` | prose |
| **R2-P3** | `docs/procedure.md` and `docs/run-envelope.md` §3 give the one-path-per-recording rule | prose |
| **R2-P4** | `docs/pipeline.md` §4 says what a field with a default does to the request | prose |
| **R2-P5** | `docs/evaluation.md`'s `config` table names the tools every node can call, and the cassette counts | prose |

### 9.1 What the probe settled, and what it did not

`response_format_for` was changed on a measurement rather than on the dialect's documentation.
Sixty calls to `mistral-small-2603` at `temperature=0.0` over ten prompts from the project's
own cassette: **0 of 20 clean** under the schema as Pydantic writes it, across two runs, and
**10 of 10 clean** under each of `additionalProperties: false` alone, all-properties-required
alone, and both together with `Maybe[str]` flattened.

**`additionalProperties: false` alone was sufficient for this backend**, and the change is the
full compliance repair anyway. `strict: true` names a contract, and sending a request that does
not meet it is the defect rather than the symptom. The narrower fix would leave the same
mismatch in place for the next backend to handle differently.

**vLLM was probed before the change and is clean either way**: ten prompts against
`Qwen/Qwen3-1.7B`, 10 of 10 under the live schema and 10 of 10 under each repair. So the change
is needed on one backend and safe on the other, rather than assumed to be.

### 9.2 Two corrections made while building

**The cassettes were re-recorded and the re-recording was reverted.** The premise was that a
recording made under the old wire schema is a record of behaviour that no longer occurs. It is
not: a cassette key is computed from the `ModelRequest` the library builds, not from what the
adapter puts on the wire, so every key was unchanged and every cassette still replays. The
evidence about what the adapter sends lives in `tests/fixtures/wire/`, where the new assertion
went. The re-recording also cost something: the new `eval.jsonl` had both examples answered
correctly on all three rollouts, which would have deleted the measurement
`test_the_same_question_answered_differently_across_rollouts` exists to hold. Reverted, and the
`CHANGELOG.md` entry that said to re-record was corrected.

**`scripts/build_conformance_fixtures.py` could not reproduce its own fixtures.** It writes
`budget` as `deferred_to = "measure"` into a brief declaring `stage = "measure"`, which run 1's
D7 fix made FT-24 count as unanswered. The committed fixture at `3ec0e5c` says
`budget = "answered"`, so it was edited by hand and the generator was not. The script's own
docstring is the standard it failed: "a fixture written by hand is a claim about what an
artifact contains rather than a measurement of one". The deferral moved to `prices`, which is
optional, because a project at `measure` has no later stage to defer a required question to.

### 9.3 Not built

- **A one-call envelope (R2-D7's option b).** Thilina's ruling: the machinery exists, a
  labelling pass is a one-node `Pipeline`, and what is missing is the signpost rather than the
  capability. Two cold sessions reaching for `complete()` is evidence about the documentation
  first. If a third does it with §1.4 in place, the docs are not the problem. His caution on the
  prose: labelling is common and not universal, so it is one subsection and one line in a
  scaffold rather than a theme.

  ***Amended 2026-08-09 at the ground-truth sitting: the test was never administered, and a
  later reading of dogfood #2 as having met it is wrong.*** Neither half of the fix reached
  that session, for two reasons that would reach any builder. **The docs half was never
  opened:** `BUILD-LOG.md` is 120,122 bytes, names `procedure.md`, `pipeline.md`, `tools.md`,
  `run-envelope.md` and `index.md`, and contains zero occurrences of `evaluation.md`. A
  subsection of a document nothing routes to is a subsection nobody reads. **The elicitation
  half never fired:** `who_labels` was `stage="measure"`, `questions_at` is cumulative upward
  only, the log records one invocation (`simple-agents questions --stage shape`), and the
  project declared `stage = "build"` throughout, so the scaffold naming §1.4 was never printed
  and no gate required it. *(A third reason existed and is not evidence about the library: that
  project's venv held a `docs/` copy older than §1.4, which an editable install onto the live
  tree produces and which only reaches someone who is both builder and library author. The two
  reasons above stand without it.)* The ruling's premise is untouched and the evidence against
  it does not exist: no third session has yet met §1.4 with §1.4 in place.
  `build-logs/ground-truth-build-log.md` §1.1 is the record, and what shipped off it is
  §1.4 rewritten, `role=` on a run, `evals/labels.jsonl`, and `who_labels` moved to `build`.
- **`EvalSuite.run` wrapping a bare client in `PacedClient`.** It would change what `identity()`
  and the manifest report, which is the one thing pacing is careful not to touch.
- **Refusing a project with more than one results file and no `results` key.** It would turn a
  working project into a failing one on its second evaluation.
