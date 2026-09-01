# Build log — the feature index

`plan.md` §1 P3-66. Started 2026-09-01. Carried `P3-3`'s remainder, folded in at scheduling.

## 1. Before any design

- The skill `simple-agents init` registers is `docs/procedure.md` verbatim:
  `pyproject.toml`'s force-include maps it to `SKILL.md`, so a section added there is in every
  coding-agent context. Measured before the change: 3,089 words, 399 lines.
- `tests/test_procedure.py` `WORD_BUDGET` already ratchets the skill's size, raised at each
  addition with the reason recorded in the comment above it.
- `docs/index.md` indexes by document; the audit's finding 6 (2026-08-29) named ten features
  its rows do not surface. 383 `##`/`###` sections across the nineteen documents, so the index
  is capability-level rather than section-level.

## 2. Design

Thilina ruled 2026-09-01 that the index lives in the skill, with conciseness binding. The
sitting settled five points, all his calls:

- **One copy, in `docs/procedure.md`, and nowhere else.** A `## The feature index` section at
  the end; the build stage points at it; `docs/index.md`'s procedure row names it. A second
  table in `index.md` was rejected as a drift machine.
- **One line per document, one entry per capability**: a feature phrase and the § that covers
  it, and nothing else. Roughly sixty entries.
- **Dense grouped lines over a table**: about two thirds the tokens, and the bold document key
  plus feature phrases scan for a model. The table shape was rejected on token cost.
- **`P3-3` closes with this item.** Its remainder, the post-review sections, got a correctness
  read here (§4); the language half stays Thilina's and nothing surfaced needing his call.
- **The original entry's README half is satisfied** by the README's documentation table and
  `P3-65`'s Quick start map; nothing further was built for it.

## 3. Build

`docs/procedure.md` gained `## The feature index`, thirteen document lines, ~690 words, and the
build stage gained the pointer sentence. The elicitation `approaches` scaffold now routes its
what-ships search there. `docs/index.md`'s procedure row names the index. `WORD_BUDGET` raised
3,200 to 3,800 with the reason recorded; `elicitation.py`'s module baseline 947 to 948 lines.
4,114 tests. Thilina reworded the four question rules in `procedure.md` mid-build ("How to ask
a question"); the wording was propagated to `HOW_A_QUESTION_IS_PUT` in `cli/main.py`, which a
test pins to the procedure's.

## 4. Verification

- `uv build`, and the wheel's `SKILL.md` read back carrying the index at 3,790 words.
- Every § the index cites was written against the target document's own headings, and a sweep
  resolving every `docs/x.md §N` cross-reference in `docs/` (358 of them) reports zero
  unresolved.
- **The carried `P3-3` read**: `pipeline.md` §2.3, `conformance.md` §3.7, `run-envelope.md` §8,
  `shipping.md` whole, and `evaluation.md` §6.3, §7.2, §7.7, with symbols checked against the
  code (`budget_per_item`, `allow_unfinished`, `behaviour_fingerprint`, `with_end_user`,
  `Trajectory.sampled`, the `max_spend` refusal). The other post-review `evaluation.md`
  sections were reverified at `P3-44` to `P3-53` within the prior four days and were swept
  mechanically rather than reread. No live run was owed: no behaviour changed.
- **What the read found**: one class of stale statement. The run-filing change of 2026-08-28
  moved evaluation rollouts to `runs/eval/<eval_id>/`, and twenty-plus shipped statements still
  showed the flat `runs/<eval_id>/` shape: `run-envelope.md` §8, `evaluation.md` §6.3 and
  thirteen path mentions, `conformance.md`'s three sample notes, docstrings in `runner.py`,
  `judgements.py`, `progress.py`, `prompts_sent.py`, `cli/main.py` and `view/walk.py`. All
  corrected under the corrections-are-never-queued rule, and the two fixtures behind
  `TestTheDocumentedNotesAreWhatIsPrinted` moved to the current layout so the pinned samples
  are printed from it. The remainder's "`run-envelope.md` §8.2" resolved to today's §8.4:
  `P3-50` inserted §8.3 and renumbered.

## 5. Doc consequences

`docs/procedure.md`, `docs/index.md` and the path corrections above. Nothing for
`CHANGELOG.md`: no format moved, and the corrected statements described a layout the reader
already has (the flat form is still read where it exists).

## 6. Left open

- A `§`-existence rule for cross-references, so the sweep in §4 is a check rather than a
  script: one dated bullet in
  [`random-thoughts-questions.md`](../random-thoughts-questions.md#L1), beside the `.md`-link
  entry of the same family.
