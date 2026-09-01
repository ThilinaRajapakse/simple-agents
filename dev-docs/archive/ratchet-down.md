# Working the ratchet down

`plan.md` §1 P3-64's record. **The lint gate is built, 2026-08-31**; the per-module sittings are open.

## Where it came from

Thilina, 2026-08-31, at the P3-63 close: *"Is there a plan for refactoring the code inside the
actual files? To ratchet down with the ratchet? Making sure code smells are gone, proper SE
principles are followed w.r.t. things like separation of concerns, abstraction, decoupling,
deduping, etc. etc.? And making sure the classes and functions aren't bloated and also follow
SE principles?"* The honest answer was no: the ratchet stops growth, and `P3-63` moved code
between files; nothing scheduled shrinking the 144 recorded units (145 after the format pass) or guarded the smells no
size check sees. He agreed to the three-part proposal the same day and set the order: the lint
gate first, then the per-module sittings carrying the judgement reading.

## What the problem is

- `scripts/shape_baseline.json` records 144 units over a threshold and nothing works the list.
- Size and branches are the only smells with a check. The `P3-63` work kept finding others by
  accident: five quoted-annotation undefined names (`MetricChange` in
  `evaluation/ratios.py`, `ProjectRatio` in `evaluation/metrics.py`), dead imports that were
  de facto re-exports, an unused local, six functions reading the recorded graph six ways.
- Separation of concerns, abstraction and duplication were judged once, at `P3-63`'s module
  boundaries, never inside the files.

## What has to be decided

**Decided 2026-08-31, Thilina:** the order is lint gate, then the sittings.

1. **The lint gate: built 2026-08-31.** `ruff check` with `F`, `B`, `A`, `C4` and `PLE`
   (no style opinions, and no `ruff format`, a separate decision not taken; `B905` excluded
   because `zip(strict=)` changes behaviour on a length mismatch). All 129 findings fixed,
   none baselined, on his call: among them the five quoted-annotation undefined names (now
   `TYPE_CHECKING` imports), seven closures over loop variables bound by default arguments,
   ten blind `pytest.raises(Exception)` narrowed to the exception each site raises, a dead
   `Example` construction, and two shim re-exports the autofix exposed (`_CeilingReached`,
   now imported from `tools.py` where it is defined). `tests/test_lint.py` is the gate:
   zero tolerance, a deliberate exception is a per-line `# noqa` with its code.
   **`ruff format` joined it later the same day, on Thilina's call**: 212 files reformatted,
   proven AST-identical apart from docstring indentation before anything else ran; fixture
   projects excluded because their source feeds recorded digests; the packed stopword list
   kept under `# fmt: skip` (a guard inside an expression is ignored); four Gemini and vLLM
   cassettes re-recorded because the lexical tool's source digest moved with its formatting,
   and the pinned digest updated with them. `tests/test_lint.py` gates format drift the same
   way it gates lint.
2. **The record machinery: built 2026-08-31**, out of what the reverification found by hand.
   Four rules, each with a firing test. `check_citations` gained `dead-md-link` (a markdown
   link target exists and its `#L` anchor is inside it; the ancestor-path search turns a link
   written for another directory into a `--fix`) and `unnamed-anchor` (a source citation past
   line 1 names a symbol a repair can re-resolve). `prose_check` gained `unknown_module` (an
   example importing a submodule the library does not have) and `unknown_role_target` (every
   `:class:`/`:func:`/`:meth:` docstring reference resolves, module-relative included).
   Turning them on found and repaired: 2,508 links unreachable from their own documents,
   29 links to retired `items/` records repointed to where each record went, four anchors
   past a document's end, and 27 unnamed anchors now named on their construct's own line,
   two of them mispaired with the wrong function and corrected against the code
   (`_removable`, `_spliced`, `_same_but` in `evaluation/variants.py`).
3. **Eight sittings by subsystem, agreed 2026-08-31** ("just go ahead and do all of it";
   per-sitting decisions delegated, only the genuinely undecidable comes back). The format
   pass moved the worklist to 145 units: reformatting pushed six over a threshold and
   dropped five. Subsystem grouping replaces the per-module list this record first carried,
   because the smells no size check sees cross module lines inside a subsystem: `P3-63`
   found six functions reading the recorded graph six ways across `conformance/`, and the
   evaluation readers all read the same run records. In order, with unit counts at the
   start:
   1. `evaluation/runner.py` (13)
   2. Evaluation reading: `compare`, `per_node`, `results`, `variants`, `examples`,
      `stand_in`, `scoring` (26)
   3. `pipeline/`: `core`, `preflight`, `recording` (19)
   4. `context.py` and `runtime/` (16)
   5. `nodes/` (15)
   6. `conformance/` (11)
   7. Records and wire: `records/`, `adapters/`, `tools.py`, `mcp.py`, `graph.py`,
      `cost.py` (21)
   8. `builtins/`, `view/`, `cli/` (24)

   Each sitting decides the subsystem's internal shape the way `P3-63` decided pipeline's,
   decomposes with the same discipline (baseline-key verification, suite green, live run
   where the runtime is touched), and reads for what no tool sees: duplication, coupling,
   misplaced abstraction. Sittings 3 to 5 sit after the evaluation pair because `P3-63`
   read those trees and its judgements carry forward.
4. **The end state is not zero.** Every recorded unit is either gone or carries a written
   reason. **A keep's reason lives in [`scripts/shape_baseline.json`](../../scripts/shape_baseline.json#L1)'s
   `reasons` map** (`shape_check` `write_baseline`, extended 2026-08-31: `--update` keeps a
   reason whose unit is still recorded and drops one whose unit has gone), so the end state
   is checkable; the closing sitting adds the suite test that every recorded unit carries
   one. Estimated 30 to 40 genuine keeps of the 145.

Per-sitting decisions are delegated; this record carries the standard, the order, and what
each sitting settled. One build log for the item, a section per sitting.

## What it waits on

none. `P3-31` waits on this item, on the same 2026-08-17 call that put the refactor before the
public release.
