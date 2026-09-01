# Build log — Consultation met a product

`plan.md` §1 `P3-33`. Started 2026-08-25. Written while building, not afterwards.

## 1. Before any design

Read against `HEAD` before anything was decided, because the sitting's framing rested on two
claims that turned out to be wrong.

- **The memo.** [`nodes.py`](../../src/simple_agents/runtime/tooling.py#L119), the
  `run.no_one_to_ask(tool.name)` guard, and
  [`context.py`](../../src/simple_agents/context.py#L1263), `note_no_one_to_ask`. Confirmed
  per-run, per-tool-name, set by the first `Unavailable` and never cleared.
- **The only working encoding is a lie.** [`tools.py`](../../src/simple_agents/tools.py#L1274),
  `resolve`: a channel returning `None` resolves `declined` and sets no memo, so a project
  wanting every question delivered had to record that the viewer was asked and said nothing.
- **`DF5-D14`'s premise, and it did not survive.** The finding said the stand-in mechanism
  already guarantees an evaluation never fires a real consultation. Three readings say
  otherwise. [`runner.py:410`](../../src/simple_agents/evaluation/runner.py#L410) `run` defaults
  `end_user` to nothing.
  [`runner.py:2556`](../../src/simple_agents/evaluation/runner.py#L2556) `_scoped_for_rollout`
  then leaves the registered channel in place.
  [`runner.py:2129`](../../src/simple_agents/evaluation/runner.py#L2129) `_refuse_unsafe_tools`
  reads only the two classes that spend or cannot be undone. Nothing refused it.
- **The project's own reasoning, from the frozen copy.** `agent.py:182-186`: "`consult` is
  `read_only` ... which is what lets an evaluation run k rollouts over n examples without
  refusing to start." The class system read correctly, reaching the conclusion the library
  offered.
- **What the project reached of the surface.** Two `consult` call sites. `select`
  (`agent.py:1596-1606`) reads `inputs.kept.get("passed_over")` where the fan-out declares
  `keep=["pool_looks_like", "directions"]` and discards the call's return value, so it is dead
  twice. Zero uses of `on_reply`, `Reply.chose`, `consult(match=)`, `consult(read=)`,
  `ModelReader` or `ModelAnswer`.
- **`Suspend`'s base class.** [`errors.py`](../../src/simple_agents/errors.py#L114), and the
  library's own broad handlers naming it before their `except Exception`
  ([`nodes.py`](../../src/simple_agents/nodes/llm.py#L173)), which is the discipline it asked of
  itself and of no project.
- **Which cassettes hold a consult schema.** Two, `suspend-gemini` and `suspend-vllm`. No
  Mistral-only arm, so the format move was affordable.

## 2. Design

Taken at `P3-32`'s sitting 1 on 2026-08-25 and recorded in
[`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L182). The `items/` record left
`items/` when this log was written.

| | Decided |
|---|---|
| `DF5-I01` | The memo engages only where the model chose the call. A node body's `consult` always reaches the channel |
| `DF5-I02` | `about=` on `consult`, recorded and passed to the channel; `asked` on the record; `answered_at` on a `Reply`. The channel contract takes the clean break to `(question, options, about)` |
| `DF5-I03` | `Suspend` derives from `BaseException`; a run completing after one was raised is refused. `RunSuspended` stays an `Exception` |
| `DF5-I37` | A channel may return `Shelved(reason=...)`: resolution `shelved`, no memo ever, a `shelved=` branch on `on_reply`, and acting on the answer when it arrives is first class |
| `DF5-I07` | No fifth side-effect class. The eval runner refuses a rollout over a consult tool whose channel is not a stand-in; `end_user=` is the waiver |
| `DF5-I06` | FT-25 keeps passing on registration and gains a detail line naming a tool never called in the run it read |
| `DF5-I04`, `DF5-I05` | `docs/product.md` §4 carries all three modes; `docs/tools.md` §4.6.3 says the memo is the model's, and §4.6 gains the per-item pattern |

**What was weighed and not taken.**

- **A fifth side-effect class for a question that costs a person's attention**, which is what the
  builder asked for in his own words. Declined: a class exactly one built-in ever declares is not
  a class a builder chooses, and it refuses nothing on its own. What he wanted the label to buy,
  that the machine not fire n×k real questions at him, is the refusal instead, reading the
  `answered_by` every channel already declares.
- **A callback rather than a pipeline** for acting on a shelved answer. Declined: every other
  callable the library takes runs inside a run, so what it does reaches a trajectory, a budget and
  a cassette, and a callback fired at filing time reaches none of them. `DF5-D13` is that failure
  measured once already.
- **Declaring the answering pipeline on the consult tool.** Declined on measurement: at filing
  time the library holds a run directory and an `about`, and reaching a tool declared inside the
  asking pipeline means rebuilding it from a manifest, which is `plan.md` §2.2's supervisor
  entry's own blocker. The inspectability argument moved to the artifacts, where it is stronger:
  what a check can read is shelved questions against answers filed.
- **A per-item routing seam.** Declined: `route=` is one decision per node execution and decides
  where a run goes; a question asked per item changes data and is handled where it is asked. What
  was owed was the pattern, which §4.6.5 now carries.
- **Appending the answer to the asking run's trajectory.** Declined: that run finished and its
  manifest carries final counts. Filing an answer starts a run instead, so nothing already
  written is touched.

## 3. Build

Five stages, each ending on the suite and a live run where one applied.

**Stage 1**, the memo and `Suspend`. `_run_tool` takes `by_model`, set at the three `AgentNode`
call sites and defaulted false for `NodeContext.call_tool`; the memo is read only when it is
true and still set by any call, so a model's first question is answered from it and carries the
reason. `Suspend` derives from `BaseException`, and a run reaching its end after one left a tool
call is refused.

**Stage 2**, `Shelved` and the record. Trajectory `0.27`: `about`, `asked`, `answered_at` and
`answers_run_id` on `consultation`, and `shelved` in `resolution`. The channel contract took the
clean break, which was 77 definitions across 19 files. `on_reply` gained a required `shelved=`.
**`_run_tool` was split first**, since the stage adds to exactly its consultation branches: one
call, four record emitters and an accounting tail, 226 code lines and 31 branches down to 78 and
under the branch threshold. `consult()` was split too, 129 and 24 down to 107 and 18.

**Stage 3**, the answer seam. [`shelf.py`](../../src/simple_agents/records/shelf.py#L1), the sibling of
`suspension.py`, at format `0.1`. `Pipeline.run`'s setup came out into `_start_run` so an
answering run writes the same artifacts as any other, and where the project declares no work the
run is one library-supplied node that does nothing, so there is no second code path.

**Stage 4**, the checks. The eval refusal in `run` and `record`, and FT-25's note.

**Stage 5**, the documents, below.

**What the build found that the design did not know.**

- A `Suspend` raised by a `ModelClient` mid-stream stopped reaching the handler that records what
  had streamed, because that handler caught `Exception`. Two streaming tests caught it.
- A channel returning a `Reply` it built itself lost `answered_at` and `declared_choice`, because
  `read_answer` only carried them off a mapping read back from a cassette. Building a `Reply` is
  what `Shelved`'s own documented example does.
- `shelf.discard_claim` and `suspension.discard_claim` collided in `pipeline.py`'s imports and
  the later one silently shadowed the first, so the shelf was never settled. The shelf's is
  `settle_shelf`.

**Surfaces touched.** `nodes.py`, `context.py`, `pipeline.py`, `tools.py`, `trajectory.py`,
`errors.py`, `builtins/consult.py`, `builtins/__init__.py`, `envelope.py`,
`evaluation/stand_in.py`, `evaluation/runner.py`, `conformance/checks.py`, `__init__.py`, and
`shelf.py` new. 3048 tests, 106 of them new across four files. Two cassettes re-recorded.

**`scripts/shape_check.py` and its baseline were written during this item**, on Thilina's
request at stage 1, and belong to the refactor entry in [`plan.md` §2.1](../plan.md#L86) rather
than to this one.

## 4. Verification

**Six cycles**, each a read-back of the code and the documents, the suite, and a live run against
vLLM `Qwen/Qwen3-1.7B` on port 8001. The sixth found nothing. Forty-three live assertions across
three probes at the end: three consultation modes, the memo line, the answer seam, the eval
refusal and the swallow refusal.

**What only a live run showed.** The model chose to pass `about="show:1421"` itself, so the
model-facing parameter is usable rather than merely present. The model read the `Shelved` text
and reported what it could not settle instead of guessing. And the answering pipeline made a real
model call, so the answering run is a real run with its own manifest, trajectory and priced call,
which is `_start_run` and `_drive` exercised on the newly extracted path.

**Nineteen defects, none of them visible to the suite or to any check.**

- **Cycle 1, three.** `docs/tools.md` claimed `about` is not in the cassette key; it is, and must
  be, so the document was corrected rather than the code. An unverified count in
  `docs/trajectory-format.md`. And `answer_shelved` put the question back on the shelf when the
  acting pipeline failed, **after** the answering record was written, so one question would carry
  a record saying it was answered and a shelf saying it was not.
  [`resume`](../../src/simple_agents/pipeline/core.py#L659) settles that in a comment.
- **Cycle 2, nine.** Six shipped examples still showed the two-argument channel and would raise
  `TypeError` on the first question asked through them; three `on_reply` refusals still listed
  three branches; `docs/index.md` and `docs/shipping.md` still described the old surface.
- **Cycle 3, three.** `docs/product.md` §4 used `Reply`, `Shelved` and `Answered` with no import
  shown, its `chose` example was under-specified, and §4.1 assigned a variable from a call that
  raises.
- **Cycle 4, three, all concurrency, all found by running threads.** The claim is per run and a
  run's shelf holds every question it left, so two people answering two different questions from
  one run contended and three of four were refused. `write_shelf` wrote in place, so a surface
  listing open questions could catch a half-written file. `read_shelf` and `release_shelf` tested
  for the file before using it, which is a window another worker's rename walks through.
- **Cycle 5, one.** Cycle 4's wait was applied to every refusal, so a call naming no question
  waited before being told so. Measured after the fix: 0.0ms and 0.2ms for the two caller errors,
  194ms for the one case that is a race.

**Two classes account for all nineteen**: an example that parses and cannot run, and a race that
appears only under threads. The first now has a guard in `tests/test_prose.py`, checked against
the defect it was written for. The second is what
[`concurrency-build-log.md`](concurrency-build-log.md#L1) already records a green suite not
seeing.

**Stability.** The suite five times at 3048, the threading tests twenty times, and the three live
probes three times, all clean.

## 5. Doc consequences

**`docs/tools.md`.** §4.6.3 is "Three ways a consultation ends without an answer", a table of
`Suspend`, `Shelved` and `Unavailable` against what each does to the run, and which fits which
trigger. New §4.6.4 on naming what a question is about and on `answered_at`; new §4.6.5 on asking
about each of many things, which is the pattern the routed form cannot cover. §4.6.1's `on_reply`
gained its fourth branch.

**`docs/product.md`.** §4 is "A question the agent cannot settle", in four parts: a request
somebody waits on, a background run that shelves, when the answer arrives, and who the channel
reaches. It carries `Pipeline.shelved` and `Pipeline.answer_shelved`.

**`docs/pipeline.md`** §1.8 on `Suspend`'s base class and the refusal.
**`docs/evaluation.md`** §5.4 on the refusal and its waiver.
**`docs/failure-taxonomy.md`** FT-20 on the consult exception, FT-25 on the note.
**`docs/shipping.md`** §4 and **`docs/index.md`** on the third mode.
**`docs/trajectory-format.md`** §4.3 for four fields and a resolution, and the version.
**`CHANGELOG.md`** for six breaking changes and two formats.

**Shipped statements that stopped being true**, all corrected: the channel contract in six
examples; `on_reply`'s three branches; "answered, unmatched, declined or unavailable"; and the
two written during this item and caught by cycle 1.

## 6. Left open

- **The elicitation `consultation` question does not ask which of the three modes a project
  needs**, which is now a choice a builder makes and the coding agent cannot infer. Not one of
  the eight dispositioned candidates. Destination: [`plan.md` §1 `P3-32`](../plan.md#L26), for
  sitting 2 or 3 to place.
- **`AXIS_FIELDS` is an unused import in `nodes.py`** and was already unused at `HEAD`.
  Destination: [`plan.md` §2.1](../plan.md#L86), the refactor entry.
- **`DF5-P3`, that no page a product builder reads says the library loads no `.env`**, touches
  `docs/product.md` §3, which this item rewrote §4 of. Destination:
  [`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L100) `DF5-I21`, still open in
  sitting 4.
- Beyond those three, destination: nothing.
