# Build log — What `behaviour_fingerprint` leaves out

`plan.md` §1 P3-18. Started 2026-08-18. Written while building, not afterwards.

## 1. Before any design

Dogfood #4's `DF4-N9` asked whether pipeline versioning is already the ablation feature.
[`findings.md` §8.3](../runs/dogfood-4/findings.md#L1153) answered it naming `graph_fingerprint`,
`_eval_id`, `ablate()` and `compare_variants`, **before `behaviour_fingerprint` shipped on
2026-08-16**, so the library was read again.

- **Three identities exist, each answering a different question.**
  [`graph_fingerprint`](../../src/simple_agents/pipeline/core.py#L2055) is shape, for whether stored
  state can be walked; [`behaviour_fingerprint`](../../src/simple_agents/pipeline/core.py#L2070) is
  what produced a stored result; [`_eval_id`](../../src/simple_agents/evaluation/runner.py#L1162)
  is whether two evaluations measured the same thing.
- **A model arm in a sweep is a `Pipeline` whose node declares `model=`**, so `compare_variants`
  moves `behaviour_fingerprint` and sweeps were never affected by any of this.
- **Three things were outside the stamp**, each recorded in the manifest: the client passed to
  `run(model=)`, every tool's `version` and declared cost, and a consultation reader's model and
  prompt. Measured on two pipelines differing in one tool body: the tool's version moved and the
  fingerprint did not.
- **The omission was never a decision.**
  [`end-user-artifact-build-log.md`](end-user-artifact-build-log.md#L76) §3 lists four
  ingredients as though they were the set, and its §6 does not mention tools.
- **A shipped statement was already false.**
  [`about_the_pipeline`](../../src/simple_agents/conformance/elicitation.py#L68) says the flag
  means the answer describes something `behaviour_fingerprint()` covers, and `backend`, which
  asks which model the project runs against, carries it. This item makes the docstring true
  rather than correcting it.

**Two things checked because the refusal depends on them.** A `Deterministic` node is refused at
construction if any of its tools takes a `ModelHandle`
([`nodes.py`](../../src/simple_agents/nodes/deterministic.py#L29)), and a `ModelReader` holds a required client
of its own, so neither kind reaches the run's client. The predicate is exactly an `LLMNode` or
`AgentNode` declaring no model.

## 2. Design

Decided at dogfood #4's sitting 2, 2026-08-18, with
[`inventory.md` DF4-I34](../runs/dogfood-4/inventory.md#L385) as the record.

Thilina's question is what moved it from the opt-in argument first proposed: *"Why can't the
behaviour fingerprint keep the run model by default? It seems like a weird behaviour to hold only
the node declared models, and builder would not anticipate that."* There is no design reason, only
that the client arrives at `run()` and the fingerprint is a method on the pipeline. Default-correct
is reachable anyway, by refusing to hand out a stamp known to be partial.

**Weighed and not taken:** documenting the hole and leaving the join to the builder, which puts
work back on them in the one place a mechanism was built to remove it; and a second manifest field
covering the model, which makes four identities and splits them on an internal distinction.

**Two calls Thilina took.** A tool's `version` is in the digest, knowing it is source-derived and
moves on a comment, because the case worth catching is a tool that silently returns different data.
And the `_eval_id` half went to `DF4-I07` rather than here.

## 3. Build

**[`behaviour_fingerprint`](../../src/simple_agents/pipeline/core.py#L2070)`(model=None)`** digests the
tool entries and the run client's identity, through
[`_run_client_identity`](../../src/simple_agents/pipeline/core.py#L2111), which reuses
[`_calling_nodes`](../../src/simple_agents/pipeline/core.py#L1957) rather than restating the predicate.
`_new_manifest` passes the run's client. `graph_fingerprint` is untouched.

**What the build found that the design did not know.**

- **The existing refusal is better and fires first.**
  [`_refuse_unserved`](../../src/simple_agents/pipeline/core.py#L2313) already refuses a run whose node
  has no client, at line 471, before `_new_manifest` at 484. So the new raise is unreachable from
  `run()` and the older message still wins where both apply.
- **`Tool.version` is derived by the `@tool` decorator, not by `Tool.__init__`.** A `Tool`
  constructed directly with no `version=` carries `None`, so the stamp cannot see its body, in the
  same way the cassette key cannot. Pre-existing and unchanged here.
- **The fixture generator was computing a `confirmed_against` that did not cover the model**, and
  the new refusal is what found it. `scripts/build_conformance_fixtures.py` now names the replay
  client once and uses it for both the runs and the stamp.
- **`ModelReader` is covered through `tools[].reader`**, so the reader's model and its prompt
  version both move the stamp. Claimed in `CHANGELOG.md` and therefore tested rather than probed.

**Manifest `0.27` to `0.28`.** 134 fixture files regenerated from the committed cassette. 2663
tests to 2670. Surfaces touched: `pipeline.py`, `manifest.py`, `conformance/brief.py`,
`conformance/elicitation.py`, `scripts/build_conformance_fixtures.py`, four documents,
`CHANGELOG.md`, `tests/test_eval_identity_and_failures.py`, `tests/test_packaging.py`.

## 4. Verification

**Live, 2026-08-18**, one `LLMNode` pipeline run against both backends in turn, which is the
development-to-production model swap the item is about. Mistral is out of credits, so the hosted
arm is Gemini.

| | Manifest format | Configured model | Stamp equals the manifest's |
|---|---|---|---|
| vLLM `Qwen/Qwen3-1.7B` | `0.28` | `Qwen/Qwen3-1.7B` | yes |
| Gemini `gemini-3.1-flash-lite` | `0.28` | `gemini-3.1-flash-lite` | yes |
| vLLM again, same pin | `0.28` | `Qwen/Qwen3-1.7B` | yes, and the same value as the first |

**What it shows.** `pipeline.behaviour_fingerprint(model=client)` equals what the run wrote, on
both backends, which is the join `docs/shipping.md` §6 asks a project to make. Swapping the backend
moved `behaviour_fingerprint` and left `graph_fingerprint` identical across all three runs. Running
the same pipeline against the same pin twice stamped one value, so the query a project makes is
stable rather than moving per run.

**The second consequence, checked separately.** `simple-agents check` over a copy of the
`conforming` fixture reports the brief's pipeline answers due for re-reading once the recorded
fingerprint differs from `confirmed_against`, which is the path a model swap now reaches.

## 5. Doc consequences

- **`docs/shipping.md` §6** takes `model=client` in its example and gains a paragraph on passing
  the client the run is passed. This is the recipe the item exists to make correct.
- **`docs/run-envelope.md` §2.1** restates what the field covers and says the run's client is in
  it. The version line reads `0.28`.
- **`docs/procedure.md`** shows the call with its argument, in both places.
- **`CHANGELOG.md`** gains an entry naming the format move.
- **`about_the_pipeline`'s docstring stops being false**, without being edited.

## 6. Left open

- **`_eval_id` still carries tool names and no tool versions**, so two pipelines differing in a
  tool body resolve to one evaluation directory, and `resume_from` mixes their rollouts.
  *(Corrected 2026-08-19: this said the resume happens because
  [`_refuse_a_moved_pipeline`](../../src/simple_agents/evaluation/runner.py#L995) compares
  `graph_fingerprint` alone, which stopped being true on 2026-08-14, four days before this was
  written. `d13e46e` added `_refuse_a_moved_configuration`, which compares the measured
  configuration field by field; it carries tool names, so a body edit produces no difference and
  the resume is allowed.)* Destination: `P3-20` stage 1, scheduled 2026-08-19,
  [`build-logs/evaluation-identity-build-log.md`](../build-logs/evaluation-identity-build-log.md#L1).
- **A `Deterministic` node's body moves nothing**, this stamp included, so §5's claim that the
  method covers everything deciding what the pipeline produces was already false when it was
  written. This item did not look at the node kind that makes no model call. Measured 2026-08-19,
  and the three shipped statements are corrected under `DF4-X10`. Destination: `P3-20` stage 1,
  [`build-logs/evaluation-identity-build-log.md`](../build-logs/evaluation-identity-build-log.md#L1).
- **A tool constructed as `Tool(...)` with no `version=` is invisible to the stamp**, as it is to
  the cassette key. Destination: `nothing`; recorded so a later reader does not read it as an
  oversight in this item.
- **Nothing has met a project that accumulates.** `P3-6`'s own note still applies: every claim
  about what a stale row costs is about behaviour no real project has met, and dogfood #5 is where
  `stored_output` is first asked of a builder. Destination: `nothing`.
