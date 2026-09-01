# Scoring rollouts that already ran — the build

Built 2026-08-10, straight off dogfood #3 rather than from a scheduled item.

**vLLM only.** Mistral was out of credits, which is the mirror of the constraint the
paid-evaluation item ran under the same day. §5 says what that leaves unverified.

---

## 1. What Thilina hit

A project metric raised `IndexError` on an answer it could not split. The evaluation ended
**after every rollout had been paid for**, wrote no results file, and the run had no cassette,
so the only path to a number was the GPU time again: 1 to 2 hours.

His reading of why, checked against the code rather than taken:

| Claim | |
|---|---|
| A raising metric destroys the whole evaluation at the last step | **True** |
| Fixing the metric does not move `eval_id`, so a re-run is refused for a used directory | **True** |
| There is no re-score path | **True** |
| Therefore 1 to 2 hours of GPU | **Only without a cassette** |

The last one is the correction that mattered. `_scored` ran after the last rollout returned;
`_eval_id` hashes the example content, seed, split, k, graph fingerprint, prompt versions and
model identity, and **metrics are not in it**, so a fixed metric names the same directory. And
`EvalResults.read` only reads a file that was written: nothing built one from trajectories, and
`aggregate`, `scores_by_metric`, `node_rates` and `totals_of` are not exported, so even
hand-rolling it meant reaching into private internals.

**But a recorded cassette makes the re-run free**, measured before anything was designed: the
cassette survives the crash, and replaying it at the same seed into a different `run_dir`
rebuilt the whole results file with **0 model calls**. His run had none, so the two fixes below
are what he needed. Both were built anyway, because a cassette is not the only thing that goes
missing.

---

## 2. Fix 1 — score as each rollout lands

`_scored` walked every rollout after the walk finished. It is now `_score`, called at each of
`_rollout`'s three return points, so a metric that cannot read the answer fails on the first
rollout it meets rather than on the thirty-third.

**Concurrency needed a second change and it is the one that does the work.** `pool.map` submits
every job immediately and the `with` block waits for all of them, so failing early inside a
rollout still paid for every rollout. Rollouts are now submitted with `submit`, collected in
order, and on any exception the ones not yet started are cancelled. Those already running
finish, so the loss is bounded by `concurrency`.

Measured, 18 rollouts at `concurrency=3` against a local model:

```
before : 18 of 18 rollouts paid for, then the evaluation died
after  :  4 of 18
```

At `concurrency=1` it stops after **1**.

---

## 3. Fix 2 — `EvalSuite.rescore(run_dir=, split=)`

Reads each rollout back from its run directory and scores it. Nothing executes a pipeline,
calls a model or spends anything.

### 3.1 The load-bearing part is recovering the answer, and it is exact

A re-score has to reconstruct what `_answer_of` was given. **`Graph` refuses a pipeline with two
nodes that have no successor** — "which of them produces the run's output depends on which path
ran. A run returns one value, from one node" — so the output node is unique by construction
rather than inferred from what happened to run last.

`terminal_node_id` reads `graph.terminal` and descends through containers to the leaf id a
trajectory records; `output_of` takes that node's last execution, decodes it, and rebuilds it
through the node's declared `output_schema`. **The rebuild is what keeps a callable `answer`
working**: without it the value comes back a plain dict and `answer=lambda out: out.city`
breaks. Suspension already rebuilds values in flight the same way.

Checked against `result.output` on seven shapes before anything else was written:

```
linear                 terminal=wrap        match=True
absence                terminal=absent      match=True
routed (short arm)     terminal=settle      match=True
routed (long arm)      terminal=settle      match=True
bounded cycle          terminal=done        match=True
nested pipeline        terminal=inner.wrap  match=True
llm terminal           terminal=extract     match=True
```

The nested case failed on the first attempt and is why `terminal_node_id` descends: `graph.terminal`
was `'inner'`, and a container records nothing under its own id.

A record written under an older schema falls back to plain data rather than raising. Refusing
there would fail the re-score on the run it is most wanted for.

### 3.2 The fingerprint refusal

Each run records the digest of the graph it walked, so scoring rollouts of one shape under a
suite holding another is caught rather than reported. Without it a builder re-scores last week's
rollouts under today's `answer` and `matches` and gets a number describing code that never ran,
with nothing in the file saying so, which is FT-15.

### 3.3 What a partial set reports, which was a defect found while building

The first working version reported `n=11` on a re-score covering 2 examples, because `n` was
`len(chosen)`. A held-out number over 2 of 11 examples presented as 11 is the failure the six
rates exist to prevent.

`n` is now the examples the number is over, and `config.incomplete` carries
`examples_in_split`, `examples_scored`, `rollouts_expected` and `rollouts_scored`. `report()`
prints it above every figure:

```
2 example(s) x 3 rollout(s) on split 'held_out', seed 1308420538
  INCOMPLETE: scored 6 of 33 rollout(s), over 2 of 11 example(s) in this split. Every figure
  below is over what ran, not over the split.

  accuracy   100.0%  [34.2%, 100.0%]  n=2 over all rollouts
```

The interval widens on its own, which is the instrument doing its job.

### 3.4 What does not survive the round trip, and is `null` rather than invented

`concurrency` and `max_spend` describe running an evaluation. `seed` is one rollout's rather
than the evaluation's, because `derive_seed` does not invert; `config.seed_source` says
`"rollout"`. `cost_basis` is a parameter, because a basis is not recoverable from a run
directory and inventing one prices the run under rates it never paid.

Results file `0.8` to `0.9`, gaining `incomplete`, `scored_from` and `seed_source`.

---

## 4. Fix 3 — why nobody asked, and the wrong answer to it

