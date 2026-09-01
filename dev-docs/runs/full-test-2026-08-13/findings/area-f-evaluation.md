# Area F: evaluation

## Summary

182 checks, 182 pass, 0 fail, 0 error, 0 skip. Evidence in
[`runs/area-f-evaluation.jsonl`](../runs/area-f-evaluation.jsonl); one row per check, carrying the
numbers each verdict rests on. A check that reproduces a defect is recorded as a pass, because
what it asserts is the observed behaviour rather than the documented one.

Coverage: the whole of `docs/evaluation.md` (1405 lines) and every module under
`src/simple_agents/evaluation/`. All 17 inventory flags were reproduced empirically and **all 17
are confirmed**; none was dismissed. Four defects were found that the inventory did not list, one
of them a blocker. The interval arithmetic was recomputed independently against `scipy` and by
hand: `wilson_ci` matches `scipy.stats.binomtest(...).proportion_ci(method="wilson")` to within
1e-12 at every one of 60 tested `(successes, n)` pairs including `n=1`, `0/n` and `n/n`, and the
bootstrap resamples examples rather than rollouts as `§4` states. The statistics are sound. What
is wrong sits around them: one sample report prints a band the code cannot produce, and the
identity an evaluation is filed under does not separate evaluations the documentation says it
separates.

Backends: a live 3x3 evaluation on vLLM (`Qwen/Qwen3-1.7B`, 9 rollouts, all correct, cassette
replayed at 9 hits and 0 misses), a live fan-out labelling pass and two paid evaluations on
Gemini. Total spend for this area is under $0.01, against a running pass total of $0.0594.

---

## Findings

### 1. Two pipelines differing only in sampling, tools or budget share one `eval_id` — blocker

