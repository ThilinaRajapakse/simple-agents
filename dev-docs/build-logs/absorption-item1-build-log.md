# Absorption item 1 — `runs()` — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`item14-build-log.md`, `item13-build-log.md` and the eight before them.

The design of record is `archive/dogfood-absorption.md` §1, approved 2026-08-09. This log records what
was measured before any code, what the sitting decided, and where building disagreed with the
spec.

**Status: sitting held 2026-08-09, building. Baseline 1211 tests at `8911d0c`.**

§1 is what was measured, §2 the sitting and its six rulings, §3 what building sharpened, §4
what it found that is nobody's design, §5 doc consequences, §6 existing tests that changed.

---

## 1. What was measured, before any design

Four probes over **1,627 real runs and 5,681 `node_execution` records**: the library's own
`runs/`, and all three dogfood projects as they stood on 2026-08-09. Scripts under the
session scratchpad; the numbers are restated here because the scratchpad is not durable.

| | library | dogfood-1 | dogfood-1-run2 | dogfood-2 |
|---|---|---|---|---|
| Top-level runs / nested eval rollouts | 475 / 25 | 4 / 470 | 95 / 540 | 18 / 0 |
| `node_execution` with `"outputs": null` | 395 | 0 | 7 | 38 |
| Recorded absences at depth 0 | **0** | **0** | **0** | **0** |
| Recorded absences at depth ≥ 1 | 19 | 285 | 499 | 1,634 |
| Manifests that failed to parse | 0 | 0 | 0 | 0 |

### 1.1 A recorded absence is never the whole value

The headline. `decode_answer` converts `{"type": "unknown"}` to `Unknown` at the outermost
level only, and the spec asked `outputs_of` to decode through it so "a recorded absence comes
back as `Unknown`". **Not one of the 2,437 recorded absences in the corpus is outermost.** A
node returns a schema object, so the absence is a field inside it:

```json
{"source": {"type": "unknown", "reason": "No size chart found on UNIQLO's site."},
 "evidence_url": "https://www.uniqlo.com/us/en/men/tops/t-shirts/uniqlo-u",
 "same_product_confirmed": false}
```

Built as specced, `outputs_of` would have returned the raw dict while its docstring promised an
`Unknown`. `holds_absence` in `per_node.py` already knew this and already recurses; its
docstring states the same fact.

### 1.2 The same top-level decode is applied to a node's output during an evaluation

`runner.py` `_node_outputs` and `_observed` both decode a node's recorded output before handing
it to a project's `node_matches` or per-node `ProjectMetric`. By 1.1 that decode has never
fired. It is not a defect: `docs/evaluation.md` §5.2 documents the raw tagged object as what a
matcher receives, and absence as the matcher's to handle. It is the reason the sitting reached
the question in §2.5.

**No dogfood ever used `expected_by_node` or `node_matches`**, so this path has run only in the
library's own tests. There is no installed base to migrate.

### 1.3 `null` is a real recorded output, and a missing node is common

440 node executions across the corpus recorded `"outputs": null`, 38 of them in dogfood-2. In
dogfood-2's 18 runs the `report` node executed in **13**; five runs stopped before it. Its own
reader guarded with `if not isinstance(outputs, dict): continue`, which swallows both cases and
also swallows a `report` that legitimately returned a list.

### 1.4 Skipping an unreadable manifest changes a shipped check's output

Never observed: 1,627 manifests, zero parse failures. But `_latest_run` today keeps a run whose
manifest will not parse, so FT-14 reports `manifest.json is not JSON: <error>, so no model
identity is readable`. Were `runs()` to skip it, `_latest_run` returns `None` and FT-13 and
FT-14 both report "no run directory under runs/" for a project that has one.

### 1.5 The module-name collision is real, and was measured rather than assumed

A package doing `from .runs import runs` shadows its own submodule. Built the package and ran
it: `import pkg.runs` binds the **function**, and so does `import pkg.runs as m`. A reader
writing either gets an `AttributeError` somewhere unrelated.

### 1.6 Changing the run-id format is cheap

`new_run_id()` is one line and every other reader treats the id as opaque. Three references in
shipped docs, all illustrative; no test asserts the shape; evaluation rollouts set their own ids
(`e1-0`, `e1-1`) and are untouched.

---

## 2. The sitting, 2026-08-09

Six questions put to Thilina with the measurements above. His rulings:

1. **Discovery is direct children by default, `nested=True` to recurse.** Accepted with the
   counter-datum on record: all thirteen fixture projects under `tests/fixtures/projects/` hold
   rollouts only and would return an empty list. Synthetic, so it does not defeat the ruling;
   the docstring must say where rollouts went.
2. **Run ids are timestamped**, folded into this item. `run_20260809T014233Z_a3f9`, so a
   directory listing is chronological.
3. **`completed()` ships as `RunHandle.finished`**, a bool property, filtered by comprehension.
   `completed` is also one of the four `outcome` values and the filter deliberately admits
   `stopped_early` as well, so the word would have meant two things.
4. **`outputs_of` raises `LookupError` naming the run's node ids** where the node never
   executed, and `RunHandle.node_ids` lists them. `None` stays the answer for a node that
   produced nothing.
5. **An unreadable manifest is still a run.** `manifest` is `{}`, `outcome` is `None`, and
   `unreadable` carries the reason.
6. **One shape for a recorded absence, everywhere.** See §2.1.

### 2.1 The ruling that grew the item

