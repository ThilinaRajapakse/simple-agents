# Build log — Working the ratchet down

`plan.md` §1 P3-64. Started 2026-08-31, and built the same day: the lint gate, the record
machinery, and eight sittings over the recorded units. The first two are logged in the
sections below beside the sittings, since one item produced all of it.

## 1. Before any design

- The worklist as it stood: [`scripts/shape_baseline.json`](../../scripts/shape_baseline.json#L1)
  (`recorded`) held 144 units at the item's opening and 145 after the `ruff format` pass, which
  pushed six units over a threshold and dropped five. Verified by diffing the baseline against
  `963e19e^`.
- The item record's per-module sitting list was checked against the tree and found stale:
  `view/findings.py`, listed second, held 2 recorded units, while `pipeline/core.py` held 12
  and `nodes/agent.py` 7 and neither was listed.
- [`pre-release-refactor-build-log.md`](pre-release-refactor-build-log.md#L46) (`Kept big
  deliberately`) already carried judgements on `AgentNode`, the executor quartet, `EvalSuite`,
  `RunContext` and `tools.py`; the sittings held every one of them on a fresh reading.

## 2. Design

The item's record was [`items/ratchet-down.md`](../archive/ratchet-down.md#L1), now in
`archive/`; this log carries its content. Thilina's origin question, 2026-08-31, at the P3-63
close: *"Is there a plan for refactoring the code inside the actual files? To ratchet down
with the ratchet? Making sure code smells are gone, proper SE principles are followed w.r.t.
things like separation of concerns, abstraction, decoupling, deduping, etc. etc.? And making
sure the classes and functions aren't bloated and also follow SE principles?"* He set the
order (lint gate first, then the sittings) and on 2026-08-31 delegated the per-sitting
decisions: *"just go ahead and do all of it"*, with only the genuinely undecidable coming
back.

**Decided at this item:**

- **The lint gate** (commits `963e19e`, `4ac2363`): `ruff check` with `F`, `B`, `A`, `C4`,
  `PLE` at zero tolerance, 129 findings fixed and none baselined; `ruff format` over 212
  files, proven AST-identical apart from docstring indentation; both gated by
  [`tests/test_lint.py`](../../tests/test_lint.py#L1). Fixture projects excluded because
  their source feeds recorded digests; four Gemini and vLLM cassettes re-recorded because the
  lexical tool's digest moved.
- **The record machinery** (commit `b7883e2`): `check_citations` gained `dead-md-link` and
  `unnamed-anchor`, `prose_check` gained `unknown_module` and `unknown_role_target`, each
  with a firing test.
- **Eight sittings by subsystem** replaced the stale per-module list, because the smells no
  size check sees cross module lines inside a subsystem: sitting 1 `evaluation/runner.py`,
  2 the evaluation readers, 3 `pipeline/`, 4 `context.py` and `runtime/`, 5 `nodes/`,
  6 `conformance/`, 7 records and wire, 8 `builtins/`, `view/`, `cli/`.
- **A keep's reason lives in the baseline.** `shape_check`'s `write_baseline` carries a
  `reasons` map keyed like `recorded`: `--update` keeps a reason whose unit is still recorded
  and drops one whose unit has gone, `--list` prints them, and
  [`tests/test_shape.py`](../../tests/test_shape.py#L162) (`TestKeepReasons`,
  `TestTheWorklistIsWorked`) fires the mechanism and the end state both ways.
- **Weighed and not taken:** decomposing record constructors, refusal messages and check
  catalogues to duck a line threshold. Their length is the record's width, the message's
  prose or the taxonomy's size, and splitting them scatters one subject. The estimate in the
  item record, 30 to 40 keeps of 145, assumed most units would decompose; the reading found
  the opposite, and §6 carries the divergence as an open judgement for Thilina.
- **Not touched on a stated constraint:** the bodies of shipped builtins. A tool's source
  digest is pinned in recorded cassettes, and the `mistral`, `agent` and `graph-loop` arms
  cannot be re-recorded, so a refactor there costs recordings the project cannot make again.

## 3. Build

No format moves. 4,083 → 4,102 tests. One commit per sitting.

- **Sitting 1, `evaluation/runner.py`** (`90f88eb`). Three concerns left the module:
  the declaration comparisons to a new [`declared.py`](../../src/simple_agents/evaluation/declared.py#L1),
  `prompt_differences` and its helpers to a new
  [`prompts_sent.py`](../../src/simple_agents/evaluation/prompts_sent.py#L21), `progress_of`
  to `progress.py` beside `RolloutProgress`, and the rollout-record classifiers
  (`_outcome_for`, `_left_out_of` and kin) to `outcomes.py` beside `classify`. Three
  duplications became shared code: `run` and `rescore`'s identical figures block is
  `_figures`, `_config` and `_rescored_config`'s twenty shared keys are `_declared_config`
  (so a key added to one can no longer be missing from the other), and `_rollout`'s three
  failure constructions are `_failed_rollout`. Two de facto re-exports fixed
  (`rollouts_under`, `RolloutProgress` reached through `runner`). Module 2583 → 2277
  recorded lines; `run` 205 → 129; `_config` left the list.
- **Sitting 2, the evaluation readers** (`7a9c390`). `node_scores` moved from `compare.py`
  to `per_node.py` and `node_rates` now reads through it, so the comparison and the rates
  provably read scores identically. `config_differences` and its walk moved to
  `declared.py`. `compare.py` gained `_all_scores` for the four score-merges and binds
  `_change`'s fixed kwargs once per comparison. `EvalResults.report` became six section
  methods. `against_baseline` and `compare.py`'s module left the list.
- **Sitting 3, `pipeline/`** (`45dc4f8`). The six constructor refusals left
  `Pipeline.__init__` for [`_refuse_non_nodes`](../../src/simple_agents/pipeline/preflight.py#L483) and kin, where P3-63 put the other validators; `__init__` left the
  list. `_verify_against`'s shape tier is `_refuse_a_changed_shape`. `_attempt`'s four
  record emissions share `_emit_unfinished`, **which fixed a defect the reading found**: the
  two error paths omitted `parent_id`, so a node that failed inside a delegated pipeline
  recorded no link to the delegation record, while a successful or suspended one did.
- **Sitting 4, `context.py` and `runtime/`** (`2635666`). `call_embedding` and
  `call_rerank`'s identical cassette walk is `_call_recorded`; `call_model` keeps its own
  body for streaming and the pool slot, and says so. `_call_model` in `runtime/calls.py`
  kept whole: its ordering is load-bearing and each stage's comment states the constraint
  that fixes it.
- **Sitting 5, `nodes/`** (`450c42b`). `AgentNode.__init__`'s tool and delegation namespace
  refusals became `_declare_dispatch_names`, following the `_declare_` idiom the constructor
  already used.
- **Sittings 6 to 8** (`741bc98`, `643e79e`, and the close): judgement sittings. The
  conformance catalogue, the records and wire, and the builder surfaces read for smells and
  their keeps reasoned; no decomposition earned its cost there.

**End state.** 141 units recorded, every one carrying a reason;
`TestTheWorklistIsWorked` holds it from here. The reasons fall into named genres: a record's
width, a message's prose, a check's rule, a lifecycle whose order is load-bearing, a loop
whose state splitting would distribute, and a shipped tool's digest constraint.

## 4. Verification

- Full suite green after every sitting; 4,102 tests at the close.
- **Live Gemini evaluation after sittings 1 and 2** (`gemini-3.1-flash-lite`, paid tier):
  three examples × k=2 through `EvalSuite.run` with a fresh recording, six rollouts, priced
  at 0.0026 USD. `progress_of` and `prompt_differences` read the live directory, and
  `rescore` over it reproduced the run's metrics exactly.
- **Live Gemini pipeline run after sitting 3**, through the reworked executor: completed,
  priced, `outcome: completed` on the manifest.
- Sitting 4's changed paths (`call_embedding`, `call_rerank`) are exercised by the recorded
  vLLM cassette tests in the suite; the cassette semantics are byte-identical by
  construction and the 174 cassette-area tests passed.
- The conformance fixtures were regenerated once (`scripts/build_conformance_fixtures.py`)
  after sitting 1's config-record unification moved key order in the results files.
- **Two full reverification cycles**, each a whole-item code read, a code-against-docs
  crosscheck, a unit-test coverage read, the full suite, and a live Gemini run.
  **Cycle 1 found one issue**: the `parent_id` fix had no firing test. Writing it also
  surfaced a pre-existing shape the test documents: a parent record is written after its
  children, so a run that dies inside a delegated pipeline never writes the delegation
  record, and the child's `parent_id` names an id the file does not hold; the link itself is
  what the fix guarantees. Cycle 1's live pass recorded a fresh Gemini evaluation, replayed
  it, and rescored it, all three reporting identical metrics. **Cycle 2 found nothing**:
  every transplanted function proved AST-identical to its pre-move original
  (`progress_of` aside, whose difference is the deliberate `_finished_totals` extraction),
  the docs describe the config block by content and not order, 4,103 tests and all four
  checks clean, and a live `AgentNode` run against Gemini completed with its tool calls
  recorded.
- **A third pass, on challenge, differenced the old code against the new directly.** A
  worktree at the pre-item commit rendered every touched reader on identical inputs:
  `report()` plain and grouped, `compare().to_record()`, `against_baseline` over a results
  file carrying a baseline and five criteria, `node_metrics`, `progress_of`,
  `prompt_differences` and `unfinished_work`, all byte-identical; and `node_rates` on 36
  randomized synthetic rollouts (unreached nodes, unlabelled nodes, partial metric coverage,
  shuffled order) produced identical records, seeded intervals included. It also found the
  soft spots in the earlier verification and closed them: `call_embedding` and `call_rerank`
  had no direct test at all (they are reached only through the retrieval handle), and now
  have a record, replay, miss and changed-identity round trip in
  [`tests/test_recorded_calls.py`](../../tests/test_recorded_calls.py#L1); and two of the
  moved dispatch refusals (a non-`Delegation` entry, two delegations sharing a name) had no
  firing test, a gap that predates the move and is closed in `tests/test_delegation.py`.
  4,110 tests.
- **The one live path the third pass still lacked ran on 2026-09-01, on request**: semantic
  search with real weights. A `Deterministic` node called `document_search` over an index
  built with `SentenceTransformerEmbeddings` and a `CrossEncoderRerank`, recording to a
  cassette: the query embed and the rerank ran the real models on CPU, both landed as
  `model_call` records parented to the tool call, and the answer was right. Replaying the
  same run served both calls from the file (`replayed: true`), invoked neither model, and
  returned the identical answer. Every recorded-call kind has now run live under the shared
  path.

## 5. Doc consequences

`CHANGELOG.md` gained the 2026-08-31 refactor entry: the `parent_id` fix, the config key
order, and the moved deep imports (`evaluation.progress`, `evaluation.prompts_sent`), with
the package-level surface unchanged. `check_citations --fix` retargeted about 70 anchors
that moved with the code across the sittings, and four citations whose targets left
`runner.py` were repointed by hand. No statement in `docs/` stopped being true.

## 6. Left open

- **The keep count diverged from the recorded estimate**: 141 keeps against the estimated
  30 to 40. The judgement is in §2 (weighed and not taken); whether any genre of keep
  should be decomposed anyway is Thilina's call at the build report, and the reasons in the
  baseline are the worklist for that conversation. Destination: the P3-64 build report to
  Thilina; nothing is queued.
- Nothing else. `P3-31`, going public, is unblocked:
  [`plan.md` §1](../plan.md#L27).
