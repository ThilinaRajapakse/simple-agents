# Item 8b — build log

**Kept while building, not reconstructed at the end.** On the precedent of `item9-build-log.md`,
`item8a-build-log.md` and `item8g-build-log.md`.

The design of record is `archive/plan-history.md` §3.1 item 8b. §1 records what was measured before the sitting,
§2 the sitting, §3 where building sharpened a decision, §4 where it turned out not to hold, §5
what the build found that is nobody's design, §6 doc consequences, §7 existing tests that had to
change.

**Status: built 2026-08-06, one document edit outstanding.** Baseline 978 tests at `e26d0e9`;
1015 now. `docs/trajectory-format.md` §1.1 is presented at §6.1 and not yet edited.

---

## 1. What was measured, before any design

Item 8g §1 is the standard: every claim is read off a file the library produced or off a live
run, never off a document. The entry for this item says the design is settled and only the build
is left, so §1 was aimed at the entry's own premise first.

The probes are `scratchpad/measure_trajectory_bytes.py`, `measure_v14.py`,
`probe_production_shape.py` and `probe_production_turns.py`. The last two build a pipeline from
the shipped constructors and run it live against Mistral `mistral-small-2603`.

### 1.1 Most of `runs/` is not in the current format, and the stale part skews the answer

348 `trajectory.jsonl` files hold 527 records. **255 of them are format `0.14`.** The other 272
were written by formats `0.4` through `0.13`, including 89 records of a `node` type that no
longer exists.

Of the 255 current records, 185 are in `runs/record-*`, the seven pipelines
`scripts/record_backend_cassettes.py` records against a live backend. The remaining 70 are probe
and test leftovers under `runs/run_*`, and **324 of the 527 records carry an `error`**, almost
all of them the same 290-byte object from a probe that was built to fail. Read over everything,
`error` is 10.6% of the bytes, which describes the directory rather than a trajectory.

Every figure below is over the 0.14 records, and the split between the recordings and the
leftovers is kept, because they disagree.

### 1.2 On the library's own recordings, the payload fields are not where the bytes are

`runs/record-*`, 185 records, 390,368 bytes.

| Record type | Records | Bytes | Share |
|---|---|---|---|
| `model_call` | 74 | 311,466 | 79.8% |
| `node_execution` | 69 | 52,799 | 13.5% |
| `tool_call` | 38 | 24,303 | 6.2% |
| `consultation` | 4 | 1,800 | 0.5% |

`inputs` plus `outputs`, across every record type: **87,329 bytes, 22.4%.**

Inside a `model_call`:

| Field | Bytes | Share of `model_call` |
|---|---|---|
| `params` | 126,465 | 41.2% |
| `provider` | 56,050 | 18.2% |
| `inputs` | 43,196 | 14.1% |
| `outputs` | 20,331 | 6.6% |
| `tokens` | 8,380 | 2.7% |
| `context` | 5,786 | 1.9% |
| `rate_limit` | 5,102 | 1.7% |

`params` is 41% and `provider` 18%, against 20.7% for the two payload fields the entry's design
governs. The largest single `params.tools` block is 3,591 bytes, in
`runs/record-tools/run_8488b22e3204/trajectory.jsonl`.

### 1.3 Two fields inside `params` are a fixed blob written again on every call

| Field | Calls carrying it | Distinct values | Bytes written | Bytes distinct | Repetition |
|---|---|---|---|---|---|
| `params.tools` | 74 of 74 | 5 | 81,502 | 9,901 | **87.9%** |
| `params.output_schema` | 37 of 74 | 2 | 35,211 | 2,031 | **94.2%** |

The five distinct `tools` values are the five tool registries across the seven recorded
pipelines. Within one run there is one value per node, written once per call the node makes.

`provider` is the other way round: **74 distinct values across 74 calls**, mean 745 bytes. It is
the raw HTTP response header block as the adapter received it, carrying `cf-ray`, `set-cookie`,
`alt-svc`, `strict-transport-security`, `x-kong-request-id` and the `date`. Its only structured
content is the `x-ratelimit-*` group, and **that group is already parsed into the record's
separate `rate_limit` field**, so those numbers are stored twice.

