# Build log — the brief against the code

`plan.md` §1 P3-7. Started and finished 2026-08-16. Written while building, not afterwards.

Closes `DF4-I03`'s mechanical and trigger halves, `DF4-I24`, `DF4-I26`, `DF4-I30`, and
`DF4-D7`'s remaining half (`DF4-I05`).

## 1. Before any design

**A check reads artifacts and imports nothing**, which decided where the trigger gets its value.
`Context` ([checks.py:164](../../src/simple_agents/conformance/checks.py#L164)) carries the
artifacts, the brief and the taxonomy, and `run_checks` never builds the project's pipeline. So a
check cannot call `behaviour_fingerprint()`. It reads the one the newest run's manifest recorded,
which P3-6 put there. **The limit that follows is stated rather than discovered later: a pipeline
edited and not run leaves the manifest unchanged, so the note stays silent until the project runs
again.** FT-13 needs a run and the build gate asks for one, so a project reaching a gate has a
fresh manifest; a coding agent mid-build who edits and does not run gets nothing.

**`_tool_entry` ([recording.py:147](../../src/simple_agents/pipeline/recording.py#L147)) carries what both
mechanical checks need**: `name`, `side_effect_class` and `offered` per tool, where `offered` is
false for a tool no node was given. That is the reachability half FT-25's specified check asks for.

**FT-25's shipped failure message could not be filled.** It opened *"The brief declares `<n>`
consultation points"*, and nothing counts consultation points: the `consultation` answer is one
prose answer. Registering the check meant rewriting the message, which is done.

**Notes are assembled in `run_checks`** from `Artifacts` methods plus `_stages_the_tier_drops`
([run.py:728](../../src/simple_agents/conformance/run.py#L728)), and the brief is in scope there,
so the trigger is a fourth note rather than new machinery.

**The taxonomy is parsed out of the shipped document**
([taxonomy.py](../../src/simple_agents/conformance/taxonomy.py#L1)), so a new entry is written in
`docs/failure-taxonomy.md` and the code reads it. Changing FT-25's surface line from
`elicitation-only` to `artifact` is part of registering it, and closes `DF4-X6`.

## 2. Design

The sitting's record was `items/brief-against-code.md`, and this section is now that file.

**Two checks that compare files, one that reads a clock, and one note that instructs the coding
agent to do what no check can.** FT-32 reads `tool_effects` against the manifest's tools; FT-25's
specified check is registered; FT-33 reads a build log that stopped; `confirmed_against` in the
brief fires the note when the pipeline moves.

**The trigger is the item's reason for existing.**
[`ship-stage-build-log.md` §3](ship-stage-build-log.md#L349): every enforcement the library has
fires on **time**, a project reaching a point, and every failure dogfood #4 found fires on
**change**. The two mechanical checks need no trigger, because they compare two files and are
right whenever they run. The note covers the entries whose truth no check can read.

**Three things Thilina ruled at the sitting, each of which changed the design.**

The note is addressed to the **coding agent**, not the builder: *"I didn't read it."* So it names
what to go read rather than presenting a finding to a person.

It **names entries and quotes no answer**. The first draft printed each entry's text, which read as
though the library shipped one project's words, and a truncated quote is something to act on
without opening the file.

**The prose entries are not left to a check.** The sitting's first cut was to check `tool_effects`
mechanically and leave `agency_boundary` alone because a program cannot read whether a sentence
describes a set of node kinds. Thilina's correction: a program cannot, and the coding agent can, so
the gap was a missing instruction rather than a missing check. That is what the note carries.

**Which entries the note names is derived, not listed.** `Question.about_the_pipeline`
([`elicitation.py` `about_the_pipeline`](../../src/simple_agents/conformance/elicitation.py#L68)) marks the ten whose
answers describe something `behaviour_fingerprint()` covers: the shape, the prompts, the sampling,
the tools, the declared model, `allow_unknown` and the budgets. A hardcoded list would have been
dogfood #4's list.

**What was weighed and not taken.** Failing rather than reporting on the moved fingerprint: a
pipeline moves several times an hour while a project is built, and the cheapest way to clear a
failure that frequent is to re-record the value without reading. Requiring a build log of every
project: whether to keep one is the builder's, so FT-33 fires on a log that stopped and a project
keeping none passes. And a mechanical check over `behavioural_constants`, dropped because it is not
a library key: it was dogfood #4's own `constant`-kind decision, whose `chose` is free prose.

## 3. Build

**Fifteen checks, 33 taxonomy entries.** FT-25 registered, FT-32 and FT-33 new, all three
`artifact` surface and tier `prototype`. `confirmed_against` on the brief,
`Question.about_the_pipeline`, and the note in `run_checks`. **2262 tests**, up 21. No format
moved.

**Three false positives found while building, and each narrowed a check.**

**The fixtures found the first two.** FT-25 first matched an answer against a set of bare words, so
the `conforming` fixture's *"Nothing. Every input the agent needs is in the collection."* failed:
a well-written answer, failed for being a sentence. It now reads the first word alone. FT-32 first
required each tool's **name** in the answer, so the same fixture's *"a read-only search over a
fixed collection"* failed for not writing `catalogue_search`. Tool names are no longer read: a
builder describes a tool in their own words, and an answer carrying a code identifier is not a
better answer.

**The live run found the third, and it is the sharper one.** With names dropped, FT-32 still failed
*"It asks the reader, and it writes one line to the builder's notes"*, an answer describing both
tools correctly, because `consult` is `read_only` and the answer never said `read_only`. The
question asks *what may this agent do that reaches outside the run*, and `read_only` is the answer
**nothing**, which a builder writes as "it only reads". `DECLARED_EFFECTS` is now `writes`,
`spends_money` and `irreversible`, and `read_only` is not read. The suite could not have found
this: the `conforming` fixture's answer happens to contain the words "read-only".

**FT-33's comparison moved from the run's start to its end**, after a live failure where the log
and the run shared a second. An entry about a run can only be written once that run has finished,
so the margin is the length of the run rather than a tolerance nobody can defend. A run that
crashed records no `ended_at` and is dated by its start.

**Surfaces touched.** `checks.py`, `brief.py`, `elicitation.py`, `run.py`; `failure-taxonomy.md`
(FT-25's surface, check and message; FT-32; FT-33; §10's index and counts), `conformance.md` (§2's
table, §3's sample report regenerated, the new §3.4, §4's counts), `procedure.md`, `index.md`,
`README.md`, `CHANGELOG.md`.

**`docs/procedure.md` is 1632 words against a budget moved 1600 to 1700**, on Thilina's approval.
The approval was framed as P3-8's need and part of it is spent here, which is said rather than left
to be noticed: P3-8 has 68 words rather than the ~60 it estimated.

**Three shipped statements stopped being true, and the re-read after the build found two of
them.** Adding a check at tier `prototype` invalidates every sentence that enumerates that tier,
and those sentences are in three documents.

1. `docs/procedure.md` stage 3's gate said *"FT-13, FT-14, FT-24, FT-29 and FT-30 pass, which at
   tier `prototype` is everything that fires before `ship`"*. It now names all eight, checked
   against `taxonomy()` rather than by hand.
2. `docs/conformance.md` §1.1's tier table listed six checks for `prototype`. Nine run.
3. **`docs/failure-taxonomy.md` §1.1 and `docs/conformance.md` §4 both said "no check reads the
   content of an answer".** FT-25 reads the first word of the `consultation` answer and FT-32
   substring-searches `tool_effects`, so the sentence this item shipped against is one this item
   made false. Both now say which two read an answer's text and that neither judges it.

**One defect the re-read found in the code.** The note named an entry whatever its status, so an
`unanswered` one was listed as due for re-reading against the code. There is no answer there to
have gone stale and FT-24 already reports it, so the note now reads answered entries alone.

## 4. Verification

**Live against Gemini `gemini-3.1-flash-lite`, four real runs**, scripted at
`scratchpad/verify_p3_7.py`: a whole project with a brief, `idea.md`, decisions and a pipeline,
changed the way dogfood #4's was.

| What it had to show | Result |
|---|---|
| FT-25 fails a project elicited on consultation whose graph has none | `failed`, *"no consultation tool is registered"* |
| ...and passes once the tool is on a node | `passed` |
| FT-32 fails a `writes` tool against a read-only answer, on a manifest a real run wrote | `failed`, naming `note_it (writes)` |
| ...and passes once the answer says it writes | `passed` |
| FT-33 fails a log written before the newest run | `failed`, naming both timestamps |
| The note is silent while the pipeline has not moved | silent |
| The note fires on a prompt edit, with no gate involved | fired, naming eight entries |
| It quotes no answer, and fails nothing | neither |

**Two things the live run showed that no unit test would have.**

The consulting run **registered the tool, offered it, and the model never called it**, and FT-25
passed. That is what the check claims: registered and reachable, never used. It is worth knowing
that a passing FT-25 says nothing about a consultation happening.

**FT-33 failed again at the end**, correctly: two more runs happened after the log was last
written. Writing the log again cleared it. That loop is the behaviour the check exists to produce,
and it ran.

**One live construction refusal, and it is `DF4-I31` met head on.** `LLMNode` takes no `tools=`, so
every tool-bearing node in the verification had to be an `AgentNode`. That is `DF4-N6` in the
inventory, still open, and this is a second instance of it costing a rewrite.

## 5. Doc consequences

| | |
|---|---|
| `docs/failure-taxonomy.md` | FT-25's surface is `artifact` and its check and message are written; FT-32 and FT-33 are new; §11 index and counts are 33 entries, 21 artifact |
| `docs/conformance.md` | §2's table gains three rows; §3's sample report regenerated from a real run; **§3.4 is new**, on the four notes; §4 reads fifteen of thirty-three |
| `docs/procedure.md` | `confirmed_against` in "two things to settle"; stage 3's gate lists all eight checks. 1632 words |
| `docs/index.md`, `README.md` | The conformance row names the notes; the taxonomy row reads 33 |
| `CHANGELOG.md` | The three checks and the note |

**`DF4-X6` closes.** The inventory recorded FT-25 as *"specified in the taxonomy and not registered
in `checks.py`"*. It is registered.

## 6. Left open

- **The note reads the newest run's manifest**, so a pipeline edited and not run leaves it silent.
  Named in §1 and in `docs/conformance.md` §3.4. Destination: nothing. Closing it means the suite
  importing the project's pipeline, which no check does.
- **FT-33 reads a modification time**, so a fresh checkout or a copied project makes every file
  look current. The failure direction is a false negative rather than a false positive. Destination:
  nothing; stated in the entry.
- **`DF4-I31`**, `LLMNode` having no `tools=`, met live here for the second time.
  [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L53) §3, open.
- **Nothing has been through this on a project that is not ours.** Every claim is about behaviour
  no builder has met, which is [`DF4-Q1`](../runs/dogfood-4/inventory.md#L433)'s standing
  condition. Dogfood #5 is where FT-32's false
  positives, if there are more, will show.
