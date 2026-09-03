# Dogfood #4 — inventory

Everything actionable from [`findings.md`](findings.md#L1), in one place, so `plan.md` and
`handoff.md` can point here rather than carrying it.

**Nothing here is agreed work.** `plan.md` §1's rule stands: everything agreed to be built is
scheduled there and nowhere else. This is the **input** to `plan.md` §1 P3-1.

**Sections are by where an item goes next.** §1 goes nowhere, §2 is already applied, §3 goes to
`plan.md`, §4 goes to the next run's `setup.md`. *(Reorganised 2026-08-15 out of eight categories
that mixed belief updates, decision-state, kinds of work and kinds of run: `A-5` was an addition
filed as an absorption, every category had a different column schema, status was written three
different ways, and `F-1` here collided with `F-01` in the full-test record. `templates/run-inventory.md`
is the shape.)*

**The inventory says what to do. `findings.md` says why we believe it.** Every row names its
finding rather than repeating it.

**P3-1 is done when no candidate is still `open`** — each is scheduled, built, or declined with a
reason. **Met 2026-08-20, at sitting 7.**

---

## 1. What we learned

Belief updates. No work attached; they change how the next thing is read.

| # | What | From |
|---|---|---|
| **DF4-L1** | **The noise floor on a real project is 0.04.** Three identical evaluations of one configuration returned 0.929, 0.889 and 0.899. Every dogfood conclusion across all four runs that rests on a smaller difference is now suspect | `DF4-D10`, §9 |
| **DF4-L2** | **The pipeline mattered more than the model, by a lot.** A prompt-wording fix moved the headline 0.84 to 0.89; four model arms across three identities, at up to twenty times the cost, separated nothing | §4.14, §9 |
| **DF4-L3** | **Three times an apparent model advantage was a defect in the harness measuring it**, each flattering the same arm, each found by reading a trajectory rather than a number | `DF4-D3`, §8.3 |
| **DF4-L4** | **`FakeModelClient` earns its place and `docs/pipeline.md` §6 is what gets it run.** Three defects before a paid call, two of which would have been billed at full price | §6 |
| **DF4-L5** | **The dogfood isolation paid.** The project rebuilt the Gemini adapter the library had shipped the day before, arrived at a strictly weaker version, and confirmed `ToolCall.provider` was necessary without ever seeing it | §6, §1.2 |
| **DF4-L6** | *Thilina, 2026-08-14:* the coding agent in the dogfood session feels less capable than in library work, which may be an artifact of the library being well-defined and the dogfood being open-ended | run notes |
| **DF4-L7** | *Thilina, 2026-08-14:* the coding agent says it ran something it has not run, and starts runs without watching whether they finish | run notes |
| **DF4-L8** | **`MemoryStore` was specified by name and never reached.** `queue_architecture` named it as the cache mechanism; the project built SQLite instead, needing three tables, an append-only judgement history and queries a scoped store answers none of, and `memory` is `None` in all 3,293 manifests. The first dogfood evidence about the memory item says the shape was wrong for the one project that specified it. *(Added 2026-08-20 at the completeness audit; the semantic-recall half is `DF4-Q4`.)* | §8.4 |

## 2. What was corrected

A statement the run disproved, and where it was written. **Applied on sight, never queued**, so
this is a log rather than a backlog.

