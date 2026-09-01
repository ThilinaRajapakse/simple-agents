# Build log — The pre-release refactor

`plan.md` §1 P3-63. Started 2026-08-31, built 2026-08-31.

## 1. Before any design

The 2026-08-17 measurement in
[`design/module-structure.md`](../design/module-structure.md#L1) was re-measured before
anything moved: [`nodes.py`] had grown 3,349 → 4,613 lines and [`pipeline.py`] 2,922 → 4,183
while `P3-33` to `P3-62` landed, with the `Pipeline` class at 2,686 lines across 65 methods and
`AgentNode._one` at 430. The clusters were the same clusters at larger sizes, so the doc's
argument stood and its tables kept their dated figures. Two claims did not survive checking:
the plan row's "the baseline only shrinks" (123 units at writing, 145 at re-measurement,
because later items legitimately added units with `--update`), and `P3-33`'s hand-added
`AXIS_FIELDS` baseline note (no such entry remained; the dead import itself did, in `nodes.py`,
and left at stage 1). The citation posture was measured too: `check_citations` was clean at the
pre-refactor commit, so every problem it reported afterwards was owed to the move.

## 2. Design

Decided at the 2026-08-31 scoping sitting, Thilina approving the hierarchy and the four
answers; this section carries the item record's design, so that file leaves `items/`.

**Where it came from.** Accepted 2026-08-17 as *"the two largest modules carry subsystems that
settled where they were first called"*, raised by Thilina, who put a refactor before release,
and widened 2026-08-25 from the two modules to the refactor generally. His verbatim list:
follow good SE discipline, break up massive files, proper module hierarchy, decompose large
units, marked not exhaustive.

**The hierarchy.** The public surface through `__init__.py` unchanged;
`simple_agents.nodes` and `simple_agents.pipeline` stay importable as packages; import
direction `pipeline → nodes → runtime → formats`.

- `nodes/`: `base.py`, `llm.py`, `agent.py`, `deterministic.py`, `delegation.py`, `fanout.py`.
- `runtime/` (new): `calls.py`, `tooling.py`, `metering.py`, `handles.py`, `consultation.py`,
  `suspending.py`, `budgets.py`.
- `pipeline/`: `core.py`, `edges.py`, `events.py`, `preflight.py`, `recording.py`.

**The four questions from
[`design/module-structure.md`](../design/module-structure.md#L121) (`What was undecided`),
answered:** tool execution, model-call plumbing and cost metering are three modules; the
manifest writer leaves `Pipeline` entirely; the pre-flight validators are one module; the
two-way import is resolved by the split, with `delegation.py` keeping the one surviving
deferred import.

**Kept big deliberately:** `AgentNode` (the interpreter loop) and the executor quartet in
`pipeline/core.py`, recorded in the baseline. `EvalSuite` and `RunContext` were examined under
the same test and kept whole: each is one stateful orchestrator, and decomposing one
distributes its state. `tools.py` was kept whole on a different ground: 27 constructs, the
largest 183 lines, one subject whose breadth is the module's size.

**Weighed and not taken:** moving `_ToolOutcome` into `tooling.py` (its natural name), because
`tooling → consultation → tooling` would then be an import cycle; it lives in `metering.py`
with `_refuse_bounded_cost` and `_cost_record`, all three being about what a call spends or
declares. Splitting `AgentNode._one` and `EvalSuite.run` was declined for the recorded reason.

## 3. Build

Six stages, each committed with the suite green; no format moved; 4,072 → 4,083 tests.

- **Stage 1** (`e0fa256`, `cf6363b`, `d4bdf26`): `runtime/` extracted, seven modules. The
  extraction was scripted: an AST splitter lifts named top-level constructs with their
  decorators and leading comments, computes each target's import block from the names the
  moved code uses, and reports any moved code still referencing what stays, which is how the
  boundary errors were caught before they compiled. `_Suspending`, `_refuse_over_budget` and
  `_spent_since` left `pipeline.py`; the `_suspending` lazy-import helper is deleted.
- **Stage 2** (`270eb03`): `nodes.py` became `nodes/`. The analysis moved the whole failure
  cluster (`_Failures`, `_STOPS_THE_RUN`, `_ends_the_run`, `_refuse_one_failure_wearing_a_tolerance`,
  `_kept_for`, `_sequence_for`, `_RAN_OUT`) into `fanout.py`, its only caller, which dissolved
  a `base ↔ fanout` cycle the first cut had. The repo's own packaging rule (a package
  `__init__` exports everything it imports) pushed the private reach-ins to direct submodule
  imports and put `NotBuilt`, already public at the top level, into the package `__all__`.
