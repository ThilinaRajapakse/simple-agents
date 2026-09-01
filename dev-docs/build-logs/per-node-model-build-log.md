# Build log — per-node model selection (`archive/plan-history.md` §1.3)

Written while building, not afterwards. Newest section last.

---

## 1. What the code actually does today, read 2026-08-10

Read before designing anything, because `archive/plan-history.md` §1.3 is a summary written at the item 8e
sitting and the machine is the authority.

### 1.1 The four claims in the handoff brief, verified

| Claim | Verdict |
|---|---|
| `Pipeline.run(model=...)` threads one client through about six signatures | **Understated: ten** |
| The manifest records one `models.configured` | **True.** One optional dict, written from the client's identity |
| FT-14 reads `models.configured` as a single object | **True.** One identifier, one revision, one verdict |
| `model_call` records already carry the identity per call | **True, and the serving model as well.** No trajectory format bump is needed |
| The cassette key already carries model identity | **True.** Built at the call site, so a client arriving per node keys per node with no change |
| Item 8e left the stream flag on the node and the usage waiver on the adapter | **True.** Both shipped adapters carry the waiver |

Ten signatures in `pipeline.py` carry the client, starting at
[pipeline.py `Pipeline.run`](../../src/simple_agents/pipeline/core.py#L491): run, resume,
_restored_manifest, _verify_against, _drive, execute, _walk, _attempt, _new_manifest and
_refuse_unstreamable.

The pin is written from `model.identity().to_manifest()` into one field on
[manifest.py `Manifest`](../../src/simple_agents/records/manifest.py#L56), read as one object by
[checks.py `ft_14`](../../src/simple_agents/conformance/checks.py#L394), and compared against
the resuming client on a resume.

Each call already records `backend`, `request_model`, `model_revision` and `response_model`, on
[trajectory.py `ModelCallRecord`](../../src/simple_agents/records/trajectory.py#L300). The key is built
from the client passed to the call, in
[context.py `RunContext.call_model`](../../src/simple_agents/context.py#L792). The waiver is a
constructor flag on [mistral.py `MistralClient`](../../src/simple_agents/adapters/mistral.py#L54)
and on [vllm.py `VLLMClient`](../../src/simple_agents/adapters/vllm.py#L65).

**Attribution is already possible without a format bump.** A `model_call` record has no node id;
it carries `parent_id`, and the walk from a call to its node already exists for per-node metrics
in [per_node.py `_owners`](../../src/simple_agents/evaluation/per_node.py#L839), including the
two-hop case where a tool made the call.

### 1.2 What the plan does not name, found by reading

**Two consequences past the three §1.3 lists (manifest, per-node metrics, streaming).**

**(a) Cost is derived under one basis for the whole run, and nothing checks the basis against
the call.** [cost.py `total_cost`](../../src/simple_agents/cost.py#L524) applies
`envelope.cost_basis` to every `model_call` record.
[`_price`](../../src/simple_agents/cost.py#L585) reads `tokens` and
[`_compute`](../../src/simple_agents/cost.py#L692) reads duration and
`concurrent_requests`; neither reads `backend` or `request_model`. Per-token rates are a
property of one model, so two models under one `PriceBasis` price one of them at the other's
rates, and the figure is wrong with nothing saying so. It reaches `totals.cost`, `results`,
`compare()`, and `max_cost` enforcement, which is a budget bound to a wrong number.

*This is also a hole that exists today*, reachable by misconfiguration rather than by accident:
a `VLLMClient` run under a `PriceBasis` prices device-time calls on hosted token rates and
returns a plausible number.

**(b) Variant comparison claims a model swap it cannot express.**
[variants.py](../../src/simple_agents/evaluation/variants.py#L1) opens "Adding a tool, removing
one, changing a prompt, **swapping a model** and rewiring the graph are the same operation with
a different variant". `compare_variants` takes one `model=` for every arm and
`plan_variant` compares `manifest_nodes()`, which records nothing about the model. So a model
swap is the one listed operation that is not expressible today. Declaring the model on the node
makes the docstring true.

### 1.3 What per-node models would break, enumerated from the call sites

- [`_verify_against`](../../src/simple_agents/pipeline/core.py#L858) compares
  `models.configured` against the resuming client and reports `model` in `changed`.
- [`_refuse_unstreamable`](../../src/simple_agents/pipeline/core.py#L858) checks the run-level
  client for `stream` and for a reasoning sink.
- [`_stream_waivers`](../../src/simple_agents/pipeline/recording.py#L388) walks one client's wrappers.
- [`EvalSuite._eval_id`](../../src/simple_agents/evaluation/runner.py#L1162) hashes one identity,
  so two evaluations differing only in a node's model would write into one directory.
- [`_pace_for`](../../src/simple_agents/evaluation/runner.py#L2862) paces one client.
- [`_REQUEST_FIELDS`](../../src/simple_agents/evaluation/variants.py#L743) decides which node
  entries taint a replay.
- [`LLMNode.execute`](../../src/simple_agents/nodes/llm.py#L170) and `AgentNode.execute` raise
  `CallerFacingError` for a missing client *at the node*, after earlier nodes have spent.

**`graph_fingerprint` is unaffected**:
[`_STRUCTURAL`](../../src/simple_agents/pipeline/recording.py#L106) is seven keys and a new node-entry
field is outside it, so a changed model stays a waivable resume difference rather than an
unwaivable shape change, which is what the run-level model change already is.

**`Deterministic` takes no model and must not gain one.** It refuses a tool carrying a
`ModelHandle` already ([`Deterministic`](../../src/simple_agents/nodes/deterministic.py#L29)), on the grounds that
FT-07 reads a `deterministic` record as one that did not sample.

---

## 2. Decisions taken, 2026-08-10

Put to Thilina with the code read first, and settled in that conversation.

| # | Decision | Ruling |
|---|---|---|
| D1 | The model is declared on the node, as `model=`, and `Pipeline.run(model=...)` is the default for a node that declares none | Approved |
| D2 | Two levels of resolution, node then run. An enclosing `Pipeline` takes no `model=` | Approved |
| D3 | `nodes[].model` records what the node declared, `null` where it takes the run's. `models.configured` unchanged | Approved |
| D4 | FT-14 checks every identity that could serve a call, one finding per offending identity, with a `<where>` placeholder added to the shipped message | Approved |
| D5 | The cost basis becomes per model, plus two pre-flight refusals | Approved |

**Why the client and not a role name (D1).** `plan_variant` and `ablate` compare pipelines, and
`_REQUEST_FIELDS` decides which nodes replay off the baseline cassette. A client on the node
makes a model swap an ordinary variant that the existing machinery sees. A role name resolved at
run time is invisible to a function that takes two pipelines and no run, so a sweep would report
a node as replayed whose requests had changed.

**Why two levels and not three (D2).** The library's own rebuilds are the argument.
`_replacing` and `_without` reconstruct a pipeline from `declared_nodes()`, which flattens: the
container object does not survive, so a `model=` declared on it has nowhere to be carried to.
Preserving it would mean pushing it onto every node inside, in a function whose job is to
rebuild one node. A client on the node object is carried by construction, which is
`simple-agents.md` §10's fail-closed rule: what gets enumerated is what is skipped, not what is
covered. The second argument is that `budget=` on that same constructor **composes** while a
`model=` would **override**.

**Why the declaration and not the resolution (D3).** `manifest_nodes()` is called with no client
in scope, by the resume check, by `plan_variant` and by the evaluation's config block. A
resolved value cannot be computed there, so recording one would mean the same fact written by
two code paths, and the one that drifts is the one no test compares.

## 3. What landed first: the node surface and the manifest

- `model=` on `LLMNode` and `AgentNode`, held as `self.model`.
- `nodes.model_for(node, default)`, the one place resolution happens. Read by both nodes'
  `execute` and by the pipeline's pre-flight checks, so what a check reasons about is the client
  the call is made against.
- `Pipeline._calling_nodes(model)`, every node of kind `llm` or `agent` with its resolved client.
- `Pipeline._refuse_unserved`, a new pre-flight refusal for a calling node with no client from
  either source. This used to raise inside the node when it was reached, by which time the nodes
  before it had spent. No test asserted the old timing.
- `_refuse_unstreamable` now iterates the calling nodes rather than reading the run's client, so
  the refusal names the node and the client its calls go to.
- `_stream_waivers` reads every client the run can reach, deduplicated by class.
- `nodes[].model` in the manifest, and `model.<node_id>` in the resume waiver set beside
  `prompts.<node_id>` and `route.<node_id>`.
- `MANIFEST_FORMAT_VERSION` 0.16 to 0.17.

**One shipped sentence was trimmed to make room**, because `LLMNode`'s docstring sat at exactly
the 20-line prose budget and the check counts blank lines. Was: "With an `output_schema` set the
pieces are fragments of JSON rather than prose, since that is what the model emits." Now: the
same without the trailing clause. The `model=` note folded into the paragraph that already holds
`output_schema` and `extra`, so it costs one line rather than a paragraph. Surfaced to Thilina
rather than left in the diff.

**1441 tests pass; `prose_check` and `check_citations` are clean.** Two test expectations gained
`"model": None`, both of which assert a full node entry.

## 4. FT-14, and the failure message that had to change

The check now resolves per node: for each `nodes[]` entry of kind `llm` or `agent`, the
identity is `entry.model` where the node declared one and `models.configured` where it did not.
Identities are deduplicated, so a run where nothing overrides checks exactly one and reads as it
did before. A manifest with no `nodes` array falls back to the configured pin alone, which is
what a project writing its own manifest produces.

**The shipped message gained a second placeholder**, on Thilina's approval, because the whole
point of the item is that the model is a per-node property and a message naming an unpinned
model has to say where it is:

> The manifest records model alias `<alias>` on `<where>` rather than a pinned version. …

`<where>` renders as the node ids the identity serves, or `every node` for a run-level client.
The alternative considered was folding the node into the alias string, which needs no doc edit
and leaves the reader guessing whether `draft:` is part of the identifier.

**Two conditions moved.** The old "this run made no model call" pass was `not configured and not
observed`, which would have wrongly passed a run whose nodes all declare their own client and
whose `configured` is therefore `null`. And a passing run with more than one model now says so
in `detail`, naming each model and the nodes it served.

## 5. Cost, and a promise that had to be narrowed

**What was approved (D5) was two refusals, one of them wider than what shipped.** The approved
rule 1 was "a basis of the wrong kind for the backend is refused", which was also going to close
a hole that exists today: a `VLLMClient` under a `PriceBasis` prices device-time calls at hosted
token rates and returns a plausible number.

**Measured before writing it: that rule refuses five of the library's own test files.**
`FakeModelClient` reports `backend="self_hosted"`, and `tests/test_eval_runner.py`,
`test_labelling_pass.py`, `test_adapter_integration.py`, `test_tool_spend.py` and
`test_run_envelope.py` all pair it with a `PriceBasis`. That is not a test-fixture problem. A
builder testing their pipeline offline against their production `PriceBasis` is doing something
reasonable, and refusing them teaches nothing: the cost of a run against a fake client is
meaningless whatever basis prices it.

**So rule 1 narrowed to the case this item creates**: a single basis where the run's calling
nodes span **more than one backend**. That cannot be wrong, needs no fixture changes, and is
exactly the ambiguity per-node models introduce. Rule 2 is unchanged: a single `PriceBasis`
where the run calls more than one model. A single `ComputeBasis` over several self-hosted models
is deliberately allowed, since a device rate belongs to the deployment.

**The pre-existing single-backend mismatch is still open**, and is the one thing promised at D5
that did not land. It needs its own decision, because the honest fix is either refusing
`FakeModelClient` under a price basis or giving that client a way to say it stands in for a
hosted model.

## 6. The live recording, which is what a fake client cannot show

`scripts/record_backend_cassettes.py mixed` records a two-node pipeline with `reduce` on a local
`Qwen/Qwen3-1.7B` and `answer` on `mistral-small-2603`, under one basis per model. Recorded
2026-08-10 against both backends at once. `tests/test_adapter_integration.py`
`TestTwoBackendsInOneRun` replays it.

What the recording establishes that 27 fake-client tests could not:

- **The two adapters coexist in one run.** Both calls replay from one cassette, so the keys
  separated them rather than colliding.
- **The run needs no client of its own.** `models.configured` is `null` and both nodes declare
  their own, which is the case that could not be expressed before this item.
- **One total across two bases.** The hosted call priced on tokens plus the self-hosted call
  priced on device time, in one currency: `4.30e-05 USD`.
- **A correction to an assumption carried from the older vLLM recording.** The first version of
  the cost assertion expected `is_upper_bound` to be true, copying the reasoning from
  `TestVLLM`. The server reported one request in flight, so the compute half is a measurement
  and the total carries no bound. `report_concurrency` defaults to true, which the older
  recording predates.

**A model-behaviour finding, recorded because it is the sort of thing a dogfood catches.** The
first recording came back with `mistral-small-2603` choosing the `unknown` branch and writing
"the facts mention the weight of the Aurora 3 Pro as 1.4 kg, which directly answers the
question" as the *reason for absence*. The 1.7B had extracted the fact correctly and passed it
on. The prompt said "Report `unknown` if they do not say", and the model read that as an
instruction about what to report rather than a condition. Re-recorded with "Report `unknown`
only when the facts do not contain the answer; where they do, give it", which answered `1.4 kg`.
Nothing in the library was wrong, and no schema check catches it: absence was returned in the
declared shape with a reason string that happens to contain the answer.

## 7. What is built, and what the suite says

**1475 tests pass, `prose_check` and `check_citations` clean.** 34 tests are new: 27 in
`tests/test_per_node_models.py` and 7 replaying the mixed recording.

Shipped surfaces changed: `docs/pipeline.md` §2.4 (new), `docs/run-envelope.md` §2.2, §2.6 and
§4.1, `docs/model-clients.md` §1, `docs/conformance.md` §2.3, `docs/failure-taxonomy.md` FT-14,
`docs/evaluation.md` §10, and `CHANGELOG.md`.