**Claimed.** [§6.1 L478-484](../../../../docs/evaluation.md#L478): "`eval_id` is derived from what
defines the evaluation ... two evaluations differing in any of those write into different ones."
[§6.5 L685](../../../../docs/evaluation.md#L685): "A changed pipeline, prompt, split, k, seed or
model already produces a different `eval_id`, so it is refused here."
[§10 L1136-1138](../../../../docs/evaluation.md#L1136) names "a tool added or removed ... a
temperature moved" as variants `compare_variants` runs.

**Actual.** `_eval_id` ([`runner.py` L878-897](../../../../src/simple_agents/evaluation/runner.py#L1162))
hashes `graph_fingerprint()`, which
([`pipeline.py` L1875-1890](../../../../src/simple_agents/pipeline/core.py#L1836)) covers node ids, kinds,
edges, loop bounds, error edges, retry policies and output schemas. Sampling parameters, tools,
`allow_unknown` and budgets are outside it, and nothing else in `_eval_id` carries them. Four
edits produce a byte-identical `eval_id`: `temperature`, `max_output_tokens`, `allow_unknown` and
the pipeline budget. Adding or removing a tool on an `AgentNode` does too.

Three consequences, each independently reproduced.

**1a. `compare_variants` cannot run the variant §10 leads with.** The baseline arm runs and is paid
for, then the variant arm resolves to the same directory and is refused by
`_refuse_a_used_directory`:

```
'<run_dir>/eval_02b6a18f59f2' already holds an evaluation's rollouts. A rollout appends to the
trajectory it finds, so running into this directory again would produce trajectories holding
two runs...
```

Reproduction: `F-EVALID-SWEEP`. A three-node baseline against the same pipeline with
`temperature=0.7` on one node, 20 examples at k=2. The message names neither the variant nor the
sweep, and the refusal arrives after the baseline's 40 rollouts have been spent.

**1b. `resume_from` mixes rollouts across the change and the results file does not say so.**
Reproduction: `F-EVALID-RESUME`. An evaluation is run at `temperature=None`, two rollouts are
deleted, and the run is resumed under a suite whose node declares `temperature=0.7`. The resume is
accepted, the missing rollouts run hot, and `config.nodes` records
`{'temperature': 0.7, ...}` for a set in which four of six rollouts ran at `None`. The client
confirms both temperatures reached the backend. This is the case
[§6.5 L682-687](../../../../docs/evaluation.md#L682) says the `eval_id` check prevents, and FT-15 is
the failure it names.

**1c. `rescore` accepts rollouts a different configuration produced.** Reproduction:
`F-EVALID-RESCORE`. `_refuse_a_moved_pipeline`
([`runner.py` L803-826](../../../../src/simple_agents/evaluation/runner.py#L995)) compares
`graph_fingerprint`, so rollouts run at one temperature are scored under a suite declaring
another, and the written `config` describes the suite rather than the runs. The refusal quoted at
[§6.4 L645-649](../../../../docs/evaluation.md#L645) never fires.

**Severity: blocker.** 1a makes the headline operation of §10 fail on its own leading example. 1b
reports a number over a set that never ran together, which is the defect the `eval_id` check
exists to prevent.

### 2. `resume_from` is refused on the default recording path — major

**Claimed.** [§6.5 L673-676](../../../../docs/evaluation.md#L673) shows the call with an ordinary
envelope:

```python
suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
          resume_from="runs/eval_a1226bc495df")
```

**Actual.** An evaluation records by default into `<run_dir>/<eval_id>/cassette.jsonl`
([§6.3 L517](../../../../docs/evaluation.md#L517)). On the resuming call
`_recording_by_default` ([`runner.py` L1662-1680](../../../../src/simple_agents/evaluation/runner.py#L2654))
constructs `Cassette.record` over that same path, which already exists, and `Cassette.record`
refuses a file that already holds a recording. The evaluation that stopped is the one that wrote
it, so the refusal fires exactly when resuming is wanted:

```
Cassette.record('<run_dir>/<eval_id>/cassette.jsonl') was given a file that already holds a
recording. Replay serves the first response recorded for each request...
```

The message is about recording and never mentions `resume_from`.

**Reproduction:** `F-RESUME-CASSETTE`. Run three examples at k=2, delete one example's two
rollout directories, call `run(..., resume_from=<eval_dir>)`.

`F-RESUME-WORKAROUNDS` establishes the boundary: resuming succeeds under `record=False`, under
`Cassette.off()`, and under an envelope naming its own cassette path. Only the default path,
which is what §6.5 shows, fails.

**Severity: major.** The documented recovery path for a long evaluation that stopped does not run,
and the message does not point at the cause.

### 3. A suspending rollout is absorbed by every rate — major (F-02 blast radius)

The lead agent established that `_rollout`'s bare `except Exception`
([`runner.py` L989-1002](../../../../src/simple_agents/evaluation/runner.py#L1323)) catches
`RunSuspended` and scores `failed` rather than raising, against
[§7.4 L845-846](../../../../docs/evaluation.md#L845). Measured here: what an evaluation of a
consulting agent then reports.

**Actual.** Reproduction `F-02-BLAST`, four examples at k=3 through a node that raises `Suspend`.
Every rollout scores `failed`. The six rates come back fully formed and internally consistent:
`accuracy` 0.0, `false_confidence_rate` 0.0, `recall` 0.0, `abstention_rate` 0.0, `failure_rate`
1.0, `precision_when_asserting` undefined with a reason. No rate silently absorbs the suspension
in the sense of hiding it: `failure_rate` 1.0 is the signal, and it is a correct reading of the
outcomes as classified. What is absent is any statement that the runs are resumable.

`F-02-STATE` confirms `suspension.json` is written for every suspended rollout, so the runs are
recoverable and nothing in the results file says so. `F-02-NOTHING-SAYS-SO` runs a suspending
pipeline and a crashing pipeline side by side: both report `failed` with `failure_rate` 1.0, and
the only difference is the free text inside `rollout.error`. No field of the results file, and no
line of `report()`, separates an evaluation waiting on a person from one whose nodes threw.

**Severity: major.** An evaluation of a consulting agent against a live backend reports a total
failure that is really a queue of resumable runs, and the report gives no route back to them.

### 4. The §8.1 sample report prints a reach band the code cannot produce — major (F-01)

**Claimed.** [§8.1 L992](../../../../docs/evaluation.md#L992), over a 3-example by 3-rollout
evaluation:

```
  hunt        agent         100.0% [70%,100%]        9     19     19  0.001038 USD         -
```

**Actual.** Recomputed independently (`F-01-ARITHMETIC`): `wilson_ci(9, 9)` is
`[0.7005, 1.0]`, which formats as `[70%,100%]`. `wilson_ci(3, 3)` is `[0.4385, 1.0]`, which
formats as `[44%,100%]`. Both match `scipy` exactly. The printed band is therefore the interval
over 9 rollouts.

`reach` is grouped over `by_example.values()`
([`per_node.py` L255-267](../../../../src/simple_agents/evaluation/per_node.py#L255)), so `n` is the
example count. Running the real thing (`F-01`, three examples at k=3) produces
`interval.n == 3` and the report line `hunt        llm           100.0% [44%,100%]`. Confirmed
again on the live vLLM evaluation (`EVAL-LIVE-REACH`), which reports `n=3` over 9 rollouts.

The stated rule at [§4 L276](../../../../docs/evaluation.md#L276) holds in the code. The sample output
is what is wrong.

**Severity: major, documentation.** `docs/` is a prompt surface, and a coding agent that writes a
schema check or a fixture from this block encodes an interval the library never emits.

### 5. `write_labels` raises a bare `TypeError` on the verdict §1.5 tells the reader to write — major

**Claimed.** [§1.5 L178-184](../../../../docs/evaluation.md#L178) shows the labelling snippet:

```python
Label(id=outcome.item["id"], verdict=outcome.value.answerable, ...)
```

where `answerable` is declared `Maybe[bool]` in the surrounding example.

**Actual.** When the labelling model reports absence, `outcome.value.answerable` is an `Unknown`.
`write_labels` ([`labels.py` L175](../../../../src/simple_agents/evaluation/labels.py#L198)) calls
`json.dumps(label.to_json(), ensure_ascii=False)` with no `default=`, and raises:

```
TypeError: Object of type Unknown is not JSON serializable
```

The two comparable writers both pass `default=str`: `ExampleSet.to_jsonl`
([`examples.py` L446](../../../../src/simple_agents/evaluation/examples.py#L446)) and
([`results.py` `EvalResults.write`](../../../../src/simple_agents/evaluation/results.py#L566)).
`Label.verdict` is typed `Any`, so nothing refuses the value at construction either.

**Reproduction:** `F-LABEL-UNKNOWN`. The file is left unchanged, because `lines` is built before
the file is opened, so nothing is corrupted. This first surfaced as a real failure of the live
labelling pass on Gemini, where one of three candidates came back `unknown`.

**Severity: major.** The documented snippet fails on the case the schema exists to express, and the
error names neither the label nor the field.

### 6. `totals.tool_spend.currency` is null where no node made a model call — minor

**Claimed.** [§8 L949](../../../../docs/evaluation.md#L949): `tool_spend` is "what the tools were
charged".

**Actual.** `totals_of` ([`results.py` `totals_of`](../../../../src/simple_agents/evaluation/results.py#L861))
takes `tool_spend.currency` from the accumulated model `Cost`, not from the tool spend. An
evaluation whose pipeline is `Deterministic` and whose tool declares
`DeclaredCost(currency="USD", per_call=0.001)` reports
`{'amount': 0.006, 'currency': None, 'calls': 6}`. The amount is right and carries no unit.

**Reproduction:** `F-TOOLSPEND-CURRENCY`, two examples at k=3 through one paid tool, cost basis
declared in USD.

**Severity: minor.** A figure with no unit cannot be summed or compared, which is the reason
`DeclaredCost.__post_init__` refuses `per_call` without a `currency`.

### 7. The §7.6 refusal cannot fire on a recording `suite.record` made — minor

[§7.6](../../../../docs/evaluation.md#L859) refuses a replay whose file answers one tool call two
ways. `suite.record` forces `Cassette.update`
([`runner.py` `eval_seed`](../../../../src/simple_agents/evaluation/runner.py#L616)), under which a call
already on file is served rather than made again, so a second answer is never written.
`EVAL-AMBIG-RECORD` records a non-deterministic `clock` tool over two examples at k=3: six calls
are attempted, one entry lands, and every rollout replays the first rollout's value with no
refusal. The refusal does fire on the cassette `suite.run` records itself (`EVAL-AMBIG`), where
one `Cassette.record` is shared across rollouts and two answers do land under one key.

Both behaviours match what §6.3.1 L586-589 states. The finding is the asymmetry: the guard §7.6
describes is unreachable on the path §6.3.1 recommends as the cheaper one.

**Severity: minor.**

### 8. The remaining inventory flags, confirmed as documentation defects

Each reproduced; none changes a number, so all are cosmetic to minor.

- **F-03.** `_taint` walks forward along `reaches`
  ([`variants.py` L671-686](../../../../src/simple_agents/evaluation/variants.py#L762)), so every node
  downstream of the change is `live` too. `F-03` shows `verify` marked `live` when `hunt` changed;
  `F-03b` shows `hunt` marked `replayed` when `verify` changed. §10 L1162 understates it and
  §10.1 L1184-1186 states it correctly.
- **F-04.** `ablate().skipped` carries at least six reasons against the three
  [§10.2 L1233](../../../../docs/evaluation.md#L1233) lists. `F-04` reproduces "no edge reaches it",
  `F-04b` "it is the only node in the pipeline", `F-04c` a `Loop(then=<removed>)` whose target
  leads to more than one node.
- **F-05.** `plan.live_calls` is 2 for a two-calling-node pipeline, so it is per rollout.
  `_refuse_over_ceiling` multiplies by `examples * k`, confirmed by `EVAL-MAXLIVE`: 4 examples at
  k=5 gives "at most 80 live model calls" and "baseline: at most 40". The unlabelled `45` at
  §10 L1131 reads as a sweep total and is not one.
- **F-06.** `Recording.paid_calls` is 0 after a recording that made 4 provider calls and used no
  paid tool. The docstring at [`runner.py` `paid_calls`](../../../../src/simple_agents/evaluation/runner.py#L167)
  says it counts provider calls; the body counts paid tool calls.
- **F-07.** `allow_mixed_cassette=True` bypasses the §7.3 refusal, and an evaluation runs to
  completion under `Cassette.update` with `config.cassette.mode` of `update`. §7.3 presents the
  refusal with no override.
- **F-08.** Three fields are nulled by a rescore, not two: `concurrency`, `run_concurrency` and
  `max_spend`. §6.4 L663 names two and omits `run_concurrency`.
- **F-09.** `config` carries exactly three keys the §8 table does not list: `max_spend`,
  `scored_from`, `seed_source`. `incomplete` is present only on a rescore. Verified by
  differencing the written key set against the table.
- **F-10.** A `shared_source` pair carries `similarity=0.1111`, a number. The docstring at
  [`examples.py`, `Overlap.similarity`](../../../../src/simple_agents/evaluation/examples.py#L288) says `None`; §1.2
  L86 agrees with the code.
- **F-11.** `contamination(threshold=1.0)` over two identically worded examples flags the pair,
  because the code tests `similarity >= threshold`. §1.2 L89 says "above which", under which
  nothing would ever be flagged at 1.0. The generated detail string already says "at or above".
- **F-12.** A pair that is both a near-duplicate and shares a source is reported once, as
  `near_duplicate` only, because the `shared_source` check is an `elif`. A project counting kinds
  to decide how to redraw a split undercounts `shared_source`.
- **F-13.** `_eval_id` hashes `model.identity()` and each node's own `model`; two clients with
  different identities give different ids. §6.1 L477-479 omits the model and §6.5 L686 includes
  it, so the two sections disagree. (See finding 1: the list is incomplete in the other direction
  as well.)
- **F-14.** `progress_of` returns `outcomes` and never `failed`, which its own docstring example
  at [`runner.py` L1712-1714](../../../../src/simple_agents/evaluation/runner.py#L2901) shows. The
  same docstring contains a full-width `１` in `elapsed_s': １840.2`, confirmed by string test.
  §6.6 L717-719 is correct.
- **F-15.** Every `RolloutProgress` snapshot carries `cost=None`, including under a declared cost
  basis, so `describe()` cannot print the `0.0412 USD` its docstring shows. §6.6 L704 is correct.
- **F-16.** A `record=False` evaluation re-scores and reproduces its numbers exactly. §6.3 L550
  says it "cannot be replayed or re-scored"; the first half holds and the second does not, as the
  flag predicted.
- **F-17.** An evaluation of `held_out` is refused for an overlap between `dev` and `scratch`,
  because `_refuse_contaminated_split` compares every cross-split pair in the set. The message
  says the pairs "fall on both sides of this split", which is untrue for the pair it then names.

---

## The 17 flags

| Flag | Verdict | Evidence, in one line |
|---|---|---|
| F-01 | **Confirmed** | `wilson_ci(9,9)` prints `[70%,100%]` and `wilson_ci(3,3)` prints `[44%,100%]`; a real 3x3 run reports `interval.n == 3` and `[44%,100%]`. |
| F-02 | **Confirmed** (lead) | Blast radius measured: every rollout `failed`, `failure_rate` 1.0, `suspension.json` written, and nothing in the file separates it from a crash. |
| F-03 | **Confirmed** | `plan_variant` marks `verify` `live` when only `hunt` changed; `hunt` is `replayed` when only `verify` changed. |
| F-04 | **Confirmed** | Three further skip reasons reproduced: entry node, only node, `Loop(then=)` with more than one onward node. |
| F-05 | **Confirmed** | `plan.live_calls == 2` for two calling nodes; the ceiling multiplies by `examples * k` to 80. |
| F-06 | **Confirmed** | `paid_calls == 0` after a recording that made 4 provider calls with no paid tool. |
| F-07 | **Confirmed** | `allow_mixed_cassette=True` runs a full evaluation under `Cassette.update`; §7.3 documents no override. |
| F-08 | **Confirmed** | `run_concurrency` is nulled by a rescore alongside `concurrency` and `max_spend`; §6.4 names two. |
| F-09 | **Confirmed** | Differencing the written `config` against the §8 table leaves exactly `max_spend`, `scored_from`, `seed_source`. |
| F-10 | **Confirmed** | A `shared_source` pair carries `similarity=0.1111`; the docstring says `None`. |
| F-11 | **Confirmed** | `threshold=1.0` flags identical wording, because the test is `>=`. |
| F-12 | **Confirmed** | A pair that is both reports one `Overlap`, `kind == "near_duplicate"`. |
| F-13 | **Confirmed** | Two clients with different identities give different `eval_id`s; §6.1's list omits the model. |
| F-14 | **Confirmed** | `"failed" not in progress_of(...)`; `outcomes` is returned; the full-width `１` is present in the docstring. |
| F-15 | **Confirmed** | Every snapshot has `cost is None` under a declared cost basis. |
| F-16 | **Confirmed** | `record=False` then `rescore` reproduces the six rates exactly. |
| F-17 | **Confirmed** | An evaluation of `held_out` is refused naming a `dev`/`scratch` pair. |

All 17 confirmed; none dismissed.

---

## What was verified numerically

Independently recomputed rather than read back from the library.

- **Wilson.** 60 `(successes, n)` pairs across `n` in 1, 2, 3, 4, 5, 9, 10, 20, 30, 50, 100, 999,
  each against `scipy.stats.binomtest(...).proportion_ci(method="wilson")`. Worst absolute
  deviation over all endpoints: below 1e-12. The degenerate cases behave: `wilson_ci(0, 1)` and
  `wilson_ci(1, 1)` are non-zero width and clamp only the endpoint that sits on a bound, with the
  other endpoint equal to the unclamped algebra to 1e-12 (`EVAL-092`, `EVAL-WILSON-N1`).
- **`_z_for`.** Matches `scipy.stats.norm.ppf` at 0.90, 0.95 and 0.99 to under 1e-9.
- **The resampling unit.** The same six per-example means at k=1, k=5 and k=20 give a
  byte-identical interval, with `interval.n == 6` throughout and `interval.k` recording 1, 5 and
  20. A flat bootstrap over the same k x n values, computed here, narrows as k grows. So the §4
  rule holds in the code (`EVAL-BOOTSTRAP-UNIT`).
- **The point estimate.** `bootstrap_ci([[1.0]*100] + [[0.0]]*99).point` is exactly 0.01, not the
  rollout-weighted 0.502513. On an unbalanced set it is 0.75 by example, not 0.83333 by rollout.
- **Percentile indices.** 100 sorted estimates at 0.95 read at indices 2 and 97, not 2 and 98.
- **The zero-or-one fallback.** An all-identical 0/1 set returns Wilson and is not zero width; an
  all-identical non-0/1 set stays a zero-width bootstrap; a set of all-0 and all-1 examples does
  not take the Wilson branch.
- **The six denominators.** Hand-built four-example outcome vectors covering all five outcomes.
  `recall` includes `failed` rollouts of value examples and scores them 0;
  `precision_when_asserting` excludes them. Both confirmed at the rollout count.
- **`absent_proportion`.** 3 of 8 is exactly 0.375; 1 of 3 is exactly `1/3` with no rounding.
- **Per-node cost.** 4 calls at 10 input and 5 output tokens against a declared basis price to
  `4 * (10/1e6 * 1.0 + 5/1e6 * 2.0)`, matched to 1e-12.
- **Paid evaluation.** The Gemini evaluation's `totals.cost.value` of 0.000181 USD equals the
  price recomputed from the reported token counts and the published rates to 1e-9.
- **`totals.cost`.** With one priced node and one whose tokens came back unknown, `value` is
  `None`, `measured` is the priced part, and `unpriced_nodes` names the other.
- **Paired difference.** A constant +0.10 shift over 20 examples gives a zero-width interval at
  0.10 that excludes zero, and the comparison returns `moved=True`; the §9 L1075-1077 warning
  about zero width reading as certainty is not enforced as a verdict rule.
- **Ratio of totals.** 11/5 = 2.2 against a mean of per-example ratios of 1.75, with the bootstrap
  point on the latter, as §11.3 states.

---

## What could not be tested, and why

- **`Recording.spend` against a real paid tool over a real provider.** The paid-tool checks use a
  local stub declaring `DeclaredCost`, because no shipped tool bills a real account. The metering
  path is exercised; the provider's own invoice is not.
- **`max_spend` binding part-way through an evaluation.** It cannot: §7.2 L780-782 states it is
  checked before the first rollout and never binds during one, and the ceiling arithmetic is what
  was tested instead.
- **A rollout suspended through a real consultation channel against a live backend.** `F-02` uses
  a `Suspend` raised from a `Deterministic` node, which reaches `_rollout` by the same path. The
  live-backend variant was not run because it needs a provider round trip per rollout to reach the
  stopping point, and the classification is decided by the exception type rather than by what
  raised it.
- **Concurrency above 4, and `run_concurrency` under real contention.** Seed stability was checked
  at 1 and 4 and the recorded `config` values were checked, but no test drove enough parallelism
  to expose a race in the shared cassette lock.
- **`compare_variants` over a variant differing in sampling only.** Blocked by finding 1. The
  sweep was exercised with an output-schema change instead, which does move the fingerprint.
- **vLLM for part of the pass.** The server was restarted by another agent mid-suite and served a
  different model. One suite ran against a dead model id before this was noticed; those rows were
  purged and re-run. The final live evaluation is genuine (`Qwen/Qwen3-1.7B`, 9 correct rollouts,
  9 cassette hits and 0 misses); the labelling pass and the paid evaluations ran on Gemini.

---

## What I might have missed

- **Nested pipelines.** Per-node figures for a node inside a delegated pipeline
  ([§5 L354-357](../../../../docs/evaluation.md#L354), `orchestrate.research.hunt`) were read in the
  source but not run. `manifest_containers` and the `_Shape` stitching in `variants.py` are the
  least exercised code in the area.
- **`Over.ALL` end to end.** The three `Over` denominators were tested through `score_of`
  directly, and only `VALUE_EXISTS` was carried through a full evaluation.
- **`node_metrics` with `Unknown` on either side.** [§11.5 L1365-1371](../../../../docs/evaluation.md#L1365)
  says both the recorded output and the label carry `Unknown`. `holds_absence` was tested as a
  unit; the per-node metric was not run with an absent label.
- **Interval behaviour at very large n.** The bootstrap was exercised at n up to 100 examples. A
  set of thousands may expose a cost or a precision issue neither reached.
- **The redaction path on a cassette an evaluation writes.** [§6.3 L537-542](../../../../docs/evaluation.md#L537)
  claims records are redacted before being written under the run's rules. That belongs to another
  area and was taken as given here.
- **`compare` over project metrics declared per node.** `compare` pairs them in `_nodes`, and the
  end-to-end project metric comparison was tested; the per-node one was read but not run.
- **Whether finding 1 has further consequences.** Only three were chased. Anything else keyed on
  `eval_id` or on `graph_fingerprint` alone inherits the same gap.