- **Stage 3a** (`c2b6535`): `pipeline.py` became `pipeline/`. **One module beyond the agreed
  five**: `answering.py`, the shelf-answer path, a coherent cluster postdating the 2026-08-17
  measurement that fit none of the agreed files; flagged to Thilina in the build report, and
  he proceeded without objection. `Pipeline` is used at runtime only in `isinstance` checks
  for a nested pipeline standing as a node, so `events.py` and `recording.py` reach it by a
  deferred body import on the `delegation.py` pattern.
- **Stage 3b** (`06b6711`): ten validator methods and the manifest-writer trio
  (`_node_entries`, `_new_manifest`, `_close_manifest`) left the class as functions taking the
  pipeline. The mechanical `self → pipeline` rename hit two things the script had to be taught
  about: an inner loop variable already named `pipeline` (renamed `inner` first), and the
  literal `self` inside error-message strings ("`def stream(self, …)`", "self-hosted"),
  restored by hand.
- **Stage 4** (`381faa4`): the two near-identical `_captured(...)` argument blocks and the
  three identical spend-accumulation blocks in `AgentNode._one` became two closures over the
  loop's state, `captured_here` and `fold_spend`; the fourth accumulation site is the
  model-call variant and stays. A dead `identity = client.identity()` line and two stale lazy
  imports left with it. `shape_check` came back clean with `_one` under its recorded size.
