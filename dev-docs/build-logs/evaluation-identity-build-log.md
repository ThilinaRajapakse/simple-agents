# Build log — what an evaluation's identity covers, and what the prompts show

`plan.md` §1 P3-20. Started 2026-08-19, built the same day. Two stages: what the identity
**declares**, then what the trajectories **show**.

## 1. Before any design

Everything below was measured against `be78524` before anything was decided, because
`DF4-I07`'s entry carried two faces written days apart and the newer one predated `P3-6`,
`P3-15` and `P3-18`. Each probe is two pipelines differing in one thing.

| What differs | `graph_fingerprint` | `behaviour_fingerprint` | `_eval_id` |
|---|---|---|---|
| A tool's body, declared through `@tool` | same | **moves** | **same** |
| A `Deterministic` node's body | same | **same** | **same** |
| A prompt's body, no `prompt_version=` | same | moves | moves |
| A prompt's body, `prompt_version="4"` on both | same | **same** | **same** |

**Row 1 was `P3-18`'s Left open and is confirmed.** The tool's version moved
`sha256:aa4d52b117e0` to `sha256:42608933a241`, the stamp moved with it, and the evaluation
directory stayed `eval_31211894ea66`.
[`recording.py`](../../src/simple_agents/pipeline/recording.py#L458) (`_node_entries`), the `tools` key of a node entry,
recorded `sorted(t.name for t in ...)`.

**Rows 2 and 4 were in no record.** A `Deterministic` node's function is versioned nowhere:
everything after
[`recording.py`](../../src/simple_agents/pipeline/recording.py#L547), `if not isinstance(node, Deterministic)`,
is skipped, so its entry carried `node_id`, `node_kind`, `successors`, `route`,
`consultation_route`, `loop`, `on_error`, `retry`, `schema`, `accepts` and `tools` and nothing
about what the node does. And
[`manifest.py`](../../src/simple_agents/records/manifest.py#L596), `source_version`, returned
`{"version": declared, "source": "declared"}` and discarded the hash, so declaring a version
switched off the only automatic trace.

**Two records were wrong and are corrected under `DF4-X11`.** `DF4-I07`'s entry and
[`what-the-stamp-covers-build-log.md`](what-the-stamp-covers-build-log.md#L119) §6 both said
`resume_from` is unprotected because `_refuse_a_moved_pipeline` compares `graph_fingerprint`
alone. `d13e46e` added `_refuse_a_moved_configuration` on 2026-08-14, four days before the
sentence was written. The conclusion survives because that comparison carries tool names.

## 2. Design

The sitting is `runs/dogfood-4/inventory.md` §3, sitting 3, 2026-08-19. `items/evaluation-identity.md`
held this and has left `items/`.

**Two halves of one subject.** Declaration catches a change before the second run is paid for;
observation catches what nothing could declare, after both. `DF4-I07` is the first and `DF4-I19`
the second; `DF4-I23` was `DF4-I19` filed a second time by the pre-reorganisation categories and
is declined.

**One item rather than two, on Thilina's call.** Asked whether the halves were orthogonal:

> "are P3-20 and 21 large builds or completely orthogonal? If not, I would just do them
> together."

and earlier, on whether stage 2 belonged in this sitting at all:

> "Why don't we just do both here?"

**Measured before that call.** The halves share no code, and combining saves no format bump,
because only stage 1 touches the 132 manifest fixtures. What couples them is the `derived` field,
which stage 2's report reads and which does not exist until stage 1, and one section of
`docs/evaluation.md` that both would write.

**Option A over two that were not taken.** Widen what the identity covers, and say in the docs to
declare a version where a node or tool reads data that changes underneath it. **Option B** was a
dedicated `run(measured_over=...)` seam, rejected as a fourth way to say one thing and no more
automatic, since both rest on the builder changing a string. **Option C**, the across-evaluation
comparison, is not an alternative: it is stage 2, and it is the same reader as the within-run one
under a different grouping.

**Stage 2 reports and never fails.** The library cannot tell `DF4-D10`'s sorting bug from a
project working as designed: a prompt reading the clock, memory that accumulates, or a tool
holding state, which is `DF4-X1` and which dogfood #4 has.

**The hash is recorded beside a declared version rather than replacing it.** The first reading
was that the choice lay between the declaration winning and the source winning, and that keeping
the source live would move every figure on a whitespace edit. Recording both closes it: identity
and the stamp digest the declaration alone, and anything comparing two runs sees the source moved.

**`_eval_id` was widened in place rather than collapsed into `behaviour_fingerprint`.** The two
overlap almost completely, which is how they drifted apart, but collapsing them makes
`run(model=None)` on a pipeline whose node takes the run's client fail at `_eval_id` with a
fingerprint message instead of at the node with `_refuse_unserved`'s. Measured: `_eval_id` returns
`eval_0732a656ac41` there today and `behaviour_fingerprint(None)` raises.

## 3. Build

**Manifest `0.28` to `0.29`.** 2682 tests to 2714. Every fixture evaluation directory was renamed,
`eval_d5e2231ecc32` to `eval_52debf269aab`, which is the migration this item imposes on any project
holding one.

- **`Deterministic` records `fn`** on its manifest node entry, in `source_version`'s shape, and
  takes `version=`. `_STRUCTURAL` is unchanged, so `graph_fingerprint` still answers whether
  stored state can be walked.
- **`Pipeline.manifest_tools()`**, beside the three accessors it sits with.
- **`_measured_configuration` gained `tools`**, which puts tool versions into `_eval_id` and into
  the resume and rescore refusal in one change, and keeps that refusal naming the field that moved.
- **`source_version` records `derived`**, and `_tool_entry` does too. `_without_derived` strips it
  before any digest or comparison, so only the declaration decides identity.
- **`_warn_a_moved_declaration`** fires from `_refuse_a_moved_pipeline`, so `resume_from` and
  `rescore` report a declaration that stayed put while its source moved.
- **`prompt_differences(run_dir, against=None)`**, public beside `runs()` and `progress_of()`.
  No format change: it reads run directories.

**Three things the build found that the design did not know.**

**A `Deterministic` body cannot be versioned by source plus closure.** `_closed_over` renders a
captured dict by value, so a node holding state across its own calls changes version while the run
runs, and `behaviour_fingerprint` is the value a project joins its stored results on.
`tests/test_suspension.py`'s `TestWaitingOnAClock` caught it: its `park` closes over a
`{"already": False}` flag. `source_version(..., closure=False)` is what ships, and a node whose
behaviour depends on captured data declares `version=`. **The same defect exists for prompts and
routes and is left open below.**

**`_verify_against` compared a prompt entry whole**, so recording the hash inside it would have
refused a resume the declaration says is the same pipeline. Every version is now compared the same
way, on `version`, which is what the caller controls.

**A `Deterministic` node's function was compared nowhere on resume.** Half a resumed run's
trajectory could come from a body the other half never ran. `fn.<node_id>` is now refused unless
waived, the way a prompt is.

**Three more the reverification cycles found, after the first pass was clean.**

**The results file embeds `manifest_nodes()` and the rollouts' prompts**, so `derived` landed in
it at an unbumped `0.18`. It is stripped there rather than the format bumped: nothing reads it out
of a results file, and where nothing was declared it equals `version`, so `compare()` would have
named every prompt edit twice.

**`derived` was recorded even where it repeats `version`**, which is the undeclared path and the
common one. It is omitted when equal. Measured on `plan_variant` before deciding, because
stripping it from `compare_variants` too was the alternative: with a held declaration `derived`
is the only thing marking the node changed, and without it two pipelines differing in a body under
one declared version are refused as having nothing different at all. **This also closes a hole
`P3-18` recorded and left**: a `Tool` constructed by hand with no `version=` now carries `derived`,
so its body is traced where it was traced nowhere.

**`prompt_differences` over a directory of evaluations returned zeros**, which reads as agreement.
An evaluation writes rollouts into `<run_dir>/<eval_id>/`, so a caller passing `run_dir` got
nothing and no indication why. Both sides of a comparison are refused now, naming an evaluation
under the directory.

**What the cycles cost, measured rather than assumed.** `_tool_entry` now hashes each tool's source
on every manifest read. Over 40 file-backed tools that is 1.1ms per read, steady because
`linecache` caches, or about 1ms per rollout against its model calls.

## 4. Verification

**Five reverification cycles**, the first three of which each found something. Pass 5 found
nothing new, and the live run below was re-run after each.

**Live against vLLM**, `Qwen/Qwen3-1.7B` on port 8001, six cases end to end. Mistral is out of
credits. Every node declared `max_output_tokens=4000`; the preflight call returned in 0.5s.

| | What it showed |
|---|---|
| An edited `Deterministic` body, nothing declared | `eval_7fe55b43d7e5` and `eval_5fd133e7970d`: separate directories |
| The same body twice | `eval_7fe55b43d7e5` again |
| A declared version held over an edited body | `eval_da7c892c5e86` both times, as declared |
| `prompt_differences` inside one evaluation | 0 differing over 2 groups, 4 rollouts |
| `prompt_differences` across the two | both examples differing at `judge`, `across_runs` true, and `node 'read'` named as a declaration held over `sha256:d9d67fa322c4` to `sha256:f6141e7a80af` |
| `rescore` across the same pair | scored, and warned once, naming the node and both hashes |

**The live run found a defect the unit tests did not.** Two evaluations of one declared
configuration produce **one directory name**, which is the case `against=` exists for, and the
reader prefixed rollouts with that name. Both sides collided and the comparison silently reported
nothing. It is keyed on which directory was read now, a same-directory comparison is refused, and
`test_two_evaluations_under_one_directory_name_are_told_apart` fails without the fix.

**Mutation checks.** Removing `_without_derived` from the digest and the `fn` entry fails 7 tests;
reverting the reader's keying fails 2. `tests/test_loop_and_budgets.py`'s
`TestToolTimeIsRunWallClock` flaked once on wall clock and passed on three consecutive full runs.

## 5. Doc consequences

- **`docs/evaluation.md` §6.7 and §6.8** are new: what the directory name covers and what it
  cannot, and comparing the prompts that were actually sent.
- **`docs/run-envelope.md`** §2.3 carries `derived`, §2.6 carries `fn` and no longer says a
  `deterministic` node carries none of these fields, §2.1's `tools` row carries `derived`, and the
  version line reads `0.29`.
- **`docs/pipeline.md`** §2.1 documents `Deterministic(version=)`, and §1.1 and §1.8 add a
  `Deterministic` function to what a resume refuses.
- **`docs/shipping.md` §6** names the `Deterministic` body and says a held declaration does not
  move the stamp.
- **Three shipped statements stopped being true and are corrected under `DF4-X10`**:
  `docs/shipping.md`, `docs/run-envelope.md` and `behaviour_fingerprint`'s own docstring each
  claimed the stamp covers everything that decides what the pipeline produces.
- **`CHANGELOG.md`** carries the entry and the format move.

## 6. Left open

- **A prompt or a route closing over mutable state changed version while the run ran.**
  **Closed by `P3-21`**, 2026-08-19: a version is taken when the node is declared. The tool half
  of it was built there and reverted, and stays open in that log's §6.
  [`a-version-when-it-is-declared-build-log.md`](a-version-when-it-is-declared-build-log.md#L1)
- **FT-15 specified a check and `checks.py` registered none.** The `derived` field is what one
  would read first, and this item put it in the manifest without registering the check.
  **Closed by `P3-21`**, with the entry's check text corrected to what a check can read.
  [`a-version-when-it-is-declared-build-log.md`](a-version-when-it-is-declared-build-log.md#L1)
- **A tool's version reaching `_eval_id` means a project that edits a tool body cannot resume.**
  Ruled 2026-08-19 by Thilina that this needs no fixing: an evaluation is a measurement, and half
  of one measured under another tool is a number describing nothing. Destination: `nothing`.