| # | The statement | Where it was written | Corrected |
|---|---|---|---|
| **DF4-X1** | "Results do not depend on how many ran at once" | `docs/evaluation.md` §6.2 | True of the library, false of every project holding state in a tool. `DF4-I11` is the fix |
| **DF4-X2** | Consultation is a designed interaction rather than a fault path | `CLAUDE.md` glossary, `docs/tools.md` §4.6, FT-25 | True of the design, false of both projects that used it. `DF4-I01` is what makes it true |
| **DF4-X3** | `compare_variants` "fails on its own leading example, after paying for a baseline arm" | `RULINGS.md` D2, third cause | Confirmed as a misreading; §8.2 answers it |
| **DF4-X4** | Dogfood #4 is running; no findings record exists | `plan.md`, `handoff.md` | Corrected 2026-08-15 alongside this document |
| **DF4-X5** | Overtaken: the setup document says a library change reaches the run only when the wheel is replaced, and never says what landed underneath it | [`setup.md`](setup.md#L1) | Corrected 2026-08-15 |
| **DF4-X6** | Overtaken: FT-25 is *"elicitation-only, with a static occurrence check"* | `docs/failure-taxonomy.md` FT-25 | The check is specified and `checks.py` does not register it. `DF4-I26` is the fix |
| **DF4-X7** | Overtaken: *"What decides whether it worked: dogfood #4"* | `archive/plan-history.md` §1.11 | An open question this run answers, not a false claim. Corrected 2026-08-15 |
| **DF4-X8** | A changelog entry may cite the internal record of the change | `CHANGELOG.md:109` | Ruled 2026-08-16 that it may not: an entry says what changed and stops. The line is gone, and it was the only one left. `DF4-I41` carries the eight in `tests/` that are not |
| **DF4-X9** | "The same evaluation run twice writes into the same directory and the second overwrites the first" | `docs/evaluation.md` §6.1 | False: `_refuse_a_used_directory` raises `UsedRunDirectory` unless `resume_from` was given. Verified on the machine 2026-08-16 and corrected the same day. Found while checking `DF4-I34` |
| **DF4-X10** | `behaviour_fingerprint` "covers everything that decides what the pipeline produces" | `docs/shipping.md` §6, `docs/run-envelope.md` §2.1, and the method's own docstring | False: a `Deterministic` node's body decides what the pipeline produces and moves nothing at all. Measured 2026-08-19 at sitting 3. The universal claim is gone from all three and the enumeration stands; `P3-20` extends the list rather than deleting a caveat |
| **DF4-X12** | *"the scaffold said to show the pairs first, and only the threshold reached him"* | [`findings.md`](findings.md#L808) §5, `DF4-P4` | False. The scaffold names an operation `ExampleSet` did not offer: `contamination(threshold=)` returns only pairs at or above the threshold, so on a set that is clean at every threshold there is nothing to show, and the sweep the builder saw is what following it looks like. Measured 2026-08-20 and corrected the same day; `P3-28` shipped `nearest_cross_split` so the scaffold can be followed |
| **DF4-X13** | A shipped file may cite an internal id where it cites no internal filename | `src/simple_agents/conformance/checks.py`, `_unseeded` | The 2026-08-16 sweep behind `DF4-X8` searched for filenames, so `DF4-D6` in a docstring survived it and shipped inside the wheel. Removed 2026-08-20, and `prose_check.py`'s `INTERNAL_REF` now matches `DFn-Dn` and `P3-n` as well |
| **DF4-X11** | `resume_from` mixes rollouts across a tool edit "because `_refuse_a_moved_pipeline` compares `graph_fingerprint` alone" | `DF4-I07`'s entry below, [`build-logs/what-the-stamp-covers-build-log.md`](../../build-logs/what-the-stamp-covers-build-log.md#L119) §6 | False when it was written on 2026-08-18: `d13e46e` added `_refuse_a_moved_configuration` on 2026-08-14, which compares the measured configuration field by field. The conclusion holds because that comparison carries tool **names**. Corrected 2026-08-19 |
| **DF4-X14** | Overtaken: "`docs/procedure.md` stage 5 is when to read this", said of the `ship` stage | `docs/shipping.md:3` | `P3-28` made `ship` stage 6 and this was the one stale stage reference left in shipped files. Corrected 2026-08-20 at sitting 7 |
| **DF4-X15** | Of `suite.run`: "the k rollouts of one example share what they buy: a tool called with the same arguments in all five is called once and served four times (FT-20)" | `docs/evaluation.md` §6.3, and `runner.py` `_recording_by_default`'s docstring | False for a fresh `suite.run`: its default cassette is `Cassette.record`, and `serves_hits` is replay and update only, so all five calls run live and the sharing happens on a later replay, under a resume, or under `suite.record`. FT-20's own taxonomy text attributes the sharing correctly. Found 2026-08-20 by `P3-30`'s before-any-design verification and corrected the same day |

## 3. Candidates

**The id never changes and is never reused**, so re-tagging and reordering are free. `kind` is a
tag rather than a section. **The table is in the order to take them and the top row is next**: a
live blocker sits above everything it blocks, and resolved rows sink below every open one. `status` names where the candidate went, and its vocabulary is `plan.md`'s sections:
`open`, `accepted §2.1`, `deferred §2.2`, `scheduled P3-n`, `built <log>`, or
`declined: <reason>`.

**The open rows are grouped into sittings, agreed 2026-08-18.** Twenty-one were ordered one at a
time, which split three subjects across the queue and left three rows at positions 14 to 16 that
the record already answers. Each group is one sitting's worth and the rows follow it in the table,
so the top row is still what happens next.

| Sitting | Rows | Why they are one |
|---|---|---|
| ~~**1. Node shape and fan-out**~~ | `DF4-I31`, `DF4-I10`, `DF4-I32` | **Closed 2026-08-18.** `DF4-I31` decided which node kinds carry the fan-out mechanism and shipped as `P3-15`; the other two are defects in it and shipped as `P3-16`, in their final home rather than twice |
| ~~**2. What the record already answers**~~ | `DF4-I33`, `DF4-I34`, `DF4-I35` | **Closed 2026-08-18.** [`findings.md` §8.3](findings.md#L1141) was right on `DF4-I33`, stale on `DF4-I34` and understated on `DF4-I35`. All three built the same day: `P3-17`, `P3-18`, `P3-19` |
| ~~**3. The identity of an evaluation**~~ | `DF4-I07`, `DF4-I19`, `DF4-I23` | **Closed 2026-08-19.** Two halves of one subject rather than three rows: `DF4-I07` is what the identity **declares** and `DF4-I19` is what the trajectories **show**. Declaration catches a change before the second run is paid for; observation catches what nothing could declare, after both. `DF4-I23` was `DF4-I19` filed a second time by the pre-reorganisation categories. Both stages of `P3-20` |
| ~~**4. Agentic waste**~~ | `DF4-I21`, `DF4-I22`, `DF4-I36` | **Closed 2026-08-19** as `P3-22`, built the same day as `P3-23` to `P3-26`. The report line existed and was never printed: `results.report()` renders `ended: finish 12, max_steps 90` and fifteen of the project's results files carry that count, and the project wrote its own printer instead. What is missing is the join with what those executions spent, a surface that is reached without writing code, and a gate on the one member with no benign reading |
| ~~**5. What a figure is reported against**~~ | `DF4-I17`, `DF4-I18` | **Closed 2026-08-19** and built 2026-08-20 as `P3-27`, five stages. One subject rather than two rows: what a number is read against. `DF4-I17` is how much it moves with nothing changed, and the measured answer is that most of that is computable from one run's own rollouts; `DF4-I18` is the mix it was pooled over and the floor it has to clear. `plan.md` §2.2's entry for an answer that left a `required` condition empty came in as stage 5 |
| ~~**6. The procedure and the coding agent**~~ | `DF4-I14`, `DF4-I28`, `DF4-I29`, `DF4-I37`, `DF4-I41` | **Closed and built 2026-08-20** as `P3-28`, in six stages. Framed as no library code and three of the five needed it. `DF4-I14` and `DF4-I28` were one event and not the one the record described: the scaffold named an operation `ExampleSet` could not perform. `DF4-I29` reframed from volunteering sources to a `research` stage, on Thilina's instruction to break the system into parts and research the parts |
| ~~**7. The product boundary**~~ | `DF4-I06`, `DF4-I38` | **Closed 2026-08-20**, both scheduled as `P3-30` and built the same day. The product becomes a first-class concept: a glossary term, `docs/product.md`, a required `used_through` question, a product section of `design.md` with a check reading it, and the rules for the artifact that accumulates. No store, server or scheduler ships; `P3-6`'s precedent stands and the checks read declarations. `DF4-Q2` is answered in the design: three product shapes, the store one of them |

| # | What | Evidence | Kind | Size | Blocked by | Status |
|---|---|---|---|---|---|---|
| **DF4-I06** | The conformance suite's artifact model reads a results file and a run directory; the product can be a third thing | `DF4-D1` | change | sitting | — | built `build-logs/the-product-build-log.md` |
| **DF4-I38** | A UI is built as a display over stored output rather than as part of the system | `DF4-N14` | decide | sitting | — | built `build-logs/the-product-build-log.md` |
| **DF4-I14** | `too_similar` reached the builder as a bare threshold rather than the pairs to judge | `DF4-P4` | fix | cheap | — | built `build-logs/research-stage-build-log.md` |
| **DF4-I28** | An elicitation question used an undefined term a builder could not answer | `DF4-N2` | fix | cheap | — | built `build-logs/research-stage-build-log.md` |
| **DF4-I29** | The coding agent never volunteers sources or uses its own search to find them | `DF4-N3` | add | item | — | built `build-logs/research-stage-build-log.md` |
| **DF4-I37** | The procedure says what artifacts exist and never where they go, so a project scatters files | `DF4-N13` | change | cheap | — | built `build-logs/research-stage-build-log.md` |
| **DF4-I41** | A shipped file cites an internal record the builder cannot read. **Decided and half applied 2026-08-16**: `CHANGELOG.md` is fixed, eight citations in `tests/` are not | housekeeping, `7d1cf4b` | fix | cheap | — | built `build-logs/research-stage-build-log.md` |
| **DF4-I17** | `noise_floor.py`: repeat one configuration n times and report the range | `noise_floor.py`, §9 | absorb | item | — | built `build-logs/what-a-figure-is-reported-against-build-log.md` |
| **DF4-I18** | **Every figure reportable grouped by a property of the example**, with the do-nothing baseline beside the headline | `compare_arms.py`, §7, §9 | absorb | item | — | built `build-logs/what-a-figure-is-reported-against-build-log.md` |
| **DF4-I21** | A report line for an agentic node that reached `max_steps` having called no tool | `DF4-D5` | add | cheap | — | built `build-logs/unfinished-work-build-log.md` |
| **DF4-I22** | A check for an agentic node that terminated on `max_steps` having called no tool | `DF4-D5` | add | cheap | — | built `build-logs/unfinished-work-build-log.md` |
| **DF4-I36** | Can the library detect a node that runs and achieves nothing until `max_steps` | `DF4-N12` | add | item | — | built `build-logs/unfinished-work-build-log.md` |
| **DF4-I07** | What an evaluation's identity covers: not the data a node reads, not a tool's body, and not a `Deterministic` node's body | `DF4-D11` | change | item | — | built `build-logs/evaluation-identity-build-log.md` |
| **DF4-I19** | Compare the prompts that were actually sent: the k rollouts of one example, and one example across two evaluations | `DF4-D10` | add | item | — | built `build-logs/evaluation-identity-build-log.md` |
| **DF4-I23** | A check that k rollouts of one example sent the same prompt at one `prompt_version` | `DF4-D10` | add | cheap | — | declined: duplicate of DF4-I19, filed twice by the pre-reorganisation categories |
| **DF4-I33** | Gemini's `thought_signature` is dropped by `messages_to_wire`, and whether that degrades multi-turn tool use | `DF4-N8` | decide | cheap | — | built `build-logs/adapter-backend-state-build-log.md` |
| **DF4-I34** | Whether pipeline versioning for evaluations and ablations is already `graph_fingerprint`, `behaviour_fingerprint` and `compare_variants`. **A third identity shipped 2026-08-16 and §8.3's answer predates it** | `DF4-N9` | decide | cheap | — | built `build-logs/what-the-stamp-covers-build-log.md` |
| **DF4-I35** | Progress bars and indicators for anything running. `on_rollout=` ships the data and nothing renders it, and **`P3-16` added an `item` phase to `on_progress=` on 2026-08-18**, so a fan-out's items are a second channel shipping data nothing renders | `DF4-N10` | add | item | — | built `build-logs/progress-display-build-log.md` |
| **DF4-I10** | A transport failure inside a fan-out is classified as an abstention | `DF4-D3` | fix | item | — | built `build-logs/fan-out-defects-build-log.md` |
| **DF4-I32** | Whether the store step only writes at the end of a fan-out, and whether that is library-side | `DF4-N7` | decide | cheap | — | built `build-logs/fan-out-defects-build-log.md` |
| **DF4-I31** | `LLMNode` has `over=` and no tools; `AgentNode` and `Deterministic` have tools and no `over=`. **Decided 2026-08-18**: `over=` lifts to all three kinds and `LLMNode` gains `tools=` | `DF4-N6` | decide | sitting | — | built `build-logs/fan-out-and-node-shape-build-log.md` |
| **DF4-I04** | The `Reply` matcher. **Widened 2026-08-16 and folded into P3-9**: the matcher is one of six assumptions in the evaluation half of consultation | §8.1, `PENDING-SIGNOFF.md` item 6 | decide | cheap | — | built `build-logs/end-user-in-an-evaluation-build-log.md` |
| **DF4-I02** | The product is a third artifact and nothing looks at it | `DF4-D1` | decide | sitting | — | built `build-logs/end-user-artifact-build-log.md` |
| **DF4-I20** | Staleness as a query, plus something that refreshes what it identifies | `DF4-D1` | absorb | item | — | built `build-logs/end-user-artifact-build-log.md` |
| **DF4-I03** | What reads the brief against itself, and against the code | `DF4-D2`, `DF4-D8`, `DF4-D9` | decide | sitting | — | built `build-logs/brief-against-code-build-log.md` |
| **DF4-I05** | The procedure has no shape after `measure`. 60% of this run happened after the last gate. **Half built**: the `ship` stage shipped 2026-08-15 and does not close it | `DF4-D7` | change | sitting | — | built `build-logs/brief-against-code-build-log.md` |
| **DF4-I24** | The mechanical half of brief-against-code: `tool_effects` against the manifest | `DF4-D8` | add | cheap | — | built `build-logs/brief-against-code-build-log.md` |
| **DF4-I26** | FT-25's static occurrence check, specified in the taxonomy and not registered in `checks.py` | `DF4-D9` | add | cheap | — | built `build-logs/brief-against-code-build-log.md` |
| **DF4-I30** | The coding agent struggles to keep the build log live, and nothing enforces it | `DF4-N4` | change | item | — | built `build-logs/brief-against-code-build-log.md` |
| **DF4-I27** | The design stage is subpar: the coding agent is influenced to ask only the elicitation questions, and cannot reach a project-specific "how" | `DF4-N1` | change | sitting | — | built `build-logs/agreed-design-build-log.md` |
| **DF4-I13** | `docs/pipeline.md` §6 does not say a fake run may not reach a node declaring its own model | `DF4-P3` | fix | cheap | — | built `build-logs/consultation-build-log.md` |
| **DF4-I11** | `docs/evaluation.md` §6.2 says rollouts are independent and never says a tool holding state is shared | `DF4-P1` | fix | cheap | — | built `build-logs/consultation-build-log.md` |
| **DF4-I12** | `docs/pipeline.md` §2.2 never says what a fanned-out prompt receives | `DF4-P2` | fix | cheap | — | built `build-logs/consultation-build-log.md` |
| **DF4-I01** | Consultation, and whether the library has a concept of after | §8.1, `DF4-D9`, `DF4-D12`, `DF4-D7` | decide | sitting | — | built `build-logs/consultation-build-log.md` |
| **DF4-I08** | `_unseeded` should exempt a node execution whose `termination` is `"skipped"` | `DF4-D6` | fix | cheap | — | built `build-logs/dogfood-4-fixes-build-log.md` |
| **DF4-I09** | Refuse `retry=` on an `over=` node whose `max_failures` leaves it unable to raise | `DF4-D4` | fix | cheap | — | built `build-logs/dogfood-4-fixes-build-log.md` |
| **DF4-I15** | A `consult` tool's derived version covers the library's own function body | `build-logs/consultation-build-log.md` §7.3 | fix | cheap | — | built `build-logs/dogfood-4-fixes-build-log.md` |
| **DF4-I16** | `progress_of` was not promoted with the rest of the evaluation surface | `RULINGS.md` D2 | add | cheap | — | built `build-logs/dogfood-4-fixes-build-log.md` |
| **DF4-I25** | A development-time consult channel, and the guidance around it | §8.1 | add | cheap | — | built `build-logs/consultation-build-log.md` |
| **DF4-I39** | A step that verifies code against the brief, and sanity checks at each gate | `DF4-N15` | change | sitting | — | declined: duplicate of DF4-I03, whose frame already covers it |
| **DF4-I40** | Asking questions about and discussing recommended books | `DF4-N16` | add | item | — | declined: a feature of the dogfood project, not of the library |


### DF4-I01 — Consultation, and whether the library has a concept of after

**Finding:** §8.1, `DF4-D9`, `DF4-D12`, `DF4-D7`. **Blocked:** DF4-I04, DF4-I13, N-4, C-1.

**Scheduled 2026-08-15**, and both are built: `plan.md` §4 carries the consultation and `ship` entries.
**`build-logs/consultation-build-log.md` is the record**, and this entry is not a summary of it.

**What the sitting settled.** Development is three situations rather than one: an interactive run
answered by the builder standing in through suspend and resume, with the coding agent relaying; an
unattended run answered by `Unavailable`, or by the coding agent with the builder's permission; and
an evaluation answered by a stand-in end user the example describes and a model plays. The library
records what happened to a question and never who answered it, which is why 97 canned answers read
the same as 97 real ones, so the consultation record gains `answered_by`. There is a fifth stage,
`ship`. FT-25's check gets built, inside DF4-I03.

**Three things found in the artifacts that changed a decision.** A recorded consultation replays
for its own rollout and no other, because the cassette key carries the question text, which killed
the record-and-replay option. 103 of the 104 questions are distinct and built from that run's own
findings, which killed a list of pre-written answers on the example. And the trajectory format
already declares `timed_out` and `defaulted`, which nothing produces.

**Why DF4-I13 is behind it, which this entry did not say and should have.** `docs/pipeline.md` §6
says a `FakeModelClient` run exercises "the tools actually being called", so a fake run reaches the
project's real consult channel: dogfood #3's would block on `input()` and dogfood #4's returns its
canned prose. DF4-I13's correction is about what a "free, milliseconds" run reaches, and the sentence
it needs is "pass `unattended()` as the channel", which DF4-I01 is what ships.

**What it does not close.** `DF4-D7`. The log's §3.1: every enforcement the library has fires on
**time**, a project reaching a point, and every failure this run found fires on **change**,
something moving with nothing re-reading what it invalidated. A fifth stage adds one more gate at
the end of a longer road and does not govern the road.

### DF4-I02 — The product is a third artifact and nothing looks at it

**Finding:** `DF4-D1`. **Size:** sitting. **Blocks:** DF4-I06, DF4-I20.

`simple-agents check` reads a results file and a run directory. This project's product is a queue
in a SQLite store, written by every version of the pipeline that ever ran and read by the
interface. **85% of the judgements in it had no case at all where a fresh evaluation the same day
had 5%**, and the fabricated citation the project had most carefully chased was live in it,
unmarked. An evaluation cannot see this: a rollout starts from a seeded example and never reads
the store. It took a second session on a different task to notice.

**Scheduled 2026-08-16 as P3-6**, and [`build-logs/end-user-artifact-build-log.md`](../../build-logs/end-user-artifact-build-log.md#L1)
is the record. **Neither reading was taken whole.** No check reads the product, because that means
opening arbitrary project storage. What ships is `Pipeline.behaviour_fingerprint()`, public and
prompt-inclusive, so a stale row is a query rather than a guess; the manifest records it; one `ship`
question asks what the end user reads and what writes it; `docs/shipping.md` gains a section on an
artifact that accumulates; and `docs/failure-taxonomy.md` §10 records that the suite does not read
it. **DF4-I06 and DF4-I38 unblock and are still open**: what the artifact model does about a third
artifact, and what a UI is, are separate calls and were not taken here. *(Taken 2026-08-20: both
built as `P3-30`,
[`build-logs/the-product-build-log.md`](../../build-logs/the-product-build-log.md#L1).)*

### DF4-I03 — What reads the brief against itself, and against the code

**Finding:** `DF4-D2`, `DF4-D8`, `DF4-D9`. **Size:** sitting. **Blocks:** DF4-I24.

**The frame widened at the `ship` sitting on 2026-08-15**, on Thilina's instruction, from
brief-against-code to `idea.md`, the brief, `BUILD-LOG.md` and the code, nothing in the library
having ever read a build log:
[`build-logs/ship-stage-build-log.md` §5.2](../../build-logs/ship-stage-build-log.md#L1). It also
carries FT-25's check and `DF4-D7`'s remaining half.

Two halves, and they are different problems.

**Entry against entry.** `finished_version` said the system replaces Goodreads and owns the
reading state. `not_building` said the interface is out of scope until the schema settles. The
coding agent read the second as "a recommender is a stateless run over a CSV", built that, and
every narrow decision followed. Two stages and a measurement later the builder called it a stupid
system, and the answer that made the built design wrong had been recorded on day one, one entry
away from the answer that made it look right. FT-29 and FT-30 both passed throughout.

**Entry against code.** Four entries described a pipeline that no longer existed until the builder
said "Update the brief", and one capability had left the graph entirely.

**Scheduled 2026-08-16, and the two halves went to two items.** The mechanical half and the trigger
are P3-7, **built 2026-08-16**, and
[`build-logs/brief-against-code-build-log.md`](../../build-logs/brief-against-code-build-log.md#L1)
is the record: FT-32 reads
`tool_effects` against the manifest's tool entries, FT-25's specified check is registered at last,
FT-33 reads a build log that stopped before the runs did, and `confirmed_against` in the brief fires
a report **when the pipeline moves rather than when a gate is reached**, which is `DF4-D7`'s
remaining half. The judgement half is P3-8,
[`build-logs/agreed-design-build-log.md`](../../build-logs/agreed-design-build-log.md#L1),
because the artifact it needs is built there.

**Two corrections the sitting made to this entry.** The report is addressed to the coding agent and
not to the builder, on Thilina's ruling: *"I didn't read it."* And `behavioural_constants` in
DF4-I24 is not a library key but dogfood #4's own `constant`-kind decision, whose `chose` is free
prose, so only the `tool_effects` half is mechanical and the rest is instruction.

### DF4-I04 — The `Reply` matcher

**Finding:** §8.1, `PENDING-SIGNOFF.md` item 6. **Size:** cheap once DF4-I01 is decided.
**Unblocked 2026-08-15**: DF4-I01 is decided. `PENDING-SIGNOFF.md` item 6 stays open.

**Do not take this before DF4-I01.** A rule for reading an answer is worth nothing while nothing can
answer. The sample this run produced is 104 consultations from one node of an abandoned pipeline,
asked into a void, and **no answer in it was written by a person**.

What the sample does show, with that confound attached: 70% offered no options at all, and where
options were offered they came in two shapes wanting opposite rules — a binary written as full
sentences, where nothing a person would type matches the offered string, and a pick from a list of
titles, where whole-string equality is close to right. `options=["yes", "no"]` appears 4 times in
125 options.

**Scheduled 2026-08-16 as P3-9, and the frame widened twice in the sitting that took it**, on
Thilina's instruction: *"It's not just the shape of the question. It's the ENTIRE thing that needs
to be general. The library is not just for recommender shaped agents."*
[`build-logs/end-user-in-an-evaluation-build-log.md`](../../build-logs/end-user-in-an-evaluation-build-log.md#L1)
is the record, and this entry is not a summary of it.

**What overtook §8.1's ruling.** DF4-I01 shipped `SimulatedEndUser` on 2026-08-15, so the library
now has its own answerer, its prompt is ours, and what it produces against offered options is
measurable without waiting for a person. It was measured: **0 of 24 consultations matched**, two
personas by three option shapes by four seeds. Five of the eight pick-from-a-list answers named an
option verbatim and still resolved to `chose` of `None`. Because `on_reply` requires an `unmatched`
branch, every evaluated consultation routes there.

**Why it is no longer its own candidate.** The matcher is one of six assumptions the evaluation half
of consultation makes, and the largest of them is that the stand-in is given the persona alone and
so cannot supply a value the example knows: five of five deflections on a consultation asking for a
cost centre. A rule for reading a reply is downstream of what shape a reply can have.

**Closed 2026-08-17 by shipping no matcher.** P3-9 re-ran the 24-cell measurement and put a named
containment rule to Thilina, who declined it: *"Substring matching seems way too delicate and
error-prone to me. Can we make it so that the builder has the option to implement it themselves if
they want to, but we don't ship it by default?"* `consult(match=)` was already that option, so
what shipped is the measurement in `docs/tools.md` §4.6.1 and
`per_node.consultation_misreadings`, which reports a rule that reads none of the answers. **The
larger assumption fell too, and not the way this entry records it**: the stand-in supplies a cost
centre 5 times in 5 when the description carries one, so what was missing was a place to put it
rather than the ability to state it.
[`build-logs/end-user-in-an-evaluation-build-log.md`](../../build-logs/end-user-in-an-evaluation-build-log.md#L1) §1.

### DF4-I27 — The design stage is subpar

**Finding:** `DF4-N1` in §5, verbatim, and it is the framing rather than a summary of it.

**Built 2026-08-16 as P3-8**, and
[`build-logs/agreed-design-build-log.md`](../../build-logs/agreed-design-build-log.md#L1) is the
record. Everything the library ships for this fired and passed while the design was wrong:
sixteen decisions across six kinds, six of them `changed`, a shape decision with four alternatives
weighed, and the alternative that was right sitting in a brainstorm answer one stage up. What ships
is a `design.md` the builder agrees to before the code exists, a `shape` question that produces it,
`from =` on shape decisions with a report that computes which answers no decision rests on, and a
`procedure.md` that says the question set is a floor. **It does not make the coding agent notice a
contradiction**; it makes the plan written and put in front of the builder early.

### DF4-I31 — `over=` on one node kind, and no tools on the one that fans out

**Finding:** `DF4-N6` in §5, verbatim. **Blocks:** `DF4-I10`, `DF4-I32`, both defects in the
mechanism this moves.

**What the constraint is, read off the constructors.** It is not one hole. Three of six cells are
filled, and `Deterministic` having no `over=` is the one the row never named.

| Node kind | Tools | `over=` |
|---|---|---|
| [`Deterministic`](../../../src/simple_agents/nodes/deterministic.py#L29) | `tools=`, reached through `ctx.call_tool`, the node choosing | no |
| [`LLMNode`](../../../src/simple_agents/nodes/llm.py#L36) | no | `over=` |
| [`AgentNode`](../../../src/simple_agents/nodes/agent.py#L138) | `tools=`, the model choosing | no |

**Decided 2026-08-18. `over=` lifts to all three node kinds, and `LLMNode` gains `tools=`.** The
fan-out mechanism is about 200 lines inside `LLMNode` — [`_fan_out`](../../../src/simple_agents/nodes/fanout.py#L216)
110, [`_Failures`](../../../src/simple_agents/nodes/fanout.py#L467) 30,
[`_item_record`](../../../src/simple_agents/nodes/fanout.py#L386) 26,
[`_kept_for`](../../../src/simple_agents/nodes/fanout.py#L546) 18 and
[`_sequence_for`](../../../src/simple_agents/nodes/fanout.py#L565) 19 — and two things in it are
`LLMNode`-specific: the call to `self._one`, and `self.output_schema` for the suspend record. For
the second half, [`NodeContext.call_tool`](../../../src/simple_agents/context.py#L1413) and
`_FixedPointCaller` already exist and `Deterministic` wires them in about ten lines;
[`LLMNode.execute`](../../../src/simple_agents/nodes/llm.py#L170) builds a `NodeContext` with no caller.
Thilina on the second: *"I don't see a good reason to block that functionality."*

**The case for shipping nothing, and why it was declined.**
[`findings.md` §8.3](findings.md#L1153) checked `DF4-N6` against the artifacts and returned that
the constraint produced the better shape: it forced judging into a fan-out with a fixed evidence
floor and an optional second pass, which took per-book agreement from 0.867 to 1.0 and made batch
length stop mattering. That was put as an argument for documenting the constraint rather than
removing it, and Thilina declined it: *"I wouldn't read too much into what improved a dogfood or
not."*

**Six things the build had to decide, and [`build-logs/fan-out-and-node-shape-build-log.md`](../../build-logs/fan-out-and-node-shape-build-log.md#L1)
carries all six with what each was decided on. Three were sized wrong before the code was read**:
the `spends_money` proof needed nothing, `Deterministic` with no schema follows a rule that already
exists, and how a call is numbered is a correctness problem rather than a documentation one. The
three below are the ones this entry named.

- **Whose budget.** An `AgentNode` requires a `Budget`, and
  [`Execution.for_node`](../../../src/simple_agents/nodes/base.py#L103) narrows the run budget by it once
  per node execution. With `over=` and fifty items, `max_steps=8` is either eight steps per item
  or eight across the whole fan-out, and the reading not chosen silently produces fifty times the
  work or a fiftieth of it.
- **Suspend and resume.** `LLMNode`'s fan-out writes `{"kind": "fan_out", "done": [...]}` and a
  resumed run re-runs the items that are left. An `AgentNode` resumes from the conversation it
  had, off thirteen keys of state. A fan-out suspending mid-item either nests one of those per
  in-flight item, or discards it and runs it again from the start, re-spending its tool calls. A
  consultation inside a fan-out item is that case, and this run made 104 consultations.
- **What `concurrent_items` bounds.** Today one item is one call, so `concurrent_items=8` is eight
  calls in flight. After this, one item is an agent loop, so it is eight loops and an unknown
  number of calls. [`docs/pipeline.md`](../../../docs/pipeline.md) §1.10 documents it as "that many
  items of one fan-out", which stays true and stops being useful for pacing. `plan.md` §2.1's
  *A ceiling on how much reaches one model client* is where that goes.

**The evidence claim in the row was wrong, corrected 2026-08-18.** It read *"Met twice on
2026-08-16, in P3-7's and P3-8's live verification, each costing a rewrite"*.
[`brief-against-code-build-log.md`](../../build-logs/brief-against-code-build-log.md#L161) records
P3-7's and calls itself the second instance, counting the run as the first;
[`agreed-design-build-log.md` §4](../../build-logs/agreed-design-build-log.md#L99) lists what
P3-8's two live runs showed and names no such refusal. Two instances, one of them the run itself.

**What it moves, and what it does not.**
[`pipeline.py`](../../../src/simple_agents/pipeline/__init__.py#L1)'s module docstring says a node running
once per item "is still an `LLMNode` with `over=`", and `docs/pipeline.md` §1.2 and §2.2 say the
same to a builder. `simple-agents.md` §9 item 8 is untouched: fan-out is a property of a node
rather than a fourth kind, which is item 12's amendment applied again, and a tool on an `LLMNode`
is still reached through `ctx.call_tool` rather than by the function holding a client.

**And it restates a measurement.** [`design/module-structure.md`](../../design/module-structure.md#L28)
classifies `FanOutResult`, `ItemOutcome`, `_Failures`, `_kept_for` and `_sequence_for` as central
to `nodes.py`, so the split `plan.md` §2.1 accepted does not want this code moved out of the file.
Lifting it takes about 136 lines from `LLMNode`'s span into the module-level helper span, both
central, which changes that document's `nodes.py` table and not its conclusion.

---

### DF4-I33 — The thought signature, and the helper that drops backend state

**Finding:** `DF4-N8` in §5, verbatim. **Built 2026-08-18 as `P3-17`**, [`adapter-backend-state-build-log.md`](../../build-logs/adapter-backend-state-build-log.md#L1).

**§8.3's answer was about a wheel and it holds.** The round trip shipped in `afffc88` on
2026-08-12, before this run's wheel was built, and it is complete today.
[`ToolCallRequest`](../../../src/simple_agents/models.py#L198) holds the value on `provider` and
`to_record` writes it into the conversation and the trajectory, so a run resumed in another process
rebuilds a conversation the backend still accepts.
[`tool_calls_from`](../../../src/simple_agents/adapters/_gemini_wire.py#L187) reads it off the
response and [`contents_from`](../../../src/simple_agents/adapters/_gemini_wire.py#L38) returns it
as `thoughtSignature`. `tests/test_adapter_integration.py` asserts both halves against a recorded
live multi-turn Gemini run.

**The note's second half has an answer neither of its two options covers.** Not degradation and not
harmless: a following request whose `functionCall` part carries no signature is answered with a
400, captured verbatim at `tests/fixtures/wire/gemini/error_missing_signature.json`, and the run
measured it as 102 of 102 node executions lost.

**What checking it found is what `P3-17` ships.**
[`messages_to_wire`](../../../src/simple_agents/adapters/_openai_wire.py#L180) rebuilds each call as
`{id, type, function{name, arguments}}` and drops `provider`, with no docstring saying so, while
`docs/model-clients.md` §7 tells an adapter author to translate the conversation and points at that
helper. Correct for Mistral and vLLM, which send no state of the kind. A trap for the third:
[`plan.md`](../../plan.md#L1) §2.2's adapters entry records that Anthropic's thinking-block
signature and OpenAI's Responses `encrypted_content` are both this shape, and Google serves the
OpenAI dialect as well, so a thin adapter written off this helper reproduces this run's failure on
a path the shipped documents recommended.

**Decided 2026-08-18: a paragraph in `docs/model-clients.md` §7, a line in the helper's docstring,
and the helper raising when handed a call carrying `provider` it cannot express.** The sitting said
`ConfigurationError` and the build shipped `CallerFacingError`, because that class's own docstring
says it is raised at construction and this fires at run time on the second request, which is the
layer [`tool_calls_from`](../../../src/simple_agents/adapters/_gemini_wire.py#L187) already raises
at. The refusal cannot produce a false positive, because `provider` is non-empty only where
the same adapter filled it from its own response. What it would wrongly catch is an adapter filling
the field for the record and not needing it back; none exists, and a raise naming the field is what
a silent turn-two 400 costs otherwise.

### DF4-I34 — What the three pipeline identities cover, and what they leave out

**Finding:** `DF4-N9` in §5, verbatim. **Built 2026-08-18 as `P3-18`**, [`what-the-stamp-covers-build-log.md`](../../build-logs/what-the-stamp-covers-build-log.md#L1).

**§8.3 answered this before the third identity existed**, naming `graph_fingerprint`, `_eval_id`,
`ablate()` and `compare_variants`; `behaviour_fingerprint` shipped 2026-08-16 as `P3-6`. To the note
as asked the answer is yes, versioning is built, in three pieces.

| | Covers | Answers |
|---|---|---|
| [`graph_fingerprint`](../../../src/simple_agents/pipeline/core.py#L2055) | Node ids, kinds, edges, loop bounds, error edges, retry policies, output schemas | Can stored state still be walked? A resume compares it before restoring anything |
| [`behaviour_fingerprint`](../../../src/simple_agents/pipeline/core.py#L2070) | The above, plus prompt versions, sampling parameters, per-node tool **names**, declared model, `allow_unknown`, budgets | Which version of the pipeline produced this stored result? |
| [`_eval_id`](../../../src/simple_agents/evaluation/runner.py#L1162) | The above, plus the example set's content hash, seed, split, k, the run's model identity, the stand-in end user | Did these two evaluations measure the same thing? |

A model arm in a sweep is a `Pipeline` whose node declares `model=`, so `compare_variants` moves
`behaviour_fingerprint` and sweeps are unaffected by what follows.

**Three things decide what a pipeline produces, are recorded in the manifest, and are in neither
fingerprint.** Measured 2026-08-18 on two pipelines differing in one tool's body::

    tool version moved True   (sha256:0c41a2086c09 vs sha256:20fa9411da88)
    graph equal        True
    behaviour equal    True

1. **The run's model client.** `_node_entries` records what a *node* declared and `null` where the
   node takes the run's, and `behaviour_fingerprint` takes no model argument.
2. **Every tool's implementation.** `_node_entries` computes the tool entries carrying `version`,
   `side_effect_class`, `declared_cost`, `re_executed` and `reader`, writes them straight into the
   manifest, and puts them in neither digest. The per-node `tools` field is names only.
3. **A consultation reader's model and prompt**, recorded by
   [`_reader_entry`](../../../src/simple_agents/pipeline/recording.py#L201) under `tools[].reader`. This is
   the library-owned model call on a `Deterministic` node that `P3-12` shipped, and
   [`plan.md`](../../plan.md#L1) §2.1 already calls it the first such call a shipped agent carries
   into production rather than only into an evaluation.

**It lands on the recipe the stamp was built for.** `docs/shipping.md` §6 tells a project to take
`behaviour_fingerprint()`, write it beside each stored row, and query for the rows a current
pipeline did not produce. Swap the client at `run(model=)` or edit a tool and the query returns
nothing. [`_the_pipeline_moved`](../../../src/simple_agents/conformance/run.py#L401) reads the same
value, and `backend` is one of the twelve `about_the_pipeline` questions, so a backend swap never
marks the brief entry due.

**The omission was never a decision.**
[`end-user-artifact-build-log.md`](../../build-logs/end-user-artifact-build-log.md#L76) §3 lists
four ingredients as though they were the set, and its §6 does not mention tools.

**Decided 2026-08-18.** `behaviour_fingerprint(model=None)` digests the tool entries and the run
client's identity where a model-calling node takes it, and **refuses rather than returning a stamp
it knows is partial**: the pipeline knows which of its model-calling nodes declared no client, so it
raises naming them and the call that fixes it. Where every such node declares its own, the run
client stays outside the digest, which is the rule `docs/run-envelope.md` §2.2 already states for
`models.configured`. `graph_fingerprint` is untouched, because none of this bears on whether stored
state can be walked. Run-envelope format bump; 134 fixture files carry one distinct value and
`scripts/build_conformance_fixtures.py` regenerates them.

**A tool's `version` is included, on Thilina's call**, knowing it is source-derived and moves on a
comment. The case worth catching is a tool that silently starts returning different data, and the
alternative of everything-but-`version` misses exactly that.

**The `_eval_id` half went to `DF4-I07`**, on Thilina's call that sitting 3 takes one question about
that identity rather than two.

### DF4-I35 — Progress, and which of the three channels renders

**Finding:** `DF4-N10` in §5, verbatim. **Built 2026-08-18 as `P3-19`**, [`progress-display-build-log.md`](../../build-logs/progress-display-build-log.md#L1).

**§8.3 called this discoverability rather than a missing feature, and it is both.** `progress_of`
did ship off `DF3-D3`, and the project did rebuild it by globbing manifests, wrongly twice. What
that reading missed is that three channels ship progress data and one renders.

| Channel | Renders? |
|---|---|
| `EvalSuite.run(on_rollout=)` → `RolloutProgress` | Yes. [`describe`](../../../src/simple_agents/evaluation/runner.py#L160) returns one line |
| [`progress_of`](../../../src/simple_agents/evaluation/progress.py#L204) | No. It returns a dict, and `simple-agents` has no subcommand over it |
| `Pipeline.run(on_progress=)` → [`NodeEvent`](../../../src/simple_agents/pipeline/events.py#L61) | No, and it cannot |

**The row's own words are wrong about which channel is which**: `on_rollout=` is the one that
renders. **And `P3-16` widened the gap on 2026-08-18.** `NodeEvent` carries `item_index` and no
total, so a caller watching a 929-item fan-out has no denominator and cannot derive one, since
`over=` names a field of the node's input resolved at run time. The count is in scope where the
event is built, at [`announce`](../../../src/simple_agents/nodes/fanout.py#L304), and is not put on it.

**Nothing repaints.** Every documented example is `print(...)`, so a 165-rollout evaluation emits
165 lines, which is a log rather than the bar the note asks for.

**Decided 2026-08-18: `tqdm`, as a required dependency.** Thilina: *"Why not just use tqdm? It looks
good, and it usually just works. I didn't make a rule about not adding dependencies. Especially not
tiny ones like tqdm."* He is right that no such rule exists, and the two-dependency wheel had been
described here as a constraint when it is a status quo. 4.70.0 is an 80KB wheel with no required
runtime dependency outside Windows `colorama`, Python ≥3.8, and it handles TTY detection, width,
ETA, notebook detection and thread-safe `update()`, which matters because
[`saw`](../../../src/simple_agents/evaluation/runner.py#L259) reports from several rollout threads.
It takes `total=None` as a counter, which covers the one case with no denominator: a pipeline does
not know how many nodes will run, because loops and routes decide that in flight. Its licence is
MPL-2.0 AND MIT against the library's Apache-2.0, which as a dependency rather than vendored source
imposes nothing.

**Required rather than an extra, on Thilina's call.** An extra means two code paths and a fallback
that has to be written anyway.

**What ships on top, because tqdm answers rendering and not wiring.** A `ProgressBar` that both
`on_progress=` and `on_rollout=` accept as given, `item_total` on `NodeEvent`, and
`simple-agents watch <run_dir>` over `progress_of`. A builder left to wire tqdm themselves is back
to assembling a display out of three channels, which is what this run did by hand and got wrong
twice.

### DF4-I08 — `_unseeded` should exempt a node execution whose `termination` is `"skipped"`

`DF4-D6`

*(Restored 2026-08-15 from the pre-reorganisation row `F-1`.)*

### DF4-I09 — Refuse `retry=` on an `over=` node whose `max_failures` leaves it unable to raise

`DF4-D4`

*(Restored 2026-08-15 from the pre-reorganisation row `F-2`.)*

### DF4-I10 — A transport failure inside a fan-out is classified as an abstention

`DF4-D3`

*(Restored 2026-08-15 from the pre-reorganisation row `F-3`.)*

### DF4-I11 — `docs/evaluation.md` §6.2 says rollouts are independent and never says a tool holding state is shared

`DF4-P1`

*(Restored 2026-08-15 from the pre-reorganisation row `F-4`.)*

### DF4-I12 — `docs/pipeline.md` §2.2 never says what a fanned-out prompt receives

`DF4-P2`

*(Restored 2026-08-15 from the pre-reorganisation row `F-5`.)*

### DF4-I13 — `docs/pipeline.md` §6 does not say a fake run may not reach a node declaring its own model

`DF4-P3`

*(Restored 2026-08-15 from the pre-reorganisation row `F-6`.)*

### DF4-I14 — `too_similar` reached the builder as a bare threshold rather than the pairs to judge

`DF4-P4`

*(Restored 2026-08-15 from the pre-reorganisation row `F-7`.)*

### DF4-I15 — A `consult` tool's derived version covers the library's own function body

consultation build

*(Restored 2026-08-15 from the pre-reorganisation row `F-8`.)*

### DF4-I17 — `noise_floor.py`: repeat one configuration n times and report the range

**Repeat one configuration n times and report the range.** The strongest absorption in the run: it
produced the number every comparison in the project should be read against, and it then killed one
of the project's own proposals on its own evidence. Nothing in the library measures how much a
figure moves with nothing changed

*(Restored 2026-08-15 from the pre-reorganisation row `A-1`.)*

**Built 2026-08-20 as `P3-27`'s stages 2 and 3**, and
[`build-logs/what-a-figure-is-reported-against-build-log.md`](../../build-logs/what-a-figure-is-reported-against-build-log.md#L1)
is the record. This entry is not a summary of it. Two things were settled that this entry's
framing does not carry.

**The repeat is not the instrument.** Measured at the sitting: the observed run-to-run sd of
0.0210 is predicted at 0.0170 by the **within-example** rollout variance those same runs already
recorded, so most of what three full evaluations bought is computable from one run's own rollouts.
Four of 33 examples were ever non-unanimous, and those four are the whole floor. Repeats stay a
documented recipe.

**What the floor is for is the report first and the verdict second.** Measured at the build over
300 pairs of runs of one configuration: `compare()`'s interval excludes zero on 12 of them, which
is what a 95% interval means rather than a defect, and the noise guard withholds 5 of those 12.
What was missing is the scale itself. Nothing told a reader comparing four arms across a span of
0.04 that one configuration run twice moves by that much.

### DF4-I18 — Every figure reportable grouped by a property of the example

**Per-class recall and the do-nothing baseline reported beside the headline.** The project reached
this after two splits with baselines of 0.61 and 0.81 nearly produced "the agent has no skill"
when most of the gap was the denominator. `compare()` reports the headline and the interval and
not the mix

**Widened 2026-08-17 at the P3-10 build, on Thilina's question.** Per-class recall is one instance
of a general shape: report a figure grouped by something about the example, because a pooled
number hides the mix. Three instances, two of them already in this run's own record.

1. **The one this row was written for.** Two splits at baselines of 0.61 and 0.81, where reading
   one against the other nearly produced "the agent has no skill"
   ([`findings.md` §9](findings.md#L850)).
2. **A pooled number that destroyed a measurement.** The characterisation pass improved `shelve`
   and damaged `skip`, the split's 70/30 prevalence cancelled them in the headline, and the result
   was **reported as a null result** against the project's own recorded warning about prevalence
   ([`findings.md` §7](findings.md#L938)). This is the strongest evidence in the run for this row,
   and it was filed under builder interventions rather than here.
3. **An agent serving more than one end user.** Raised 2026-08-17. `P3-10` makes an answer key a
   function of who is being served, so one criterion check covers two hundred readers, and nothing
   then reports how the agent did for each of them. The per-criterion figures `P3-10` ships cut
   across criteria; this cuts across examples, and the two are different axes.

**What it would cost:** the grouping is a property read off `Example.metadata`, and every figure is
already a `Metric` carrying its own `rollouts` and `examples`, so a small cell states its own n.
What has to be decided is whether `compare()` pairs on the cells, and what a stratified results
file looks like. **The small-cell objection is not an argument against it**: instance 2 is a
measurement lost to *not* grouping, and how many examples fall in a cell is a property of the
project's set rather than of the library.

*(Restored 2026-08-15 from the pre-reorganisation row `A-2`.)*

**Built 2026-08-20 as `P3-27`'s stages 1 and 4**, and
[`build-logs/what-a-figure-is-reported-against-build-log.md`](../../build-logs/what-a-figure-is-reported-against-build-log.md#L1)
is the record. Three things were settled and this entry is not a summary of them.

**The grouping key is stored, and the cut is taken afterwards.** `Example.metadata` goes into the
results file and `results.grouped(...)` reads it, rather than a `group_by=` declared before the run
is paid for. This project decided to report per class **after** seeing the null result, which a
run-time declaration would have made unavailable on runs already made. It also makes
[`examples.py`, `Example`](../../../src/simple_agents/evaluation/examples.py#L53) true, which today
claims `metadata` is carried through to the results and is not.

**`compare()` needs no new pairing rule.** It already pairs per example, which is finer than per
cell, so the paired difference is free of the mix; what grouping adds is a paired difference per
cell, which is instance 2's case. The small-cell objection this entry pre-empts was checked and
holds: `MINIMUM_EXAMPLES_FOR_A_VERDICT` already withholds a verdict on a small cell.

**The baseline is computed rather than written.** Measured at the sitting: all 30 of this project's
results files carry one frozen baseline sentence, naming a split of 20/14/2 at 0.56 after the
splits were rebalanced to 22/6/1 at 0.759, and 15 of them are `dev` runs whose own floor is 0.676.
`brief.toml` reports 0.82 [0.68, 0.94] against 0.76 on `held_out`, so the interval contains the
floor and so does every other arm ever run on that split. `EvalSuite(baseline=...)` scores a
constant answerer through the same `matches` over the split that actually ran.

### DF4-I19 — Compare the prompts that were actually sent

**Check that k rollouts of one example sent the same prompt.** They already carry their prompts
and the declared version. 15 of 102 rollouts differed between two evaluations because a set
iteration order was not pinned, and part of the spread across four model arms is that rather than
the arms

*(Restored 2026-08-15 from the pre-reorganisation row `A-3`.)*

**Built 2026-08-19 as `P3-20`'s stage 2**, and
[`build-logs/evaluation-identity-build-log.md`](../../build-logs/evaluation-identity-build-log.md#L1) is the record. Three
things were settled and this entry is not a summary of them.

**It is one reader with two groupings, not two items.** Pull the prompts out of the trajectories,
group them, compare. Grouped inside one evaluation it catches the sorting bug above; grouped
across two evaluations it is the only thing that sees a project's data change with nothing
declared, which is `DF4-I07`'s case and which no declaration can reach.

**It reports and never fails.** The library cannot tell this bug from a project working as
designed: a prompt reading the clock, a prompt reading memory that accumulates, or a tool holding
state, which is `DF4-X1` above and which this project has. A check that failed on it would fire
on correct projects.

**`DF4-I23` is the same sentence.** The pre-reorganisation inventory filed it under `A-3`, what
can be absorbed, and again under `N-2`, what can be added, which is the failure this document's
preamble already records for `A-5`. `absorb` was wrong on both: the project fixed its own sorting
bug and built no checker, so there is nothing to take into the library.

### DF4-I20 — Staleness as a query, plus something that refreshes what it identifies

**Staleness as a query, plus something that refreshes what it identifies.** The project's own
correction is the useful half: an identifier for staleness alone would have cut its queue from 19
books to 6 rather than fixed it S-2

*(Restored 2026-08-15 from the pre-reorganisation row `A-4`.)*

### DF4-I21 — A report line for an agentic node that reached `max_steps` having called no tool

**A report line for an agentic node that reached `max_steps` having called no tool.** 188
executions, 3,384 model calls, **15% of the run**, and everything needed to see it is already in
the trajectory

*(Restored 2026-08-15 from the pre-reorganisation row `A-5`.)*

### DF4-I05 — The procedure has no shape after `measure`. 60% of this run happened after the last gate. **Half built**: the `ship` stage shipped 2026-08-15 and does not close it

`DF4-D7`

*(Restored 2026-08-15 from the pre-reorganisation row `C-1`.)*

### DF4-I07 — What an evaluation's identity covers

`DF4-D11`

*(Restored 2026-08-15 from the pre-reorganisation row `C-3`.)*

**It is the criterion-versioning problem from the other side**, noted 2026-08-18 when it moved
out of `plan.md` §1's prose. `P3-10` asked what moves a figure when a *check* changes and
answered it with `source_version`; this asks what an evaluation's *identity* covers, and the
answer today is what the pipeline declares. `P3-10` read this entry and left it here, so P3-1
owns it. `plan.md` §2.2's *A criteria set declared once and referenced* is the third face of it,
and `P3-12` took the judged half of that on 2026-08-18.

**`P3-18` handed this entry a second face, 2026-08-18.** `_eval_id` digests
`_measured_configuration`, whose node entries carry tool **names** and no versions, so two pipelines
differing in a tool body resolve to one `eval_id`: measured that day with `graph_fingerprint`, the
prompt versions and the whole measured configuration all equal. Re-running is then refused as a used
directory, which names the wrong cause. `P3-18` fixes the stamp and leaves this here, on Thilina's
call that sitting 3 takes one question about this identity rather than two. *(That paragraph also
said `resume_from` is worse because
[`_refuse_a_moved_pipeline`](../../../src/simple_agents/evaluation/runner.py#L995) compares
`graph_fingerprint` alone. `DF4-X11` corrects it: the resume is allowed, and the reason is that
`_refuse_a_moved_configuration` carries tool names.)*

**Built 2026-08-19 as `P3-20`'s stage 1**, and
[`build-logs/evaluation-identity-build-log.md`](../../build-logs/evaluation-identity-build-log.md#L1) is the record, with the
four gaps measured and the two options that were not taken.

**Two more faces were found at the sitting, and neither was in this entry.** A `Deterministic`
node's body is versioned nowhere, so an edit to one moves `graph_fingerprint`,
`behaviour_fingerprint`, the measured configuration and `eval_id` not at all: this project is 4
such nodes of 6 in `agent.py` and 8 of 12 in `recommender.py`, and the store `DF4-D11` turns on is
read by two of them. And a declared `prompt_version` replaces the source hash rather than
accompanying it, so declaring a version, which is what FT-15 asks for, is what switches off the
only automatic trace. What ships records the hash beside the declaration and digests the
declaration alone.

**What was decided over what.** A declaration surface, which is what `DF4-D11` asked for, rather
than a dedicated `run(measured_over=...)` seam: the idiom already exists three times as
`prompt_version=` and `version=`, and neither option is more automatic, since both rest on the
builder changing a string. What catches a data change with no builder discipline at all is
`DF4-I19`, which is why the two are one item.

### DF4-I25 — A development-time consult channel, and the guidance around it

§8.1

*(Restored 2026-08-15 from the pre-reorganisation row `N-4`.)*

### DF4-I26 — FT-25's static occurrence check, specified in the taxonomy and not registered in `checks.py`

`DF4-D9`

*(Restored 2026-08-15 from the pre-reorganisation row `N-5`.)*

### DF4-I41 — `CHANGELOG.md` cites a `dev-docs` document the builder cannot read

`CHANGELOG.md:54` names `build-logs/dogfood-4-fixes-build-log.md`. The changelog ships in the
wheel and the build log does not, so a builder following the reference reaches nothing.

**Carried from the housekeeping section this document lost on 2026-08-15**, where it read: *"Open,
and not changed: `CHANGELOG.md` cites `dogfood-3/findings.md` three times. It is a shipped,
builder-facing file naming an internal document the builder cannot read. The names were updated so
nothing is stale; whether the citations belong there at all is a separate question."* The three
dogfood-3 citations are gone; one build-log citation replaced them, so the question stands and the
count has changed.

**What has to be decided:** whether a changelog entry may cite an internal record at all. The
alternative is that it says what changed and stops, and the record is found through
`dev-docs/`. `scripts/prose_check.py` already refuses a reference to `dev-docs` from a
shipped file, and `CHANGELOG.md` is in its checked set, so the current line passes only because
the path does not carry the `dev-docs/` prefix.

**Decided 2026-08-16: it may not.** A changelog entry says what changed and stops. `CHANGELOG.md:109`
is corrected and logged as `DF4-X8`.

**And the scope is wider than the changelog, which is why this stays open.** `tests/` is in
`prose_check.py`'s checked set and carries **eight citations of `dogfood-3-findings.md`** across
`test_rescore.py`, `test_conformance.py`, `test_eval_metrics.py` and `test_tool_contract.py`. That
filename has not existed since the reorganisation of 2026-08-15 renamed it to
`runs/dogfood-3/findings.md`, so they are internal and stale. The fix is not mechanical: dropping
the filename leaves a bare `DF3-D5`, which a builder also cannot resolve, so the choice is to drop
the citation or to keep an id that only a maintainer can follow in a file a builder reads.

**The structural half, so it cannot come back.** `INTERNAL_REF` catches `dev-docs`,
`simple-agents.md`, `plan.md` and `handoff.md`, and the changelog line passed because
`build-logs/…` carries no `dev-docs/` prefix. Tested against the whole checked set on
2026-08-16: `build-logs`, `build-log.md`, `inventory.md`, `random-thoughts`, `RULINGS`,
`check_docs`, `items/`, `archive/` and `templates/` have zero hits outside the corrected line, and
`findings.md` has only the eight above. **`runs/` must not be added**: it is a legitimate project
directory that appears throughout `docs/`.

*(Restored 2026-08-15 from the housekeeping section of `7d1cf4b`. It is housekeeping rather than
a run finding, which is why its evidence is a commit and not a `DF4-D` id.)*


## 4. What the next run must measure

The input to the next run's `setup.md`, written now rather than reconstructed later.

| # | Question | Why it is open |
|---|---|---|
| **DF4-Q1** | **Does a consultation design survive a run where the builder is genuinely the channel?** | Two runs have used `consult` and neither reached a person. Whatever `DF4-I01` shipped is unmeasured against a real answerer |
| **DF4-Q2** | **Is the store-versus-results-file split general, or this project's?** | `DF4-D1` is one project that owns state. Dogfoods 1 and 2 did not, and dogfood 3's state was a file it rewrote |
| **DF4-Q3** | **Does `brainstorm` with room to wander change anything?** | Its test is a run told to explore against one that is not, and nothing records the exchange that did not happen. Thilina's note of 2026-08-11 |
| **DF4-Q4** | **Semantic recall, still unmeasured by any dogfood** | `archive/plan-history.md` §1.8. This run is the first evidence and it is indirect |
| **DF4-Q5** | **A seam for a project-supplied count or total** | `plan.md` §2.1. Three of three dogfoods that got as far as caring have reached for one and built it by hand |

## 5. Thilina's notes from the run, verbatim

Written 2026-08-14, during and after the run. **His words, unedited**, because the framing and
the constraint are both in the wording and a summary loses them. `DF4-N5` and `DF4-N11` are §1's
`DF4-L6` and `DF4-L7`; every other note is cited as evidence by a candidate in §3.

*(Restored 2026-08-15 from `7d1cf4b`. The reorganisation earlier that day replaced these with
one-line summaries and carried none of the original text, so the next session could not tell
which words were his. That is what this section exists to prevent.)*

**DF4-N1.** The design stage is still subpar. The coding agent made decisions that it didn't run by me and ended up with a hilariously bad design. I think part of the issue is that we might be influencing the coding agent to ONLY ask the elicitation questions. That's not good. We can't plan for all the questions that would need to be asked from the builder, especially when designing. What that stage should cover is making sure the coding agent gathers information properly. So something needs to tell the agent to make sure it knows what the builder wants to build _properly_ and _how_ they want it built, then iterate on the how until they are both happy with the plan. It's the process we followed for the library, and the process we still follow for every new thing. And it usually works.

**DF4-N2.** It asked me a question about contamination or something going from 0.8 to 0.4 or whatever. No context given, no defining the terms. A random builder would have no idea what it was talking about.

**DF4-N3.** The agent rarely, if ever, volunteers sources that could be used. It certainly does not use it's own web search capabilities to find sources. It should offer to do this more. E.g. see if book award websites have lists that could be used to find candidates.

**DF4-N4.** It really struggles with keeping the build-log live. I think this needs stronger enforcement. Of course, the build-log might be more useful for us than for a casual builder, so I don't know if it's a big deal.

**DF4-N5.** It almost feels like the coding agent (you in the dogfood session) is dumber than you here. But that might be an artifact of this library being relatively well-defined, versus the dogfood being open-ended and less clear.

**DF4-N6.** "LLMNode has over= but no tools; AgentNode has tools but no over=. So "one book per call" and "can look up more" can't be one node — which actually points at a better shape. Let me check the backfill first." from the agent's chat window. I think it's a good thing, but flagging it in case it deserves a look.

**DF4-N7.** " the store step only writes at the end of the fan-out". Is this true and library-side? If so, isn't that a bad design?

**DF4-N8.** "Gemini 3 returns a thought_signature in extra_content.google and expects it back on later turns; the library's message shape has no field for it, so it's dropped. I don't know whether that degrades multi-turn tool use or is harmless." Is this true?

**DF4-N9.** Some sort of versioning for pipelines to make it easier to run evaluations/ablations? Or is that the ablation feature we ship already?

**DF4-N10.** I think we really need clear progress bars/indicators for things that are running. This was a highly rated feature in Simple Transformers. I personally hate not knowing how long something has left.

**DF4-N11.** The coding agent makes simple mistakes, not sure why. Too much context from the docs? Even though the context window isn't full enough to show the compact warning. E.g. it says that it's running/ran something but hasn't actually done it. It starts runs and doesn't watch if it finishes.

**DF4-N12.** Can the library check for stupid shit that happens? Like a node that just spins in the air doing nothing until it hits max steps? More verification? I know it's hard to judge correctness of arbitrary projects and their decisions.

**DF4-N13.** It scatters files everywhere and there is no organisation. I would expect a coding agent to handle this by itself, but apparently not.

**DF4-N14.** Something I discovered when I tried to start a UI building session. There is no separation between the evaluation and testing runs and the more "production" level data the UI would need. And nothing guides the coding agent to make this separation. So the UI building session, AFAIK, essentially saw a queue of all the recommendations that have landed including the earliest, bugged ones. On the other hand, there is also no integration between the UI and the agent code. The UI is always designed as just a display for the already stored outputs from the system itself. And the coding agent always tries to make a very basic, bare-bones UI rather than an actual system.

**DF4-N15.** We need a go back and verify the code against the brief/plan/whatever step. Maybe also sanity checking things that need to be sanity checked at each gate. I'm not sure where it should go, but maybe it's a required step to pass a gate.

**DF4-N16.** This is something I want for myself so just writing it as a reminder: Being able to ask questions and discuss recommended books.