### 1.4 On a production shape, the payload fields are 91% of the bytes and the entry's premise holds

`probe_production_shape.py`: twelve product pages of the length a retailer page has, 28,276
characters, about 7,000 tokens. A search tool over them, one `AgentNode`, live Mistral. This is
the dogfood #2 shape rather than a three-line corpus.

| Run | Model calls | Tool calls | Bytes | `inputs`+`outputs` | `params` | `provider` |
|---|---|---|---|---|---|---|
| 2 turns, 3 parallel searches | 2 | 4 | 160,837 | **93.1%** | 3.0% | 1.2% |
| 6 turns, one search each | 7 | 7 | 382,960 | **91.1%** | 4.5% | 1.8% |

**§1.2's ordering is an artefact of a three-line corpus.** The design's premise about where the
bytes are is right for the shape a production project has, and the local measurement does not
refute it.

Two things the entry does not say. The growth is quadratic in turns, because the whole
conversation is re-sent and re-recorded every turn:

| Call | Messages | `inputs` bytes | Cumulative |
|---|---|---|---|
| 1 | 1 | 522 | 522 |
| 2 | 3 | 13,108 | 13,630 |
| 3 | 5 | 25,940 | 39,570 |
| 4 | 7 | 38,769 | 78,339 |
| 5 | 9 | 51,608 | 129,947 |
| 6 | 11 | 64,442 | 194,389 |
| 7 | 13 | 77,271 | 271,660 |

And **the entry's own sizing is low by about a factor of four**. It says a five-turn node over a
4,000-token context writes on the order of 100KB per run. A six-turn node over a 7,000-token
corpus wrote 383KB.

### 1.5 1% sampling cuts volume by 10x, not by two orders of magnitude

The entry's stated effect is that governing `inputs` and `outputs` at 1% "cuts volume by roughly
two orders of magnitude". Sampling is a per-run decision, so the average run costs
`remainder + rate x payload`, and the remainder is a floor.

Measured on the six-turn run, 382,960 bytes, remainder 34,246:

| Rate | Bytes per run | Reduction |
|---|---|---|
| 1.0 | 382,960 | 1.0x |
| 0.1 | 69,117 | 5.5x |
| **0.01** | **37,733** | **10.1x** |
| 0.0 | 34,246 | 11.2x |

**Even rate 0 gets 11.2x.** Two orders of magnitude is not reachable by sampling the payload
fields, whatever the rate.

### 1.6 What the floor is made of, and it is the fields §1.2 pointed at

Inside the 34,246-byte remainder of the six-turn run:

| Field | Bytes | Share of the remainder | Share of the whole file |
|---|---|---|---|
| `params.tools` | 16,345 | **48%** | 4.3% |
| `provider` | 6,850 | **20%** | 1.8% |
| everything else | 11,051 | 32% | 2.9% |

`params.tools` had **one distinct value across the seven calls**. So the two fields §1.2 found
are 6% of the raw file and **68% of what survives sampling**. The local measurement pointed at
the right fields for the wrong reason.

### 1.7 The payload is already written twice inside one run

On the two-turn run, 160,837 bytes:

| | Bytes | Share of the file |
|---|---|---|
| `tool_call.outputs`, three searches | 73,294 | 45.6% |
| the same three results re-written inside `model_call.inputs.messages` | 73,691 | 45.8% |
| together | 146,985 | **91.4%** |

A retrieved passage is recorded once where the tool returned it and again in every subsequent
model call that carries it in the conversation. This is what a reference rather than a full
render would collapse, which is the entry's second open question.

### 1.8 The `{"type": "unknown"}` convention cannot carry a nulled payload

The entry says the existing convention "already covers the shape a nullable payload needs". Run
rather than argued, over `per_node` and `decode_answer`:

