# Build log — the product

`plan.md` §1 P3-30. Started 2026-08-20. Written while building, not afterwards.

## 1. Before any design

The design was settled at the sitting the same day, so what belongs here are the two questions
the record left to the source. Both were read on 2026-08-20, before any dependent text shipped.

**Overlapping `run()` calls are safe under named conditions, and the library already ships the
pattern.** [`EvalSuite`](../../src/simple_agents/evaluation/runner.py#L189) calls
`self.pipeline.run(...)` from a thread pool on one `Pipeline`, and `tests/test_concurrency.py`
exercises two rollouts of four-wide runs at once. `Pipeline` assigns to `self` only at
construction; everything per-run is built inside `run()` and passed down. `RunEnvelope`'s
`with_*` methods copy. `RunContext`'s counters and `Manifest` are instance-level and locked,
and no module-level mutable state sits on the run path. The conditions `docs/product.md` has
to state: a distinct `run_id` per call, a `MemoryStore` scope per run, a thread-safe client,
explicit pacing, and a `HostPolicy` per run.

**Four defects found by that reading**, each dispositioned by Thilina the same day: 1 and 2
fixed in this item, 3 recorded on `plan.md` §2.1's ceiling entry, 4 noted here and nowhere
else:

1. [`context.py:76`](../../src/simple_agents/context.py#L76) `new_run_id` is the UTC second
   plus four hex characters, and a collision merges two runs silently:
   [`envelope.py` `prepare`](../../src/simple_agents/envelope.py#L844) `prepare` makes the directory
   with `exist_ok=True` and [`trajectory.py:825`](../../src/simple_agents/records/trajectory.py#L825)
   `TrajectoryWriter` opens append, so both runs write one trajectory, one manifest and one
   suspension record with nothing raised. The eval runner guards its own rollouts;
   `Pipeline.run` has no guard.
2. [`spend_fetch`](../../src/simple_agents/tools.py#L572)
   counts on the shared policy object with an unguarded read-modify-write and no per-run
   reset, so `max_fetches`, documented as a ceiling for the whole run, is a process-lifetime
   ceiling shared by every run holding the object, and its refusal text ("This run has made
   its limit") is false where runs overlap.
3. [`pacing.py:224`](../../src/simple_agents/pacing.py#L224) `expect_callers` overwrites
   rather than accumulates, so a run starting mid-flight resets the floor the first run paces
   against, and N overlapping runs under-pace by a factor of N. A `min_remaining_requests`
   passed to the constructor is not overridden, which is the documented escape. This is
   `plan.md` §2.1's ceiling entry met again.
4. [`http.py:79`](../../src/simple_agents/builtins/http.py#L79) `http_fetch`'s
   `min_interval_s` closure is unguarded across runs; the interval degrades and nothing else
   is harmed.

**A store write during an evaluation points at the run's own directory, and the mechanism
differs by step kind.** A [`Deterministic`](../../src/simple_agents/nodes/deterministic.py#L29) body always
executes, replay included (its `execute` calls `self.fn` unconditionally), and
`ctx.workspace` is the run's fresh directory. A tool's function receives only its arguments
and handles ([`tools.py:819`](../../src/simple_agents/tools.py#L819) `call`); the run
directory reaches it only through a [`Workspace`](../../src/simple_agents/tools.py#L204)
handle, and holding one makes the tool re-execute on replay (`RE_EXECUTED_HANDLE_TYPES`).
No role, no `live`, and no evaluation flag reaches tool or node
code; the memory store is the one store the library redirects per rollout
([`runner.py:2556`](../../src/simple_agents/evaluation/runner.py#L2556) `_scoped_for_rollout`).
A `writes` tool is never refused and never redirected, so a pipeline ending in a write to the
product's store writes seeded results into it examples × k times at any concurrency. What the
docs can truthfully say: evaluation output goes to the run's workspace; a real-store
destination is bound at declaration, and swapping it moves the tool's derived version and so
the cassette key.

**And the reading found a shipped statement false**, corrected on sight and logged as
`DF4-X15` in [`inventory.md` §2](../runs/dogfood-4/inventory.md#L59): `docs/evaluation.md`
§6.3 claimed `suite.run`'s k rollouts share a recorded tool answer, and a fresh `suite.run`
records without serving; the sharing belongs to replays, resumes and `suite.record`. FT-20's
taxonomy text had it right.

## 2. Design

The sitting of 2026-08-20, eight decisions, all agreed by Thilina. This section is
`items/the-product.md`, the item's record, moved here when this log opened. It waited on
nothing.

### Where it came from

Dogfood #4's sitting 7, the last of `P3-1`, held 2026-08-20 over `DF4-I06` (the conformance
suite's artifact model reads a results file and a run directory; the product can be a third
thing) and `DF4-I38` (a UI is built as a display over stored output rather than as part of the
system). Both descend from [`DF4-D1`](../runs/dogfood-4/findings.md#L197), the run's largest
finding, and from `DF4-N14`, verbatim in [`inventory.md` §5](../runs/dogfood-4/inventory.md#L823).

Thilina's framing at the kickoff: *"Possibly the biggest issue I had with DF4 is that the coding
agent does not consider the fact that what's being built is something that would actually get
used, even when it was explicitly told that I want something that replaces Goodreads. ... The
final product that was built was simply a view over some evaluations and runs that were done
during development."*

The inbox entry of 2026-08-18 on scheduling (*"refreshing data, like pulling from an API on a
schedule, or watching something"*) folded into this item as the trigger question, with the
mechanism kept live in [`plan.md` §2.2](../plan.md#L137).

### What the problem is

**The library models development completely and the thing being built not at all.** The
trajectory records what the agent did, the results file what a measurement found, the brief what
was agreed; the artifact the end user opens has no name, no question, no design surface and no
place in any check. The glossary defines the agent as one component of the project and never
names the component the end user touches. Of the 43 elicitation questions none asks what the end
user opens: `what_it_does` asks who receives the output, `presentation` asks the result's shape
and states the library ships nothing that shows it, and `stored_output` asks what they read at
the last gate, after everything is built. `design.md`'s three sections are all about the agent.

Reasoned from the problem rather than the dogfood, a product comes in three shapes, and most
real ones mix them: **request-shaped** (the end user asks, a run answers), **artifact-shaped**
(runs maintain something read between runs), **effect-shaped** (runs act inside someone else's
tool). This answers `DF4-Q2`: the store is one of three shapes, so nothing here may assume it.
Auditing what any of the three needs against what ships: invocation, suspension across a
surface, consultation channels, `live` and `role` on runs, the stamp, the feedback loop and
cost reporting all exist. What is missing is the concept, the procedure, the assembled story,
the trigger, and provenance on the persisted artifact. Dogfood #4 is what the gap produces:
`finished_version` said "replaces Goodreads and owns the reading state" on day one, and a UI
session at the end, with no concept to reach for, built a display over the store.

### The eight decisions

1. **"The product" is a named part of the project**, in `docs/index.md`'s vocabulary and the
   `CLAUDE.md` glossary: what the end user uses, the surface they meet the agent through and
   any artifact kept for them to read. Every project has one, and the builder's own script is
   the degenerate case. `DF4-I06` is answered in principle: the conformance suite gains no
   reader of project storage (`P3-6`'s precedent stands undefeated), and the product enters as
   a declared thing.
2. **It enters at brainstorm and is pinned at design.** One new required brainstorm question,
   `used_through`: what does the end user open, and what happens when they do; the scaffold
   asks for the surface, the actions, and what makes a run happen. `design.md` gains a required
   fourth section: every end-user interaction classified as exactly one of **starts a run**,
   **answers a waiting run**, **reads the artifact**, or **records a judgement**, plus, where
   an artifact exists, what writes it, what refreshes it and what triggers runs. A display over
   stored output has zero interactions of the first two kinds, and the classification is what
   puts that in front of the builder before code exists (`DF4-I38`'s answer). Stage 4 writes
   the pipeline and the product.
3. **The artifact rules.** The measured failure was superseded versions and no refresh, and was
   never dev against live: dogfood #4's queue was legitimately development-written, with the
   builder as end user. The stamp and refresh (`P3-6`) are designed in the design section;
   `stored_output` stays at ship as the confirmation that what shipped matches. One new rule to
   document: a rollout must not write the product's artifact, mechanism verified at build.
4. **Almost no runtime.** (a) No shipped store object: the one observed artifact was tables
   inside the project's own schema, so `plan.md` §2.2 takes the entry with its decider. (b) No
   server: `docs/product.md` assembles the invocation story (a request is `run` under
   `with_live()`, `Suspend` across the surface, `resume` on answer, progress, cost per run),
   and one `P3-2` example project is product-shaped. (c) No scheduler: the trigger is elicited
   and the pattern documented; the mechanism stays live as its own §2.2 entry on Thilina's call.
5. **Checks read declarations.** `used_through` rides FT-24; a check reads the design section
   (FT-37, or FT-34 widened, the build decides); `simple-agents report` gains a live-runs note
   rather than a gate; two `docs/failure-taxonomy.md` §10 rows (the store is not opened, which
   exists since `P3-6`, and nothing verifies the surface reaches the agent, which is new).
6. **A seventeenth document, `docs/product.md`**, pointed at from procedure stages 1, 3 and 4,
   with a deployment note: wherever the product runs, `runs/` lands where the project reads
   back, or `docs/shipping.md` §2's loop goes blind.

### Open, for the build

- The rollout-write mechanism: where a store-writing step points during an evaluation.
  `docs/evaluation.md` §6.2 warns that state in a tool is shared across rollouts and says
  nothing about where to point a store write. Verify against the code which candidate is right:
  the run directory, replaying the write tool, or a scratch store the example seeds.
- Whether one `Pipeline` and one envelope safely serve overlapping `run()` calls, verified
  rather than assumed, and stated in `docs/product.md` either way. Pacing under many end users
  is `plan.md` §2.1's ceiling entry (its fifth instance): cited, never solved here.
- FT-37 against widening FT-34's reading.
- The brief's shape moves again, the day after `P3-28` moved it (`used_through`, and the design
  section's confirmation key). Cheap pre-adoption; the build log records the cost.

## 3. Build

**The vocabulary, 2026-08-20.** "The product" enters `docs/index.md`'s vocabulary table and the
`CLAUDE.md` glossary: what the end user uses, the surface they meet the agent through and any
artifact the project keeps for them to read; the agent runs inside it, and the builder's own
script is the smallest case.

**The `DF4-X15` correction, 2026-08-20.** `docs/evaluation.md` §6.3's sharing sentence and
`_recording_by_default`'s docstring, both corrected the day the §1 reading found them.

**Defect 1's fix, 2026-08-20, on Thilina's call.** `new_run_id` carries eight random
characters where it carried four; the docstring, `envelope.py`'s example, `docs/run-envelope.md`
§3's format sentence and one test's regex moved with it. Nothing parses the id.

**Defect 2's full fix, 2026-08-20, on Thilina's call, with the mechanism agreed at its own
mini-sitting**: `HostPolicy` takes `MemoryStore`'s shape. The object the project builds is the
declaration; each run binds its own copy through
[`bound_fetch_policy`](../../src/simple_agents/context.py#L421) on `RunContext`, keyed per
declaration so two tools declaring two policies get two tallies. The copy reaches tools as the
sixth handle type (beside `SpendMeter` among the non-re-running ones, since a replayed fetch
is served and must not refetch), and nodes and routes at `ctx.fetch_policy`. `admit` and
`spend_fetch` on the declaration itself refuse with the instruction naming both routes; the
copy's mutators run under a lock, which closes the unguarded read-modify-write. A tool taking
the parameter with no declaration on the tool or the pipeline is refused at `Pipeline`
construction. The manifest's `fetch_policy` keeps its shape and its counts become the run's
own. `http_fetch` and `read_page` moved their bodies onto the injected copy, with one
description constant per tool so the two signature variants cannot drift; their derived
versions move, and no recorded cassette held a fetch call. Tests went from 2927 to 2931;
`tests/test_host_policy.py` carries the template refusal, the per-run separation and the
construction refusal.

**What the fix does not cover, recorded rather than silent**: a delegated pipeline whose tool
relies on the root pipeline's declaration is refused at the delegate's own construction, since
a delegate cannot see the root; declaring on the delegate or the tool is the path. And a
tool-declared policy that is no pipeline's is still absent from the manifest, which is parity
with what shipped before.

**The concept ships, 2026-08-20.** `used_through`, fourteenth at brainstorm and ninth
required, with the surface list left open-ended on Thilina's wording. The `design.md` product
section, with FT-34 widened through
[`DESIGN_SECTIONS`](../../src/simple_agents/conformance/artifacts.py#L60): one tuple entry,
and the taxonomy's own text carries the four interaction kinds. `docs/product.md` as the
seventeenth document, forced into the same change by the meta-tests, which refuse a shipped
citation of a document that does not exist. Fixtures regenerated with a `used_through` answer,
a product section, and the shape decision resting on the new answer. Index and README rows.
**The procedure was reviewed whole rather than budged**, on Thilina's instruction: four
passages restated documents the file points at, or said a thing twice, and were trimmed with
his approval, so the file is at 2158 words against the unchanged 2160 budget. 2933 tests.

**The report's live-runs line was found built, and never built here.** `P3-25` already prints
"N of them made by an end user" from
[`reporting.py:152`](../../src/simple_agents/cli/reporting.py#L152) `_activity_line`, so decision 5's report note
cost nothing. The two `docs/failure-taxonomy.md` §10 rows, the `docs/evaluation.md` §6.2
extension (the store write that outlives the run, and where it points), the
`docs/shipping.md` §6 and `stored_output` cross-references, and the `presentation` scaffold's
pointer closed the chunk.

## 4. Verification

**Live against Gemini `gemini-3.1-flash-lite`, 2026-08-20**, scripted at
`scratchpad/verify_p3_30_hostpolicy.py`: a `Deterministic` node fetching `example.com` for
real under a `HostPolicy`, admitting `iana.org` through `ctx.fetch_policy`, then an `LLMNode`
reading a line of it. One run alone, then two overlapping from threads, through one `Pipeline`
and one declaration.

| What it had to show | Result |
|---|---|
| A generated id carries eight characters | `run_20260820T130049Z_3039e93b`, and the two overlapping runs started inside one second and did not collide |
| Each run counts its own fetches | `fetches: 1` and the `iana.org` admission in all three manifests |
| The declaration is untouched | `fetches == 0` and no admissions, after three runs |
| `ctx.fetch_policy` reaches a node body live | The admission above was made there |

**What the live run met first is FT-09**, the refusal P3-6's verification also recorded: a
schema with no `unknown` variant is refused at construction, and the message's first fix,
`Maybe[str]`, is what the script then used.

**The closing live run, 2026-08-20**, scripted at `scratchpad/verify_p3_30_product.py`: the
product story whole. A request handler started a run under `env.with_live()` against Gemini;
the agent consulted through the surface, whose channel raised `Suspend`; the process ended;
`Pipeline.suspensions` listed the waiting runs the way a surface's inbox would; and a separate
process rebuilt the pipeline and resumed with the answer. Output
`title='The Thursday Murder Club'` for "a cozy mystery", and the manifest closed with
`live: True, outcome: completed`. The caller-facing exception is `RunSuspended`, whose message
carries the resume call verbatim, which the script followed.

## 5. Doc consequences

Accumulating; listed as they land. So far: `docs/index.md` (vocabulary row);
`docs/evaluation.md` §6.3 corrected under `DF4-X15`; `docs/tools.md` §3.2 (the sixth handle
type) and §4.4 (the declaration each run binds a copy of, `ctx.fetch_policy`, and the tool
parameter); `docs/run-envelope.md` §3's id sentence; and two `CHANGELOG.md` entries. The
statement that stopped being true is §4.4's, that project code admits by calling the policy
object it built.

## 6. Left open

- **Whether dogfood #5 is product-first.** Several of this item's deciders point at it: the
  store entry, the scheduler entry, and `DF4-Q1`'s real answerer, which a product surface
  finally is. Destination: [`plan.md` §2.2's store entry](../plan.md#L147), whose decider
  names that run, with the TVTime inbox entry as a candidate task; the run's own `setup.md`
  takes it from there.
- **A tool-declared policy that is no pipeline's is absent from the manifest**, which is
  parity with what shipped before this item. Destination: nothing; recorded in §3 so the
  omission reads as known.
- **A delegated pipeline cannot lean on the root's fetch declaration**: its own construction
  refuses first. Declaring on the delegate or the tool is the path, and the refusal says so.
  Destination: nothing.
- **The product-shaped example project.** Destination:
  [`items/example-projects.md`](../items/example-projects.md#L1747) §19.9, written at the
  sitting.
