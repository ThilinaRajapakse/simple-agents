# The dogfood protocol

How a dogfood run is set up and what is recorded. Reused by every run and by the meta-eval
(`items/meta-eval.md`), so it lives here rather than in `plan.md`.

**Ran six times**: dogfood #1 twice on 2026-08-07, dogfood #2 on 2026-08-07 to 08, dogfood #3 on
2026-08-10 to 11, dogfood #4 on 2026-08-11 to 13, dogfood #5 on 2026-08-20 to 24, and dogfood #6 on
2026-09-01 to 02, which was Thilina's own build against the public package rather than a protocol run. Each run has its
own directory beside this file, and `archive/plan-history.md` holds the run-by-run narrative.

## 1. Protocol

1. Open a **fresh** coding-agent session. No context from this design work.
2. Point it at Simple Agents and say: *"build \<task\> using Simple Agents."*
3. **Sit on your hands — but answer what you are asked.** This is an asymmetry, and it is the sharpest instrument in the protocol:
   - **Library-prompted elicitation → answer it, fully, and volunteer nothing beyond the question asked.** This is not an intervention. It is the product working. Refusing to answer would break the mechanism under test.
   - **Unsolicited helping, clarifying, correcting, or rescuing → forbidden.** If you are forced into it, that is a documentation bug.
4. Take notes on every point where it goes wrong, gets confused, skips a gate, or asks something the library should have already told it.
5. **Three things go in the log, and they are not the same bug:**
   - **Interventions you were forced to make** — the library failed to tell the coding agent something it needed.
   - **Questions you were asked that the library should have answered itself** — elicitation firing where documentation should have sufficed. Over-asking is a real failure mode; it burns the builder's patience and trains them to answer carelessly.
   - **Things you wanted to volunteer but were never asked for** — a *missing* elicitation question. This is the highest-value entry in the log and the easiest to miss, because nothing happens to prompt you to record it. Watch for the urge to interrupt; that urge is the signal.
6. Run it cold **two or three times** where the task warrants it. Variance across runs separates systematic failures from noise — the same eval discipline the library preaches, applied to the library.

## 2. The build log asked for, and why each part earns its place

Interactions recorded verbatim, so the log can be checked against the builder rather than trusted,
plus three requirements added off what verifying the first two logs cost:

- **`WAITING ON BUILDER` when the coding agent starts waiting on an answer, and `RESUMED` when it gets one.** This is the one figure not on disk anywhere else.
- **Every figure names the file it was read from.**

**The timestamp on every entry left this list at `P3-47`, 2026-08-27.** It was here for elapsed
per stage, and [`findings.md` §1.4](dogfood-5/findings.md#L140) measured what it was worth against
2,669 `started_at`/`ended_at` pairs and the log's 69 dated sections: from `build` onward the
manifests carry elapsed per stage and every clock time in the log's prose matched a run to within
a minute, so it was redundant; before `build` the manifests carry nothing and half of dogfood #3's
stamps were composed rather than read, so it was untrustworthy. What replaced it is `recorded_at`
on every answered brief entry and every decision, which is in a formatted file a gate reads rather
than in prose (`docs/conformance.md` §2.1). **The stamp is still written by hand**: dogfood #6's coding agent wrote
twenty of thirty-three in local time with a `Z` suffix, two hours off, while the view's own stamps
were right ([`dogfood-6/findings.md` `DF6-D9`](dogfood-6/findings.md#L242)). A formatted file makes
the stamp readable and not true.

**Nothing is said about deleting or overwriting an artifact.** Asking the coding agent to record
what it deleted tells it that deleting is expected, and what a run destroys is a finding about the
library rather than about the log. Decided 2026-08-07, on Thilina's instruction.

**The format carries no Simple Agents vocabulary**, so the same log can be asked for from a build
that does not use the library. That comparison is the meta-eval (`items/meta-eval.md`), and a log
that names stages and gates cannot serve both arms. Anything specific to this library belongs in
the prompt for this arm.

## 3. What four runs of it have shown

**The artifacts are the instrument and the log is for what they cannot hold**, chiefly the waiting
time: every finding in all four records except three came from reading files.

**What changed at dogfood #3 is which step-5 category pays.** The first three runs produced one
entry between them, an elicitation scaffold offering options too coarse
(`runs/dogfood-2/findings.md` §7.1). Dogfood #3 filled the third category, things the builder
wanted to volunteer and was never asked for, with **six decisions the coding agent made alone**,
and that became the largest finding in its record (`runs/dogfood-3/findings.md` `DF3-D8`). So the
categories are a checklist that has caught something no artifact would have shown, and the third
one is where to look.

**A run with no build log costs one figure and no others.** Dogfood #3 was not asked for one.
Every other requirement above was recoverable from the artifacts, and the waiting time was not.
`runs/dogfood-3/findings.md` §1.1 records what stood in for it by accident: the project's git
object store held snapshots of files the run later deleted, which is how three destroyed
evaluations were recovered. **That is luck rather than a method.**