| `outputs` on a `node_execution` | `absent_outputs` | `decode_answer` returns |
|---|---|---|
| `{"answer": "Kirkwall"}` | 0 | the dict |
| `{"answer": {"type": "unknown", "reason": "the pages do not say"}}` | **1** | the dict |
| `{"type": "unknown", "reason": "not sampled"}` | **1** | `Unknown(reason='not sampled')` |
| `null` | 0 | `None` |

A payload nulled with that convention is **indistinguishable from a node that reported an
absence**. `absent_outputs` reaches a project's results file through `NodeMetrics.to_record`, so
the number is wrong rather than missing.

`null` is not available either. `docs/trajectory-format.md` §3 already gives it two meanings on
`node_execution.outputs`, "errored before producing anything" and "skipped", and §5.1 states
that `null`, `""` and absence never mean `unknown`. `node_execution.inputs` is required and not
nullable at all.

### 1.9 Per-node metrics do read payloads, in two places

The entry states that per-node metrics, cost derivation and budgets are unaffected "because none
of them read payloads". Two thirds of that is true.

| Reader | Reads a payload | What it does |
|---|---|---|
| `evaluation/per_node.py:349` | `record["outputs"]` | `absent_outputs`, how often this node said the value is not there |
| `evaluation/runner.py:317` | `record["outputs"]` | per-node `matched`, against `expected_by_node` |
| `cost.py`, `budget.py`, `evaluation/compare.py` | no | tokens, timestamps and counts only |

`runner.py:305` states the reason for the first one in its own docstring: "The output compared is
the one written to the trajectory rather than the object the node returned, so the same
comparison can be made again from a results file and a run directory long after the process that
produced them has gone."

### 1.10 FT-13's check cannot tell a full trajectory from an empty one

`conformance/checks.py:102` reads the run directory's `trajectory.jsonl` and requires: every line
parses, every record carries the ten common fields and one of the four record types, and at least
one is a `node_execution`. It reads no payload. **A trajectory written at rate 0 passes it.**

`ft_07` at `checks.py:293` reads `seed` on `node_execution` and `model_call` records only, and
also passes at any rate.

### 1.11 A `consultation` record has no `inputs` and no `outputs`

Its payload fields are `prompt`, `options` and `response` (`trajectory.py:337`,
`docs/trajectory-format.md` §4.3). A design governing `inputs` and `outputs` **does not touch the
record type that is end-user answers by definition**, which is the subject of the entry's first
open question.

`Redaction` is a single flat set of rules applied to every record by the writer
(`redaction.py:101`), with no per-record-type scope.

### 1.12 The writer flushes every record, so a run's outcome is not known when its records are written

`TrajectoryWriter.write` at `trajectory.py:427` writes one line and flushes it. The class
docstring gives the reason: "Append-only and flat, so a crashed run leaves a readable prefix
rather than a corrupt document."

The entry's design says "a run that errored keeps full payloads whatever the rate". A run's
outcome is known at `Manifest.close`, after every record has been written and flushed. So that
clause cannot be implemented by deciding at write time.

### 1.13 A suspended run writes the full conversation to a second file

`nodes.py:1019` captures `node_state` including `messages`, and `suspension.py:72` writes
`inputs`, `frames` and `node_state` to the suspension state file. Nothing in a trajectory-level
sampling design reaches it.

---

## 2. The sitting, and what it settled

Held 2026-08-06, after §1's measurements. Seven questions were put. Six were answered on the
first pass; Q1 was sent back for verification and is recorded at §2.1.

The entry says the design is settled and only the build is left. §1 left that partly true: the
premise about where the bytes are survived, and four of the entry's other claims did not.