Thilina's question was why the dogfood session neither recorded a cassette nor raised it with
him. Four answers, and none is that the documentation was silent.

- **`docs/procedure.md` said it and framed it as an optimisation**: "A recording makes the
  second evaluation free." An agent driving at the first number reads that as skippable.
- **The one elicitation question that touches it, `reproduce`, asks the wrong thing.** "Does a
  specific past run have to be reproducible later?" For a local model the reasonable answer is
  no, because re-running looks cheap until something eats it.
- **It is optional, and at the `build` stage.**
- **Nothing refuses or checks it.** Every other load-bearing thing here is a refusal.

### 4.1 The first attempt was wrong and Thilina caught it

`reproduce` was rewritten to ask "What would it cost to run this agent again over the whole
example set?". **`rerun_cost` sits directly above it, same stage, also optional, and already
asks that**: "How many times may this be re-run before the builder wants to see the bill?", with
a scaffold that already says to price one example and multiply. The rewrite made two adjacent
optional questions ask one thing, and destroyed a question that asked something distinct.

It also failed the standard the commit that created the question set was named for, "make the
gate ask what only the builder can answer". Whether the library should keep a copy of responses
it already received is not a decision the builder has information about.

### 4.2 What shipped instead, on Thilina's ruling

**The default is what fixes this, not the wording.** An evaluation records its rollouts, into
`<run_dir>/<eval_id>/cassette.jsonl`, unless the envelope names a cassette of its own.
`record=False` turns it off. So the failure §1 describes cannot recur by omission.

`reproduce` is reverted verbatim. It still has scope the default does not cover: the default is
`EvalSuite.run`'s, and a production `Pipeline.run` still records nothing unless asked. What is
worth keeping from the rewrite moved into `rerun_cost`'s scaffold, where the cost question
already lived: that the figure is paid once rather than per attempt at scoring it.

**A first attempt at the informing question was added and then removed the same day.**
`stored_responses` at the `measure` stage asked whether the builder was content for the
evaluation's responses to be written to disk, and told them to pass `record=False` where the
material must not be stored at all. **That is false.** `trajectory` defaults to
`Trajectory.full()`, so a `model_call` record already carries the whole prompt and the whole
response; measured on the live run, trajectories 43,075 bytes against a cassette of 41,612.
`record=False` removes the second copy and leaves the first. The lever that keeps payloads off
disk is `Trajectory.sampled(0.0)`, a different knob.

**Which answers the question Thilina then asked**, whether there is any sane reason to turn the
cassette off given the trajectory holds the same content. Measured on `Pipeline.run`:

```
Trajectory.full()        trajectory holds the payload: True   cassette: True
Trajectory.sampled(0.0)  trajectory holds the payload: False  cassette: True
```

For privacy, no: with a full trajectory the cassette discloses nothing new. The exception is a
sampled trajectory, where the cassette becomes the only copy and a defaulted one would defeat
the single control the library offers. An evaluation refuses a sampled trajectory outright, so
this can only bite a production run. What is left as a reason is disk, which the cassette
roughly doubles, and for which there is no `Cassette.sampled()`.

**Settled, not yet built.** Thilina's design: every run records by default, not only an
evaluation; a cassette is sampled with its trajectory on the same per-run decision, so the runs
that keep payloads are the runs that can replay and no other; and one question, informing the
builder that this is on and asking whether they object. `Trajectory.keeps(run_id)` is
deterministic and known at run start, so the linkage has somewhere to go. It changes
`RunEnvelope`'s default, which reaches every run in the library rather than every evaluation, so
it is its own piece of work with its own blast radius to measure.

**`stored_responses` was deleted rather than repaired**, back to 29 questions, because the
question it should be is the merged one and that cannot be written truthfully until the default
it would describe exists.

### 4.3 A defect the default exposed

`_config` recorded `envelope.cassette.to_manifest()` from the envelope passed in, not the one the
rollouts ran under. With recording on by default, a results file said `cassette.mode: "off"` for
an evaluation that had recorded 41 KB. It now reads the scoped envelope. This was invisible
before, because the two were always the same.

---

## 5. Tests and live verification

**1595 to 1614.** `tests/test_rescore.py`, 19 in three classes. `TestFailingEarly` (3): stopping
early under concurrency and serialised, and a working metric still scoring every rollout.
`TestRecoveringTheAnswer` (5): the terminal id, a container's leaf, the schema rebuild, an
absence, and a run that never reached the terminal. `TestRescore` (11): scoring without
executing, the file reading back, agreeing with the evaluation that produced the rollouts, a
metric added afterwards, the partial set, the fingerprint refusal, an empty directory, the seed
source, the null fields, per-node cost needing the basis, and a failed rollout staying failed.

**Live, against `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on vLLM.** Six depot questions,
five answerable and one not, k=3.

```
1. metric raises              stopped after 4 of 18 rollouts
2. rescore the 4              0 model calls, 0.01s, INCOMPLETE 4 of 18 over 2 of 6
3. full run, then rescore     accuracy        1.0   == 1.0
                              recall          1.0   == 1.0
                              abstention_rate 0.167 == 0.167
                              failure_rate    0.0   == 0.0
                              country_len     0.0   == 0.0
                              outcomes match: True
4. rescore, other pipeline    refused, both fingerprints named
```

**The absence is the part a fake client cannot produce.** The model returned
`{"city": {"type": "unknown", "reason": "The passages do not mention the Marlow depot or its
location."}}` in 671 ms, and the re-score recovered it as an `Unknown` and scored it as a
correct abstention.

**What Mistral's absence leaves unverified**: a re-score of rollouts made against a hosted
backend, where `cost_basis` is a `PriceBasis` and the manifest carries cache-read and
cache-write token classes. The path does not branch on backend, but it was not run.
