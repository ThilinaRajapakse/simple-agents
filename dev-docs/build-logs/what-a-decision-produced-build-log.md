# Build log — what a decision produced

`plan.md` §1 P3-29. Started 2026-08-27. Written while building, not afterwards.

## 1. Before any design

The item's "What has to be decided" was checked against the code before anything was designed,
because it had been corrected the same morning and still guessed at a split.

| Claim in the record | Read against | Held? |
|---|---|---|
| `Decision` carries `rests_on` as a structured tuple, so `produces` has a precedent | [`decisions.py` `Decision`](../../src/simple_agents/conformance/decisions.py#L166) | Yes. Parsed from `from`, refuses a bare string |
| FT-32 reads side-effect classes and no tool name, so it is untouched | [`checks.py` `ft_32`](../../src/simple_agents/conformance/checks.py#L1000) | Yes |
| The two neighbouring mechanisms are report notes | [`run.py` `_answers_no_decision_rests_on`](../../src/simple_agents/conformance/run.py#L454), [`_dependencies_no_research_rests_under`](../../src/simple_agents/conformance/run.py#L518) | Yes |
| FT-40 and FT-41 are the note-then-fail pattern to copy | [`checks.py` `ft_40`](../../src/simple_agents/conformance/checks.py#L1791), [`ft_41`](../../src/simple_agents/conformance/checks.py#L1882) | Yes. Neither names a `Stage:` field; each reads `ctx.stage()` |
| FT-41 is the highest entry | `docs/failure-taxonomy.md` | Yes, so this is FT-42 |

**Then the measurement `DF5-I16` rests on was re-run**, on Thilina's instruction. The item's
§"The measurement, re-run 2026-08-27" holds the result. Two things it changed:

- **"36 named nowhere" was the wrong row.** The figure for *named in no decision* is **51 of 56**;
  36 is *named in no decision and in neither `design.md` nor `ROADMAP.md`*. Every recorded figure
  reproduced exactly once the reading was pinned down.
- **The recorded mechanism reached 17 of 59.** "The modules the node callables come from" is
  `agent` alone on dogfood #5, plus three constants of `simple_agents.builtins.http`. Every
  constant `DF5-D10` quotes is outside it.

**And the join surface was measured**, which the record had as the newest run's manifest. Dogfood
#5's newest agent run is one pipeline of seven: 5 node ids of the 34 its 2,669 runs recorded.
[`load_project`](../../src/simple_agents/view/discovery.py#L43) does not rescue it, finding zero
pipelines there, since the project declares `build_*()` functions rather than
`@pipeline_factory` or a module-level `Pipeline`.

## 2. Design

**`items/what-a-decision-produced.md` was this item's record, and its text is here now.**
The shape was settled at dogfood #5's sitting 3; four questions were put to Thilina on
2026-08-27 and each is below with the measurement it turned on.

### What the problem was

**A capability can reach a run having gone through no surface the builder saw.** Measured across
dogfood #4's 3,293 manifests on 2026-08-20: five tools ran that the brief never named —
`whats_new` in 96 runs, `already_owned` in 5, and `uncommon_books`, `verify_books` and
`web_search` in 2 each. `simple-agents check` reported 11 of 11 passing over it. `uncommon_books`
is the tool holding all four candidate sources the builder had to prompt for, and no `dependency`
decision records any of them.

**FT-32 is not the check that catches this, and asking it to would be wrong.**
[`ft_32`](../../src/simple_agents/conformance/checks.py#L1000) compares the side-effect classes a
manifest declares against the `tool_effects` answer, and deliberately reads no tool name: *"a
builder describes a tool in their own words, and an answer naming a code identifier is not a
better answer."* That rationale is about builder-facing prose and it stands. The first framing of
this item put the check on that surface and read as a conflict with it; the conflict was the
placement.

**Nothing else joins.** A `dependency` decision's `chose` and `considered` are prose and are put
to the builder, so they carry the same objection. `research.md`'s survey rows are prose. The
manifest is the side being compared against and cannot be both.

**Nothing. The shape was settled at dogfood #5's sitting 3 and the four remaining questions were
decided on 2026-08-27**, after the measurement below was re-run against the frozen copy. A
decision is the only artifact that is both something the builder agreed to and already half
machine-readable: `kind`, `status` and `rests_on` are structured while `chose` and `because` are
the prose. So a decision names what it became, in a structured field beside them:

```toml
[decisions.uncommon_sources]
kind = "dependency"
chose = "Goodreads Listopia tags, awesome-scifi, awesome-fantasy, publisher catalogues"
produces = ["uncommon_books", "explore_tag", "take_books_from"]
```

No identifier enters builder-facing prose, FT-32 is untouched, and the join against the run
record is exact rather than a name match over English.

**Which kinds carry it, settled 2026-08-26 at sitting 3.** `produces` belongs on `dependency`,
`shape`, `prompt_rule` and `constant`, and not on `measurement` or `presentation`, and the join
is read in **both** directions: a decision naming something no run produced, and something a run
produced that no decision names. The evidence is
[`inventory.md` `DF5-I13`](../runs/dogfood-5/inventory.md#L123): dogfood #5's `agency_boundary`
named two agentic steps and three ran, so a `shape` decision's `produces` joined against the run
record would have failed on the first run. *(This section proposed the opposite split until
2026-08-27, guessing that `constant` and `prompt_rule` mostly do not create an artifact.
`DF5-I16` is why they do.)*

**`DF5-I16` is folded in and is the `constant` half.** The manifest records the module-level
numeric constants of the project's own modules the run reaches, by the same introspection
`behaviour_fingerprint` already does for prompt source, and a `constant` decision names them
under `produces`. **One decision may cover many.** A free-standing command was rejected at
sitting 3, for `DF5-X7`'s corrected reason: the moment of use is the `build` gate and
`simple-agents check` is what runs at it.

### The measurement, re-run 2026-08-27

Taken on `/home/thilina/Projects/dogfood-5-frozen`, over `agent.py`, `tvtime/` and `web/`. **The
recorded figures reproduce exactly and two of them meant something narrower than this record
said.**

| | |
|---|---|
| Module-level numeric constants | **59**, under **56** distinct names |
| Named in a decision of any kind | **5** (2 of them in a `constant` decision) |
| Named in no decision | **51** |
| Named in no decision and in neither `design.md` nor `ROADMAP.md` | **36** |

**"36 named nowhere" was the last row, not the third.** This record and `DF5-I16` both carried it
as the count named in no decision, which is 51. Corrected here and in the inventory row.

**The recorded mechanism reached 17 of the 59.** "The modules the node callables come from"
resolves to `agent` alone on dogfood #5, which defines all 34 node callables at module level and
calls into `tvtime/` from inside their bodies, plus `simple_agents.builtins.http`, whose three
constants are the library's own. Every constant `DF5-D10` quotes is outside that set:
`ranker.WEIGHT`, `ranker.RATING` and `schedule.WINDOW_DAYS` in `tvtime/`, and `web.PER_PAGE`,
`web.SEMANTIC_DEPTH`, `web.ANNOUNCED_ON_DISCOVER` and `web.REASON_CHARS` in `web/app.py`.

### The four decisions of 2026-08-27

**1. Which modules the manifest reads, Thilina's call: the project-module closure.** The modules
the node callables come from, plus the project's own modules those import, transitively.
Measured: **48 of the 56 distinct names**, every one in `agent.py` and `tvtime/`. The eight it
misses are `web/app.py`'s seven and `tvtime/preferences.py`'s one, a module no node path
imports. **The seven are the product surface**, which the `presentation` kind covers and which
sitting 3 settled carries no `produces`, so the boundary the closure draws is the boundary the
kinds already draw. The alternatives were the recorded rule at 17 of 56, and every `.py` file
under the project root at 56 of 56, which a run cannot see and which would have moved the whole
mechanism out of the manifest and into a filesystem scan at check time.

**2. What the join reads, Thilina's call: every manifest under `runs/`.** The record had it read
the newest run's manifest. **Measured: that reads one pipeline of seven.** Dogfood #5's newest
agent run is the queue pipeline, five nodes and two tools; across its 2,669 runs it has produced
34 node ids and four tool names. A `shape` decision naming a discovery node would have been
reported as naming something no run produced, on nothing but which command was typed last.
FT-40's code-reading route does not rescue it: `load_project` finds pipelines through
`@pipeline_factory` or a module-level `Pipeline`, and dogfood #5 has `build_*()` functions, so it
returns **zero**. Reading all 2,669 manifests costs **0.08s**, and FT-41 already walks them.

**3. The gate, Thilina's call: the forward direction fails at `ship`; the reverse reports at
every stage and never fails.** `DF5-I16`'s row said note-before-`ship`, fail-at-`ship` for both.
Thilina, 2026-08-27: *"I want the coding agent to check with the builder on important constants,
but asking about every single one would be way too overkill and would probably just get ignored
by both the coding agent and the builder."* Measured at `ship` on dogfood #5 under decisions 1
and 2: the reverse direction would have demanded **71 names** — 25 node ids, 3 tool names and 43
constants — across a brief holding 31 decisions. The forward direction is a factual error about
something that does not exist and carries no judgement, so it gates; the reverse is a
completeness demand the library cannot judge, since `MIN_INTERVAL_S = 0.34` is TVmaze's published
rate limit and not the builder's to decide.

**4. `behaviour_fingerprint`, Thilina's call: constants stay out of it.** Recorded in the
manifest beside it. A constant in a module the pipeline imports is not something the pipeline
declares, and putting it in would move the stamp whenever any number in any reachable module
changed, including ones nothing reads. `docs/shipping.md` §6's recipe re-runs work when the stamp
moves, so a false move costs money. `docs/run-envelope.md` says plainly that editing a constant
does not move it.

### A deleted step, asked and declined 2026-08-27

Thilina asked whether the coding agent should get a way to confirm something was deleted so it
drops out of the union. **Declined, and the existing surface does it.** Measured: of the 25 node
ids the reverse note would print on dogfood #5, **17 were still running on the final day and 8
were last seen on 2026-08-20 or 21**. A deleted step fails nothing under this design, since the
forward direction resolves it against the union correctly and the reverse never fails, so the
whole question is the length of a report. A `[retired]` key would be the one brief key no
artifact can contradict, which is somewhere to put the awkward ones in the item that exists
because a coding agent made 37 decisions alone. **Naming a deleted step under `produces` on the
decision that removed it takes it out of the reverse list already**, because that list holds what
no decision names, and it reaches the builder as a `changed` decision. The note groups by
recency and drops nothing: what the newest run carries, then what was last seen earlier with the
date.

## 3. Build

**Manifest format `0.32` → `0.33`**, one field: `constants`, a `module`, `name` and `value` each.

| Surface | What |
|---|---|
| [`manifest.py` `module_constants`](../../src/simple_agents/records/manifest.py#L830) | The introspection: seed modules from the node callables, closure over the project's own, names from the source and values from the namespace |
| [`pipeline.py` `manifest_constants`](../../src/simple_agents/pipeline/core.py#L2001) | The public accessor, beside `manifest_tools` and `manifest_prompts` |
| [`decisions.py` `PRODUCING_KINDS`](../../src/simple_agents/conformance/decisions.py#L354) | `produces` on `Decision` and `DecisionKind`, and the refusal on the two kinds that carry none |
| [`checks.py` `ft_42`](../../src/simple_agents/conformance/checks.py#L2016) | The forward direction |
| [`run.py` `_produced_by_no_decision`](../../src/simple_agents/conformance/run.py#L557) | The reverse, grouped by recency |
| [`produced.py`](../../src/simple_agents/conformance/produced.py#L1) | What every run recorded, read once for both |

**3487 tests, up from 3415.** Two new files: `tests/test_manifest_constants.py` and
`tests/fixtures/constants_project/`. One new fixture project, `decision-produced-nothing`, and
`produces` on the conforming fixture's four producing decisions.

**What the build found that the design did not know.** Six defects, each found by reading the code
back after it passed, and each with a test that fires on it:

1. **A module reached only by importing data from it was missed.** The walk followed modules,
   functions and classes in the namespace; `from .config import LIMITS` binds a dict, so `config`
   was never reached and the numbers beside `LIMITS` were invisible. That is the exact shape the
   item exists for. The module's own imports are now read from its source as well.
2. **An installed path was matched as text.** A project at `/x/library` was under an installed
   path at `/x/lib`. Compared by path component now.
3. **The source cache never expired.** A module edited and re-imported in one process, which is
   what `view --serve` does, was answered from what it used to say. The file's mtime is in the key.
4. **The note fired on a project with no runs**, saying its runs predate format `0.33`.
5. **A project upgrading from `0.32` failed at `ship`** claiming it never built constants it has,
   because no run carried a `constants` array to join against. A name only a `constant` decision
   records is left out where no run recorded any, and the pass says so.
6. **A malformed manifest entry raised**, taking the whole report with it, and an unparseable
   manifest counted as a run read.

**And two crashes on a brief typo**, one of them pre-existing: `produces = 5` and `from = 5` both
raised `TypeError` rather than naming what the field takes. Both now refuse with the shape to
write. `from`'s was there before this item.

## 4. Verification

**vLLM `Qwen/Qwen3-1.7B` on port 8001** and **Gemini `gemini-3.1-flash-lite`**, a two-node
pipeline whose callables live in `agent.py` and whose numbers live in two modules beside it.

| What | Result |
|---|---|
| Live run, both backends | `completed`, manifest `format_version` `0.33` |
| Constants recorded | 7, across `agent`, `shortlist.catalogue` and `shortlist.scoring`. `_ROUNDING` excluded, `simple_agents` excluded |
| FT-42 at `build` | Note: `explain_the_pick`, a node the brief agreed to and the project never built |
| FT-42 at `ship` | Failure, on the same name |
| The reverse note | The 5 constants no decision names; the 2 a `constant` decision names are absent, and so are the node ids and tools the other decisions name |
| `behaviour_fingerprint` | Unchanged across the fixture rebuild. Only `format_version` moved |

**Against dogfood #5's frozen copy**, with the current library: 48 distinct constant names across
9 modules, no `simple_agents` module among them, and the report's note naming 34 node ids and 4
tool names with 11 of the nodes dated to before the last day.

**Six read-verify-test-live cycles were run** and the sixth found nothing new. Defects 1 to 3 came
out of cycle 1's read, 4 and 5 out of cycle 3's, 6 out of cycle 4's.

## 5. Doc consequences

| File | What |
|---|---|
| `docs/run-envelope.md` | §2.9 `constants`; the field row; version `0.33` |
| `docs/conformance.md` | §2.2 "What a decision became"; the note in §4.4; FT-42's rows in §3 and its table; the sample report regenerated; five counts moved from twenty-four to twenty-five |
| `docs/failure-taxonomy.md` | FT-42, its index row, the counts, and the FT-40/41 stage sentence |
| `docs/procedure.md` | `produces` in the decisions example and one sentence beside it, and one clause at stage 4 |
| `CHANGELOG.md` | The four changes, each with what it costs a project |
| `README.md` | 41 failures to 42, twenty-four checks to twenty-five |

**`docs/procedure.md` is at exactly its 3000-word budget**, which
[`test_procedure.py`](../../tests/test_procedure.py#L70) `WORD_BUDGET` enforces. It had 47 words of headroom
before this item. The next addition to that file has to take something out.

## 6. Left open

- **`considered = 5` in a brief still raises `TypeError`.** The same crash as `from` and
  `produces`, one line away, left because `considered` holds prose alternatives rather than names
  and needs its own message. → [`plan.md` §2.1 `considered`](../plan.md#L43).
- **`web/app.py`'s constants are unreachable from a run**, by decision 1. A product surface's
  numbers reach a builder through `presentation`, which carries no `produces`, so nothing joins
  them. → [`plan.md` §2.2 `a product surface's numbers`](../plan.md#L240), with what would decide it.
- **The manifest's `constants` array is uncapped.** 48 entries on dogfood #5, about 3KB, written
  into every rollout's manifest. A project with hundreds of modules writes proportionally more.
  Nothing has measured one. → [`plan.md` §2.2 `a cap on the manifest's constants array`](../plan.md#L253).