| The entry says | §1 measured |
|---|---|
| `inputs` and `outputs` are nearly all of the bytes | True at production shape, 91%. False on the library's own recordings, 22% (§1.2, §1.4) |
| 1% "cuts volume by roughly two orders of magnitude" | 10.1x. Rate 0 gets 11.2x (§1.5) |
| a five-turn node writes on the order of 100KB per run | A six-turn node wrote 383KB (§1.4) |
| the `{"type": "unknown"}` convention already covers a nullable payload | It collides with a reported absence, measurably (§1.8) |
| per-node metrics are unaffected, none of them read payloads | Two readers do (§1.9) |
| a run that errored keeps full payloads whatever the rate | Not decidable at write time (§1.12) |

### 2.1 The floor is cut where cutting it breaks nothing, and not further

**Settled after verification: the hash reference and the minimal `provider` cut. The full
allowlist is not taken.** Thilina's question was what the two lose and whether anything already
built needs what they move, and he ruled that the answer had to be verified against every
existing feature rather than argued.

Verified across `src/`, `tests/`, `scripts/` and `docs/`. Fourteen readers of a `model_call`
record's `params` and `provider`:

| Reader | Reads | Hash-reference `params.tools` | `provider` allowlist |
|---|---|---|---|
| `cassette.model_call_key`, `cassette.py:298` | the **request**, via `params_for_record()` | safe | safe |
| the cassette file's stored request, `context.py:461` | the same object | safe | safe |
| the `CassetteMiss` diff message | the cassette's stored request | safe | safe |
| `test_adapter_integration.py:444` | `params.tools` **from the cassette** | safe | safe |
| `test_adapter_integration.py:538` | `params.seed` from the cassette | safe | safe |
| `test_adapters.py:291` | `response.provider`, the adapter object | safe | safe |
| `test_adapters.py:337` | `call["provider"]["x-request-id"]`, **the record** | safe | **breaks** |
| `test_adapters.py:336` | `set-cookie` scrubbed out of the record | safe | **premise gone** |
| `test_trajectory_conformance.py:76,88` | that the fields exist | passes | passes |
| `per_node`, `cost`, `budget`, `compare`, `variants`, `plan_variant` | neither field | safe | safe |
| the six conformance checks | common fields, seeds, results | safe | safe |
| resume, `_STRUCTURAL`, `graph_fingerprint` | the manifest node entry, which holds no `params` | safe | safe |

**The hash reference breaks nothing, and the reason is that `params_for_record` has two
consumers.** It feeds the cassette key and the record. Only the record changes, so every
committed cassette key stays byte-identical and nothing is re-recorded.

**The allowlist breaks `test_a_credential_in_the_passthrough_is_redacted`**, which plants
`set-cookie: session=super-secret-value` and asserts it is scrubbed while `x-request-id`
survives. Not recording the header block is a stronger guarantee than redacting it, and it
deletes a shipped FT-16 demonstration to get there.

Measured on the six-turn run at rate 0.01, against the run directory rather than the trajectory
alone, since the reference moves bytes into the manifest:

| | Reduction |
|---|---|
| sampling alone | 9.3x |
| plus the hash reference | 13.8x |
| plus dropping the five `x-ratelimit-*` headers already parsed into `rate_limit` | 14.6x |
| plus the full allowlist | 16.7x |

**The estimate offered at the sitting was ~28x and ~45x and was wrong.** It was not measured
before it was put. Correcting it changed the recommendation: the full allowlist buys 2x over the
minimal cut and costs the FT-16 demonstration, so the recommendation became the reference plus
the minimal cut, with the allowlist left to be argued as an FT-16 change on its own.

**What the reference costs, stated:** a trajectory line no longer carries the tool schemas. Read
beside its manifest it loses nothing; copied away from its run directory it does.

### 2.2 A nulled payload gets its own tag, and the omission is enumerable

**Settled: `{"type": "not_recorded", "reason": "sampling"}`, plus the path listed in an
`omissions` array beside `redactions`.**

§1.8 is what decided it. `{"type": "unknown"}` makes a nulled payload count as a node that
reported an absence: `absent_outputs` incremented, `decode_answer` returned
`Unknown(reason='not sampled')`. That number reaches a project's results file through
`NodeMetrics.to_record`, so it is wrong rather than missing. `null` was unavailable for a
different reason: `docs/trajectory-format.md` §3 already gives it two meanings on `outputs`, and
`node_execution.inputs` is not nullable at all.

