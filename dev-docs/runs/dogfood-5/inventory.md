# Dogfood #5 — inventory

Everything actionable from [`findings.md`](findings.md#L1), in one place, so `plan.md` and
`handoff.md` can point here rather than carrying it.

**Nothing here is agreed work.** `plan.md` §1's rule stands: everything agreed to be built is
scheduled there and nowhere else. This is the **input** to `plan.md` §1 `P3-32`.

**Sections are by where an item goes next.** §1 goes nowhere, §2 is already applied, §3 goes to
`plan.md`, §4 goes to the next run's `setup.md`, and §5 is Thilina's notes verbatim, because the
framing and the constraint are both in the wording and a summary loses them.

**The inventory says what to do. `findings.md` says why we believe it.** Every row names its
finding rather than repeating it. A citation between the two resolves both ways: this side is
the source of truth and `check_docs.py --fix` writes the `**Acted on:**` lines in `findings.md`.

**Drafted 2026-08-25.** Every disposition is Thilina's, taken at a sitting and written to the row,
which is the mode agreed for this run's records on 2026-08-24. **`P3-32` is done when no candidate
is still `open`**, and `P3-31`, going public, waits on all of it, decided 2026-08-25. **Sitting 1
was taken and built on 2026-08-25**: eight candidates, `DF5-I01` to `DF5-I07` and `DF5-I37`,
shipped as [`P3-33`](../../plan.md#L519). **Sitting 2 was taken and built on 2026-08-25**: five
candidates, `DF5-I08` to `DF5-I12`, shipped as [`P3-34`](../../plan.md#L507). **Sitting 3 was
taken on 2026-08-26** and scheduled four items rather than one: `DF5-I13` and `DF5-I16` answered
[`P3-29`](../../plan.md#L1)'s open question and were folded into it, `DF5-I14` and `DF5-I15` went to
`P3-36`, **built 2026-08-26**, and `DF5-I17`, `DF5-I38` and the two raised at the sitting went to `P3-37`. `DF5-I22` left
sitting 4 for [`P3-35`](../../plan.md#L1). **Sitting 4 was taken on 2026-08-27** and scheduled
five items: `DF5-I18`, `DF5-I20` and `DF5-I21` went to `P3-44`, `DF5-I19` to `P3-45`,
`DF5-I29` to `P3-46`, `DF5-I26` to `P3-47`, and `DF5-I31` to `P3-48` with `plan.md` §2.1's
count-or-total seam. **Four `plan.md` §2.2 entries closed with it** and a fifth narrowed from
six answer shapes to four. **Sitting 5 was taken on 2026-08-28** and scheduled one item:
`DF5-I23`, `DF5-I24` and `DF5-I25` all went to [`P3-50`](../../plan.md#L1), which carries
`plan.md` §2.1's `Cassette.update` entry as the other half of `DF5-I25`. It also created
[`P3-51`](../../plan.md#L1), the results visualiser, which is no candidate here, and deferred one
proposal of its own into §2.2. **Sitting 6 was taken on 2026-08-28** and scheduled two items:
`DF5-I27` went to [`P3-52`](../../plan.md#L1) and `DF5-I28` to [`P3-53`](../../plan.md#L1), which
carries `plan.md` §2.2's per-node ratio entry as the other half of it. **Sitting 7 was taken on
2026-08-28** and scheduled one item: all four of `DF5-I32` to `DF5-I35` went to
[`P3-54`](../../plan.md#L533), **built the same day**, which carries `plan.md` §2.1's `ConfigurationError`-in-a-fan-out
entry and §2.2's resumed-fan-out-bar entry, both closed with it. **Sitting 8 was taken on 2026-08-28**, the last: `DF5-I36` folded into [`P3-31`](../../plan.md#L30) rather than becoming an item, and with it **40 candidates, 0 open**, so `P3-32` is done. *(`P3-50` built 2026-08-28.)* *(`P3-37` built 2026-08-27; `P3-44` to `P3-48` built by 2026-08-28.)*

---

## 1. What we learned

Belief updates. No work attached; they change how the next thing is read.

| # | What | From |
|---|---|---|
| **DF5-L1** | **Consultation met a product, and 104 of 109 questions never reached it.** The once-per-run rule was built for a model asking a person who is not there; a `Deterministic` node asking one question per item is the other case, and the mechanism keys on the tool's name and cannot tell them apart. Every consultation figure the library reports is a count of recordings: 1,654 records, 109 questions, 5 put to a person, 2 answered | `DF5-D1`, `DF5-D2` |
| **DF5-L2** | **The product concept and the research stage both held at a cold start.** `used_through` was answered with a surface and a trigger mix, fourteen interactions were classified four ways and the coding agent cited the classification unprompted; nine parts were decomposed before a search was run, every candidate carried an outcome, and FT-36 passed. `DF4-N14` did not recur | §2, §3.7 |
| **DF5-L3** | **An instruction with no gate behind it is not followed, and a facility named once in a document is not reached.** `simple-agents check` ran 21 times in 116 commits; `confirmed_against` and `simple-agents report` never, though the report's first line named the two failures the log spent three exchanges finding by hand. **`report` was named**, in bold, at [`docs/procedure.md`](../../../docs/procedure.md#L259) stage 5 `measure`; what separates it from `check` is that `check` is named at nine places including every gate and `report` at one (`DF5-X7`). Sixteen library facilities were never reached, and the project rebuilt progress, per-node figures, a noise floor, grouping, the staleness refresh and retry by hand. The one gate that fired during legitimate work, FT-33 under a corpus pass, was taught to the next session as noise | `DF5-D6`, `DF5-D4`, §2 |
| **DF5-L4** | **Every check fires on a project reaching a point, and this product was built after the last one.** Thirty exchanges and 45% of the log came after `ship`, with every check green throughout. `DF4-D7` for the third time, one stage later each time | `DF5-D19` |
| **DF5-L5** | **The manifests carry per-stage elapsed from `build` onward, to the minute, and nothing before it.** Brainstorm, research, shape and design left fourteen dated log sections and no stamp. The log's few clock times were read rather than composed, so dogfood #3's finding did not repeat | §1.4 |
| **DF5-L6** | **The thin-agency reading came true, and the evidence for it is confounded.** Zero `AgentNode` at the freeze, both removed before the first commit, and the builder opened the post-ship conversation with "expanding the agency". Most of the "agency does not converge" evidence was a 4-bit 30B model on a 16k window | `DF5-D7`, `DF5-D9`, §4 |
| **DF5-L7** | **The protocol's asymmetry did not hold for a product the builder wanted**, as `setup.md` §6 said it would not. Seven interventions the builder was forced into, each something the library could have put in front of the coding agent; four questions he could not answer as put, which is `DF4-N2` again after `P3-28` fixed one instance of it; and the process reminders, the log and the commits, the procedure owns and he had to give | §3.8 |
| **DF5-L8** | **Three of the analysis's first readings were wrong, and each was a name or a mechanism read once.** `consultations` for `consultation`, `key` for `name`, and FT-33 tripped by the corpus pass rather than by the end user. A reading is checked against the source and the source against the artifacts before it is written | §1.3 |
| **DF5-L9** | **The count seam's evidence did not arrive.** `DF4-Q5` predicted a tracker is counts everywhere; the project's counts are page sizes and labelling progress, which the library does not cover, and the run-progress case carries no count. The §2.1 entry stands on three earlier runs and gains nothing from this one | §2 |
| **DF5-L10** | **The absence machinery moved three of this project's figures without the report saying so**: a headline whose false-confidence rate is partly four held-out examples invented to satisfy FT-04, a baseline floor at 0.0 where the project's metric returns 1.0, and a denominator that dropped the worst case | `DF5-D23`, `DF5-D18`, `DF5-D29` |

## 2. What was corrected

A statement the run disproved, and where it was written. **Applied on sight, never queued**, so
this is a log rather than a backlog.

| # | The statement | Where it was written | Corrected |
|---|---|---|---|
| **DF5-X1** | "`None` on a run still executing", of `outcome` in the `runs()` field table | `docs/run-envelope.md` §8 | 2026-08-25, on sight while `findings.md` was written, uncommitted: "`None` on a run still executing, or on one whose process ended before it wrote its outcome". `DF5-I25` is the mechanism that would make the two distinguishable |
| **DF5-X2** | Overtaken: "Four dogfoods have run" and "Ran four times" | `handoff.md` under *Where the build stands*; [`dogfood-protocol.md`](../dogfood-protocol.md#L6) | 2026-08-25: five, dogfood #5 on 2026-08-20 to 24 |
| **DF5-X3** | Overtaken: "dogfood #5 runs first and feeds it" | `plan.md` §1, `P3-31`'s state; `handoff.md`, "dogfood #5 runs first" | 2026-08-25: it has run, `P3-32` works it through, and `P3-31` waits on all of it (`DF5-X5`) |
| **DF5-X4** | "Thilina's four notes from the run are quoted verbatim where they land and numbered `DF5-N1` to `DF5-N4`" | [`findings.md` §3](findings.md#L219) | 2026-08-25: five, `DF5-N5` being the note of 2026-08-25 quoted at `DF5-D23`; §3.8 already said five. *(§1.1's "its four notes" is the conformance check's and stands.)* |
| **DF5-X6** | Overtaken: "Thilina's five notes from the run are quoted verbatim where they land and numbered `DF5-N1` to `DF5-N5`" | [`findings.md` §3](findings.md#L219) | 2026-08-25 at sitting 1: six, `DF5-N6` being his note scoping `DF5-I37`, and it is from the sitting rather than from the run. *(§3.8's "the five notes" is a count of what the run wanted and never asked for, and stands.)* |
| **DF5-X7** | "a facility no gate names is not reached", of `simple-agents report` | `DF5-L3`, this record | 2026-08-26 at sitting 3, on Thilina's challenge: *"perhaps, the library never instructed the coding agent to use `report`. How was the coding agent supposed to know?"* Measured against `docs/procedure.md`: `report` **is** named, in bold, at stage 5. `simple-agents check` is named at nine places including every one of the six gates and `report` at one, so what failed is surfacing at the moment of use rather than a missing gate. The learning is reworded and `DF5-I16`'s disposition rests on the corrected version |
| **DF5-X8** | Overtaken: "six, `DF5-N6` being his note scoping `DF5-I37`" | §5's header, and `DF5-X6` | 2026-08-26 at sitting 3: nine. `DF5-N7`, `DF5-N8` and `DF5-N9` are from that sitting, and `DF5-N7` created `P3-35` rather than scoping a candidate |
| **DF5-X9** | "`agency_boundary` names two agentic steps in a project with none", and the record's silence about any other | [`findings.md` `DF5-D7`](findings.md#L486) | 2026-08-26, at `P3-35`'s prototype, on sight: **three steps ran as `AgentNode`**, not two. 18 of 2,393 manifests carry a node of kind `agent`, all on 2026-08-20; fifteen are `find_candidates` and `hunt_reviews`, three are `judge_candidates` alone, which the brief, the decision and this record all omit. The finding's own two claims stand. It was found by assembling the artifacts rather than by reading them, which is [`P3-35`](../../plan.md#L1)'s premise |
| **DF5-X10** | "`docs/pipeline.md` §5 covers suspension itself", and "`Pipeline.resume` continues it when the answer comes back (`docs/pipeline.md` §5)" | `docs/product.md` §4.1; `docs/shipping.md` §4 | 2026-08-27 while building `P3-37`, on sight: §5 is Budgets and suspension is §1.8. Both corrected. Three other citations of §5, in `docs/model-clients.md` and `docs/trajectory-format.md` twice, are about budgets and stand |
| **DF5-X15** | "`docs/procedure.md` §4 is how a coding agent uses these" | [`decisions.py`](../../../src/simple_agents/conformance/decisions.py#L18)'s module docstring | 2026-08-28, reverifying what dogfood #5 has landed. **`docs/procedure.md` numbers no heading**, so a coding agent following that pointer finds nothing. It names the section instead. `prose_check`'s `missing_section` rule existed and did not fire: `sections_of` returns an empty set for a document with no numbered headings and the rule read `if known and ...`, so **a document with no numbered sections accepted every reference into it**. The guard is gone and `tests/test_prose.py` fires both sides. A scan of every `§n` reference in `docs/` and `src/` found this one and no other |
| **DF5-X16** | "§8.2 gained the tool block", and "§8.2's table is" | [`research-stage-build-log.md`](../../build-logs/research-stage-build-log.md#L1); [`unfinished-work-build-log.md`](../../build-logs/unfinished-work-build-log.md#L1) | 2026-08-28: `P3-50` added `docs/run-envelope.md` §8.3 and pushed that section to §8.4, so both statements named the wrong one. Corrected in both |
| **DF5-X17** | A test asserting `GeminiClient` refuses a missing key passed only on a machine with `GEMINI_API_KEY` unexported | [`test_adapters.py`](../../../tests/test_adapters.py#L1285) | 2026-08-28, found when the reverification exported the key to run live: `api_key=None` falls back to the environment, so there was nothing to refuse and the test failed. **Its Mistral sibling twelve hundred lines above already cleared the variable**, which is `0.11`'s lesson that a fix applied to one surface has to be checked against the others. The suite now passes with both keys exported and with neither |
| **DF5-X18** | Twenty-six citation labels naming a line their own anchor did not go to | across `dev-docs/`, four of them in this run's own records | 2026-08-28, found while writing sitting 6's kickoff. **The rule existed and could not see them**: `check_citations`'s `label-mismatch` is documented as "the label says one line and the anchor says another", and `LABEL_LINE` wanted the digits at the end of the label, where a label in backticks ends with a backtick. **Backticks are the house style**, so it fired only on the form the conventions discourage. The pattern takes an optional trailing backtick now, `--fix` repairs the label to its anchor and keeps the backtick, all twenty-six are repaired, and `tests/test_check_citations.py` fires three sides of it. Same shape as `DF5-X15`: a rule that named the right thing and checked a narrower one |
| **DF5-X19** | "`judged_steps` is re-asked when the graph changes", one of `DF5-I28`'s three parts | [`inventory.md`](inventory.md#L120)'s `DF5-I28` row | 2026-08-28 at sitting 6, before the candidate was scoped. **It was already built, at sitting 2.** `judged_steps` carries `about_the_pipeline=True` ([`elicitation.py`](../../../src/simple_agents/conformance/elicitation.py#L443) `judged_steps`), so [`checks.py`](../../../src/simple_agents/conformance/checks.py#L1586) `entries_about_the_pipeline` includes it and **FT-38** names it among the entries due when the brief's `confirmed_against` disagrees with the newest run's `behaviour_fingerprint`. `P3-34` shipped FT-38 on 2026-08-25, the same day this row was written, out of `DF5-I11` and `DF5-D6`. The row's other two parts stand and are `P3-53` |
| **DF5-X20** | "N of M rollouts right", the view's count for the agent and for its declared floor | [`view/evaluation.py`](../../../src/simple_agents/view/evaluation.py#L132) `_is_right` | 2026-08-28, `P3-52`'s seventh reverification cycle. **The view held its own list of right outcomes and two of the three names were not outcomes**: `{"correct", "correct_absent", "right_abstention"}` against the enum's `correct` and `correct_abstention`. **Every right report of absence counted as wrong**, on the agent's line, on the floor's, and in the list of examples that went wrong. Measured on three rollouts whose `results.report()` said accuracy 100%: the view said **1 of 3**, and a floor of two right abstentions said **0 of 3**. **3,796 tests were green over it.** It reads [`Outcome.succeeded`](../../../src/simple_agents/evaluation/outcomes.py#L132) now, so the view cannot part from the library's own definition again, and four tests fire on it. Same shape as `DF5-L8`: a name read once and never checked against the source |
| **DF5-X21** | "Five small mechanisms", the sitting 7 group's title, against the four rows under it | [`inventory.md`](inventory.md#L113)'s grouping table | 2026-08-28 at sitting 7. The count came from [`findings.md` §3.6](findings.md#L869), *"Five smaller mechanisms, each with a measured cost"*, which holds `DF5-D25` to `DF5-D29`. `DF5-D29` became `DF5-I30`, which sat in sitting 6's group and shipped in `P3-48`, so the sitting has held four rows since it was written on 2026-08-25 (`6bce181`) and the title was never decremented. Same shape as `DF5-X11`: a count in a header that stopped matching the rows it counts. Retitled *"Four small mechanisms"*. *(The row's "or two if the document fixes go separately" goes with it: none of the four is a document fix, and the shape is one item.)* |
| **DF5-X5** | Overtaken: "What lands before release is the front half … Evaluation- and ship-stage defects land after the repository is public" | [`setup.md` §2.1](setup.md#L61) | 2026-08-25, Thilina at this inventory's first reading: the whole of it lands before the repository is public, so `P3-32` sits above `P3-31` and `P3-31` waits on it. `setup.md` carries the note; [`items/going-public.md`](../../items/going-public.md#L1) says what it waits on |
| **DF5-X11** | "40 candidates, 14 open", and `plan.md`'s "37 candidates, 24 still `open`" | This record's header; [`plan.md` §1](../../plan.md#L26)'s `P3-32` row; [`handoff.md`](../../handoff.md#L35) | 2026-08-27 at sitting 4: corrected in all three to what the table holds, which was 18 open before the sitting disposed of seven. The header was decremented by hand once per item built, while the rows it counted had been marked `built` when the sitting took them, so each build made the number worse. `check_counts` in [`check_docs.py`](../../check_docs.py#L487) now recomputes it, with two fixtures |
| **DF5-X12** | "FT-04 stands down where every model-calling node declares `allow_unknown=False`, and FT-09 refuses a schema with no `unknown` branch, so between the two there was no honest way to say 'absence is not a state of this task'" | [`findings.md` `DF5-D23`](findings.md#L803) | 2026-08-27 at sitting 4. **There was a way, and it is one keyword.** FT-04's shipped failure message names it verbatim ([`docs/failure-taxonomy.md`](../../../docs/failure-taxonomy.md#L110)): *"If absence is impossible for this task, say so where it is enforced: `allow_unknown=False` on every node that calls a model."* Measured: the headline evaluation's pipeline has **one** model-calling node, `judge_candidates`; `allow_unknown` appears nowhere in the project's `agent.py`; and across all 2,669 manifests, all **2,730** model-calling node entries carry `allow_unknown: true`. The waiver was never used once. The finding's other claims stand, and `DF5-I29`'s disposition rests on the corrected version |
| **DF5-X13** | "It needs `P3-12` as well", of shape G1, and "G1 and H1 are enumerated and not scheduled" | [`design/answer-shapes.md`](../../design/answer-shapes.md#L1002), the six-shapes table and the roadmap's closing notes | 2026-08-27 at sitting 4: `P3-12` and `P3-13` both closed 2026-08-18, nine days before, so the judge seam G1 waited on has shipped. What G1 still needs is a judgement over a pair of arms and a figure that is a count rather than a mean, and it is `P3-48`. *(A second framing corrected the same day, Thilina's at the sitting: the library is not limited to "binary classifications". Fourteen of the twenty-four kinds ship or are expressible, including graded criteria, partial credit, per-field absence and conditions a model or a person decides.)* |
| **DF5-X14** | "Six artifacts carry their own format version", and "the current formats are ... manifest `0.35`" | [`CHANGELOG.md`](../../../CHANGELOG.md#L5), its header and its Unreleased opening | 2026-08-27 while building `P3-44`. **Seven, and the manifest is at `0.36`.** `MANIFEST_FORMAT_VERSION` is `0.36` and the file recorded `0.34` to `0.35` and stopped, so `P3-39`'s second bump, the `conversation` object, was in no entry; the conversation file itself carries `CONVERSATION_FORMAT_VERSION` on every record and was missing from the list of versioned artifacts. Both corrected, and the missing entry written |

## 3. Candidates

**The id never changes and is never reused**, so re-tagging and reordering are free. `kind` is a
tag rather than a section. **The table is in the order to take them and the top row is next**: a
live blocker sits above everything it blocks, and resolved rows sink below every open one.
`status` names where the candidate went, and its vocabulary is `plan.md`'s sections: `open`,
`accepted §2.1`, `deferred §2.2`, `scheduled P3-n`, `built <log>`, or `declined: <reason>`.

**Size is this record's first estimate and the sitting's to change.** `cheap` is an afternoon,
`item` a scheduled build with a log, `sitting` something that needs deciding before it can be
sized.

**The open rows are grouped into sittings, agreed 2026-08-25**, on dogfood #4's precedent: rows
ordered one at a time split subjects across the queue. Each group is one sitting's worth, the
rows follow it in the table, and the top row is still what happens next. **A group whose sitting
has been taken sinks with its rows**, under the ordering rule above, so the top group is the next
sitting. The third column says why the rows are one and, where it is already clear, the shape the
sitting is likely to give them; it decides nothing.

**What a sitting produces is built before the next sitting is taken**, Thilina 2026-08-25:
*"unless there is a very good reason not to, I think the better way to do DF absorption is to
finish the implementation once a sitting is done before moving to the next one. That's why we
group. Otherwise we end up with a lot of hypothetical plans that may collide."* So `P3-32` is not
one continuous item: it alternates with the items its sittings schedule, and the queue shows that.

| Sitting | Rows | Why they are one |
|---|---|---|
| **8. Going public** — **taken 2026-08-28** | `DF5-I36` | `P3-31`'s own scan pass, told what this run adds to it. **Folded into [`P3-31`](../../plan.md#L30)** rather than scheduled on its own, since [`items/going-public.md`](../../items/going-public.md#L1) already carries the scan as open work. **What the sitting settled**: the 3.1GB of trajectories are in a repository of their own and nothing from a dogfood project goes public, so the scan reads `dev-docs/` alone; rules do what rules can and Thilina reads only what needs his judgement. It also closed `plan.md` §2.1's shipped-comment entry, whose decider this run met six times over |
| **7. Four small mechanisms** — **taken 2026-08-28** | `DF5-I32` to `DF5-I35` | Cheap and independent, and all four are one genre: a library surface that reads as working and is not, which is [`dogfood-4-fixes`](../../build-logs/dogfood-4-fixes-build-log.md#L1)'s own framing. **All four went to [`P3-54`](../../plan.md#L533)**, **built 2026-08-28**, one item on that precedent, with `plan.md` §2.1's `ConfigurationError`-in-a-fan-out entry and §2.2's resumed-fan-out-bar entry folded in and both closed. **`DF5-I35` was left out of `P3-50`'s `Retry-After` work** and is now the tool-side half of it. *(This group read "Five small mechanisms" and held four rows from the day it was written: `DF5-X21`.)*
| **6. Evaluation, and absence** — **taken 2026-08-28** | `DF5-I27` and `DF5-I28` | `DF5-I29` was the requirement and the two figures it moved without saying so followed it; **three of the five left this group before it was taken**, `DF5-I29` into [`P3-46`](../../plan.md#L1) and `DF5-I31` into [`P3-48`](../../plan.md#L1) at sitting 4, and `DF5-I30` into `P3-48` at its own sitting. **What is left is the floor and the order**: a baseline that avoided nothing scoring as though it had, and an evaluation the coding agent never thought to build back to front. `DF5-I28` is the only `item`-sized row still open in this run. **It split two ways**: `DF5-I27` is [`P3-52`](../../plan.md#L1), **built 2026-08-28**, and `DF5-I28` is [`P3-53`](../../plan.md#L1), which also carries `plan.md` §2.2's per-node ratio entry, pulled in on Thilina's call. One third of `DF5-I28` was found already built (`DF5-X19`) |
| **5. Money, time, and a killed run** — **taken 2026-08-28** | `DF5-I23` to `DF5-I25` | One Gemini evaluation produced all three, and each is a run's record failing to say something true about it: what it spent, what it waited for, whether it is alive. **`DF5-I26` left this group** into sitting 4 and is built. **`DF5-I25` gained a second half on 2026-08-26**, `plan.md` §2.1's `Cassette.update` entry, which the sitting closed with it. All three went to `P3-50`, **built 2026-08-28**, and the sitting also created `P3-51` |
| **4. Stores, and the design** — **taken 2026-08-27** | `DF5-I18` to `DF5-I21`, and `DF5-I26`, `DF5-I29` and `DF5-I31` pulled in as the other `decide` rows | Two §2.2 entries whose deciders named this run and were met in the direction neither predicted, and two cheap document fixes behind them that need no decision. **`DF5-I22` left this group on 2026-08-26**, absorbed into [`P3-35`](../../plan.md#L1). It split five ways: the store row and both document fixes are `P3-44`, the artifact stamp is `P3-45`, absence is `P3-46`, the timestamp is `P3-47`, and the two answer shapes are `P3-48` |
| **3. Agency, and the questions never asked** — **taken 2026-08-26** | `DF5-I13` to `DF5-I17`, `DF5-I38`, and `DF5-I39` and `DF5-I40` raised at the sitting | What the coding agent decided alone and what the procedure never asked. It split four ways rather than into one item: the two joins answered `P3-29`'s open question and went into it; the handle and the agency questions are `P3-36`; how a question is put, which consultation mode, and the two raised at the sitting are `P3-37`. **The sitting also produced `P3-35`, `P3-38` and `P3-39`**, none of them a candidate here |
| **2. What the checks read** — **taken and built 2026-08-25** | `DF5-I08` to `DF5-I12` | Each is a check that passed over something it should have seen. `DF5-I11` and `DF5-I12` were one decision, the mechanism and the frame of `DF4-D7`'s third recurrence; `DF5-I10` is item-sized on its own. All five went to `P3-34`, built the same day |
| **1. Consultation met a product** — **taken and built 2026-08-25** | `DF5-I01` to `DF5-I07`, and `DF5-I37` raised at the sitting | What the run was set up to produce. `DF5-I01` is the mechanism and `DF5-I02` its measurement, two halves of one subject as `DF4-I07` and `DF4-I19` were; `DF5-I03` and `DF5-I07` are cheap and change behaviour, so they are decided here rather than in a batch; `DF5-I04`, `DF5-I05` and `DF5-I06` are the document and check consequences of whatever is decided. All eight went to `P3-33`, with `DF5-I37` |

| # | What | Evidence | Kind | Size | Blocked by | Status |
|---|---|---|---|---|---|---|
| **DF5-I36** | The `dev-docs` scan pass reads this run's records and the 3.1GB of trajectories under the project's `runs/` carrying the builder's watch history, which `findings.md` quotes titles from | §4 | change | cheap | — | scheduled `P3-31` |
| **DF5-I32** | A fan-out whose every item failed with one exception type and one message completed under `max_failures` with nothing written, three times in one project | `DF5-D25` | add | cheap | — | built `build-logs/dogfood-5-fixes-build-log.md` |
| **DF5-I33** | `concurrent_items` above `Pipeline.run(concurrency=)` is silent, twice in one project: a line at run start naming the declarations the run's concurrency cuts | `DF5-D26` | add | cheap | — | built `build-logs/dogfood-5-fixes-build-log.md` |
| **DF5-I34** | `value_or` recognises one of an absence's four shapes, and `Field(description=)` on a `Maybe` field replaces the absence description the library supplies; a tagged absence reached a page four times | `DF5-D27` | fix | cheap | — | built `build-logs/dogfood-5-fixes-build-log.md` |
| **DF5-I35** | `http_fetch` has no retry and honours no `Retry-After`, so a throttled source reads as absence; 736 such errors on record, and the model clients already honour the header | `DF5-D28` | add | cheap | — | built `build-logs/dogfood-5-fixes-build-log.md` |
| **DF5-I27** | A baseline callable returning `None` is accepted and scored as a failure that avoided nothing, so the avoidance floor reads 0.0 where the project's metric returns 1.0 and the brief says it should. **Two independent defects, both reproduced 2026-08-28**: `None` reads as a rollout that produced no output, and a metric whose `over` excludes non-asserting rollouts reports a structural 0.0 its score function never saw | `DF5-D18` | fix | cheap | — | built `build-logs/the-do-nothing-floor-build-log.md` |
| **DF5-I28** | Evaluating back to front: the procedure says to score the last step first with ideal inputs and work backwards, and `node_matches` reaches the coding agent before it builds its own probes. **The library refuses the second rung and allows the first**, measured 2026-08-28: a terminal node lifted into its own `Pipeline` runs, and every node behind it is refused on its dangling `successors`. *(This row also read “`judged_steps` is re-asked when the graph changes” until 2026-08-28; that was already built, `DF5-X19`.)* | `DF5-D22`, `DF5-N4` | change | item | — | built `build-logs/evaluating-back-to-front-build-log.md` |
| **DF5-I23** | A results file whose 16 of 27 rollouts carry an exact price reports `null`; the manifest holds the measured portion and nothing prints it | `DF5-D15` | fix | cheap | — | built `build-logs/what-a-run-says-it-cost-build-log.md` |
| **DF5-I24** | The retry backed off 54 calls, 28 minutes, against a monthly-cap 429 whose message says it cannot clear inside the window; the provider's message says which 429 it is and nothing reads it | `DF5-D15` | change | cheap | — | built `build-logs/what-a-run-says-it-cost-build-log.md` |
| **DF5-I25** | A killed run's manifest reads as still executing forever: a run past some bound with no `ended_at` is reported as abandoned, or the trajectory's last record dates it | `DF5-D16` | add | cheap | — | built `build-logs/what-a-run-says-it-cost-build-log.md` |
| **DF5-I18** | `MemoryStore` named in three places and built nowhere, for the second project running: the deferred entry's decider is met, and what it decides | `DF5-D11` | decide | sitting | — | built `build-logs/what-a-store-is-for-build-log.md` |
| **DF5-I19** | The artifact recipe hand-built in all three parts and broken in fact for two days: the shipped-store entry's decider is met, and what it decides | `DF5-D12` | decide | sitting | — | built `build-logs/what-a-stored-result-is-stamped-with-build-log.md` |
| **DF5-I20** | A node body fetched 24,244 articles outside the tool layer, invisible to policy, cassette and record: a sentence in `docs/tools.md` on what a run loses, and a taxonomy row under what the suite does not read | `DF5-D13` | fix | cheap | — | built `build-logs/what-a-store-is-for-build-log.md` |
| **DF5-I21** | `docs/product.md` §3's request handler loads no credential, the library reads no `.env`, and no page a product builder reads says so; the site answered 500 for two days | `DF5-P3` | fix | cheap | — | built `build-logs/what-a-store-is-for-build-log.md` |
| **DF5-I26** | The timestamp entry's decider is answered both ways: the manifests carry per-stage elapsed from `build` onward and nothing before it, so the entry closes for those stages and the elicitation stages need a clock on the log's headings or nothing | §1.4 | decide | cheap | — | built `build-logs/when-a-decision-was-made-build-log.md` |
| **DF5-I29** | FT-04 as a requirement or a question: whether the brief can declare that absence is not a state of the task, and whether FT-04 and FT-09 both read that declaration | `DF5-D23`, `DF5-N5` | decide | sitting | — | built `build-logs/absence-declared-where-it-is-enforced-build-log.md` |
| **DF5-I30** | The results file says which `Over` a figure was computed under, and the default for a metric over what the run refrained from is decided | `DF5-D29` | fix | cheap | — | built `build-logs/a-figure-that-is-not-a-mean-build-log.md` |
| **DF5-I31** | Two answer shapes this project needed and declared itself, a ranked list where position counts (C2) and a pairwise preference with no key (G1): the six-shapes entry's decider, a project that needs them, is met for two | §4 | decide | cheap | — | built `build-logs/a-figure-that-is-not-a-mean-build-log.md` |
| **DF5-I22** | **Absorbed into `P3-35`, the common language**, 2026-08-26 at sitting 3. The design gate asking for the graph `Pipeline.to_mermaid()` draws is the small answer to the question that item asks the large version of, and settling it alone would fix the small one first | `DF5-D21`, `DF5-N2` | add | cheap | — | built `build-logs/the-common-language-build-log.md` |
| **DF5-I13** | **`produces` on a `shape` decision names the nodes it became**, joined against the node ids every run under `runs/` recorded. An `agency_boundary` naming two agentic steps would have failed the join on the first run. **This is the evidence that answered `P3-29`'s one open question**: `produces` belongs on `dependency`, `shape`, `prompt_rule` and `constant`, and not on `measurement` or `presentation`, and the join is read in **both** directions. *(Said the newest run's manifest until 2026-08-27. Measured: that is one pipeline of seven on this project, five node ids of 34, so a decision about any other pipeline would have been reported as naming something no run produced.)* | `DF5-D7` | change | cheap | — | built `build-logs/what-a-decision-produced-build-log.md` |
| **DF5-I16** | **The manifest records the module-level numeric constants of the project's own modules the run reaches**, the same introspection `behaviour_fingerprint` does for prompt source, and a `constant` decision names them under `produces`. **One decision may cover many.** A command was rejected for `DF5-X7`'s corrected reason: the moment of use is the `build` gate, and `check` is what runs there. **Reported at every stage and never failed**, decided 2026-08-27: measured at `ship` on the frozen copy the reverse direction would have demanded 71 names, and which constants are the builder's is a judgement the library cannot make. Re-measured 2026-08-27: 59 constants, 56 distinct names, 5 named in a decision, **51 named in no decision**, 36 named in no decision and in neither `design.md` nor `ROADMAP.md`. *(This row read the last figure as the third until then, and scoped the modules to the ones the node callables come from, which reaches 17 of 56 on this project.)* | `DF5-D10`, `DF5-N3` | add | item | — | built `build-logs/what-a-decision-produced-build-log.md` |
| **DF5-I14** | **A handle, in the general form**, and the bounded loop named as the pattern where it is right. Not a seventh special case: one annotation carrying the node's input with an optional key, which makes the six existing handles members of it. LangGraph's `InjectedState`, Pydantic AI's `RunContext` and the OpenAI SDK's `RunContextWrapper` all do this and all hide it from the model's schema. It joins `RE_EXECUTED_HANDLE_TYPES`, so the tool is never stored and re-runs over that rollout's own input | `DF5-D8` | decide | cheap | — | built `build-logs/what-an-agent-may-do-alone-build-log.md` |
| **DF5-I15** | **`anything_else`, required, re-asked at every gate.** `BriefEntry` gains `asked_at` and the gate refuses while it is behind `stage`, which is `understanding_confirmed_at`'s mechanism moved from a document being re-read to a question being re-asked; the answer accumulates labelled by stage and "nothing" is an answer. **And `agency_boundary` is asked as a want** and put together with `consultation`: what the builder would like it to work out for itself, and what a step that decides for itself should check with a person | `DF5-D9`, `DF5-N1` | add | cheap | — | built `build-logs/what-an-agent-may-do-alone-build-log.md` |
| **DF5-I17** | **The rule goes where a question is composed**: `docs/procedure.md` and the `simple-agents questions` preamble both carry it, and it governs the wheel's questions and the ones the coding agent writes itself. `answer_form`'s `ask` is rewritten and all 46 read for the same defect. **No vocabulary test**, on Thilina's call (`DF5-N8`): its `ask` carries no library vocabulary at all, and offering a choice with no instance is not mechanically detectable. One ratchet, that no `ask` carries a `docs/` path or an `FT-nn`, at zero violations today | §3.8 | change | cheap | — | built `build-logs/the-build-is-a-conversation-build-log.md` |
| **DF5-I38** | **Folded into `consultation`'s scaffold, read off `used_through`.** The trigger decides the mode, and that answer is already in the brief one stage earlier. Named in the builder's terms rather than as `Suspend`, `Shelved` and `Unavailable`: somebody waiting can be kept waiting; a run a schedule fired cannot stop, so its question goes on a list; a run nobody was ever going to answer finishes without it. No new brief key | `DF5-I37`, [`consultation-met-a-product`](../../build-logs/consultation-met-a-product-build-log.md#L1) §6 | add | cheap | — | built `build-logs/the-build-is-a-conversation-build-log.md` |
| **DF5-I39** | **Raised at sitting 3, 2026-08-26**, by Thilina: *"the coding agent never considered running a pipeline to be anything other than hitting go and collecting what falls out at the end."* Measured: `engaged` mode is written, wired and selected whenever somebody is on the site, and **`Pipeline.resume` is called nowhere in the project** — the run stops, the question renders, and nothing continues it. **The procedure names it at `build`** (run it once with the consultation live, answering as the builder, `answered_by="builder"`), the coding agent is named as `resume`'s own `ask_someone`, and a check reads the `resumed_at` the manifest already writes: a note from `build`, and a failure at `ship` where a suspension is open and **no run under `runs/` has ever recorded a `resumed_at`** | `DF5-D3`, `DF5-D9`, §3.8 | add | item | — | built `build-logs/the-build-is-a-conversation-build-log.md` |
| **DF5-I40** | **Raised at sitting 3, 2026-08-26**, by Thilina: *"the library forcefully pushes the eval suite … the coding agent follows the eval suite, where consultation is awkward."* The eval runner is the only repeated execution the coding agent is ever shown and it refuses a live channel, so by construction nobody is there: a stand-in was configured on 249 rollouts and asked nothing. **Said at `shape`** rather than at `measure`, where the cost is already sunk, and **reported rather than failed**: FT-25's `_was_it_ever_reached` detail widens to the newest results file. *(The library does not force the tier: `prototype` skips `measure` and `used_through` is the second question asked.)* | `DF5-D20`, `DF5-D8`, `DF5-D23` | add | item | — | built `build-logs/the-build-is-a-conversation-build-log.md` |
| **DF5-I08** | **The report names the pipeline it certified**, every run, since the failure was silent rather than unstated: the docs describe `role=` twice and the project set it on none of 13 envelopes. `procedure.md`'s sentence generalises past a labelling pass and moves into `build`. **FT-33's rule is unchanged**, `role` being the defect. **`plan.md` §2.2's variant-arm entry folds in**: a sweep's arms declare `role="variant"` and the baseline keeps `agent` | `DF5-D4` | decide | cheap | — | built `build-logs/what-the-checks-read-build-log.md` |
| **DF5-I09** | **`not_applicable`, with the detail unchanged.** Of the seven checks that pass carrying a detail, six are vacuously true and FT-03 is the one whose artifact exists, whose property is checkable, and which measured nothing. `n/a` gains a third reason in `docs/conformance.md` and `docs/procedure.md` | `DF5-D24` | fix | cheap | — | built `build-logs/what-the-checks-read-build-log.md` |
| **DF5-I10** | **The results file carries `behaviour_fingerprint`**, and `check` **fails at `ship`** where it differs from the newest run's, noting it before. **The rollouts join by the evaluation's identity rather than by path**, which a copied project breaks, and a rollout whose manifest starts after the file was written is a note | `DF5-D5`, `DF5-D17` | add | item | — | built `build-logs/what-the-checks-read-build-log.md` |
| **DF5-I11** | **`confirmed_against` becomes a gate at `ship`**, a note before it, which defeats a rationale written into shipped code. **There is no report gate**, a report being read rather than passed: FT-35's own pass line names the runs it did not read and points at `simple-agents report runs/` | `DF5-D6` | decide | sitting | — | built `build-logs/what-the-checks-read-build-log.md` |
| **DF5-I12** | **No seventh stage.** A `ship`-stage check re-fires on every later `check` run, so the road after the last gate is governed by checks that read change, which is `DF5-I08`, `DF5-I10` and `DF5-I11`. **`check` gains a note on what the live runs did**, the one artifact that road leaves | `DF5-D19` | decide | sitting | — | built `build-logs/what-the-checks-read-build-log.md` |
| **DF5-I01** | **The memo engages only where the model chose the call.** A `consult` called from a node body always reaches the channel; a record answered from the memo keeps the first call's reason, and `DF5-I02`'s `reached` field is what says the channel was not reached | `DF5-D1` | change | item | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I02** | **`about=` on `consult`**, an identity separate from the wording, recorded and passed to the channel; **`reached`** on the record, which the library knows; and **`answered_at`** on a `Reply`, which only the channel knows and which is what separates fourteen answers from two. *(Two of this row's proposals changed while building and it was not updated; corrected 2026-08-27 while verifying. `reached` shipped as `asked`, and `about` **is** part of the cassette key, measured: two calls of the same words under different `about` record and replay as two.)* | `DF5-D2` | change | item | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I03** | **`Suspend` derives from `BaseException`**, as `SystemExit` and `KeyboardInterrupt` do, and a run that completes after a suspension left a tool call is refused at the end of `run()`. `RunSuspended` stays an `Exception` | `DF5-D3` | change | cheap | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I04** | `docs/product.md` §4 tells the suspend-and-resume story alone; **it carries all three modes** and which trigger fits which, shelving being what a run fired by cron or a store write can do and suspending what it cannot | `DF5-P2`, `DF5-D3` | fix | cheap | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I05** | `docs/tools.md` §4.6.3 states the once-per-run rule for the model's case only: **it says the memo is the model's**, that a node body's questions always reach the channel, and it carries the per-item pattern, since §4.6 shows only the routed one and `route=` cannot route a question asked per item | `DF5-P1` | fix | cheap | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I06** | FT-25 passes on a consult tool offered to a node whose consultation is dead code, and a stand-in end user configured on 249 rollouts was never asked. **It keeps passing on registration and gains a detail line** naming the tool that was never called in the runs it read; failing would fail a project whose consultation triggers rarely | `DF5-D20` | change | cheap | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I07** | `consult` is `read_only` and the builder says it reaches him. **No fifth class: the eval runner refuses a rollout over a consult tool whose channel is not a stand-in**, reading the `answered_by` FT-31 already reads, and `end_user=` is the waiver. FT-19 is unchanged and the refusal that reads it is FT-20's | `DF5-D14` | change | cheap | — | built `build-logs/consultation-met-a-product-build-log.md` |
| **DF5-I37** | **A third thing a channel may return, `Shelved(reason=...)`**: the question is on record and an answer may come later. Resolution `shelved` rather than `unavailable`, no memo ever, a `shelved=` branch on `on_reply`, and a count that reads asked-and-outstanding. The product used this mode for 1,654 of 1,654 consultations and had to spell it as `Unavailable`. **And acting on the answer the moment it arrives is first class**, not only at the next run | `DF5-D1`, `DF5-D3`, `DF5-P2`, `DF5-N6` | add | item | — | built `build-logs/consultation-met-a-product-build-log.md` |

### DF5-I23, DF5-I24 and DF5-I25 — One evaluation, three things a run failed to say

**Findings:** `DF5-D15` and `DF5-D16`. **Size:** one item, larger than the three `cheap` estimates
these rows carried.

All three were found in `runs/eval_b7c83906be49`, the only Gemini evaluation: 27 rollouts, 994
model calls, 54 refused with a 429. **Taken as one item because each is the same failure**, a
run's own record not saying something true about it, and because verifying them needs one live
run rather than three.

**Decided 2026-08-28 at sitting 5**, as [`P3-50`](../../plan.md#L1), with
[`build-logs/what-a-run-says-it-cost-build-log.md`](../../build-logs/what-a-run-says-it-cost-build-log.md#L1) carrying all eight
decisions and the measurements behind them. What is worth recording here is what the sitting
found that the rows did not know.

**The measured portion exists twice already, and the row named the wrong one.** `DF5-I23` says
"the manifest holds the measured portion and nothing prints it". Measured at the sitting: the
library computes cost with two adders that disagree on purpose.
[`Cost.plus`](../../../src/simple_agents/cost.py#L187) makes a total unknown where one call is
unmeasured, which is what keeps `value` honest;
[`Spend.plus`](../../../src/simple_agents/budget.py#L82) skips it and keeps counting, which is what
`max_cost` is enforced against. Pricing all 994 calls individually gives **$5.5024**, and the 24
rollout manifests' `charged_cost` sum to **$5.5024** by the other route. The results file says
`null` with `measured: null`, `simple-agents report` says `3.9744 USD`, and
[`view/runs_overlay.py` `_cost_of`](../../../src/simple_agents/view/runs_overlay.py#L384) returns
**`0.0`**, which is a wrong number rather than an absent one and which
[`findings.py` `_one_step_costs_most`](../../../src/simple_agents/view/findings.py#L699) then reads.
The view defect was found at the sitting while checking a scoping question and is `P3-50`'s.

**`measured` was already built for this case and failed on granularity.**
[`totals_of`](../../../src/simple_agents/evaluation/results.py#L861) sums per node, one unknown call
makes a whole node unpriced, and this project's two model-calling nodes were both hit. The fix is
per-call accumulation, not a new field.

**Every one of the 54 refusals waited exactly 31,000 ms**, which is the bare backoff ladder, so no
`Retry-After` was present on any of them. A live probe the same day confirmed Gemini publishes no
rate-limit headers at all, so `PacedClient` is a passthrough for it and **the message text was the
only signal on the wire**. `DF5-I24`'s premise holds exactly.

**And the 28 minutes are recovered by reading the message alone.** A cross-call circuit breaker
was proposed at the sitting as the half that recovers them and then dropped, because not retrying
the call removes all 1,674 seconds by itself. It is [`plan.md` §2.2](../../plan.md#L212).

**All 13 killed runs declared a wall-clock bound**, 3,600,000 ms or 900,000 ms, so
`started_at + max_wall_clock_ms` dates every one of them and needs no new field. The trajectory's
last record, which `DF5-I25` offered as the alternative, covers 8 of the 13; it is the fallback
rather than the mechanism.

**A run does not record what it was given, and that is the fourth thing.** `node_execution.inputs`
is written when a node **ends**, so a run killed inside its first node has its inputs nowhere;
[`SuspensionState`](../../../src/simple_agents/records/suspension.py#L51) carries `inputs` because a run that
stops has to say what it was doing, and a crash is a suspension nobody got to write. `P3-50` adds
a `run_start` record. **The argument is the record's completeness**: two counts of crashed runs
were offered at the sitting, one for and one against, and Thilina rejected both as designing for
the dogfood.

### DF5-I18 and DF5-I19 — The two store deciders, both met

**Findings:** `DF5-D11`, `DF5-D12`. **Size:** sitting.

Both are `plan.md` §2.2 entries whose deciders named this run, and both deciders were met in the
direction the entries did not predict.

**The memory store** ([entry](../../plan.md#L278), `The memory store's shape`) waited on "a
second project that persists state choosing or refusing the store for stated reasons". The
second project named it in the design, the store's docstring and the brief, described it as in
use, and never constructed it; what the product needed was a shelf that lists, dedupes, marks
answers and is read by a page, and a scoped key-value store with `remember` and `recall` offers
none of those. The steer came from `docs/product.md` §3. Two projects, one pattern: the store's
shape is a personal memory for an agent and what a product persists is its own data model.

*Corrected 2026-08-27 at `P3-39`'s sitting, on Thilina's question: "Doesn't it make sense that
the projects chose SQL over the memory store for something like the show catalogue?"* **It does,
and the framing above does not survive it.** A catalogue is relational data with queries over
it; `MemoryStore` is a scoped key-value store with `remember`, `recall` and a text search, and
was never a candidate for one. A project keeping its catalogue in SQL is not a refusal of the
store. **The question this row has to answer is narrower: did anything need a personal memory
for an agent — facts about one end user, carried between runs — and refuse the store for it?**
Storing a catalogue elsewhere is evidence on neither side. What survives unchanged is that
`memory` is `None` in all 3,293 manifests of dogfood #4, so how well the store works is
unmeasured rather than measured badly.

**And a shape question `P3-39` raised that this row should take.**
[`MemoryStore(directory, scope=...)`](../../../src/simple_agents/memory.py#L130) `MemoryStore` fuses two
things with different lifetimes: where the store lives, which is project configuration set once,
and whose memory this is, which is per request. Fusing them forces an envelope rebuild on every
incoming request. `P3-39` settled the conversation store the other way — the store on the
envelope, the identity on `run()` beside `run_id` — and if that is right there, `scope=` is on
the wrong object here. It is a cheap fix and an argument for keeping the store, not against it.

**The shipped store** ([entry](../../plan.md#L289), `A shipped store for the product's artifact`)
waited on "dogfood #5 hand-building the
same four behaviours again with the docs naming them". It did; two of the four broke for two
days, `absorbed_through` is written and read by nothing, and the refresh reports staleness
rather than acting on it. What was not predicted: `P3-6`'s rule that no check opens project
storage is what kept the library from seeing any of it, and this record does not reopen that.

What is to decide is the two entries' fate: closed with the evidence recorded, promoted, or
left with a new decider. They can be taken together because the evidence is the same project.

### What sitting 4 decided, 2026-08-27

**Both entries closed.** `DF5-I18` is [`P3-44`](../../plan.md#L1) and `DF5-I19` is
[`P3-45`](../../plan.md#L1).

**The memory store, and what settled it is who writes.** Measured at the sitting on the frozen
copy: `Store.judge()` is called from `web/app.py` routes only, never from a node and never from
`agent.py`, so the **200 judgements** (176 `not_for_me`, 16 `liked`, 7 `queued`, 1
`seen_and_disliked`, 23 carrying a free-text note) were written by the product from end-user
clicks. `remember` is a tool the agent calls inside a run. The line the documents will state:
**the memory store holds what the agent learns and writes; what the end user tells the product is
the project's data model and reaches the run as inputs.** So the shape was never reached rather
than found wanting, and [`docs/product.md` §3](../../../docs/product.md#L1)'s scoping sentence is
what sent two projects there. `scope=` moves to `run(memory_scope=)` with it, on `P3-39`'s
precedent. Also measured: `shelved.json` holds 7 questions with `answer: null` on every one, and
`design.md:306`'s claim that a shelved answer reaches the next run through the store is false
now that [`Pipeline.answer_shelved`](../../../src/simple_agents/pipeline/core.py#L968) exists.

**The shipped store, declined, and a defect found looking for it.** Three of the project's six
stored artifacts carry a stamp that is not a `behaviour_fingerprint` at all
(`announced-fbe9be02ab1f1eaa`, `schedule-806d1b3d1914ab09`, and the literal `labelling`), because
those surfaces make no model call; a library store keyed on the fingerprint covers half of them.
`P3-6` means no check reads project storage either. **And the fingerprint moves when the
consultation channel does**, measured against the current library: two pipelines differing only in
which channel `consult()` was built over give different stamps, so every slate dogfood #5 built
from a click reported itself stale the instant it was written. `P3-45` takes the channel out and
leaves `docs/shipping.md` §6 as documentation.

### DF5-I29 — Absence as a requirement, on a task with no absent state

**Finding:** `DF5-D23`, and `DF5-N5` is the framing. **Size:** sitting.

FT-04 fails an `evaluated` project whose held-out split holds no example expecting absence, and
FT-09 refuses a schema with no `unknown` branch, so between the two there was no honest way to
say "absence is not a state of this task". The builder said it at `shape` ("Never absent —
change the tier"); the coding agent declined to lower the tier on the procedure's own sentence,
called the empty quarter a dishonest absence case in writing, and then generated twenty of
them because the gate needed four. Every one of them scored `false_confidence`, since an empty
slate inside a dict is an assertion.

The decision: whether FT-04 is a requirement or a question, and whether the brief can declare
absence is not a state of the task and have both checks read that declaration. The rule was
written for tasks where silence is an answer, a lookup that may find nothing; a recommender
always has something to say. What the sitting owes is the line between the two kinds of task,
because the check has to read it.

**Decided 2026-08-27 at sitting 4**, as [`P3-46`](../../plan.md#L1), and the premise above is
corrected at `DF5-X12`. **The honest way existed**: FT-04's failure message names
`allow_unknown=False` verbatim, the headline pipeline has one model-calling node, and the waiver
was never used in any of 2,669 manifests. So what failed is surfacing, and the two seams are that
the declaration is per-node while the question was asked per-task, and that the waiver is
all-or-nothing while FT-04 is about the scored answer. The waiver narrows to the node producing
the scored answer, and FT-04's message reads the brief's `absence_vs_error`. **Rejected**: letting
the brief waive the gate outright, since a declaration on the object being enforced is what the
manifest records; and demoting FT-04 to a question, since twenty invented examples is what an
unreachable escape produces rather than what an over-strict rule produces.

### DF5-I08 — The batch pass that ran as the agent

**Finding:** `DF5-D4`. **Size:** cheap, inside `P3-34`.

`build_summaries.py` and the title-resolution pass wrote 2,310 of the project's 2,669 runs, all
of them declaring `role: "agent"`. Measured at the sitting, 2026-08-25: the project builds
**13 `RunEnvelope`s and sets `role=` on none of them**, while 51 runs set `live=True` through
`env.with_live()`. **The same object's other field was found and used.** What separates them is
placement: `live=True` is a bolded instruction inside stage 6 of `docs/procedure.md`, and `role=`
is one sentence in the Layout section whose only example is a labelling pass.
[`docs/run-envelope.md` §2.1](../../../docs/run-envelope.md#L110) describes it properly and its
two examples, a labelling pass and a judge, are model-calling passes over the project's own data,
which is what `build_summaries.py` is. **The case was named twice and missed anyway**, which is
why another sentence is not the answer.

**Decided 2026-08-25: the report names the pipeline it certified, on every run.**
[`_latest_run`](../../../src/simple_agents/conformance/artifacts.py#L423) picks by recency among
`role=agent`, so during the corpus passes FT-13, FT-14, FT-15, FT-25 and FT-32 certified a
two-node summariser. Naming the nodes rather than the path is what makes that visible: a person
reading `write_summary → keep_summaries` under their recommender's conformance report sees it.
Nineteen distinct pipelines have run under `role=agent` in this project.

**`procedure.md`'s sentence generalises past a labelling pass and moves into `build`**, which is
the stage where a batch script gets written. That is the smaller half of the docs option and it
is taken beside the report line rather than instead of it.

**FT-33's rule is unchanged, and `role` was the defect.** With the corpus passes declaring
themselves, the newest agent run dates the log again; FT-33 passes on the frozen copy today. The
residual is that a long evaluation still makes it fail until the log is touched, and that is the
check asking for the log entry the procedure already asks for.

**`plan.md` §2.2's "A variant arm saying it is not the agent" folds into this item**, Thilina's
call at the sitting. That entry was deferred 2026-08-10 and named its decider as **what FT-13 and
FT-14 are for**, predicting *"a project whose last activity was a sweep has FT-13 and FT-14
certify one rollout of one arm"*. On the frozen copy they read
`runs/eval_b7c83906be49/cut-2026-03-23-2`, one rollout of one evaluation, so the prediction
landed.

**Decided at the build: the arm declares `role="variant"` and the baseline keeps `agent`.** The
entry framed this as a choice between the baseline keeping `agent`, which makes the newest agent
run a baseline rollout, and the whole sweep declaring itself, which it said would fail FT-13 on a
project that has only ever swept. **The first is what an arm is**: the baseline is the pipeline
the project has, run over the example set, and an arm is a pipeline it does not have. **The
entry's cost note applies to the option not taken**, and does not land here: measured live at the
build, a project whose only runs are a sweep certifies the baseline's rollout and FT-13 passes.
`VARIANT_ROLE` is the value, and what those two checks certify is answered once, here, rather
than twice.

**The entry, moved verbatim from `plan.md` §2.2**, since folding it in means its text lands here
rather than being read and re-written:

> **A variant arm saying it is not the agent.** *Deferred 2026-08-10.* Named 2026-08-10 at the verification pass, where `docs/run-envelope.md` §2.1 was found claiming it already happens. `RunEnvelope(role=...)` separates a labelling pass and a judge from the agent's own runs, and the shipped sentence listed an ablation arm beside them; nothing sets one. `compare_variants` copies the envelope with `with_cassette` alone, so every arm writes `role: "agent"` and a project whose last activity was a sweep has FT-13 and FT-14 certify one rollout of one arm. **What shipped instead** was the sentence narrowed to the two roles the library actually declares. **What it would cost:** the baseline arm is the agent, so a design has to say whether it keeps `agent` — which makes "the newest agent run" a baseline rollout rather than an ordinary run — or whether the whole sweep declares itself and a project that has only ever swept then fails FT-13. **What decides whether it is worth owning:** what FT-13 and FT-14 are for. The ambiguity the cost above rests on is not there: [`compare_variants`](../../../src/simple_agents/evaluation/variants.py#L313) takes `baseline` as its own argument and the variants as a mapping beside it, so the library knows which arm is the agent and which are not, at the call site and with nothing to infer. That leaves one decision, and it is about the two checks rather than about the sweep: whether a project that has only ever swept certifies at all. [`_latest_run`](../../../src/simple_agents/conformance/artifacts.py#L423) already reads only runs whose role is `agent`, so declaring the variant arms costs one field and makes the answer no. Deciding what those two checks are certifying is the whole of it, and no project has to turn up for it. The behaviour is not new and is not the sweep's: `_latest_run` reads nested rollouts for any project that only ever evaluated, which is what lets a project that measured and never ran the agent alone pass at all.

### DF5-I10 — Nothing joins a headline to the pipeline that made it

**Findings:** `DF5-D5`, `DF5-D17`. **Size:** item, inside `P3-34`.

The headline the tier rests on returned `recommendations: []` in all 27 rollouts, was three days
and about 100 commits old at the freeze, and was produced by a six-node pipeline where the
shipped one has nine. FT-01 to FT-07 read it and pass, because it has a held-out split, seeds,
intervals and absence cases. The number is honest and it is zero.

**Decided 2026-08-25, three parts.**

**The results file carries `behaviour_fingerprint`.** Its `config` carries `graph_fingerprint`,
which is shape alone, beside `nodes`, `containers`, `prompts`, `tools`, `model` and `budget` —
most of the fingerprint's material, undigested. It is a results-format bump and one row in
`docs/evaluation.md`'s field table.

*(Said at the sitting: "the suite knows the model at write time, so the stamp is exact and
[`behaviour_fingerprint`](../../../src/simple_agents/pipeline/core.py#L2070)'s refusal cannot fire."
It can. `EvalSuite.run` takes `model=None`, and a pipeline with a node that calls whatever the
run is given then refuses rather than returning a stamp that would not move with the model, so
the file records `null` and FT-37 reports it blocked. Corrected 2026-08-25 at the build.)*

**`check` fails at `ship` where it differs from the newest run's, and notes it before.** During
`measure` a pipeline moves several times an hour and clearing the failure costs a paid
evaluation, so a gate there would be cleared by re-running money. At `ship` the number is being
shown to somebody else. A `ship`-stage check re-fires on every later `check` run, which is what
makes this govern the road after the gate rather than one moment on it (`DF5-I12`).

**The rollouts join by identity rather than by path, and drift is a note.** Measured at the
sitting: this project's rollout paths are absolute into `/home/thilina/Projects/dogfood-5/runs/`,
so in the frozen copy every one of them points outside the tree and a path check would report 27
false failures. `P3-20` made the evaluation directory's name its identity, so
`evals/results/eval_537a12d02a72.json` names `runs/eval_537a12d02a72/` with no path involved,
which catches `DF5-D17`'s second case. Its first case is caught by the clock: a rollout whose
manifest starts after the results file was written is a rollout the file does not describe, which
is 21 rollouts at 11:53Z against a file written at 11:46Z. Bookkeeping drift is a note; the stale
fingerprint is what fails. *(A file written by `rescore` is left out of this, found at the build:
its identity is the rescoring configuration's and names no directory, so reading it here told the
reader to re-score a path that never existed.
[`what-the-checks-read-build-log.md`](../../build-logs/what-the-checks-read-build-log.md#L1) §3.)*

### DF5-I11 and DF5-I12 — The instructions with no gate, and the road after the last one

**Findings:** `DF5-D6`, `DF5-D19`. **Size:** sitting, and probably one sitting for both.

`DF5-D6` is the mechanism: the gated instruction was followed 21 times and the two ungated
ones never, and one of them, `simple-agents report`, would have shown on day one the two
failures the log spent three exchanges finding by hand. `confirmed_against` at `ship` is the
obvious gate; a report gate has no obvious shape, because a report is read rather than passed.

`DF5-D19` is the frame: `DF4-D7` asked what governs the road after the last gate, `P3-7`'s
`confirmed_against` was the one mechanism that fires on change rather than on reaching a point,
and this run records it was never used. Every check the library has fires on a point; 45% of
this project happened after the last one. The `ship` stage was `DF4-I05`'s half answer.
Whether a stage after `ship` is the answer, or a check that fires on change is, or nothing is
and the procedure says so, is the decision.

**Decided 2026-08-25, and they are one decision.**

**`confirmed_against` becomes a gate at `ship`, a note before it.** This defeats a rationale
written into shipped code: [`_the_pipeline_moved`](../../../src/simple_agents/conformance/run.py#L401)
says *"It reports and never fails. A graph moves several times an hour while a project is built,
and a failure that frequent is cleared by re-recording the value rather than by reading."* The
situation against it, measured on the frozen copy at the sitting: the note prints twelve entries
due with the fingerprint to record, it printed on all 21 `check` runs the log records, it was
acted on none of them, and one of the twelve, `agency_boundary`, describes two `AgentNode`s the
project never had. **The objection is accepted rather than argued away**: the clearing action is
mechanical. It is worth taking because half of what these entries claim gains a real join at
`DF5-I13`, and the other half is prose nothing can check, for which "somebody read it once since
the code last moved" is the strongest true statement available.

**There is no report gate.** A report is read rather than passed, and the signal the instruction
wanted is already inside `check` and scoped away. Measured at the sitting: `simple-agents report
runs/` prints `judge_candidates` *"produced nothing: 29 unit(s) of work, spending 251 of 3,451
model call(s)"* and two more like it, while FT-35 passed saying *"Read 6 of the 2,669 run(s) under
runs/ … 2,650 made by a pipeline this one has changed since. No node spent an allowance without
acting."* [`spend.py`](../../../src/simple_agents/conformance/spend.py#L66) scopes to one
`behaviour_fingerprint` on purpose, since a figure over a pipeline that changed is a stale figure.
**So FT-35's own pass line names the runs it did not read and points at `report`**, and
`_spend_that_produced_nothing`, which already names `report` and never fired for the same reason,
does the same. The stale figures themselves are not reported: that is what the scope rule exists
to prevent.

**No seventh stage, and `DF4-D7` is answered rather than deferred a fourth time.** A stage moves
the boundary rather than removing it, and `P3-28` is the record of what one costs. The road after
the last gate is governed by checks whose subject is change — `DF5-I08`'s header line,
`DF5-I10`'s fingerprint gate and this item's `confirmed_against` gate — on one fact: **`stage = "ship"` stays
in the brief, so a `ship`-stage check fires on every subsequent `check` run.** This project ran
`check` 21 times across the post-`ship` 45% of its log, and each of those runs would have fired
both gates.

**And the limit is stated rather than left to be found next run.** The library cannot see the JSON
API, the Flutter app or the cron job that were built after `ship`. What it can see of that road is
the live run, and no check except FT-31 reads one:
[`_latest_run`](../../../src/simple_agents/conformance/artifacts.py#L423) prefers a run that is
not live and reads a live one only where the project has no other, which no project ever is —
this one had 2,618 others against 51 live runs. The seam is built and used once
([`Artifacts.live_run`](../../../src/simple_agents/conformance/artifacts.py#L114)), so **`check`
gains a note at `ship` naming what the live runs did**: which the newest one is, when it
started, and which run the checks read instead. It stays a note, because a live run is the end
user's material and may be sampled down to nothing.

*(This line read "how many, since when, and by which pipeline" when it was written. **How many
was dropped at the build**: counting them is a second pass over every manifest, on top of the one
FT-35 already makes, and `runs("runs/", live=True)`, which the note names, is what answers it for
a reader who wants the number. **Which pipeline was dropped** because the header line above the
checks already names one, and a second pipeline named in a note below them reads as a
correction of it.)*

### DF5-I01 — The once-per-run memo met a product

**Finding:** `DF5-D1`. **Size:** item, inside `P3-33`.

The rule is right for the case it was built for: an `AgentNode` that keeps asking a person who
is not there is a count rather than a hundred round trips. A `Deterministic` node asking one
distinct question per item is the other case, and the memo keys on the tool's name, so it
cannot tell them apart. The product's shelf got 5 of 109 questions, and 1,640 records carry the
channel's own reason on questions the channel never saw.

Three decisions, and the finding declines all three. **Scope:** per run, as now, or per node
execution, or per question. **The channel:** whether one that shelves declares itself, so it is
reached for every question and the memo never engages. **The record:** whether a memo-answered
consultation carries its own reason, or the first call's as now. The honest options are not
independent: a channel that declares it shelves makes the scope question moot for that channel,
and a per-question scope makes the declaration unnecessary but turns a hundred round trips back
into a hundred. `docs/tools.md` §4.6.3 (`DF5-I05`) says whatever this decides.

**Decided 2026-08-25: the memo engages only where the model chose the call.** A `consult` reached
through `ctx.call_tool` from a node body always reaches the channel; the model's own tool calls in
an `AgentNode` loop are memoed as now. The library already has the two call sites separately
([`tooling.py:66`](../../../src/simple_agents/runtime/tooling.py#L66), `__call__`, is a node body's;
[`agent.py:375`](../../../src/simple_agents/nodes/agent.py#L375), `_one`, is the model's), so this is one
argument threaded through. **The line is the memo's own purpose**: it is an instruction to stop
asking, and only a model can read an instruction. A `for` loop cannot, so silencing it discards
the questions the code was written to ask.

**The record's reason keeps the first call's text**, which is the true statement of why nobody
could be asked; `DF5-I02`'s `reached` field is what says the channel was not reached this time.

**A channel declaring that it shelves was decided and then superseded the same sitting** by
`DF5-I37`. A channel that returns `Shelved` never returns `Unavailable`, so the memo never engages
and there is nothing to declare, and a return value beside `Unavailable` in the docs is reachable
where an attribute assigned onto a function is not: this project's coding agent found neither.

### DF5-I02 — A consultation has no identity beyond its wording

**Finding:** `DF5-D2`. **Size:** item, inside `P3-33`.

The end user answered twice and the artifact says fourteen times, because the channel found a
stored answer by exact text match and the library recorded each replay as `answered`. The
wording embeds a day count, so the same question re-asks the day after it was answered. The
project's `Store.shelve` has an `about` parameter nothing passes; `consult` takes no key; the
cassette keys a consultation on its text (`DF4-I01` found the same for replay).

Two halves. **An identity** on a consultation, separate from its wording, which is what a
shelf, a cassette and an inbox each dedupe on. **A field** on the record saying whether a
person was reached this time, which is what every count the library reports (`counts.consultation`,
`consultation_resolutions`, `unanswered_consultations`, FT-25, FT-31) would need to say
"109 questions, 5 put to a person, 2 answered" instead of "1,654 consultations, 1,640
unanswered". The first is a format move on the consult tool and the trajectory; the second is
a format move on the record alone.

**Decided 2026-08-25: `about=`, `reached` and `answered_at`, all three.**

**`about=` on `consult`**, optional, recorded on the consultation and passed to the channel, which
is what a shelf, an inbox and a report dedupe on. **It is not part of the cassette key**, and that
was decided rather than assumed: a replay has to reproduce the run that was recorded, and serving a
recorded answer against a differently worded question is a replay lying about what was asked. The
cassette keeps keying on the whole call.

**The channel contract takes the clean break** to `(question, options, about)`. Nothing is
released. The alternative was passing `about` only to a channel whose signature declares it, which
is one more thing a builder has to know exists.

**Two fields, because one does not do the job the row claimed.** `reached` says whether the library
called the channel or answered from the memo, which the library knows exactly and which fixes the
1,640. It does **not** separate fourteen answers from two: those fourteen calls all reached the
channel, which found a stored answer by text match. Only the channel knows an answer is not new, so
**`answered_at` on a `Reply`** is what it sets, `None` meaning the person answered just now. *(The
row read "a field ... which is what separates fourteen answers from two" until 2026-08-25, which
was one field doing two jobs.)*

### DF5-I37 — The third consultation mode, which the library has no word for

**Findings:** `DF5-D1`, `DF5-D3`, `DF5-P2`. **Raised at sitting 1, 2026-08-25**, by Thilina:
*"I am concerned that the current consultation patterns are not easily usable by a practical
project and that's why this mess happened."* **Size:** item, inside `P3-33`.

**The library ships two modes and this product needed a third.** Engaged: raise `Suspend`, the run
stops, the person answers, `resume`. Unavailable: nobody is there, stop asking, proceed without.
The third is *ask, publish the question, do not wait, finish the run, and let the answer reach a
later run*. It is what a run fired by cron or by a store write can do and suspending is what it
cannot, and it carried 1,654 of 1,654 of this product's consultations.

**The library has no word for it, so the project spelled it as `Unavailable`**, and everything
downstream then did the right thing for the wrong meaning: the memo fired, because nobody-to-ask is
what it is for; the resolution says `unavailable` where the truth is asked-and-outstanding; the
counts say unanswered where they mean pending; `on_reply(unavailable=...)` routes it as the absence
of a choice; and `Pipeline.suspensions` reports zero because nothing suspended.

**The only encoding that works today is a lie.** Returning `None` instead of `Unavailable` resolves
as `declined` ([`tools.py:1392`](../../../src/simple_agents/tools.py#L1392), `resolve`) and never
sets the memo ([`consultation.py:350`](../../../src/simple_agents/runtime/consultation.py#L350), `note_no_one_to_ask`),
so every question would have reached the shelf and every record would say the viewer was asked and
said nothing.

**What it is.** `Shelved(reason=...)`, a third thing a channel may return beside `Reply`, `None`
and `Unavailable`: resolution `shelved` on the record, no memo ever, a `shelved=` branch on
`on_reply`, and a count that reads asked-and-outstanding rather than unanswered. It pairs with
`DF5-I02`: `about=` is the identity the later run's channel looks the answer up by, and
`answered_at` is what says the answer is not new.

**The name is `Shelved` and not `Deferred`**, Thilina's call at the sitting: `deferred` is already
one of the three brief entry statuses ([`brief.py` `STATUSES`](../../../src/simple_agents/conformance/brief.py#L53),
`STATUSES`), shipped and checked, and the docs are a prompt surface.

**Acting on the answer the moment it arrives is part of this and is first class**, Thilina at
the sitting, `DF5-N6`. The run that asked has finished, so there is no suspension state and nothing
to resume: what has to happen is that the answer reaches whatever the project would do about it,
then, rather than at the next run. In this product that is the viewer answering "gave up on it" on
the questions page and the show leaving up-next immediately. The next-run case stays legitimate and
is what a question whose answer only changes the next recommendation wants.

**What only the library can do here** is put the answer in the trajectory of the run that asked,
linked to the question by `answers=` the way a resume's answering record already is
([`consultation.py:29`](../../../src/simple_agents/runtime/consultation.py#L29) `_delivered_answer`). Today an answer arriving after the
run finished lives only in the project's own store, which is why every figure the library reports
counts records rather than answers. **What it must not do** is run anything the caller did not
call: `simple-agents.md` §2.1's containment holds, and the trigger is the project's own handler.
The `plan.md` §2.2 scheduler entry is not this and is not reopened by it; that entry is about the
library owning a trigger, and this is a seam the project calls.

**What it costs.** A new `resolution` value is a trajectory format move, which `P3-33` is taking
anyway for `about`, `reached` and `answered_at`. `on_reply` gains a fourth required branch, which
breaks every route built so far. `docs/tools.md` §4.6 and `docs/product.md` §4 gain the third mode,
which is `DF5-I05` and `DF5-I04` widened rather than new work. The answer seam is the part with no
sizing yet, and the questions it has to settle are in
[`build-logs/consultation-met-a-product-build-log.md`](../../build-logs/consultation-met-a-product-build-log.md#L1).

**What was argued against it**, and did not win: `Unavailable` plus a project store already
expresses this once `DF5-I01` stops the memo interfering, and a fourth thing to distinguish is a
cost. Taking `DF5-I01` alone makes this product work, 109 questions reaching the shelf. What stays
wrong under that is what the record says about them, which is the half the run was set up to
measure.

## 4. What the next run must measure

The input to the next run's `setup.md`, written now rather than reconstructed later. A finding
that can only close with another run belongs here and not in §3.

| # | Question | Why it is open |
|---|---|---|
| **DF5-Q1** | **Does a second cold run separate the coding agent's agency decisions from the local model they were measured on?** | Most of the "agency does not converge" evidence was a 4-bit 30B model on a 16k window. The protocol asks for a second run where the task warrants it, and this one's existence-shaped questions are answered, so the second run has one thing to isolate. §4 |
| **DF5-Q2** | **What does a seeded start answer, answer wrongly with no gate catching it, and still have to ask?** | The seeded-start entry in `plan.md` §2.2 names this run as the free baseline arm; the seeded arm has not run |
| **DF5-Q3** | **Does any product use suspend-and-resume across its surface?** | The first product-first run used shelving for 1,654 of 1,654 consultations, engaged mode was dead code, and `Pipeline.resume` was called nowhere. The story `docs/product.md` §4 tells has no product yet. `DF5-D3` |
| **DF5-Q4** | **Does a real answerer answer when the questions reach him?** | `DF4-Q1` came back in the negative for a reason in the library rather than in the design: 5 of 109 questions reached the shelf. Whatever `DF5-I01` and `DF5-I02` decide is unmeasured against a person. `DF5-D1`, `DF5-D2` |
| **DF5-Q5** | **Semantic recall, still unmeasured by any dogfood** | `DF4-Q4` carried forward: the run never reached memory. `DF5-D11` |
| **DF5-Q6** | **Does the elicitation stages' elapsed time need a clock on the log's headings?** | Depends on `DF5-I26`. If the stages before `build` need a stamp the manifests cannot carry, a sixth run is asked for one and it is composed again unless something writes it. §1.4 |

## 5. Thilina's notes from the run, verbatim

Written 2026-08-20 during the run, 2026-08-25 after it and at sitting 1, and 2026-08-26 at
sitting 3. **His words, unedited**, because the framing and the constraint are both in the
wording and a summary loses them. Every note is cited by a candidate in §3, except `DF5-N7`,
which created [`P3-35`](../../plan.md#L1) instead and is cited from `DF5-I22`, the candidate
that item absorbed. **`DF5-N6` is out of order deliberately**: it belongs beside `DF5-I37`,
which it scopes.

**DF5-N1.** The agent asks questions well, and they are scoped better than before. But I think "anything else" or open ended questions would be useful for the builder to provide further info, feedback, or any other additions that were not directly elicited.

**DF5-N2.** It still didn't tell me exactly how it plans to wire things up. Now it does tell me what it uses, but not really the specifics.

**DF5-N3.** "gather_candidate_pool filters the catalogue, ranks all 67,353 eligible shows, then truncates: return {**inputs, "pool": ordered[:pool_size]}". It made this unbelievably dumb decision WITHOUT asking me. I could have told it that that's stupid.

**DF5-N4.** Tying into the previous point, I don't think the coding agent is making use of per node metrics. It certainly does not appear smart enough to figure out that this needs to be evaluated back to front. Recommendation performance for a given show -> selecting candidates -> building the pool of candidates.

**DF5-N6.** To add to the Shelved option, it should be easy for the project to write the logic so that something happens/updates when a Shelved consultation is resolved. For DF5 it would mean that the app asks if the user wants to abandon a show since the user hasn't seen it for months. That goes into the questions that are waiting for the user. At some random point, the user answers yes. This should then immediately trigger whatever the answer is supposed to do (remove the show from up next in DF5). This should be a first class option. Of course, other scenarios might require waiting for the next run or whatever.

**DF5-N5.** I think the library went way too overboard on the whole 'absent answer' thing. It makes the coding agent try to invent something to fill that requirement because a tv show recommender doesn't really have an absent/unknown condition that can go into an eval set.

**DF5-N7.** *(2026-08-26, sitting 3. It created `P3-35`; `DF5-I22` is the candidate it absorbed.)* designing an agentic system really isn't an easy project. I think what we are doing is helping, by forcing these conversations between builder and coding agent, and the checks. But I feel like we are missing a sort of "common language". All the docs and the briefs and the whatnot are a coding agent's wheelhouse. It's a lot of text, and a coding agent reads text in seconds. Put a few thousand lines of text in front of a human, and the typical reaction is to zone out and say "just do what you think is best". But the builder is the one with the idea for the project, the creativity, and intuition. We need to build a bridge. What we have now is a few lines strung over the river. I am not saying that's not helpful, it is, I am asking if we can do more. Off the top of my head, can we build something where we have a (mostly) visual design that both the builder and coding agent can look at and easily understand the parts and what's going on. I am thinking of literally something out of a sci-fi movie. The system imagined/drawn in 3D space with all the pieces of the pipeline or pipelines. Not a drag and drop, but a visualizer that acts as the common language and at a level of abstraction where both a builder and a coding agent can function.

**DF5-N8.** *(2026-08-26, sitting 3. It is why `DF5-I17` ships no vocabulary test.)* The builder is not stupid. The builder may use the library multiple times and get familiar with the terms. Don't overcorrect in the other direction. A test for questions carrying library vocab may be too strict, especially the node names.

**DF5-N9.** *(2026-08-26, sitting 3. It corrected `DF5-L3` and decided `DF5-I16`'s shape.)* This may be true, but it may also be influenced by the fact that, perhaps, the library never instructed the coding agent to use "report". How was the coding agent supposed to know about the facility? The library is big and the documentation is big too. It's our job to surface the right tools at the right time.
