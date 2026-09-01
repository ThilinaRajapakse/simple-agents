# Build log — what the end user sees

`plan.md` §1 P3-6. Started and finished 2026-08-16. Written while building, not afterwards.

Closes `DF4-I02` and `DF4-I20` off [`findings.md` DF4-D1](../runs/dogfood-4/findings.md#L197).

## 1. Before any design

Four things checked in the source before anything was decided, and two of them changed the design.

**`Pipeline.graph_fingerprint`
([`graph_fingerprint`](../../src/simple_agents/pipeline/core.py#L2055)) is shape alone**, by its own
docstring: node ids, kinds, edges, loop bounds, error edges, retry policies and output schemas. **So
the staleness dogfood #4 met would not have moved it.** That project's rows went stale on a prompt
version, and a prompt edit changes no node, no edge and no schema. A project stamping with the
identity the library already publishes would have found a stale row and a current one identical.
This is what made a second identity worth building rather than a documentation line pointing at the
first.

**The only prompt-inclusive identity computed anywhere is `_eval_id`
([runner.py:1162](../../src/simple_agents/evaluation/runner.py#L1162)), and it cannot be reused.** It
mixes the examples' content hash, the seed, the split and `k` into the digest, so it names an
evaluation rather than a pipeline. No production run has any of those.

**Its pipeline-only ingredients are three public methods**, already composed by
`_measured_configuration` ([runner.py:2824](../../src/simple_agents/evaluation/runner.py#L2824)):
`manifest_nodes()`, `manifest_containers()` and `budget.to_record()`. So the new method assembles
what exists rather than walking the graph again.

**Prompts are not in the node entries.** `_node_entries`
([recording.py:458](../../src/simple_agents/pipeline/recording.py#L458)) returns prompts in a separate slot,
keyed by node id, so a digest over `manifest_nodes()` alone would have missed the exact case this
item exists for. `manifest_prompts()` goes in explicitly.

## 2. Design

The sitting's record was `items/end-user-artifact.md`, and this section is now that file.

**The problem.** `simple-agents check` opens a run directory and a results file
([`conformance.md` §2](../../docs/conformance.md#L79)). A project that accumulates its own output has
a third artifact, and the end user reads that one. In dogfood #4, 22 of the 26 judgements the queue
read had an empty supporting case where a fresh evaluation the same day had 5 of 102, every empty one
written before the prompt version that exists because the field was coming back empty. An evaluation
could not have seen it: a rollout starts from a seeded example and reads nothing the agent wrote
before. `simple-agents check` read 11 of 11 throughout.

**Neither reading was taken whole.** The wide reading, that a conformance suite certifying a
measurement while the shipped artifact is assembled from superseded versions of itself is certifying
the wrong thing, would mean opening whatever storage the project chose. The narrow reading, that this
is the project's business and §10 should say so, leaves the run's largest finding answered by a
sentence. What ships is the identity a project stamps with, the question that makes the artifact
something the builder is asked about, and the §10 row.

**Five parts**, agreed with Thilina on 2026-08-16:

1. `Pipeline.behaviour_fingerprint()`, public and prompt-inclusive.
2. The run's manifest records it. Manifest `0.24` to `0.25`.
3. A required `ship` question, `stored_output`.
4. `docs/shipping.md` §6.
5. A `docs/failure-taxonomy.md` §10 row.

**What was weighed and not taken.** A check that reads the product, which would mean opening
arbitrary project storage, and is named in §10 so its absence is a ruling rather than an oversight.
A declaration surface where the project registers its store with the library, which makes the library
own a reader for every storage a project might pick. And stopping at the question alone, which the
sitting rejected because dogfood #4's hand-stamped constant is the thing a computed identity fixes:
`DF4-D10` is the same class of failure one level down, a declared version that did not move while
the prompt did.

**Three names considered**: `output_identity()`, `produced_by()` and `behaviour_fingerprint()`. The
last was taken on Thilina's approval, because shape against behaviour is the distinction from
`graph_fingerprint` and that docstring already draws it in those terms.

## 3. Build

**`Pipeline.behaviour_fingerprint()`** ([core.py:2070](../../src/simple_agents/pipeline/core.py#L2070), `behaviour_fingerprint`),
a digest over `manifest_nodes()`, `manifest_containers()`, `manifest_prompts()` and
`budget.to_record()`. Strictly wider than `graph_fingerprint()`, which digests a structural subset of
the same node entries.

**The manifest carries it** under `behaviour_fingerprint`, written where `graph_fingerprint` is
written, read back by `Manifest.from_record`. **Manifest `0.24` to `0.25`.**

**`stored_output`**, required at `ship`, in
[`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L578). 34 questions, 24
required. Its scaffold carries the two things that go in the answer where the artifact accumulates:
the stamp, and what re-runs the results a current pipeline did not produce.

**`docs/shipping.md` §6**, and the old §6 became §7. Only §1, §2 and §4 are cited from outside the
document, so the renumbering reaches nothing.

**§10 of the taxonomy** gains the row, naming `stored_output` as what handles it.

**`docs/procedure.md` stage 5** gains three lines, taking it to **1596 words against the 1600
budget**. It fits. P3-8 is what moves the budget.

**2241 tests**, up 9. `docs/run-envelope.md` §2.1 and its version line, `docs/index.md` and
`CHANGELOG.md` follow the field.

**What the build found that the design did not.** Nothing in the mechanism. Two meta-tests caught
what a hand-check would have missed: `test_the_manifest_document_lists_every_key_the_manifest_writes`
failed the moment the field landed, and
`test_the_run_envelope_document_states_the_manifest_version_the_writer_writes` failed on the version
line. Both are the packaging suite doing its job.

## 4. Verification

**Live against Gemini `gemini-3.1-flash-lite`, four real runs**, scripted at
`scratchpad/verify_p3_6.py`. vLLM was not running and Mistral is out of credits.

| What it had to show | Result |
|---|---|
| A real run records the fingerprint, and it equals the pipeline's | `sha256:213998182146fc28` on both, and `format_version` `0.25` |
| It is not the graph fingerprint | Different values on the same manifest |
| An edited prompt moves it and leaves the shape alone | `graph` `sha256:d4b891d2e3bfa040` on both pipelines; `behaviour` moved to `sha256:94e59c769d747f81` |
| The pattern §6 prints actually runs | Two judgements written under the old stamp, the query found both under the new one, the re-run cleared them |

**One thing the live run showed that no unit test would have.** The first schema written for it was
refused by FT-09 at construction, because a yes-or-no verdict has an absent state and the schema had
none. That is the library working, and it is worth recording that the refusal is what a builder meets
first when following §6's example with their own schema.

## 5. Doc consequences

| | |
|---|---|
| `docs/shipping.md` | New §6, "What the end user reads, once it outlives the run". Old §6 is now §7 |
| `docs/failure-taxonomy.md` | A §10 row: whether what the end user reads was produced by the pipeline that was measured |
| `docs/procedure.md` | Stage 5 names the artifact and the stamp. 1596 words |
| `docs/run-envelope.md` | §2.1 gains `behaviour_fingerprint`; the version line reads `0.25` |
| `docs/index.md` | The `shipping.md` row names the new section |
| `CHANGELOG.md` | The manifest bump and the three surfaces |

**No shipped statement stopped being true.** The field is new and §10 gained a row rather than losing
one. `design/trajectory-format-changelog.md` gets nothing: the trajectory did not move.

## 6. Left open

- **`_eval_id` still repeats the ingredients** rather than composing `behaviour_fingerprint()`.
  Rewriting it would change every evaluation directory name for no gain a project can see, so it was
  left. Destination: nothing; recorded here so a later reader does not read the duplication as an
  oversight.
- **`DF4-I06`** (whether the conformance suite's artifact model gains a third artifact) and
  **`DF4-I38`** (a UI built as a display over stored output) unblock from this and are open. Both are
  in [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L53) §3 and neither was decided
  here.
- **Nothing has shipped, so none of this has met a project that accumulates.** [`DF4-Q1`](../runs/dogfood-4/inventory.md#L433)'s standing
  condition applies: every claim here is about behaviour no run of a real project has met, and
  dogfood #5 is where `stored_output` first gets asked of a builder.