The array follows §5.3's existing rule that "this field was empty" and "this field was removed"
must be distinguishable. Sampling is that problem again.

### 2.3 An evaluation refuses a sampled envelope

**Settled: `EvalSuite.run` raises `ConfigurationError` on one.**

§1.9 measured two payload readers, and the second states its own reason at
`evaluation/runner.py:305`: the output compared is the one written to the trajectory "so the same
comparison can be made again from a results file and a run directory long after the process that
produced them has gone". Sampling inside an evaluation destroys that.

Documenting the consequence instead was rejected: two shipped metrics would be silently wrong,
which is the failure class the library exists to prevent.

### 2.4 Payloads are stripped at close, not withheld at write time

**Settled: write full, strip at close. Thilina's ruling was that sampling out an errored run is
too risky.**

§1.12 is why the question existed: the writer flushes each record and a run's outcome is known at
`Manifest.close`, so tail-based sampling cannot decide at write time. Head-based sampling from
the run seed was the alternative and was rejected on the ground above.

**This changes `docs/trajectory-format.md` §1.1**, which says records are "never rewritten" and
that the writer needs "no seek, no close-time fixup, and no in-memory buffer". The sentence was
written to protect crash-readability, and a close-time strip preserves it better than the status
quo: a crashed run keeps its full payloads, which is the run a builder wants full. **The wording
is to be presented before it is edited, not changed in passing.**

### 2.5 FT-13 reports the rate and does not fail on it

**Settled.** §1.10 measured that `ft_13` reads structure only, so a trajectory written at rate 0
passes it, and so does `ft_07`. The check reports the rate in its output; the gate stays about
the artifact existing and being readable.

Failing at rate 0 was rejected as contradicting the acceptance of rate 0 as a legitimate setting.
Leaving it silent was rejected because the check would then read as a check that behaviour was
recorded.

### 2.6 Sampling governs `consultation.response`

**Settled, and it reframes the entry's own open question.** §1.11 found that a `consultation`
record has no `inputs` and no `outputs`: its payload fields are `prompt`, `options` and
`response`. So the design as written does not touch the record type that is end-user answers by
definition.

`response` comes under the same tag. Whether `consultation` also needs per-record-type redaction
rules stays open until dogfood #2 produces real ones, which is what the entry says. `Redaction`
has no per-record-type scope today (`redaction.py:101`).

### 2.7 The full render stays, and the duplication is recorded as measured

**Settled.** The entry says to decide this with real sizes from dogfood #1, and there is no
dogfood. §1.7 settles it short of one: on the two-turn run, 91.4% of the file is one set of three
search results, written once where the tool returned them and again in every model call carrying
them in the conversation.

That is a measured 2x floor on the payload itself, before any sampling. It is not enough to build
content-addressed payload storage in this item, and it is enough to stop the question waiting on
a dogfood.

### 2.8 Scope

One item, on Thilina's ruling. Trajectory `0.14` to `0.15` and manifest `0.9` to `0.10`, each
with its version-literal test and the packaging test that its document states it. `docs/`
consequences written after the build and presented rather than buried. Nothing in
`docs/evaluation.md`.

---

## 3. What building it changed about the design

### 3.1 Only two of the five `x-ratelimit-*` headers are duplicated, and the cut is worth 0.3x

The sitting recommended dropping "the five `x-ratelimit-*` headers already parsed into
`rate_limit`". Reading `adapters/mistral.py:221` while building found that **two are parsed**,
`x-ratelimit-remaining-req-minute` and `x-ratelimit-remaining-tokens-minute`. The other three
carry the window size and the query cost and are stored nowhere else, so dropping them would
lose information rather than remove a copy.

Measured on the six-turn run: the two duplicated headers are 601 bytes per run against 1,423
for all five, which moves the reduction from 13.8x to 14.1x rather than to 14.6x.