The spec's decode is a no-op (§1.1), so the live options were to make it work or to drop it.
Dropping it was recommended, on the grounds that `node_matches` receives the raw tagged object
by documented contract and one recorded value would otherwise arrive in two shapes. **Thilina
asked whether both readers could convert instead.** They can, and that is what ships:

> **A record is data; a value a node produced is a value.** `read_trajectory` still yields raw
> JSON records. Everywhere the library hands back the thing a node produced —
> `RunHandle.outputs_of`, and the output given to `node_matches` or a per-node `ProjectMetric` —
> it is converted, and `isinstance(value, Unknown)` is the absence test everywhere in the
> library, live or read back.

What that costs, all of it named before the ruling: the conversion recurses; `holds_absence`
learns `Unknown`; the labels convert the same way or the two sides of a comparison diverge;
`docs/evaluation.md` §5.2 and §11.1 change what they promise; the library's own tests move.
**Two of those fail silently if missed** — a miscounted `absent_outputs`, and a label that stops
matching — and Thilina asked for a test on each.

---

## 3. Where building sharpened a decision

### 3.1 The run id holds seconds, and the tie is broken elsewhere

A first test asserted that two ids sort into the order the runs happened, and it failed: both
runs started inside one second, so the random tail decided. Two ways out were live. Millisecond
precision in the id makes the name authoritative and makes the id longer and harder to read;
seconds keeps it readable and leaves sub-second runs unordered by name.

**Seconds ships.** `runs()` orders by the manifest's `started_at`, which is millisecond
precision, so the ordering a reader gets is right either way, and the id's job is to make a
directory listing legible rather than to be the sort key. Both halves are pinned by a test, and
`docs/run-envelope.md` §1.1 states the precision rather than implying the name is the order.

### 3.2 `outputs_of` has two failures, not one

A run that wrote no trajectory and a run that wrote one without that node are different repairs,
so the message splits: the first names the outcome to read, the second names the nodes that did
run. The second is the one dogfood-2's reader needed on 5 of its 18 runs.

### 3.3 `node_ids` costs nothing and answers the question the raise provokes

Both come out of one walk: a dict keyed by node id, each entry overwritten by that node's later
executions, gives last-execution outputs as its values and first-execution order as its keys.

## 4. What building found that is nobody's design

### 4.1 A per-node label holding an absence in a field was written to the file as a string

`encode_answer` converted a bare `Unknown` and dumped a model, and walked nothing. A label
declared as a whole node output, which is what `expected_by_node` asks for, therefore reached
`json.dumps(..., default=str)` with an `Unknown` object still inside it:

```
old: {"source": "type='unknown' reason='not published'", "confirmed": false}
new: {"source": {"type": "unknown", "reason": "not published"}, "confirmed": false}
```

Read back, `"source"` is a string that matches nothing, and `content_hash()` changes with the
repr. **Silent, and it predates this item.** It was never hit because no dogfood used
`expected_by_node` at all (§1.2), and the library's own tests labelled nodes with bare values.

The recursion the sitting ordered for `decode_answer` is what fixes it, applied to its inverse:
the pair has to walk the same structures or a round trip is not one. `test_example_sets.py`
holds it now.

### 4.2 Three readers of "a node's last recorded output" now exist

`RunHandle._node_outputs` and the runner's `_node_outputs` and `_observed`. All three exclude a
skipped execution and take the last record per node, and all three decode through the same
function, so the shape cannot drift. The walks are not shared because the runner needs
`reached_in` over the same record list and would otherwise read each trajectory twice.
Consolidating is a candidate, not this item's business.

## 5. Doc consequences

| Document | What changed |
|---|---|
| `docs/run-envelope.md` §1.1 | The generated run id's format and precision |
| `docs/run-envelope.md` §8, new | `runs()`, the handle's surface, nesting, and §8.1 on what an output comes back as |
| `docs/evaluation.md` §5.2 | A node matcher receives `Unknown` on both sides, replacing the paragraph promising the tagged object |
| `docs/evaluation.md` §11.5 | The same for a per-node `ProjectMetric` |
| `docs/trajectory-format.md` §5.1 | The tagged object is how a file stores absence, not what a reader of a value gets back |
| `docs/index.md` | The run-envelope row names reading runs back |
| `CHANGELOG.md` | One `Added`, two `Changed`, with what a project has to do |

The wheel was rebuilt, and the new §8 was read back out of it.

## 6. Existing tests that had to change

Two, both in `test_eval_runner.py`, and both because the contract they pin is the one that
moved:

- `test_per_node_accuracy_is_reported_where_the_example_labels_the_node` reached into the tagged
  object with `output.get("answer", {}).get("reason") == getattr(expected, "reason", None)` to
  compare an absence. That clause is now dead: `output.get("answer") == expected` matches both
  sides directly, which is the change in one line.
- `test_the_recorded_output_is_what_a_node_matcher_sees` still holds, since the output is still
  plain recorded data at the top level.

**Nothing else in the suite moved.** 1211 tests at the baseline, 1238 after, all passing, with
the 27 new ones split between `test_runs.py` (24) and the two silent spots plus the label round
trip (3).

## 7. Verified against real artifacts

The API was run over dogfood-2's 18 recorded runs, which were written by an older version of the
library and carry the old id format:

```
runs listed: 18 | finished: 14
runs whose report node ran: 13
suggestions collected across every run: 29
a chase source: Unknown(type='unknown', reason='The product page and site search did not ...')
```

That is `fitfinder/results.py`'s `collect_from_runs`, 45 lines, reproduced in five, including
the guard it hand-rolled for the 5 runs that never reached `report`. The 13 matches the figure
measured in §1.3 before any code was written.
