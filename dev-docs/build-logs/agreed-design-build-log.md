# Build log — the design the builder agreed to

`plan.md` §1 P3-8. Started and finished 2026-08-16. Written while building, not afterwards.

Closes `DF4-I27` and `DF4-I03`'s judgement half, off `DF4-N1` and
[`findings.md` DF4-D2](../runs/dogfood-4/findings.md#L252).

## 1. Before any design

**The `shape` elicitation question the sitting approved already exists, as a decision kind.**
`DECISION_KINDS` ([`decisions.py` `DECISION_KINDS`](../../src/simple_agents/conformance/decisions.py#L67)) asks
*"Here are the steps the agent will take, which of them decide things for themselves, and which
model runs each. Is this the shape the builder pictured?"* Adding an elicitation question asking
the same thing gives the builder two surfaces for one question. **Put to Thilina and dropped**,
which is why the question set is still 38.

**And `idea.md` is the precedent for an artifact with no question behind it.** No elicitation
question produces it: `docs/procedure.md` says write it and FT-29 checks it. `design.md` takes the
same shape, so what was missing was the artifact and never the asking.

**FT-29's machinery is four `idea.md`-specific names**: `DEFAULT_IDEA`, `IDEA_SECTIONS`,
`empty_sections` ([artifacts.py:215](../../src/simple_agents/conformance/artifacts.py#L215)) and
`understanding_confirmed_at`, and `_account_reason` hardcodes the filename in every message.
Widening it to a second file was possible and was not taken: **FT-29 fires from `brainstorm` and
there is no design at `brainstorm`**, so one entry would have to be due at two stages and say so in
one message. FT-34 takes `· Stage: shape`, which FT-31 already proves works.

**`Decision` already parses an unused `stage` field and a `considered` list**
([decisions.py:166](../../src/simple_agents/conformance/decisions.py#L166)), so `from` is a field of
the same shape and `decisions_from` is the one place it lands.

## 2. Design

The sitting's record was `items/agreed-design.md`, and this section is now that file.

**Everything the library shipped for this fired, passed, and the design was still wrong.** Sixteen
decisions across six kinds, six `changed`, a shape decision with four alternatives weighed, and the
alternative that was right sitting in a brainstorm answer one stage up. FT-29 and FT-30 passed
throughout. `chose` is one sentence, and a builder cannot react to a sentence.

**Four decisions, all Thilina's**, taken 2026-08-16 with the arguments beside each.

1. **No new elicitation question.** §1's finding.
2. **FT-34 rather than widening FT-29**, on the stage split.
3. **Three sections, not five.** *What each step decides for itself* is the brief's
   `agency_boundary` and *what it will not do* is `not_building`; a project asked to write either
   twice is filling in a form. The three that survive are the walk-through, what it holds on to
   between runs, and what the builder said.
4. **The complement is computed over seven entries**: the core six that say what the builder wants
   built, plus `success_story`, which is the only optional one whose content is about the steps the
   agent takes.

**Thilina added the verbatim-and-live requirement to §3**, and what each half means mechanically was
put to him rather than assumed:

- **Live** is the P3-7 note, which now names `design.md` alongside the entries when the pipeline
  moves under it. Change-triggered, reusing a mechanism rather than adding one.
- **Verbatim** is `quoted_in` ([artifacts.py:336](../../src/simple_agents/conformance/artifacts.py#L336)):
  the third section carries a blockquote or text in quotation marks. **This reads a shape, never a
  fact**, and §10 carries the row saying so. It catches "nobody recorded anything anyone said" and
  nothing finer.

**Why the complement rather than the list.** The sitting first argued that an omission from `from`
is loud to a builder reading the brief. Thilina killed that: *"I didn't read it."* So the check
prints what **no** decision names, which needs nobody to notice anything.

## 3. Build

**Sixteen checks, 34 taxonomy entries.** FT-34 at `· Stage: shape`, `design.md` with three sections
and a quotation, `design_confirmed_at` on the brief, `Decision.rests_on` from `from`,
`Question.about_what_is_wanted` on seven questions, and the complement note. **2276 tests**, up 14.
No format moved.

**Two pre-existing defects the fixture rebuild exposed, and they are the finding of this build.**
`scripts/build_conformance_fixtures.py` writes `stage = "measure"` on every fixture and defers
`prices` to `measure`. **A `prototype` project has no `measure` stage, and `Brief.read` has refused
both since the `ship` stage landed on 2026-08-15.** So the generator has been unrunnable for a day
and nothing ran it: the committed fixtures were the last output of a script that no longer works,
and every conformance test has been running against them. Both are fixed, the stage and the
deferral now follow the tier, and the fixtures are regenerated.

**What that says about the wider practice**, and it is worth more than the fix: a generator is code
with no test over it, and the artifacts it produces are committed, so it can rot silently while
everything that reads its output stays green. `ship-stage-build-log.md` §4 lists what that item had
to touch and this script is not on the list.

**`docs/procedure.md` is 1722 words against a budget moved 1700 to 1750**, on Thilina's approval,
the third move. The estimate of ~60 words was wrong by half: the item grew a `design.md` line in the
Layout block, `design_confirmed_at`, `from`, the floor rewrite, and two gate lists that stopped
being true when FT-34 joined at `shape`.

**One consolidation was found and reverted.** Stage 3 opens *"Agree the shape before writing it"*,
which now duplicates stage 2. Cutting it saves 11 words and reads well on the merits, and
[`test_it_puts_the_design_discussion_before_the_pipeline_is_written`](../../tests/test_procedure.py#L1093) guards that sentence with *"The decisions
are settled where the code is written, not only named at the start."* **It was found while hunting
for words, and changing shipped guidance a test protects for that reason is the wrong order of
operations.** It stays open as a question to argue on its own.

## 4. Verification

**Live against Gemini `gemini-3.1-flash-lite`, two real runs**, scripted at
`scratchpad/verify_p3_8.py`: a whole project, then the failure `DF4-N1` describes.

| What it had to show | Result |
|---|---|
| FT-34 fails a project whose design was never written down | `failed`, *"no design.md"* |
| ...a section left blank | `failed`, naming *'What it holds on to between runs'* |
| ...the builder paraphrased rather than quoted | `failed`, *"quotes nobody"* |
| ...and passes with three sections and the builder quoted | `passed` |
| The complement names the answer no shape decision rests on | `finished_version` |
| ...and says nothing once the shape names it | silent |
| `design.md` is named when the pipeline moves under it | named |
| Neither note fails anything | `report.ok` |

**The complement reproduced dogfood #4's finding on a live project**, which is the strongest thing
here. The brief's `finished_version` said *"It sorts a whole list and learns which calls I disagreed
with"*; the shape decision chose *"one judging node, holding nothing between runs"*; the report
named `finished_version` as an answer the shape does not rest on. That is `DF4-D2`'s shape exactly,
caught at the moment the decision was recorded rather than two days later.

## 5. Doc consequences

| | |
|---|---|
| `docs/failure-taxonomy.md` | FT-34 is new, at `· Stage: shape`; §10 gains the row about whose words are in a quotation; §11 index and counts are 34 entries, 22 artifact |
| `docs/conformance.md` | §1.1's tier row and stage note; §2's table; §3's sample report regenerated; §3.4's fifth note, with the `from` example; §4 reads sixteen of thirty-four |
| `docs/procedure.md` | The question set is a floor; the Layout gains `design.md`; stage 2 writes it and iterates; three gate statements corrected. 1726 words |
| `README.md`, `CHANGELOG.md` | 34 entries; what shipped |

**Five shipped statements stopped being true and are corrected**, and the re-read after the build
found three of them. Stage 2's gate now names FT-34 and stage 3's names FT-32 to FT-34.
`docs/conformance.md` §1 listed the brief's keys and carried none of `design_confirmed_at`,
`confirmed_against` or `from`; §4's "three limits" is four, with FT-34's quotation among them.

**And stage 2's gate said "Nothing else can yet", which was measured and is false.** At `shape`
FT-25 passes where the `consultation` answer opens on a negation, and FT-33 passes where the
project keeps no build log. It now says the checks that read a run cannot pass yet, which is what
was meant and is true.

**This is the fourth enumeration to break in three items.** Adding a check invalidates every
sentence that lists its tier, its stage, or what passes at a gate, and those sentences are spread
across three documents with nothing relating them to the code. A meta-test over them is the
obvious answer and is not built here: it is named in §6 as the thing to weigh next time rather
than taken on unasked.

## 6. Left open

- ~~**The stage 3 consolidation**, above.~~ **Settled 2026-08-17.** The two stages agree
  different things and both stay: stage 2 what the agent does, stage 3 how it is built.
  What was wrong is that `shape` named the stage, the stage 3 instruction and a decision
  kind. Stage 3 now says *agree how it will be built* and reads `design.md` for departures:
  [`docs/procedure.md`](../../docs/procedure.md#L138).
- **`quoted_in` reads a shape.** A coding agent can blockquote its own summary and pass. §10 says
  so. Destination: nothing; it is the FT-24 ceiling in a second place.
- ~~**A meta-test over the gate enumerations.**~~ **Taken 2026-08-17, and it split in two.**
  A **count** of a set the code defines is checkable as written, and `prose_check`'s
  `miscount` rule now does it. A **list of ids at a gate** is not: the set is not derivable
  from `taxonomy()` and `CHECKS`, which give 14 to 16 per stage against the 3, 4 and 10 the
  gates claimed, because the claim is what a conforming project has green rather than what
  applies. So the gates stopped enumerating instead:
  [`docs/procedure.md`](../../docs/procedure.md#L102).
- **Nothing has met a builder.** FT-34 fails a project that has not written `design.md`, and no
  project outside this repository has been asked to. [`DF4-Q1`](../runs/dogfood-4/inventory.md#L433)'s standing
  condition, and dogfood #5 is where the three sections meet somebody who did not design them.