**Built as the two.** The premise Thilina approved was that the cut removes a second copy of
something the record already holds, and that premise is true of two headers and false of three.

### 3.2 The reference is two fields rather than a type change inside one

`params.tools` was a list and `params.output_schema` an object. Writing `{"ref": "sha256:..."}`
into either would have been an object where a list was, and an object with a `ref` key where a
JSON schema was. `params.tools_ref` and `params.output_schema_ref` are bare strings, which is
what `nodes[].schema` and `prompts.<node>.version` already are in the manifest.

### 3.3 `params_for_record` had two consumers and the split is what makes the cassette safe

`ModelRequest.params_for_record` fed the record's `params` and the cassette key. It is now
`params_for_key`, unchanged and still hashed in full, and a new `params_for_record(register)`
builds the record's shape. §2.1's verification depended on this being a split rather than an
edit: every committed cassette key is byte-identical and no recording was re-made.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Twenty guards, disabled one at a time, and the one that stayed quiet was the test

Nineteen of twenty failed the test named against them on the first pass. The quiet one was
`_omit` skipping a payload that is already `null`, and the reason is item 8g §4.1's shape
again: **the test never reached the guard.**

The fixture was an erroring pipeline at rate 0, chosen because a node that raises writes
`outputs: null`. A run that errored keeps its payloads, so `strip_payloads` was never called
and the guard was never executed. The test asserted a true thing about a run the code under
test does not touch.

The shape that produces a `null` payload on a run whose payloads *are* dropped is a **skipped
node**: `_emit_skip` writes `outputs=None` on a run that completes. The fixture is now a
four-node graph whose route skips one arm. **20 of 20 fire.**

The pass ran each case with `PYTHONDONTWRITEBYTECODE=1` and cleared every `__pycache__` after
restoring, per item 8g §4.2. `scratchpad/guard_pass.py` is the script.

---

## 5. Findings

### 5.1 The reduction measured on a production shape is 14.9x, against 13.8x to 14.6x predicted

The same six-turn pipeline the sizing came from, replayed from its cassette under both rates:

| | trajectory | manifest | run directory |
|---|---|---|---|
| `Trajectory.full()` | 360,251 B | 7,642 B | 367,893 B |
| `Trajectory.sampled(0.0)` | 13,517 B | 7,671 B | 21,188 B |

**17.4x at rate 0, and 14.9x at rate 0.01** averaged over a hundred runs. The prediction at
§2.1 was 13.8x for the reference alone and 14.6x with the header cut; the measurement is above
both, because the manifest grew by 29 bytes rather than by the 2,335 the estimate assumed. One
tools block is stored once whatever the run's length, and the estimate charged it per run
without noticing it was already being charged to the trajectory it replaced.

Both runs produce 15 records. `counts`, `totals`, `seed`, `outcome` and `budget` are identical
between them.

### 5.2 A skipped node's `inputs` is a payload and is dropped

Measured while fixing §4.1. A skipped node records `inputs` as a `join` or an `unknown` naming
the edge that did not fire, and `outputs: null`. Sampling replaces the first and leaves the
second. `termination: "skipped"` is what still says the node did not run, so the reason a
reader needs survives at every rate.

### 5.3 The trajectory format document already had the rule the reference follows

`docs/trajectory-format.md` §6: "If a value is the same for every record in a run, it belongs
in the manifest", and the row for prompt templates saying that inlining them "would bloat every
record with identical content". `params.tools` is that case and had escaped the rule. §6 now
carries a row for it, which is a rule being applied rather than a new one being made.

---

## 6. Doc consequences

Written after the build.

