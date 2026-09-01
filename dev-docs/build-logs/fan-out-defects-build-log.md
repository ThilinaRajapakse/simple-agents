# Build log — the two defects in the fan-out mechanism

`plan.md` §1 P3-16. Started 2026-08-18. Written while building, not afterwards.

Dogfood #4's `DF4-I10` and `DF4-I32`, the rest of the inventory's first sitting. Both are defects
in the mechanism [`P3-15`](fan-out-and-node-shape-build-log.md#L1) moved, which is why they sat
behind it: taken first, each fix would have been written twice.

## 1. Before any design

**`DF4-I10`: the classification is at the wrong boundary, and the finding says so.** An `over=`
fan-out collects an item failure rather than raising, and at the default `max_failures=None` it
never raises at all, so [`_outcome_for`](../../src/simple_agents/evaluation/runner.py#L2728) is
never reached: it is called once, from the `except Exception` branch of a rollout
([runner.py:2728](../../src/simple_agents/evaluation/runner.py#L2728)). A rollout whose fan-out
lost every item to the backend goes down the success path and is scored on what it returned.
Measured in the run: 15 rollouts, 14 of them 429s, `failure_rate` 0.00, and because the figure was
declared `Over.ASSERTED` those rollouts left its denominator and the arm reported the run's
highest number.

**`DF4-I32`: true, library-side, and there was no seam.** A fan-out returns one `FanOutResult` to
one successor, so a project whose side effect is in that successor writes once, at the end. The
run has a progress channel, `on_progress=` taking a
[`NodeEvent`](../../src/simple_agents/pipeline/events.py#L61) with phases `started`, `completed`,
`skipped` and `failed`, and the executor announces nodes because that is what it sees.

## 2. Design

**`DF4-I10` ships a count and reclassifies nothing**, which is the shape the library chose one
item ago for the same class of problem. `plan.md` §2.1's *An outcome for a run that consulted and
got no answer* records it: a rollout that stopped to consult and got nothing lands in `missed` and
reads as an agent failure when it is the answerer's, and what shipped was
`RolloutOutcome.unanswered_consultations`, a count, with the reclassification deferred pending a
project where the difference changes what someone does with the figure. The same argument holds
here and for the same reason: the count is what makes the thing measurable, and reclassifying is
what needs the evidence. **What was weighed and not taken:** reclassifying a rollout whose fan-out
produced no successful item as `no_response`, which covers dogfood #4's one-item case exactly and
says nothing about a hundred-item fan-out that lost one.

**What separates a transport failure from any other failed item** is the rule `_outcome_for`
already applies to a whole run: the last model call recorded an error and returned no content. An
item that failed on a reply it was given, such as one that did not validate, is the agent
producing no answer from an answer, which is what `failed` covers. `DF4-D4`'s 28 items that died on
schema validation are not these.

**`DF4-I32` adds an `item` phase to the channel that already exists.** A phase of its own rather
than a `completed` event carrying an `item_index`, so a caller counting `completed` events counts
nodes whether or not any of them fans out. **Weighed and not taken:** a separate `on_item=`
callback, which is a second channel for the same subject.

## 3. Build

**2659 tests, from 2650**, six of them written at the reverification pass. Results file `0.17` to `0.18`.

- **[`_unreached_items_in`](../../src/simple_agents/evaluation/runner.py#L2558)** reads the failed
  items off the node record and the last model call of each off `item_index`, and
  `RolloutOutcome.unreached_items` carries the count into the results file.
- **`NodeEvent` gains `item_index` and an `item` phase**, emitted by
  [`_fan_out`](../../src/simple_agents/nodes/fanout.py#L216) as each item finishes. `RunContext` gains
  `progress_sink`, because the fan-out is inside the node and the executor's own announcer is not.

**One thing the build found that the design did not know.** **A failed model call recorded no
`item_index`**, so the counter read zero on the very case it was written for.
`_emit_failed_call_record` is a different builder from the one a call that returned goes through,
and `P3-15` had threaded the item through the second and not the first. It is the same defect
class as that item's third finding, in a third place: the success path carried the item and the
failure path did not. The record a builder debugging a fan-out reads is exactly the failed one.

**One defect found at the reverification pass.** The counter keyed its failed items on
`item_index` alone, and an index is a position within one fan-out, so two fan-out nodes in one
rollout both have an item 0. A later node answering its own item 0 stood in for an earlier node's
failed one and the count read zero. Keyed on `(parent_id, item_index)` now, which is the node's
record and the item within it.

## 4. Verification

**Live against vLLM `Qwen/Qwen3-1.7B` on port 8001**, a three-item fan-out with the third call
raising, so two items reached a real backend and one did not.

| What it had to show | Result |
|---|---|
| Items announce themselves before the node finishes | `item` at 3.8s and 5.4s, node `completed` at 5.5s |
| A failed item announces its error | `item 2` with `error` set, at 5.5s |
| A failed call records which item it was for | `[(0, False), (1, False), (2, True)]` |
| The count reads the transport failure | `1` |
| A node that does not fan out announces no items | no `item` phase |
| An item that failed on a reply is not counted | `0`, against a response that did not validate |

## 5. Doc consequences

| | |
|---|---|
| `docs/evaluation.md` | `unreached_items` beside `unanswered_consultations`, with what it does not count and the rule that nothing is reclassified |
| `docs/pipeline.md` | §1.7's `phase` list gains `item`, with what a project writes on it |
| `CHANGELOG.md` | Two entries and the results-file move |

**Two shipped statements stopped being true.** `docs/pipeline.md` §1.7 read *"`phase` is
`started`, `completed`, `skipped` or `failed`"*. And `docs/trajectory-format.md` §3.4 described
what a fan-out records without `termination`, which `P3-15` had added to an item, found at the
reverification pass.

## 6. Left open

One entry. `DF4-I10` and `DF4-I32` both close, and with them the inventory's first sitting.

- **Whether a rollout whose fan-out reached the backend for no item at all should be
  reclassified.** The count ships and sorts nothing.
  Filed under `plan.md` §2.1's *An outcome for a run that consulted and got no answer*, and
  **taken into `P3-22` on 2026-08-19**, which settles the denominator question that entry
  waited on: [`design/spend-that-produced-nothing.md`](../design/spend-that-produced-nothing.md#L1) §3.
