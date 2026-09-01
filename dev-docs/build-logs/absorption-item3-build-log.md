# Absorption item 3 — the replay seed — build log

**Kept while building.** Design of record: `archive/dogfood-absorption.md` §3, approved 2026-08-09, and
**re-derived from the problem at the sitting on Thilina's instruction** rather than built to the
spec. §2 records where the two agree and where the spec was silent.

**Status: sitting held 2026-08-09, built. Baseline 1247 tests at item 2.**

---

## 1. What was measured, before any design

### 1.1 A run recorded without an explicit seed cannot be replayed

`Pipeline.run` generates a run seed when given none. Every model call's seed derives from it,
and that seed is inside the keyed request. So an ordinary record-then-replay fails:

```
recorded at run seed: 1927391078

No recorded response for call 0 of node 'extract' in /tmp/.../qa.jsonl.
The nearest recorded request for this node differs in:
  params.seed (recorded 1564526049, now 102003894)
```

**The library invents a number, makes it part of the replay key, and does not put it in the
artifact.** Everything else needed to replay is in the file: model identity, messages, sampling
parameters, tools, schema.

### 1.2 The message names a number that cannot be used

`1564526049` is the derived call seed, not the run seed. Passing it back derives a third:

```
derive_seed(1927391078, "extract", 0) = 1564526049   # what the message prints
derive_seed(1564526049, "extract", 0) = 367236198    # what pasting it gives
```

The run seed appears nowhere in the message or the file, and this is true of every cassette
recorded before this item.

### 1.3 The run directory is not where the seed can come from

`git ls-files`: **16 cassettes are committed, and no file under `runs/` is tracked.** In a fresh
checkout or in CI the recording run's manifest does not exist. Entries carry `run_id`, which
locates the run only where the directory survives, which is not the case the cassette exists for.

### 1.4 The seed cannot leave the key, and the evaluation cassette proves it

The clean-looking alternative is to drop the seed from the key: it is library-generated rather
than builder-declared, and tool calls already disambiguate repeats with an occurrence ordinal.
Re-hashing `tests/cassettes/eval.jsonl` (3 examples × 3 rollouts, 28 model calls) without it:

| | |
|---|---|
| distinct keys today | 28 |
| distinct keys with the seed removed | **17** |
| seedless keys holding more than one entry | 6, five of them holding exactly 3 |

The fives are the k=3 rollouts of one example at one node: identical prompt, different seed.
**Two of those groups recorded genuinely different answers:**

```
rollout 0: {"answer": "Kirkwall", "source": null}
rollout 1: {"answer": {"type": "unknown", "reason": "The retailer notes..."}}
rollout 2: {"answer": "Kirkwall", "source": null}
```

Without the seed in the key those three replay as one answer, the spread vanishes, and a
replayed evaluation reports a confident interval around a number no run produced. The seed
stays in the key, so the replayer has to learn it, so it travels in the file.

### 1.5 Multi-run cassettes are normal; multi-seed ones are the evaluation

Of the 15 committed cassettes, 11 hold one run and 4 hold more. `record_backend_cassettes.py`
passes a fixed `SEED`, so the multi-run graph files are single-seed. **`eval.jsonl` is the real
multi-seed case**, 9 rollouts at 9 seeds, and every project that evaluates has one.

---

## 2. The sitting, 2026-08-09

Thilina's instruction was to forget what the spec asks for, state the problem with a real
example, and design the best fix: "we make the best choices and best designs, not what was
written down before", and then, on seeing §1, "unless of course the spec is right and the best
choice agrees".

It agrees on where the seed lives, for a reason the spec does not give (§1.4). It is silent on
everything else. What shipped:

1. `CassetteEntry.run_seed`, optional and absent-tolerant.
2. A replay with no `seed=` adopts it.
3. A file naming several seeds is refused before the first call, naming the count.
4. An explicit `seed=` still wins, and a mismatch still misses loudly.
5. **The miss message names the run seed** rather than the derived one. Not in the spec, and
   the half that repairs every cassette already recorded.
6. `Cassette.recorded_seed`, the seed a replay would adopt.
7. `update` adopts it on the same rule, since the mode exists to re-run only what changed.

Approved as "1-7 doesn't seem to break anything else".

---

## 3. Where building sharpened a decision

### 3.1 The refusal lives in one function, before the manifest is written

`_seed_for(cassette)` decides: generate where nothing is being read from, adopt a lone recorded
seed, refuse where there are several. It runs before `envelope.prepare`, so a refused run
writes no directory and leaves nothing to clean up.

### 3.2 The seed note fires on the difference, not on the entry

`_seed_note` is added only where `describe_differences` reported `params.seed` **and** the
nearest entry carries a run seed. A temperature edit against a file that carries seeds says
nothing about seeds, and an old file says nothing at all. Both pinned.

### 3.3 Nothing else calls `Pipeline.run` seedlessly against a cassette

Checked rather than assumed: `EvalSuite` derives a seed per rollout and passes it, and
`compare_variants` passes one through to `EvalSuite.run` (`variants.py:349, 369`). The refusal
in 2.3 is reachable only from a bare `Pipeline.run`, which is the case it is for.

## 4. Doc consequences

| Document | What changed |
|---|---|
| `docs/run-envelope.md` §3.1 | Where a replay's seed comes from, `recorded_seed`, the refusal, and old files |
| `docs/run-envelope.md` §3.2 | The miss message naming the run seed |
| `docs/run-envelope.md` §5 | A run reading from a cassette takes the seed from the file |
| `CHANGELOG.md` | One `Added` entry |

## 5. Tests

Thirteen added, 1247 to **1260**. Eight in `test_cassette.py::TestTheSeedARunReplaysAt` covering
the field, `recorded_seed` under one seed, several seeds and none, and the message in its three
states. Five in `test_run_envelope.py::TestCassette` driving a real pipeline: a run recorded at
a generated seed replaying with none given, an explicit seed winning and missing loudly, the
multi-seed refusal, `update` adopting, and a run with no cassette still generating.

**The committed cassettes were not re-recorded.** They carry no `run_seed`, which is the
absent-field path, and every test that replays them passes an explicit seed as it did before.
The write path is exercised by the new tests through the same `_store` a live run uses.