| Document | What it said | What it says now |
|---|---|---|
| `docs/trajectory-format.md` §2 | ten common fields | Eleven. `omissions` |
| `docs/trajectory-format.md` §4.1 | `params` as configuration as sent; `provider` as the backend sent it | `params` pointing at §4.1.5; `provider` less any header already on `rate_limit` |
| `docs/trajectory-format.md` §4.1.5 | did not exist | **New.** The `params` object, the two references, and that the cassette key hashes the declarations in full |
| `docs/trajectory-format.md` §5.4 | did not exist | **New.** A payload the run did not keep, and why `not_recorded` is not `unknown` and not `null` |
| `docs/trajectory-format.md` §5.4, §5.5 | Timestamps was §5.4 | Renumbered to §5.5, with the one reference to it corrected |
| `docs/trajectory-format.md` §6 | five rows of what is not in the format | Six. Tool declarations and output schemas |
| `docs/trajectory-format.md` | version `0.14` | `0.15`, in the header, the field table and both example records |
| `docs/run-envelope.md` §1 | the envelope's four arguments | Five. `trajectory=` |
| `docs/run-envelope.md` §2.1 | the manifest's keys | `recording` and `schemas` |
| `docs/run-envelope.md` §2.7 | did not exist | **New.** The `schemas` table and what a trajectory read without its manifest loses |
| `docs/run-envelope.md` §7 | did not exist | **New.** The rate, which runs keep their payloads, what survives at every rate, and the evaluation refusal |
| `docs/run-envelope.md` §2 | manifest `0.9` | `0.10`. Edited during the build, because the packaging test that pins it would otherwise hold the suite red, which is item 8a §7's precedent |
| `docs/failure-taxonomy.md` FT-13 | "Recording is not a setting and there is nothing to switch on" | The rate, what stays complete at every rate, and that the check reads structure rather than payloads |
| `CHANGELOG.md` | trajectory `0.14`, manifest `0.9` | `0.15` and `0.10`, the three additions, and what a project has to do about each |

**Not touched, and deliberately.** `docs/evaluation.md`, which is next in Thilina's review and
already carries unreviewed text from two items. The evaluation refusal is documented in
`docs/run-envelope.md` §7 and in the error message rather than there. `docs/pipeline.md`,
`docs/tools.md`, `docs/context.md`, `docs/conformance.md`, `docs/index.md` and the model-client
pages own nothing this item changed.

### 6.1 `docs/trajectory-format.md` §1.1, presented rather than edited

Q4 settled on stripping payloads when the run closes, which is a close-time rewrite. §1.1 says
the writer does not do one. **The sentence is unedited and the build works around nothing: the
code does rewrite the file, so the document is currently wrong.** Presented at the end of the
sitting record and awaiting sign-off.

---

## 7. Existing tests that had to change

Seven, and none is a defect. Four are version literals and three are field lists the format
bump widened.

| Test | What it asserted | Why it failed |
|---|---|---|
| `test_packaging.py::test_every_format_version_is_pinned_to_a_literal` | trajectory `0.14`, manifest `0.9` | both bumped |
| `test_run_envelope.py::TestManifest::test_it_names_the_trajectory_it_belongs_to` | `trajectory_format_version` `0.14` | the same bump |
| `test_trajectory_conformance.py::TestCommonFields::test_format_version_is_declared_on_every_record` | `0.14` on every record | the same bump |
| `test_trajectory_conformance.py`, `COMMON_FIELDS` | ten fields transcribed from §2 | `omissions` added, and four type tests compare symmetrically against it |

Three more failed and were fixed **outside** `tests/`, which is the better fix in each case:

- `test_packaging.py::test_the_trajectory_format_document_states_the_version_the_writer_writes`
  and its manifest sibling were fixed by editing the two documents, which is what those tests
  exist to force.
- `test_packaging.py::test_the_manifest_document_lists_every_key_the_manifest_writes` named
  `recording` and `schemas` and was fixed by writing `docs/run-envelope.md` §2.1 and §2.7.

**The 81 fixture trajectories and 90 fixture manifests under `tests/fixtures/projects/` were
migrated to the new formats**, which is what a project on the old format would have to do and
is the migration the CHANGELOG describes.

**Total: 7 existing tests changed, 37 added. 1015 tests.**
