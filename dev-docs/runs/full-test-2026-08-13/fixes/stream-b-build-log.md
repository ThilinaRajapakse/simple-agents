# Stream B build log — evaluation

Files owned: everything under `src/simple_agents/evaluation/`, `docs/evaluation.md`, and tests
whose subject is evaluation, examples, labels, variants, rescore, paid evaluation or project
metrics.

Started after Stream A landed. Baseline suite at start: 2050 passed, 2 skipped, 0 failed.

Status: **complete**. Written incrementally; the machine went down twice during this pass.

---

## Work items

1. D2 — `_eval_id` widens to sampling, tools, budget, `allow_unknown`. `graph_fingerprint`
   untouched. `compare_variants` refusal names the variant and the sweep. **§1.**
2. D2 follow-up — surface variant comparison in `docs/evaluation.md`. **§5.**
3. D3 — split `_rollout`'s bare `except Exception` into suspension / configuration / no response /
   ordinary failure. **§3.**
4. `resume_from` on the default recording path. **§2.**
5. F-01 — the §8.1 sample report band. **§4.**
6. Documentation flags. **§6.**

---

## 1. D2. `_eval_id` is a digest of what decides what was measured

Ruling [D2](../RULINGS.md#L27), Option C. `graph_fingerprint` is untouched: it answers "can this
stored state still be walked", which is what a resume needs, and Stream A already corrected
`pipeline.md`'s claim about it.

### What `_eval_id` now hashes

Everything it hashed before — the example set's content hash, the seed, the split, `k`, the
graph fingerprint, every prompt version, the run's model — plus `_measured_configuration(pipeline)`:

```python
{"nodes": pipeline.manifest_nodes(),
 "containers": pipeline.manifest_containers(),
 "budget": pipeline.budget.to_record()}
```

**Wider than the four fields the ruling enumerates, and deliberately so.** The ruling's principle
is "everything that decides what was measured" and its list is the measured gap, not a ceiling.
`manifest_nodes()` carries the four the ruling names — `sampling`, `tools`, `allow_unknown`,
`node_budget` — and beside them `route`, `consultation_route`, `finish_check`, `context_builder`,
`stream`, `fan_out`, `accepts` and the per-node `model`. Every one of those decides what a number
was measured over, and each was as absent from `_eval_id` as the four. Enumerating four of the
twelve would have left the same defect under a different field name. The per-node `model` list
that `_eval_id` hashed separately is now inside this, so it is no longer hashed twice.

`json.dumps(..., default=str)` because a node's `extra` is provider-specific and the library does
not constrain what goes in it.

### `rescore` and `resume_from`

`_eval_id` names the directory, so `resume_from` refuses a moved configuration through the
directory-name check it already had (consequence 1b). `rescore` is given the directory, so no
name check applies to it and consequence 1c needed its own gate.

`_refuse_a_moved_pipeline` keeps the `graph_fingerprint` comparison, which is the right first
question and the right message when the shape moved. `_refuse_a_moved_configuration` follows it:
`_measured_configuration_of(handle.manifest)` against `_measured_configuration(self.pipeline)`,
diffed field by field, and the refusal names the fields rather than two digests:

```
The rollouts in 'runs/eval_...' ran under a different configuration. The graph is the same
shape, and 1 field(s) that decide what was measured are not. ...
  nodes.extract.sampling.temperature: None -> 0.7
```

The diff walker is `compare.py`'s, which already reports `nodes.hunt.sampling.temperature` for a
comparison between two results files. It was private (`_changed`); it is now
`config_differences`, and `variants.py` and `runner.py` both call it, so a refusal and a
comparison name a field the same way.

A run whose manifest records none of the three is skipped rather than refused, so a directory
written by an earlier version is scored rather than rejected on an absent record.

**Verified the round trip.** `manifest_nodes()` compared against the same array read back from a
written `manifest.json` gives no differences, so nothing in the projection changes shape by
being written and read.

### The `compare_variants` refusal names the arm and the sweep

`_refuse_a_used_directory` now raises `UsedRunDirectory`, a `ConfigurationError` subclass
carrying `run_dir`. `compare_variants` wraps every arm, the baseline included, in
`_naming_the_arm(...)` and re-raises with the arm's name, how many arms have already been paid
for, and the whole sweep:

```
compare_variants stopped on the 'hunt as one call' arm: it resolves to 'runs/eval_...', which
already holds an evaluation's rollouts. ...
1 arm(s) of this sweep have already run and been paid for.
The sweep is the baseline against 'hunt as one call', 'verify removed'. ...
```

With `_eval_id` widened, the leading example of §10 no longer collides at all: a variant differing
in a temperature or a tool now names its own directory. What remains reachable is a sweep run
twice into one `run_dir`, which is where naming the arm earns its place.

## 2. `resume_from` on the default recording path

Finding [2](../findings/area-f-evaluation.md#L82). The evaluation that stopped wrote
`<eval_dir>/cassette.jsonl`; on the resuming call `_recording_by_default` rebuilt
`Cassette.record` over it, and `Cassette.record` refuses a file that already holds a recording.
The documented call in §6.5 could not run.

`_recording_by_default` takes `resuming=`, and where the default path already holds a recording it
returns `Cassette.update(path)` instead. That is the same semantics the interrupted evaluation was
running under: the rollouts that already ran keep what they bought, a repeated tool call is served
rather than performed again (FT-20), and every model call carries its rollout's own seed so a
resumed rollout is not served another's response.

`_refuse_mixed_cassette` reads the caller's envelope and is unaffected: §7.3 refuses an evaluation
the *caller* put in `update` mode, and this is the runner continuing its own file.

## 3. D3. Different answers per failure class

Ruling [D3](../RULINGS.md#L57), Option D. `_rollout`'s one bare `except Exception` now sorts
four ways. **Which exception falls where was left to the implementation, and this is the
decision and the reasoning.**

### The classification

| Reaching `_rollout` | Answer | Why |
|---|---|---|
| `RunSuspended` | propagates to the caller | The run is waiting on a person, not finished. §7.4 already promised this. |
| `ConfigurationError` and every subclass | ends the evaluation | Declared as "wired up wrongly, and detectable before the run started", so it fails identically on every rollout. One is the whole of the information and the other k×n are not paid for. |
| `StreamUsageMissing` | ends the evaluation | The client reports no token counts on a streamed call, on every call it makes. Same reasoning, different base class. |
| `CassetteMiss` | `no_response` | The recording holds no answer for a call the run made. The agent never ran, so nothing was measured. |
| `BudgetExceeded` | `failed` | The rollout spent its allowance. That is the agent's own behaviour and belongs in `failure_rate`. |
| `ContextOverflow` | `failed` | The request the node's own context built was refused as too long. Also the agent's behaviour, and per example rather than identical everywhere (FT-17). |
| anything else, where the run stopped on a model call that recorded an error and no response | `no_response` | The backend was unreachable, rejected the request, rate-limited past its retries, or answered with a status the adapter could not use. |
| anything else | `failed` | The backend answered and the agent produced nothing usable: a tool raised, a response did not validate, a node function threw. |

### Why the last two are decided by the trajectory rather than by the exception type

**There is no type that means "transport".** Every transport failure the shipped adapters raise
is a bare `CallerFacingError`: `_error_for` returns one for 401, 403, 404, 400, 422, 429 and
5xx, and `_unreachable` returns one for a connection that never opened. So does
`nodes.py:3190` when a model's response does not match the declared output schema, which is the
agent failing and has to stay `failed`. `CallerFacingError` is raised at 50-odd sites across
`nodes.py`, `pipeline.py`, `graph.py`, `context.py`, `shapes.py` and `builtins/`, and they are a
mix of both classes. Testing for it would have swept the schema failures out of `failure_rate`,
which is the defect D3 exists to prevent, pointing the other way.

The library already writes the fact at the moment it is known. `_emit_failed_call_record` puts a
`model_call` record on the trajectory for every call that raised before returning a response,
carrying the error and no content. That record is the library's own statement of "the backend did
not answer", it is written whatever the client is, and `_rollout` already reads the trajectory on
this path for `_observed`. So the test is: **the last `model_call` this run made carries an error
and no content**.

Two properties this buys that a type test does not:

- **It works for a client the project wrote.** A `ModelClient` outside the library raises
  whatever it raises, and the record is the same either way.
- **It is exact about position.** A response that arrived and was then rejected leaves a
  `model_call` record with content and no error, so a schema failure stays `failed` even though
  the exception is the same class as a 404.

`CassetteMiss`, `BudgetExceeded` and `ContextOverflow` are named ahead of the test because each
also produces a failed call record and each needs a different answer from what the record alone
would give.

### `Outcome.NO_RESPONSE`, and why it is not called `transport_failed`

The ruling calls the class "a transport failure". A cassette miss is in it and is not transport,
and what the four sources have in common is that no answer came back, so the outcome value is
`no_response`. `docs/evaluation.md` §2.1 is the section that names it.

### What "excluded from the rates' denominators" cost

- `scores_by_metric` and `project_scores` drop those rollouts, so all six rates and every project
  metric are over what was measured.
- `EvalResults.scores_by_example` drops them too, so `compare()` pairs on the same set.
- `Metric` gains `no_response`, counted over the examples that metric's figure is over, so
  `recall` counts only the examples where a value exists.
- `report()` prints `, less 3 that got no response` on every rate line, and the undefined branch
  says it in the reason. **Beside every rate, not in a corner of the file**, which is the ruling.
- Per-node `reach` and `accuracy` are unchanged. A rollout that reached `hunt` and then lost the
  backend at `verify` did reach `hunt`, and those figures are read from the trajectory.

### `rescore` sorts it the same way

`_rescored` applies the same test, so a re-score reproduces the rates the run reported. Without
that, a `record=False` evaluation and its re-score would disagree on every rollout the backend
dropped (F-16 asserts they agree).

### `suite.record` too

`RunSuspended` propagates from `record()` rather than being named in `failed`. A recording short
one run and a recording waiting on a person are different states, and only one of them is fixed
by running it again.

### The results format moves to 0.11

`Outcome` gains a value an older reader cannot parse, and `metrics[].no_response` is a new field.
`EvalResults.read` refuses a version it does not write, so the bump is what stops an 0.10 reader
being handed `"no_response"`.

## 4. F-01 and the sample report

`docs/evaluation.md` §8.1 printed `[70%,100%]` for reach on a 3x3 evaluation, which is
`wilson_ci(9, 9)`. `reach` groups by example, so the code emits `wilson_ci(3, 3)` and the band is
`[44%,100%]`. The interval arithmetic was verified sound against scipy during the QA pass and is
untouched.

**`tests/test_sample_report.py` had the same number hand-written into it**, so the document and
its own guard agreed on a figure the library never produced. `_reach()` now calls
`wilson_ci(3, 3)` rather than restating the endpoints, which is what makes the test able to fail.

A second sample block was added showing what a rollout the backend never answered does to a
rate, and it is pinned line for line against `aggregate()`.

## 5. D2 follow-up. Surfacing the variant API

Ruled: surface it, do not redesign it. `compare_variants` already takes named arms and runs them.

`docs/evaluation.md` gains a **"What to reach for"** table immediately under the opening
paragraph, before §1, mapping six things a builder wants to the call that does it and the section
that covers it. `compare_variants` is the one the table then expands on, with the call shape and
the two sentences that say why it is not the same as running two evaluations by hand. It was
previously first named at line 1114 of 1405, inside §10.

The example imports from `simple_agents.evaluation`, which is correct today and stays correct
after the top-level exports land. **The exports and the `index.md` row are the lead's**, and both
are in the stream report.

## 6. The remaining flags

Fixed, all in files this stream owns:

- **F-01.** §8.1's `[70%,100%]` is `[44%,100%]`. §4 above.
- **F-03.** §10 said the plan marks the changed node live and everything *upstream* replayed.
  `_taint` walks forward along `reaches`, so everything the changed node can reach is live too,
  which §10.1 already stated correctly. §10 now says it and points there.
- **F-04.** §10.2 said "three things put a variant there" and named a set that does not match the
  code. Rewritten as two sources: the three `_removable` checks, quoted, and the graph's own
  refusals, which are open-ended. Verified by running `ablate` over a one-node pipeline and over
  a `Deterministic`-then-two-`LLMNode` chain and reading the sentences back.
- **F-05.** §10's `plan.live_calls # 45` was unlabelled and reads as a sweep total. It is per
  rollout, and the comment now says so with the multiplication.
- **F-06.** `Recording.paid_calls` was documented as provider calls and counts paid tool calls.
  The docstring and the §6.3.1 table now say what it counts, and say where the model-call count
  is instead.
- **F-08.** §6.4 said two fields do not survive a rescore. It is three: `run_concurrency` as well.
- **F-09.** The §8 `config` table omitted `max_spend`, `scored_from` and `seed_source`. All three
  are listed and a paragraph says what each is for.
- **F-13.** §6.1 omitted the model from the `eval_id` list while §6.5 included it. The rewritten
  §6.1 names it.
- **F-16.** §6.3 said a `record=False` evaluation "cannot be replayed or re-scored". It cannot be
  replayed; `rescore` reads trajectories rather than the cassette, so the second half was wrong.

**Left open, and reported rather than fixed** — each is a code change no ruling covers:

- **Finding 6.** `totals.tool_spend.currency` is taken from the accumulated model `Cost` rather
  than from the tool spend, so a `Deterministic` pipeline with a paid tool reports an amount with
  no unit. The fix is a `tool_currency` on `NodeMetrics`, read off each `tool_call` record's
  `spent.currency`. `Recording.currency` has the same shape and is documented rather than fixed.
- **Finding 5, F-14, F-15, F-17, F-07, F-10, F-11, F-12.** Listed in the stream report.

## 7. Live verification

### vLLM, `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` at `84455dc6`

Three examples at k=2, real documents, real extraction.

```
1. eval_id separates a temperature
   graph_fingerprint equal : True
   eval_id cool            : eval_1993155da0a6
   eval_id hot             : eval_8e2fc823561a

2. a live evaluation, then resume_from on the default recording path
   accuracy 1.0, q3's rollouts deleted, resumed
   rollouts 6, accuracy 1.0, cassette continued True

3. rescore refuses rollouts a different configuration produced
   nodes.extract.sampling.temperature: None -> 0.7
   same configuration scored: accuracy 1.0

4. a model id the server does not serve
   outcomes ['no_response'], failure_rate None, no_response 6
   every rate: "undefined ... 6 rollout(s) got no answer out of the backend"
```

The §10 leading example, live:

```
baseline eval_id : eval_8ad7ff343b9f
arm eval_id      : eval_28f783e3a3a9
changed          : {'nodes.extract.sampling.temperature': [None, 0.7]}
baseline accuracy: 1.0    arm accuracy: 1.0    moved: []
```

A `Deterministic` node raising `Suspend` inside an evaluation:

```
raised RunSuspended : 'which depot the question is about'
run_id q1-0, state on disk True
```

### Gemini, `gemini-3.1-flash-lite`, concurrency 2

```
1. a paid evaluation : accuracy 1.0, spend 0.0002185 USD, no_response 0
2. resume_from       : 4 rollouts, accuracy 1.0, cassette continued True
3. rescore refused   : nodes.extract.sampling.temperature: None -> 0.7
4. a retired model id: outcomes ['no_response'], failure_rate None, no_response 4
```

Spend for this stream: **$0.0002185**.

## 8. Tests

New: `tests/test_eval_identity_and_failures.py` (26). Added to `tests/test_variants.py`: three,
covering the arm-named refusal and a sampling-only arm running. `tests/test_sample_report.py`
rewritten to compute the reach interval rather than restate it, and extended to pin the second
§8.1 block line for line (14 in total).

Changed:

- `tests/test_eval_runner.py::test_replaying_lets_it_run_because_the_tool_is_served_from_the_file`
  asserted every rollout was `FAILED` under an empty replay. A cassette miss is now
  `no_response`, and the test asserts that and the count.
- `tests/test_rescore.py::test_a_failed_rollout_stays_failed` used
  `FakeModelClient(responses=[])`, so every rollout stopped on a model call that never returned.
  Split into two: one for a backend that never answered, asserting live and re-scored agree on
  `no_response`, and a new one for a response the schema rejected, which is still `failed`. That
  second one did not exist and is what holds the line between the two classes.
- `tests/test_sample_report.py` as above. It is the file that should have caught F-01 and could
  not, because the wrong number was written into it.
- `tests/test_packaging.py`, one line: `EVAL_FORMAT_VERSION == "0.11"`. **Not this stream's
  file.** The test's own docstring says a bump is an edit to it, and there is no other way to
  move the constant.

## 9. State at the end

`uv run pytest tests/ -q`: **2089 passed, 2 skipped, 0 failed.**
`uv run python scripts/prose_check.py`: **clean**.
`scripts/check_citations.py`: 122 problems, all anchors into `dev-docs/` records that this
stream's code movement shifted. Not run with `--fix`, per the instruction and Stream A's note
that one pass after every stream lands is the right point.
