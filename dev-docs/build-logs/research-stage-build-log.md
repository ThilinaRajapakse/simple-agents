# Build log — the research stage

`plan.md` §1 P3-28. Started 2026-08-20. Written while building, not afterwards.

Dogfood #4's sitting 6: `DF4-I14`, `DF4-I28`, `DF4-I29`, `DF4-I37` and `DF4-I41`. The sitting
was framed as documentation and elicitation with no library code, and three of the five turned
out to need code.

## 1. Before any design

Read against the artifacts rather than against the candidate rows, which is what changed two of
them.

- **`too_similar`'s scaffold names an operation the library cannot perform.**
  [`contamination`](../../src/simple_agents/evaluation/examples.py#L536) appends a pair only
  `if similarity >= threshold`, and `ExampleSet` had no ranked-overlap method at all. The
  scaffold said to *"show the builder the most similar cross-split pairs"*. Dogfood #4's set was
  clean at 0.8, 0.6 and 0.4 (`brief.toml` `entries.too_similar`, `BUILD-LOG.md:354`), so it
  returned nothing at every threshold the coding agent tried. **The threshold sweep the builder
  reported was the scaffold being followed**, not skipped. `findings.md` §5's account of
  `DF4-P4` said the opposite and is corrected as `DF4-X12`.
- **The brief records an answer in nobody's voice.** Of dogfood #4's 26 entries, three carry no
  reference to the builder. `one_real_input` is the coding agent's own reading of a file and
  `abandon_condition` is terse; the third is `too_similar`. The two entries either side of it in
  the same stage say *"He picked it over `false_confidence_rate`"* and *"He chose to keep the
  current guards"*.
- **No scaffold in the question set reaches outside the project.** All 40 were read. The five
  that instruct an action — `one_real_input`, `backend`, `improvement`, `too_similar`,
  `tool_effects` — each measure material the project already holds.
- **The decision surface records what was weighed and nothing widens it.** Dogfood #4 recorded
  16 decisions, four of kind `dependency`, weighing 13 alternatives between them. All 13 are
  variants of two catalogues checked on day one. The four sources that came from outside —
  Listopia, `awesome-scifi`, `awesome-fantasy`, publisher catalogues — appear in `brief.toml`
  only inside `agency_boundary` and `tool_effects`, as tools that exist, and went through no
  decision at all.
- **The awards case, which is what the artifact rule is built against.** `BUILD-LOG.md:459`
  asserted award shortlists *"ride the same mechanism as Listopia tags"*; `:587` recorded them in
  a table with a yield of `—`; `:1141` found that claim false and recorded *"awards are not
  sourced at all"*. `grep -i award *.py` in the project: zero hits. **A named target got
  executed and a named category got asserted away.**
- **`design.md` is absent from dogfood #4 and that is not evidence.** `design.md` and FT-34
  shipped in `df1389c` on 2026-08-16, five days after the run.
- **The library's own Gemini adapter case is not a research failure.** `DF4-L5` looks like one.
  The wheel was frozen at 2026-08-11 and [findings.md §6](../runs/dogfood-4/findings.md#L905)
  calls that *"the place the project could not reach"*. It is the dogfood isolation working.
- **Only `measure` is ever dropped by a tier.**
  [`STAGES_BY_TIER`](../../src/simple_agents/conformance/stages.py#L48) gives `prototype` every
  stage but that one, so "stages exist to be selected by tier" was no argument against a sixth.
- **`Decision.rests_on` is already on every kind.**
  [`rests_on`](../../src/simple_agents/conformance/decisions.py#L209) is generic; only the report
  line was scoped to `shape` and `presentation`.
- **`tests/` is not in the wheel.** 97 entries, none a test. The eight citations everyone had
  been counting reach nobody through it, and the one nobody had counted did:
  `checks.py` carried `DF4-D6` inside `_unseeded`'s docstring.

## 2. Design

**Six stages, `research` second.** Thilina's framing: *"This 'research' phase could be one of the
most important factors that determine how good the project is going to be."* Taken as a stage
rather than a phase inside `brainstorm` on four grounds: [simple-agents.md
§2.8](../simple-agents.md#L293)'s 2026-08-10 amendment is the same argument one step earlier;
two failures need two gates, and `brainstorm`'s cannot also assert the ground was checked;
research is the first thing in the procedure that is not a question put to the builder; and it
is where the option set every later decision draws from is fixed.

**The decomposition comes first, and the conclusion comes last.** Both from Thilina at the
sitting. *"Break the system into smaller parts and then research those parts. That's what finds
award lists or new sources."* And against an earlier draft that had the coding agent form a view
before researching: *"Isn't this what we don't want? A coding agent making a decision before
doing the research, and then riding confirmation bias all the way to the end."* So `parts` is
answered before anything is looked up and `what_this_turns_on` after everything.

**The artifact carries the builder, and FT-34's mechanism is what reads it.** `research.md`'s
fourth section is *What the builder said about it*, checked for a quotation exactly as
[`design.md`'s third](../../docs/failure-taxonomy.md#L604) is. A quotation is a shape a check can
read; whose words are inside it is not.

**The `Outcome` column is the one prescriptive thing here.** It fixes a table format on one
section of one file. It is there because the failure it catches is a dash: dogfood #4's
four-source table recorded award shortlists with `—` and the surrounding prose read as covered.

**Weighed and not taken.**

- *A section inside `idea.md` rather than a file.* Rejected: `idea.md`'s five sections are what
  the project is, and a survey of the world is not that. It also leaves one gate asserting two
  unrelated things.
- *A `looked_at` field on `dependency` decisions.* Rejected once `rests_on` turned out to be
  generic. Extending the report line costs nothing and adds no field.
- *`behaviour_fingerprint` as the staleness trigger for `research.md`* (R2 at the sitting).
  Rejected: research goes stale because the world moved, and that trigger fires only when the
  code moved, so a stalled project never re-reads.
- *Merging the inbox's plan-ingestion entry into this item.* Not taken. They run in opposite
  directions and meet only at entry provenance, which shipped here and is what plan-ingestion
  will need.
- *Numbers in the scaffolds.* Removed on Thilina's instruction: *"Don't give numbers. That's
  something a coding agent would fixate on."* So did every clause defending the design and every
  clause addressed to a maintainer rather than to the coding agent.

**Entry provenance.** `source` on a brief entry, `builder` by default, and a required question
answered `source = "coding_agent"` fails FT-24. The coding agent that has filled something in
had exactly one move before this, which is to record it as an answer and pass, and that is what
`too_similar` and `DF4-D2` both are.

**R3, and what the measurement changed.** Thilina: *"do the checks on R3 and see if it's as hard
as you are suggesting. You sometimes flip on these. Also, I think R3 should go both ways."* It
was measured and it is cheaper than the sitting had it, and one half of it does not survive:

- **FT-32 already reads the manifest and deliberately does not read tool names.**
  [`ft_32`](../../src/simple_agents/conformance/checks.py#L1000) compares side-effect classes, and
  the shipped rationale is that *"a builder describes a tool in their own words, and an answer
  naming a code identifier is not a better answer."* The forward direction contradicts that, and
  it is §6.
- **The reverse direction over manifests fires on nothing.** Measured across all 3,293 of dogfood
  #4's runs: every registered tool was called in at least one run. A per-run version would fire
  constantly and legitimately.
- **What the measurement does support is the report line**, which is what Thilina asked for
  beside the failing rules: `uncommon_books` registered in 2 of the directory's runs and called
  in 1. That ships.
- **The awards case is caught by FT-36's `Outcome` column**, which is where it actually failed.

**`DF4-I37`: C2, and no check.** The Layout gains `research.md` and a rule for the rest: code the
pipeline imports beside `agent.py`, anything run once in `scripts/`, anything read in `data/`.
Dogfood #4 put 38 files at its root and every library-written artifact landed correctly — all
3,293 run directories under `runs/`, 36 results files under `evals/results/`, no `trajectory.jsonl`
anywhere else. Naming a place is what worked, and Thilina's ruling is that nothing checks it.

**`DF4-I41`: `tests/` is a maintainer surface.** It is absent from the wheel, so a citation there
is a pointer between two records the same reader holds. `INTERNAL_REF` is scoped off it and every
other rule still applies.

## 3. Build

Five stages plus the one already applied at the sitting. 2913 tests, up from 2880. No format
version moved: the trajectory, manifest, suspension, results file and variant comparison are
untouched. **The brief's shape moved and carries no version**, which is the break named in §6.

**Stage 0 — the citations, applied at the sitting.** `DF4-D6` removed from
[`_unseeded`](../../src/simple_agents/conformance/checks.py#L1551), which was the only internal id
in the wheel. The eight `tests/` citations repointed to `dev-docs/runs/dogfood-3/findings.md`,
resolvable for the first time since the 2026-08-15 reorganisation. `INTERNAL_REF` widened to
`DFn-Dn` and `P3-n` and scoped off `MAINTAINER_TREES`. Five fixtures in `tests/test_prose.py`,
one of which walks the whole shipping set.

**A rule that was not asked for and had to be built.** Thilina's Corner carried *"Multiple bare
references like 'See §6.2.'… Section 6 of which doc and where?"*, and closing it needed a check.
`unanchored_section` found **50**: three in `src/` and 47 in `tests/`. **Thirty-five of the 47
resolved once the rule learned to read a module docstring naming one document** —
`tests/test_trajectory_conformance.py` anchors 29 references in one sentence, correctly. The
remaining 15 were anchored by hand against the target's real headings. The Corner sub-bullet is
gone rather than marked resolved.

**Stage 1 — `too_similar`.** `ExampleSet.nearest_cross_split(n=)` and `NearestPair`, exported at
both levels. The `ask` stopped asking for a number. Two other asks carried library vocabulary
(`unknown_literal` said *schema*, `context_limit` said *node*) and were reworded, and
`test_no_ask_puts_the_library_s_own_words_to_the_builder` holds all 45 asks to a vocabulary list.

**Stage 2 — the stage.** `STAGES`, `STAGES_BY_TIER`, five questions, `research.md`,
`RESEARCH_SECTIONS`, `SURVEY_SECTION`, `OUTCOME_COLUMN`, `Artifacts.research`,
`research_confirmed_at`, `rows_with_no_outcome`, `has_table`, `ft_36`, and the FT-36 taxonomy
entry. `docs/procedure.md` gained a stage and renumbered four.

**What the build found that the design did not know.**

- **`questions_at` is cumulative**, so `simple-agents questions --stage research` prints 18
  questions rather than 5. The skill's sentence had to say what the command prints.
- **`rows_with_no_outcome` naming a row by its first cell names the part rather than the
  candidate.** It joins every cell before the outcome instead, so the award row reads
  `candidates / award shortlists`.
- **The `unanchored_section` rule broke markdown resolution when first written.** Its two-line
  lookback applied to `.md` too, so a bare `§n` in a table row resolved against whatever document
  the line above named. Ten false positives across five shipped documents. The lookback is now
  source-only.
- **`docs/procedure.md` went 361 words over its budget.** The section was tightened to 215 words
  and `WORD_BUDGET` raised from 1815 to 2160 with the reason recorded beside it.
- **A consultation tool read as never reached.** Found on the second read-and-verify pass. A
  `consult` tool writes a `consultation` record and no `tool_call`, and a consultation carries
  no tool name, so the first version of `_tool_reach` reported every consultation tool at zero
  calls however often it was reached. `docs/trajectory-format.md` §4.3 carries the exact join
  and the manifest's own documentation states the intent: `answered_by` is set on a consultation
  tool *"so which tools reach a person is read here rather than guessed from a name"*, and
  `reaches` names which answerer on both sides. Verified live: two Gemini runs, one consultation
  each, no `tool_call` for `consult`, and the block reads 2 and 2.
- **A row too short to reach the `Outcome` column passed**, which is the strongest form of no
  outcome recorded. `index < len(cells)` guarded an IndexError and dropped the row.
- **A header row with no candidate under it passed every branch**, which is the cheapest way to
  defeat FT-36 and the closest thing to "no research was done" the artifact can express. The
  reader is `survey_rows` now, returning each candidate with its outcome, and FT-36 fails an
  empty one before it looks at any cell.
- **`_tool_reach` was the first code to zip handles against records positionally.** `_readable`
  filters unreadable runs out of one list and the caller filtered the other, so two runs sharing
  a `run_id` would have paired a manifest with another run's trajectory. `_readable` returns the
  pairs now.
- **`simple-agents questions` never mentioned `source`.** The whole point of
  `source = "coding_agent"` is to give the coding agent a legal way to record that it filled
  something in, and the surface it reads described only `status` and `answer`, which is the one
  move dogfood #4 made. The header names it and the gate it fails.
- **`parts`' `ask` said "steps" while its own scaffold said a part is neither the pipeline nor a
  node list.** It asks what problems the system has to solve.
- **A blank line inside the survey table reads as two tables**, which is what a markdown
  renderer does too, so the check agreeing with the renderer is right. Hit while writing a
  survey by hand at the verification pass, on the first attempt, and the message said only that
  the header had nothing under it. It names the cause where the section holds more than one
  table.
- **`has_table(..., column)` matched a data row.** A cell holding the word `Outcome` under a
  header that did not satisfied the renamed-column check. It reads the header row alone now.
- **Two tables under one section shared the first one's column index**, so the second was read
  against the wrong header or not at all. `_tables_under` splits them, since a blank line ends a
  markdown table.
- **A survey table that renamed the `Outcome` column passed.** Found on the read-and-verify
  pass rather than by a test: `has_table` said a table was there and `rows_with_no_outcome`
  reported nothing, because it had no column to read. `has_table` takes the column now, and
  FT-36 fails on it with its own message. Nine tests cover FT-36's branches.
- **`about_what_is_wanted` on `what_this_turns_on` was wrong.** It is a finding about the
  problem rather than a statement of what the builder wants. `parts` keeps the flag, and
  `test_naming_every_one_says_nothing` now reads the list off the question set.

**Stage 3 — provenance.** `SOURCES`, `BriefEntry.source`, and
[`_settled`](../../src/simple_agents/conformance/checks.py#L533) returning false for
`coding_agent`. FT-24's taxonomy entry, check paragraph and failure message all say so.

**Stage 4 — the report line and the decision mirror.** `RunsReport.tools`, `_tool_reach`, the
`tools` block in `text()` and in `to_record()`, and
`_dependencies_no_research_rests_under` as a report note beside the existing one.

**Stage 5 — the Layout.** Three homes, no check.

**The fixtures.** `scripts/build_conformance_fixtures.py` writes `research.md` and the five
entries, so every one of the 17 fixture projects was rebuilt rather than hand-edited. The
`conforming` fixture's `dependency` decision now names `approaches` and `available_material`
under `from`, and its `shape` decision names `parts`.

## 4. Verification

**Live, against Gemini `gemini-3.1-flash-lite`**, in a scratch project outside the repository.
Two runs of a two-tool `AgentNode`, both correct.

- **The report block on freshly written runs.** `who_wrote` registered in 2 and called in 2;
  `shelf_size` registered in 2 and called in 0. `--json` carries both under `tools`. This is the
  declared-and-never-reached signal on a real backend rather than on a fixture.
- **FT-36, four ways.** No `research.md`: fails naming the file. Present and complete but
  `research_confirmed_at` naming an earlier stage than the project reached: fails naming both
  stages. One `Outcome` cell replaced with `—`: fails naming `Resolving a title / fuzzy match`.
  Complete and current: passes.
- **FT-24 on provenance.** `budget` answered `source = "coding_agent"` appears in the missing
  list; flipped to `builder` it leaves it, with nothing else changed.

**Against dogfood #4's 3,293 real runs**, which is where the report block was designed and is a
larger corpus than any fixture: every registered tool called at least once, and `uncommon_books`
at 2 registrations and 1 call. **Its `consult` reads 104 and 1 and that is an old-format
artifact rather than a fact about the project**: its manifests predate `answered_by` on a tool
entry, so the join below cannot fire and the 104 consultations it recorded are invisible to it.
A project on manifest `0.31` reads correctly, which the live run is what shows.

**The suite.** 2927 passed, 2 skipped, after five read-and-verify cycles. The first found one defect, the second four, the third one, the fourth two, the fifth one, the sixth one, and the seventh none. `prose_check`, `check_docs` and `check_citations` clean;
`check_citations --fix` rewrote 70 anchors this item's edits had moved, and one remaining
`blank-line` in `runs/dogfood-2/findings.md` pointed at `nodes.py:1501` for a `run.charge` site
that is now at 3414 and was renamed with its symbol so it can be re-resolved.

## 5. Doc consequences

`docs/procedure.md` gained stage 2, renumbered stages 3 to 6, added `research.md` to the Layout
and the three homes below it. `docs/failure-taxonomy.md` gained FT-36 and its counts moved to 36
entries and three stage-gated. `docs/conformance.md` moved to nineteen checks in six places.
`docs/evaluation.md` gained §1.2.1. `docs/run-envelope.md` §8.4 gained the tool block.
`docs/index.md` and `README.md` moved from five stages to six and from eighteen checks to
nineteen. `CHANGELOG.md` carries the entry.

**Shipped statements that stopped being true**: every "five stages" and "eighteen checks", the
`Question.ask` of `unknown_literal` and `context_limit`, `too_similar`'s whole entry, FT-24's
check paragraph and failure message, and `docs/conformance.md`'s sample report, which was
regenerated from the suite rather than edited.

## 6. Left open

Three of these were filed as entries and rethought on 2026-08-20, after Thilina's correction that
counting how many dogfoods have hit something is the same argument as "no evidence yet". Two did
not survive the thinking, and the third turned out not to be blocked at all.

- **A capability that reached the run through no surface.** Five tools ran in dogfood #4 that the
  brief never named — `whats_new` in 96 runs, `already_owned` in 5, and `uncommon_books`,
  `verify_books` and `web_search` in 2 each — and `simple-agents check` reported 11 of 11 passing
  over it. **Filed against the wrong surface, which is what made it look blocked.** FT-32 reads
  side-effect classes out of the `tool_effects` answer and deliberately reads no tool name,
  because that answer is builder prose; putting the check there conflicts with that rationale and
  putting it on the decision surface does not. A `dependency` decision names what it became under
  `produces`, which is structured, is not put to the builder as prose, and joins exactly against
  the manifest. **Promoted to [`plan.md` §1](../plan.md#L17) as `P3-29`**, after `P3-14`;
  [`build-logs/what-a-decision-produced-build-log.md`](../build-logs/what-a-decision-produced-build-log.md#L1) is the record.
- **An adopted research row that names nothing built. Declined 2026-08-20.** What an adopted row
  adopts is a dependency, a technique, a method or a refusal, and only the first has a nameable
  artifact, so a rule forcing every one to name a path is wrong for most of them. The partial
  version — check a path only where the row volunteered one — fires on the project careful enough
  to write the path down and misses the one that forgot to build the thing. And "adopted and never
  built" is a claim about whether prose is true, which `docs/failure-taxonomy.md` §10 says the
  suite cannot read; what reads it is `research_confirmed_at`, which this item shipped and which
  fires at every gate after `research`. Declined rather than deferred, so it is in no section of
  [`plan.md`](../plan.md#L1).
- **A format version on the brief. Declined 2026-08-20.** `Brief.read` has one production caller,
  [`run_checks`](../../src/simple_agents/conformance/run.py#L38), and nothing reads an old brief.
  `CHANGELOG.md`'s own opening line is the test the five versioned artifacts pass and this one
  does not: they carry a version *"because a project holds files written in it"*, and `rescore`,
  `resume` and `compare()` each read an instance written earlier. A brief is read now, by the
  library installed beside it, and regenerated as the question set changes. A version would buy an
  error message saying the format moved rather than naming six missing keys, and could not buy
  even that reliably, since knowing which keys are new needs the comparison the version was meant
  to enable. Declined rather than deferred, so it is in no section of [`plan.md`](../plan.md#L1).
- **Plan-ingestion**, the inbox's *"providing a plan or doc as a starting point for a build"*.
  Entry provenance shipped here and `source = "document"` is the slot it lands in.
  [`random-thoughts-questions.md`](../random-thoughts-questions.md#L1).
