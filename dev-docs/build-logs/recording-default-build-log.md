# A run records by default, and cassettes sample with trajectories — the build

Built 2026-08-11, as `archive/plan-history.md` §1.10, off `build-logs/rescore-build-log.md` §4.2.

**vLLM only.** Mistral is out of credits, which is the mirror of the constraint the rescore
item ran under. §7 says what that leaves unverified.

---

## 1. What was measured before anything was designed

Five claims were checked against the code rather than carried over from the brief. Four held
and one was worse than stated.

### 1.1 Flipping the default alone writes nothing, and the suite does not notice

`RunEnvelope.cassette`'s default was changed to a recording cassette with no path, and the
suite run unchanged.

```
baseline                     1619 passed, 1 skipped
default flipped, no path     1616 passed, 1 skipped, 3 failed
```

The three are `tests/test_rescore.py::TestRecordingByDefault`, and they fail because
`_recording_by_default` sees an enabled cassette and leaves the eval-level path unset. **No
other test moves, and no cassette is written anywhere**, because
[`Cassette.store`](../../src/simple_agents/records/cassette.py#L383) returns
`StoreOutcome(written=False, diverged=False)` when `path is None`. The measurement of the
blast radius that the flip appears to give is void.

### 1.2 With resolution built, the blast radius is the same three tests

A prototype resolving the pathless default at run start, into `<run_dir>/<run_id>/cassette.jsonl`,
was run against the same suite.

```
resolution built             1616 passed, 1 skipped, 3 failed   (the same three)
```

So the suite says nothing about a run that now writes a second file. Nothing in it asserts
that a run wrote no cassette, which is why the void in §1.1 was invisible.

The prototype does write, and the linkage to the trajectory holds:

```
Trajectory.full()        cassette exists=True   1873 bytes   trajectory 1772 bytes
Trajectory.sampled(0.0)  cassette exists=False     0 bytes   trajectory 1812 bytes
```

The manifest carries the resolved path under `cassette.path`, and reports `mode: "off"` on the
run whose payloads were dropped.

### 1.3 An evaluation still gets one cassette across its rollouts, and `record=False` is what breaks

[`_recording_by_default`](../../src/simple_agents/evaluation/runner.py#L2654) sets
`<run_dir>/<eval_id>/cassette.jsonl` on the scoped envelope before the rollouts start, so every
rollout runs under an envelope that already names a cassette and the per-run default never
fires. The two compose.

**`record=False` does not.** It returns the envelope untouched, which under the new default is
an envelope that records — one file per rollout, which is the thing k rollouts sharing one
recorded tool answer exists to prevent (FT-20). `record=False` has to set `Cassette.off()`
explicitly.

### 1.4 A repeated `run_id` appends, and matches what the trajectory does

Measured on two runs into one run directory under the prototype default:

```
same request, same response        cassette 1 line   trajectory 4 lines   recorded=0 diverged=0
same request, different response   cassette 2 lines  trajectory 4 lines   recorded=1 diverged=1
different seed                     cassette 2 lines  trajectory 4 lines   recorded=1 diverged=0
```

The trajectory appends, 2 records becoming 4. The cassette appends the same way, does not
write a response already on file, and counts a divergence where the same request came back
different, which is what it already does within one run.

**This is why the default cannot go through `Cassette.record`.** That constructor refuses a
file that is not empty:

```
ConfigurationError: Cassette.record('/tmp/.../c.jsonl') was given a file that already holds a
recording.
```

`Pipeline.resume` writes into the run's own directory under the run's own id, so a resumed run
would meet that refusal on a file it wrote itself. The default resolves to a recording cassette
built directly, and the refusal keeps its job: a path the builder named.

### 1.5 `Trajectory.keeps(run_id)` is deterministic and settled before the first call

[`Trajectory.keeps`](../../src/simple_agents/records/trajectory.py#L719) hashes the `run_id` and
compares against the rate. `run_id` is generated at
[`Pipeline.run`](../../src/simple_agents/pipeline/core.py#L491), before `prepare`, before the seed,
before the manifest and before any node runs.

**But deciding at run start is the wrong moment, and that is what §2.1 turns on.** A run that
errored or suspended keeps its payloads whatever the rate, because the trajectory is written in
full and stripped at close. A cassette decided at run start cannot know the run will fail, so
an unselected run that errored would keep its trajectory payloads and have no recording, which
is the run most worth replaying.

### 1.6 The consent question can be written truthfully, and only in one direction

Measured on the live run at the previous item: 43,075 bytes of trajectory against a 41,612
byte cassette. A `model_call` record carries the whole prompt and the whole response by
default, so turning the cassette off protects nothing while the trajectory is full. The lever
that keeps payloads off disk is `Trajectory.sampled(0.0)`, and under this item that one lever
now governs both files. A question offering it is truthful; the deleted `stored_responses`,
which offered `record=False`, was not.

---

## 2. What §2.1 says, and what this item is to it

`simple-agents.md` §2.1's decision is "every component runs inside a run envelope that records
by construction", its rationale is that the alternative is "logging as a thing the agent author
remembers to do. They don't", and its diagram names the manifest, the trajectory log and the
cassette. Two of the three were written by construction. **The cassette was the thing the
author had to remember, which is §2.1's own description of the failure**, and the rescore item
measured an author not remembering: dogfood #3 recorded none and a metric that raised cost one
to two hours of GPU.

So this item completes §2.1 rather than changing it. No decision moved and no rationale was
argued against.

**The linkage is new and is not implied by §2.1**, so on Thilina's approval §2.1 gains a second
decision and its own why: a defaulted cassette under a sampled trajectory would be the only
copy of the payloads the project asked to stop keeping, so one decision governs both.

---

## 3. What shipped

### 3.1 The default is a cassette, not a flag

`RunEnvelope.cassette` defaults to `Cassette.into_run()`, a recording whose path is filled in
at run start by `Cassette.for_run(root)`. There is no third state and no sentinel: a builder
who passes nothing gets a recording cassette, and one who passes `Cassette.off()` gets an off
cassette, which are different values.

*A first design had the envelope hold `Cassette | None` so the library could tell "passed
nothing" from "passed off". Thilina rejected it, and it was solving a problem that stops
existing once the default itself is the recording. `cassette=None` would also have read as
"off" to a builder and recorded.*

`Cassette.store` now raises on a recording with no file rather than returning
`StoreOutcome(written=False, ...)`. §1.1 is what that no-op cost: a suite of 1619 tests that
could not tell a run recording everything from a run recording nothing.

### 3.2 The recording goes with the payloads, at the moment the payloads go

`_close_manifest` already stripped the trajectory's payloads for a run whose `run_id` the rate
did not select, and only for a run that completed or stopped early. The cassette is deleted at
that same point, under that same condition, by the same branch.

**This is Thilina's ruling and it is better than the design as settled.** Deciding at run start
would have left an errored run under sampling with payloads and no recording, and §1.5 has why.
Matching the trajectory exactly means a run that errored keeps both, which is the run most
worth replaying.

A default recording is deleted; a cassette the project named a path for is not. The run knows
which it has because `Pipeline.run` and `Pipeline.resume` resolve the path themselves and
carry `defaulted_cassette` into the close.

The manifest gains `cassette.dropped`, `null` while the file is there and the reason where the
run deleted it, and goes to `0.20`. `cassette.recorded` still counts what the run recorded
before the drop, so a reader sees calls recorded and the file gone rather than an empty
recording.

### 3.3 An evaluation still gets one file

`_recording_by_default` now tests for the unresolved default rather than for `enabled`, so the
eval-level path is still set before the rollouts start and the per-run default never fires
inside one. `record=False` sets `Cassette.off()` explicitly, which is §1.3's defect. An
envelope that says `Cassette.off()` is now honoured rather than recorded over, because off is a
statement once the default records.

`EvalSuite.record` refuses the default outright and names a path. Before that refusal it would
have read `Path(str(None))` and recorded into a file called `None` in the working directory.

### 3.4 The question, and `reproduce`

`keep_payloads`, required at `build`: "Every run keeps a record of what was sent to the model
and what came back. Should this agent's runs keep it?" 29 questions to 30.

**The framing is Thilina's and it corrected a fault.** The first draft asked whether there was
material that must not be kept, which asks the builder to audit their own material rather than
asking them the decision. The question states what happens and why, and takes an answer.

**Required rather than optional**, because §4 of the rescore log's fourth answer for why nobody
raised this was that nothing refuses or checks it. An optional question can be skipped, and
then the builder is never told.

`reproduce` keeps its question and gains a new scaffold. Its old one, "If yes, record a
cassette", describes something the library now already did. What still changes the answer is
sampling, where the runs that can be replayed are the ones their run id selects and a specific
run cannot be nominated afterwards; the scaffold names `envelope.with_trajectory(Trajectory.full())`
for a run that has to be reproducible.

---

## 4. A defect this exposed that predates it

**The conformance fixture generator has been broken since the `brainstorm` stage shipped**, and
adding a required question is what ran into it. `scripts/build_conformance_fixtures.py` builds
`brief.toml` from `required_at("measure")` and an `ANSWERS` table, so a question with no answer
in the table raises `KeyError`. Six had none: the `brainstorm` stage's, plus `too_similar`. It
also wrote neither `understanding_confirmed_at` nor `idea.md`, both of which FT-29 reads and
both of which are in the committed fixtures.

So the fixtures on disk were hand-edited after that item rather than regenerated, which is what
the script's own docstring says not to do: "Generated rather than transcribed, so a question
added to the set leaves the fixtures failing FT-24 until they are rebuilt rather than passing
against a stale list."

Repaired and regenerated. The evidence that the drift predates this item: with `src/` stashed
at HEAD, the repaired generator produces `eval_067c5860e6d7` where the committed fixtures hold
`eval_e5a1bbef5a22`, so the committed runs were written by a library the fixtures no longer
match.

**Two fixtures a copy-and-edit cannot produce** are now built rather than transcribed.
`contaminated-split` and `no-absent-examples` carry what the library computed from an example
set, so writing them into the conforming run's results file would be writing the answer the
check reads. Each is built from its own set instead: one gives an example on each side of the
split the same `source` and passes `allow_contaminated_split=True`, which is how a project gets
a number over a split like that and is the failure FT-03 reads; the other moves the example
whose answer is absence to the dev split, so the set still holds one and the held-out side is
what lacks it. Both replay the same cassette, since neither changes a question.

The contaminated fixture's report is now the real one, `shared_source` at similarity 0.6667
between `d1` and `e1`, where the transcribed file named a `d4` that its own example set did not
contain.

---

## 5. Tests

**1619 to 1635.** `tests/test_recording_default.py`, 16 in four classes.

- `TestARunRecords` (5): the file beside the trajectory, a replay of it reaching no backend,
  `Cassette.off()`, a run with no envelope at all, and the pathless store raising.
- `TestTheCassetteSamplesWithTheTrajectory` (5): a dropped run losing its recording, a kept run
  keeping it, `sampled(0.0)` keeping neither, a project's own path left alone, and an errored
  run keeping both.
- `TestARunDirectoryUsedTwice` (2): a repeated `run_id` appending the way the trajectory does,
  and a resumed run recording into the file its first half wrote.
- `TestAnEvaluationStillGetsOneCassette` (4): one file across nine rollouts, `record=False`
  writing none anywhere, an envelope saying off staying off, and `record` refusing the default.

`run_ids_by_fate(rate)` searches for one id the rate keeps and one it drops, so the sampling
tests assert the linkage rather than a hardcoded id.

---

## 6. Live, against `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on vLLM

An `AgentNode` with one tool over three depot questions, one of which the records do not
answer.

```
1. a run records, and replays
   output                      Northampton      cassette 9,227 bytes / trajectory 7,219
   manifest cassette           record, recorded=4, dropped=null
   replay                      Northampton, 0 live model calls, 0.01s against 1.1s live

2. a sampled-out run
   output                      Leicester        cassette files under the run dir: 0
   manifest cassette           recorded=4, dropped="sampling"
   trajectory                  3 model_call records, 0 payloads kept
   tokens                      still recorded: 19 uncached, 1,584 cache read, 52 output

3. an evaluation, 3 examples x k=3
   cassette files              1: eval_4848e110f834/cassette.jsonl
   tool calls executed         12, stored as 4 entries
   accuracy                    0.667
   rescore                     9 rollouts, accuracy 0.667, agrees: True
   replay of the evaluation    0 live model calls, accuracy 0.667
```

**What a fake client cannot produce is the third block's 12 against 4.** The tool body ran
twelve times while recording and the file holds four entries, because a tool call is keyed on
its arguments rather than on which rollout made it. That is the property one file per
evaluation exists for, and one file per rollout would have ended it with nothing failing.

**The second block is the linkage on a real backend**: a run that recorded four calls, kept its
token counts and its costs, and left nothing on disk holding what was said.

**The first block's byte counts run the other way to the previous item's** (43,075 trajectory
against 41,612 cassette there, 7,219 against 9,227 here). An `AgentNode` sends the whole
conversation on every call, so its cassette holds each turn's cumulative message list where the
trajectory holds each turn once. The claim the question rests on is unaffected: both files hold
the prompts and the responses.

---

## 7. What Mistral's absence leaves unverified

Mistral is out of credits. Not run: a default recording made against a hosted backend, where
the manifest carries cache-read and cache-write token classes and the cost basis is a
`PriceBasis`. Nothing in the resolution, the drop or the linkage branches on backend, and the
vLLM run above exercised all three, but a hosted run was not made.

Also not run: a `PacedClient` in front of a hosted backend recording under concurrency, where
several rollouts store into one file at once. The lock covering that is unchanged by this item
and `TestConcurrency` in `tests/test_cassette.py` covers it with fakes.