- **Phase 2** (`8462a1b`): [`conformance/recorded.py`](../../src/simple_agents/conformance/recorded.py#L26)
  (`RecordedNodes`) is the one way the recorded graph is read; `_serving_models`,
  `_answering_nodes` and `_planned_from_the_manifest` build on it, and `_last_units`,
  `_feeding` and `_calls_a_model` moved into it. `_reported_metrics` and
  `_consultations_in_the_results` share `_result_nodes`. `_unseeded` reads the record stream,
  and there is nothing shared to collect; that judgement closes the build-log entry that
  assigned the six here. `runner.py` shed five dead imports, one of which
  (`evaluation_dir`) turned out to be a de facto re-export that `evaluation/__init__.py` now
  takes from `..envelope`, its definition site.

**Changed knowingly:** `RecordedNodes` skips a malformed (non-mapping) node or container entry
where `_planned_from_the_manifest` and `_answering_nodes`'s `children` build previously raised
on one. Every moved unit was verified as a same-key move in `scripts/shape_baseline.json`
(145 before, 145 after at every stage), and the moves retired the `nodes.py` and `pipeline.py`
module entries, leaving `nodes/agent.py`'s as the deliberate keep.

**The citations followed the code** (`aede6e0`, `33cb71e`): the move broke 307, all owed to it.
`check_citations --fix` repaired the within-file drift; a migration script mapped the rest
through the pre-refactor construct table (old line → construct → new module and line,
offset-preserving); 36 labels were renamed to the files their anchors now name; the last eight
were retargeted by hand. `check_citations` is clean.

## 4. Verification

**Two live runs, one pipeline** (`Deterministic → LLMNode → AgentNode` with a `READ_ONLY`
tool): against Gemini (`gemini-3.1-flash-lite`) after stage 4, and against a local vLLM
(`Qwen/Qwen3-1.7B`, port 8001, tool parser `hermes`, `max_output_tokens=4000` for the
reasoning budget) after phase 2. Both completed with the tool called and the schema validated,
exercising the moved calls, tooling, metering, handles, budgets, suspension seam, preflight
and recording end to end. The full suite ran after every stage, 4,083 at close with nothing
deselected, and the adapter cassettes (vLLM, Mistral, Gemini arms) replayed unchanged, since
the refactor moves code and no behaviour.

What the stages found that the suite alone did not: two function-body relative imports one
level too shallow after a move (found by the first live-path test run), an intra-module call
still going through the removed method (`pipeline._node_entries()` inside `_new_manifest`),
the in-string `self` renames above, and the `evaluation_dir` re-export.

## Addendum, 2026-08-31: `records/`

Raised by Thilina after the close ("shouldn't the loose files in `src/` have a proper home?")
and decided the same day from three options: keep the top level flat, group the versioned
record formats alone, or group everything. He chose the middle one. The membership test is
what makes it decidable: **a file a project holds on disk that our format changes can break.**

[`records/`](../../src/simple_agents/records/__init__.py#L1) now holds `trajectory.py`,
`manifest.py`, `cassette.py`, `suspension.py`, `shelf.py`, `conversation.py` and
`comments.py`, about 4,550 lines. The results-file format stays in `evaluation/results.py`
with its writer, and the package docstring says so. The public surface through `__init__.py`
is unchanged, `docs/` deep-imports none of the seven (measured before deciding), and the nine
baseline entries moved 1:1. The move surfaced one real shrink: `_serving_models` left the
baseline, 145 → 144, having gone under threshold at phase 2. Two `:mod:`/`:class:` docstring
cross-references were the only in-source prose to follow. Suite 4,084 green; `check_citations`
clean after retargeting 37 files.

The fix to `failure-taxonomy.md`'s staged-entries sentence is committed now (`e0a6213`), as
exactly its own hunk, Thilina's surrounding audit edits left in his working tree.

**Same day, the root files were argued one by one on Thilina's challenge**, and 23 of 24 held:
public contract vocabulary, a seam above its implementations, layering that forbids any
package, or no sibling. The one that did not, `reporting.py`, moved into a new `cli/` package
beside the command module (`cli/main.py`, entry point now `simple_agents.cli.main:_entry_point`,
`python -m simple_agents.cli` kept by `__main__.py`). The move surfaced one real defect:
`_skill_source` located the shipped procedure by `__file__`-relative hops that broke one level
deeper, caught by `tests/test_procedure.py` and fixed by anchoring on the package directory.
Suite 4,087 green; the three baseline keys moved 1:1.

## 5. Doc consequences

`docs/` is untouched by the refactor: no shipped document names the old module files, and a
project's imports are unchanged, so `CHANGELOG.md` gains nothing. One `docs/` fix rode along
on Thilina's request: his in-flight writing-audit edit had merged FT-40, FT-41 and FT-42 into
`failure-taxonomy.md`'s staged-entries claim sentence, whose id set a test compares against
the parsed taxonomy; the FT-4x sentence is its own paragraph now, saying they carry no stage
field; committed as `e0a6213` on his call, one hunk, his surrounding audit edits untouched. In `dev-docs`,
`design/module-structure.md` carries the re-measurement, the four answers, and a dated note
that the two-way-import cost ended at stage 1.

## 6. Left open

- **The baseline is the standing worklist and the recorded units stay recorded**: `EvalSuite`
  and its methods, `RunContext`, `AgentNode` and `_one`, the executor quartet, `checks.py` and
  `context.py` module sizes. Decomposing any is a session-scale job under the standing
  2026-08-27 call. Destination: [`scripts/shape_baseline.json`](../../scripts/shape_baseline.json#L1)
  (`recorded`), which is where the next look starts.
- **A test-suite hygiene pass** (outdated and duplicated tests, not speed: 4,083 tests in
  180s measured healthy). Raised with Thilina 2026-08-31 and undecided. Destination: the
  inbox, [`random-thoughts-questions.md`](../random-thoughts-questions.md#L1).
