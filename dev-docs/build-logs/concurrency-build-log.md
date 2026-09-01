# Build log — concurrency: independent branches, and a fan-out that runs together

**Sitting 2026-08-13, built and closed the same day.** `archive/plan-history.md` §1.12 is the design of record
and carries the six decisions with their arguments; this is what building them found. Opened
before any code was written, and filled as the build went.

**1879 tests**, suspension format `0.3` to `0.4`, trajectory and manifest unchanged.

**The build is smaller than the audit.** What shipped is §3.1 and reads as a feature; what the
testing found is §3.6 and §3.9 to §3.12, seven defects of which three predate this item and one
had been telling builders to do something that does nothing. Anyone reading this for the design
wants §3.1 to §3.5. Anyone about to touch shared state wants §3.6 and §3.9.

**What is not covered, stated so nobody assumes it is.** The retry path is exercised live only
against Gemini's free tier, at one width. vLLM under sustained saturation is untested, because
dogfood #4 held the GPU throughout; the shapes were measured against it at six requests in
flight and no further. And the soak runs against a fake client, so it exercises the library's own
locking rather than any adapter's.

---

## 1. What the sitting changed about the item

**Three questions were open coming in** (`archive/plan-history.md` §1.12 as it stood on 2026-08-12): whether
concurrency is opt-in per node, per pipeline or per run; whether a fan-out and independent
branches are one mechanism or two; and what a budget refusal does to work already in flight.

**Three more were opened by reading the code before proposing anything**, and two of them are
defects that ship today with no concurrency involved:

| Found | What it is | Where it landed |
|---|---|---|
| `max_wall_clock_ms` is the sum of per-call durations, not elapsed | A fork the brief did not name: under concurrency the sum exceeds elapsed, and the axis doubles as the self-hosted cost proxy in `docs/run-envelope.md` §4 | Decision 4 |
| The library's own refusal instructs a coding agent to invent an hourly rate | `Budget` has no default for `max_cost`, so a number gets written; that number reaches `_refuse_unauditable_cost`, whose message leads with two clauses that require a cost basis and buries `max_cost=None` third | Decision 4, fixes A and B |
| A tool call's occurrence count is keyed run-globally | Adding a `search(q)` to one node invalidates another node's recorded entry. Present today; a race under concurrency | Decision 5 |

**Two claims in the brief did not survive being checked**, and both were about where the
difficulty is:

- **"`sequence` is a total order and would have to express a partial one."** It does not have to.
  `sequence` is allocated at emission and stays monotonic in write order, a parent still emits
  after its children, and `per_node` resolves a record to its node through `parent_id`. Nothing
  downstream reads the ordering as causality. What is lost is that the order is reproducible,
  which is a guarantee to restate rather than a format to change.
- **"Cassette keys are content hashes and are already order-independent. Nothing to do."** True
  of the hash and false of the input to it. A model call's key carries its seed, and the seed
  comes from a per-node counter that arrival order moves.

**One first recommendation was withdrawn before it was acted on.** Building the fan-out first and
taking branches as a following item is cheaper and lower risk, and it leaves the sentence that
put the item on the schedule exactly where it was, because that sentence is about arms rather
than items. Recorded because the reasoning is worth keeping: the cheap half of an item is not the
half that motivated it.

---

## 2. Three corrections Thilina made to the proposal

Kept because each names a rule the next design should apply, rather than only a thing that
changed.

**2.1 The run ceiling was argued for from a premise that had already been built away.** The
proposal said a run-level ceiling is right because "the quantity that must be bounded is total
calls in flight against one client". Per-node model selection shipped 2026-08-10 (§1.3), so a run
has as many clients as its nodes declare, and `_clients_of` has enumerated them and paced each
separately since the evaluation item. The structure survived; the argument for it did not, and
the corrected version is in Decision 2. **The rule:** an argument from what the library does has
to be checked against what the library does now, not against what it did when the section was
written.

**2.2 A per-client ceiling was presented as an alternative to a total, and they are not
alternatives.** They bound different harms: a total bounds thread count and the drain overshoot, a
per-client bound protects a backend's quota. Offering them as a choice between two would have
picked for the builder in a place where the builder has a reasonable preference either way, and
the case that makes it concrete is one cheap client and one expensive one. **What shipped** is
the run total and a per-node count, with the per-client ceiling in §3.2.1 naming the case it is
for. **The rule:** two mechanisms that bound different things are not options for the same
decision.

**2.3 Restricting concurrent tool calls to `READ_ONLY` was doctrine, and the library's own
position is against it.** The proposal excluded `SPENDS_MONEY` and `IRREVERSIBLE` from a turn's
concurrent group on the grounds that drain lets real actions complete past the ceiling. That is
true and it is the builder's decision to make: `simple-agents.md` §9 item 5 refuses `irreversible`
tools **in evaluation rollouts**, deliberately, and no such refusal exists in `Pipeline.run`
because a live run is the builder doing the thing on purpose. **`WRITES` stayed refused on a
different ground** that survives the same test: the workspace is created by the library and the
same `Path` is handed to every node, so refusing concurrent writes into it defends a resource the
library owns rather than one the builder owns. **The rule:** a refusal needs a reason that names
whose resource is at stake.

**2.4 A keyword that names no subject reads as a switch.** `concurrent=True` on a node was
proposed for "may overlap other nodes" beside `concurrent_items=` and `concurrent_tools=`. It
reads as turning concurrency on. Two rounds followed: naming it fully on the node, then moving it
to the pipeline as `concurrent_nodes=`, which is where a pair of nodes is in view at all. The
final shape is in Decision 2. **The rule:** every keyword names the thing it governs, and a bare
one that names nothing is the tell.

---

## 3. The build

**1851 tests pass**, 23 of them new in `tests/test_concurrency.py`. Suspension format `0.3` to
`0.4`. The trajectory and manifest formats are unchanged: nothing about a record's shape moved.

### 3.1 What shipped

| | |
|---|---|
| `Pipeline(concurrent_nodes=[[...], ...])` | Groups. Two nodes may run at the same time when a group lists both, so any number of groups of any size, and a node may be in several |
| `LLMNode(over=..., concurrent_items=8)` | Items of one fan-out |
| `AgentNode(concurrent_tools=[search, fetch])` | Named tool calls inside one turn |
| `Pipeline.run(concurrency=N)` and `resume(concurrency=N)` | Calls in flight, defaulting to 1 |
| `Pipeline.resume(answers={node_id: ...})` | For a run that stopped in more than one node |
| `RunSuspended.stops` | One entry per stopped node, each with its own `waiting_for` |
| `concurrency.py` | `WorkPool`: the ceiling, the drain rule, and `UnitOutcome` |
| `scripts/rekey_tool_calls.py` | Migrates a recorded cassette to the new tool-call key with no backend call |

**Measured, on a fake client so the numbers are the library's own overhead and not a backend's:**

| | one after another | overlapping |
|---|---|---|
| Two 0.2s branch arms | 0.60s | 0.30s |
| Three 0.3s tool calls in one turn | 0.90s | 0.30s |

### 3.2 The ceiling bounds calls, not units, and that is a correction to the sitting

§1.12 Decision 2 says the run ceiling bounds "total units in flight". It bounds **calls** in
flight, and the difference is what avoids a deadlock. A unit waiting for the units below it —
a branch arm whose node is a fan-out — would hold a slot while its own items waited for slots,
and a run whose arms all did that would wait on itself. So a slot is held for the duration of a
call to a backend and a thread that already holds one does not take a second. Thread count is
then bounded by what the declarations ask for rather than by the ceiling, which is the cheap
resource; calls are the expensive one and are what the number is for.

### 3.3 A stale label became load-bearing

`node_id` on a cassette entry was read by nothing but a miss message. Putting it in the tool-call
key made it load-bearing, and two committed recordings turned out to be wrong in that field:
`suspend.jsonl` and `suspend-vllm.jsonl` record the consultation entry under `node_id:
"consult"`, the tool's name rather than the node's. The filing path was fixed in `8911d0c` and
`test_the_filed_answer_is_keyed_under_the_node_and_not_the_tool` holds it; the recordings predate
that fix by two months and nothing noticed, because nothing read the field.

Both files are repaired. `rekey_tool_calls.py` grew `--relabel=old=new` so the repair is a
recorded command rather than a hand edit, and the general lesson is on the script: a recording
made before a fix can name a node that never made the call.

### 3.4 An exact `max_steps` needs a reservation, not a check

Decision 3 says a unit does not start unless a step remains, and the first implementation read
the budget at the top of each unit. That is check-then-act: with `max_steps=2` and two items
overlapping, both read `steps=1` and both proceeded, and the run made three calls against a
ceiling of two. The test caught it because it asserted the exact count rather than that the run
stopped.

`RunContext.one_step` is the fix: under the run's lock it counts what has been spent **plus what
is in flight**, refuses on that, and holds the reservation until the call returns. One call is
one step and a step is known before the call, which is why this axis can be exact while the other
three are measured by what a call turns out to consume and can overshoot by what was running.

### 3.5 A suspended run is a tree

`_Frame.in_progress` is a list, `node_state` is keyed by node, and each stopped node keeps its own
stack of frames below it under `below`. A level where two arms stopped therefore branches, which
a flat stack of frames could not express: the outer level has one frame and two ways down from it.

`SuspensionState` follows: `stops` is a list, one entry per stopped node with its own
`waiting_for`, `options` and `resume_not_before`, and `node_id`/`waiting_for`/`options` survive as
properties reading the first stop, so a reader of a single-stop run is unchanged. `resume(answer=)`
is refused where several stopped, naming them and pointing at `answers=`.

### 3.6 The ceiling was not being enforced, and only a measurement found it

`WorkPool.slot()` was written, documented, and **called from nowhere**. Nothing failed: `map`
clamps each call site to `min(limit, ceiling)`, so every test passed and every single-region
measurement was right. What was wrong is the case with more than one region at a time. Two arms
each fanning out at `concurrent_items=3` under `concurrency=3` put **six** calls in flight, twice
what the run declared, and a pipeline with three such arms would have put nine.

It was found by asking a client to count what it actually had in flight rather than by timing the
run. A stopwatch cannot see this: the run is faster either way, and faster is what a wrong answer
looks like here.

The fix is one slot held around each call that reaches a backend, in `RunContext.call_model` and
`RunContext.call_tool`, re-entrant per thread so a tool that calls a model through a handle does
not wait for the slot its own caller holds. `test_one_ceiling_covers_two_concurrent_regions`
holds it, and the live probe confirms it against the server: a fan-out of six under a ceiling of
two, and vLLM reports two in flight.

**The rule this leaves:** a bound that is never exercised by more than one caller is not a bound
that has been tested. The measurement has to come from the resource being bounded.

### 3.7 The scenario matrix

Twenty-three shapes, each with a 60-second timeout because a nested pool fails by hanging rather
than by answering wrongly, and each asserting on the peak number of calls in flight rather than on
elapsed time. All twenty-three pass, and the ones worth naming:

| Shape | What it establishes |
|---|---|
| Two arms, each a fan-out of four | A concurrent region inside another does not wait on itself |
| One ceiling across two regions | §3.6 |
| An `AgentNode` with concurrent tools inside a concurrent arm | Three units nested two deep |
| A fan-out inside a delegated pipeline, on its own client | Delegation and per-node models under overlap |
| A nested `Pipeline` with its own `concurrent_nodes` | Groups are per pipeline, not per run |
| A cycle, an `on_error` edge, a skip, and a join, each beside an overlapping arm | Every graph feature survives |
| An unhandled raise in one arm | Reaches the caller, and the arm beside it drains |
| `max_steps=2` across three overlapping arms | Exact |
| One arm stops, the other finishes and is kept | Drain, with the finished arm's output in the frame |
| Resuming a run that stopped in two arms | `answers=` keyed by node |
| An evaluation at `concurrency=2, run_concurrency=4` | 24 calls, both numbers in the results file |

**Four failures on the first pass, and three were the harness**: a delegate whose entry node
declared no type, a `Loop` whose `then` was inside its own cycle, and two assertions I had written
backwards, including the parent-after-child one, which the library had right and the test had
upside down. The fourth was §3.6.

### 3.8 Against a live backend

**vLLM, `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on dogfood #4's server, read-only and on
Thilina's instruction.** This is the backend that can *report* the overlap, so the library's claim
is checked against the server rather than against a stopwatch. `report_concurrency=True` reads
what vLLM had in flight during each call:

| | elapsed | server saw in flight |
|---|---|---|
| Six documents, one at a time | 0.70s | 1 |
| Six documents, six at once | 0.20s | **6** |
| Six documents, ceiling of 2 | 0.43s | **2** |
| Two branch arms, in order | 0.14s | 1 |
| Two branch arms, overlapping | 0.09s | **2** |

Same answers both ways: `[32, 34, 30, 36, 31, 33]`. A record at width six then replayed at width
one and at width six gave identical seeds and identical answers, **including one item that failed
validation and replayed as the same failure**.

**`DeviceBasis` end to end on a real device**: `0.190 device_seconds`, `is_upper_bound: false`,
which is the flag being false because the server reported its concurrency and the division was a
measurement rather than a bound.

**The overlap risk, measured rather than assumed.** `concurrent_requests` is the divisor for a
compute-basis cost, so a probe overlapping a dogfood call would leave that dogfood a wrong figure.
The probe window was `03:13:56` to `03:13:58`. In the surrounding two minutes dogfood #4 made
**207 model calls, every one of them `hosted_api` with `concurrent_requests: null`** — it was
calling Gemini throughout and reached the vLLM server not once. Nothing of its could be inflated,
and nothing was written anywhere under `/home/thilina/Projects/dogfood-4`.

**One thing the probe got wrong and the library did not.** The first attempt hung: a 30B model,
a schema with a union in it, and no `max_output_tokens`, so the server generated until the probe
was killed. `vllm:num_requests_running` showed one request open for minutes, which is how it was
diagnosed. Bounding the node fixed it.

**Gemini, `gemini-3.1-flash-lite`, a fan-out over four product descriptions.** Twelve live calls
in total across both probes.

| | in order | overlapping |
|---|---|---|
| Four documents read | 2.31s | 0.65s |

**What the fake client could not establish, and this did.** The run was recorded at
`concurrent_items=4`, then replayed twice from that cassette, once one call at a time and once at
width 4:

```
seeds    268866370, 1672364289, 1758364165, 2042367969   identical across all three
answers  32, 34, 30, 36                                  identical across all three
```

That is Decision 5 measured rather than argued: a fan-out is seeded by item index, so the request
a run sends for an item does not depend on when the item ran, and the cassette answers each item
with its own entry at any width. A cassette recorded at `concurrency=1` therefore replays against
the same pipeline at `concurrency=8`.

### 3.9 The audit: what else touches this, asked properly

The scenario matrix and the live probes establish that the three units work. They establish
nothing about the state those units share, because a lost update does not change an answer, it
changes a number in the manifest. So every piece of mutable state a concurrent call reaches was
enumerated and checked, and the check was run with `sys.setswitchinterval(1e-6)`, which preempts
threads constantly.

| Shared state | Before | Now |
|---|---|---|
| `TrajectoryWriter` | unguarded | locked, and the record is numbered inside that lock |
| `Cassette` | locked already | unchanged |
| `RunContext` counters and spend | unguarded | locked |
| **`Manifest` counters and totals** | **unguarded** | **locked** |
| `MemoryStore.write` | one scratch path per key | one per writer |
| `PacedClient` | locked already | unchanged |
| Tool spend | computed from the records at close | nothing to race |
| `httpx.Client` in the adapters | thread-safe by contract | unchanged |

**Two defects, and neither would have been found by the tests that existed.**

**The manifest lost counts.** `count_record`, `observe_model`, `observe_tokens`,
`count_cassette` and `observe_held_back` all read a number and write it back. At the default
switch interval a run of 200 overlapping calls lost nothing, so the first check said it was fine.
Forced to preempt, eight threads lost **13% of the record counts and 32% of the token totals**.
The token total feeds cost, so the failure mode is a run reporting less than it spent with nothing
raised. This was live before concurrency existed too, reachable through `EvalSuite.run`'s
rollouts, which have shared a manifest-free envelope per rollout and so never hit it.

**The trajectory could be written out of `sequence` order.** The number was taken when a record
was constructed and the write happened after, so two threads could take 5 and 6 and land 6 first.
`docs/trajectory-format.md` promises "a trajectory read line by line is already in order", which
would have quietly stopped being true. The number is now taken inside the writer's lock, so the
order in the file is the order of the numbers by construction.

**Two attempts at a regression test were thrown away for being worthless**, and this is the part
worth keeping. The first asserted the manifest totals after a 60-call concurrent run: it passed
with the locks removed, because 60 calls do not contend. The second asserted file order after a
200-call run: it caught the old numbering **one time in three**, and a flaky regression test
passes in CI while the bug is there. What replaced them: the manifest counters hammered directly
by eight threads, which fails without the lock every time; and an atomicity test that holds one
writer inside its call while another tries to write, which fails without the fix every time. Both
were checked by removing the fix and watching them fail.

**The soak.** Sixty rounds of a pipeline using all three units at once, at width 12 under a
ceiling of 16, under the same forced preemption, asserting ten invariants each round: the output,
the call and tool-call counts, the manifest agreeing with the trajectory, every call resolving to
a node, every parent written after its children, and `sequence` unique and monotonic in file
order. Sixty rounds, no failures.

### 3.10 A third defect, from asking what else reads the graph

The audit at §3.9 covered state shared between threads. It did not cover code that *rebuilds* a
pipeline, and `ablate` does: `_same_but` reconstructs an arm from the baseline's constructor
arguments, with a docstring saying "every constructor argument travels". `concurrent_nodes` did
not travel.

The arm that removes a node **outside** a group keeps both of the group's nodes and loses the
group, so it runs sequentially what the baseline overlapped. Nothing raises. A variant comparison
exists to hold one difference between two arms, and this put a second one in silently, in the
direction that makes the ablated arm look slower.

Groups now travel, narrowed to the nodes the arm still has, and a group left with fewer than two
members is dropped rather than refused, which is what lets a grouped pipeline be ablated at all.
`compare_variants` gained `run_concurrency` for the same reason.

**The rule:** a new constructor argument has to be checked against everything that rebuilds the
object, not only against everything that runs it. The docstring claiming completeness is where to
look, and it was wrong the moment the argument was added.

### 3.11 A fourth and fifth, from finishing the enumeration

The audit at §3.9 listed what a *call* touches. Asked again, wider, two more turned up in things
a call reaches through a tool.

**`VectorScan` filed vectors under the wrong documents.** Identifiers and vectors are one table
kept in two lists, extended in two statements. Two writers interleaving between them mispair the
table: measured at **843 of 2,400 vectors filed under another document's identifier**. Nothing
raises, and the scores stay right, so retrieval returns the correct passages attributed to the
wrong sources, which is an agent citing a document it never retrieved. The store's own refusal
message already names this failure ("a mismatch would file a vector under another document's
identifier") and guarded the argument case while the concurrent one was open. Both `add` and
`search` now hold the table.

**Two nodes embedding for the first time each loaded the model.** `SentenceTransformerEmbeddings`
and `LocalCrossEncoder` build their encoder lazily with no guard, so two nodes reaching them at
once build two, and two copies of one model on one device is how a load that fits runs out of
memory. Serialised.

**What was checked and left alone**, so the next reader does not re-check it: the context
builders hold no per-call state and are frozen; `ToolRegistry` is written at construction;
`Redaction`'s lazy caches are idempotent, so a race costs duplicate work and yields the same
answer; tool spend is computed from the records at close; the adapters hold configuration, a
thread-safe `httpx.Client`, and per-call locals, with the stream assembler built inside each call;
and `PacedClient` and `Cassette` were already locked.

### 3.11.1 Finishing it with the compiler rather than with a list

The two above came from asking a wider question, which is still a list I happened to think of.
So the enumeration was redone mechanically: an AST walk over `src/` for every instance-attribute
mutation, which found **283 sites across 33 modules**. Triaging those to what is written *during*
a run on an object more than one thread holds is a short list, and it is the list rather than my
recollection.

**One more fix came out of it.** `UrlCache.put` stages into `path.with_suffix(".writing")`,
derived from the key alone, so two fetches of one URL share a scratch file and one can rename a
half-written copy of the other. The same defect as `MemoryStore.write`, in the module next to it,
and the mechanical sweep is what put them side by side. Fixed the same way.

**What the sweep cleared, with the reason, so it is not re-checked.** `DocumentIndex` builds
`_postings`, `_lengths` and its vectors in `__post_init__` and `_build_vectors` is reached from
nowhere else, so the index is immutable while a run reads it. `htmlreduce`'s `_Reader` is
constructed inside the call that uses it. `PacedClient` mutates only inside its lock, and
`expect_callers` runs before the run starts. The evaluation's `_Progress` holds its own lock.
Everything else is written at construction.

**Two of my own tests were wrong before the code was.** One asserted the store stayed paired but
would have run for minutes, because an unbounded writer against an O(n) search is quadratic;
both sides are bounded now. The pattern across §3.9 and here is that a test written to confirm a
fix needs checking as hard as the fix does.

### 3.12 The Gemini soak, and what it failed to find

Run to exercise the one path nothing had touched: Gemini publishes no rate-limit allowance, so
`PacedClient` is a passthrough, `concurrency` is the only bound, and the retry-and-backoff code is
what stands between a wide fan-out and a failed run. 480 live calls over five widths.

| Items | Width | Elapsed | Correct | Held back |
|---|---|---|---|---|
| 40 | 1 | 21.10s | 40/40 | 0ms |
| 40 | 8 | 2.88s | 40/40 | 0ms |
| 40 | 20 | 6.55s | 40/40 | 0ms |
| 120 | 8 | 7.04s | 120/120 | 0ms |
| 120 | 30 | 2.17s | 120/120 | 0ms |
| 120 | 60 | **1.57s** | 120/120 | 0ms |

**It did not find what it was for.** Not one call was rate limited at any width, so the retry path
is still unexercised against a live backend. That is a fact about this account's tier rather than
about the library, and the honest statement is that the path is covered by unit tests and by
nothing live. What would exercise it is a free-tier key, where Mistral's published 50 requests a
minute made this trivial before the credits ran out.

**What it did establish.** Correctness holds at every width: 480 of 480 answers right, with the
item's own index coming back against the item, so nothing was mispaired at 60 in flight. And
**7.5x at width 60 over 120 items**, on a hosted backend, which is the figure a builder would
actually see.

**One reading not to take from the 40-item rows.** Width 20 came back slower than width 8, which
looks like the pool degrading and is not: the 120-item rows go the other way, 30 and 60 both
faster than 8. Forty items is too few to separate the backend's variance from anything, and the
first table is kept only so the comparison is not read as a trend.

### 3.12.1 The free tier, which found what the paid one could not

Thilina added a free-tier key on 2026-08-13 for exactly the gap §3.12 could not close. Sixty
items at width 30, twice.

| | Elapsed | Answered | Failed | Calls that waited | Recorded backoff |
|---|---|---|---|---|---|
| Unpaced | 64.71s | 30/60 | 30 | 13 | 403s |
| Through a `PacedClient` | 63.53s | 19/60 | 41 | 15 | 465s |

**The retry path works and is now exercised live.** Thirteen calls were refused, backed off, and
came back with the right answer; the ones that never cleared it failed with a message naming the
status, the attempts and the provider's own rate-limit page. **A fan-out kept the run alive**:
thirty items failed and the other thirty came back correct, each against its own index, which is
`max_failures=None` collecting under real pressure rather than under a fake.

**The finding is what the warning told the builder to do.** `warn_unpaced_wait` fired, correctly,
and said to wrap the adapter in a `PacedClient`. The second arm did that, and did **worse**:
`waits=0`, because Gemini publishes no allowance on any response, so the wrapper had nothing to
pace against and left every call exactly as it found it. The advice was not merely useless here,
it was the wrong instruction at the moment a builder acts on it: what bounds the rate against
this backend is how much the run sends at once.

`docs/model-clients/gemini.md` already says this. The warning did not, and **the warning is what
a builder sees**. This is the same shape as the sentence that put this whole item on the
schedule: right in a document, wrong where the decision is made. The warning now reads the
response, and where the backend published no allowance it names `concurrency=` and
`concurrent_items=` instead of a wrapper that would do nothing.

**And the run falsified a sentence this item had itself written.** The warning ended "No budget
axis is charged for it, so the run reads as slow rather than throttled", which was true until
Decision 4 made the wall clock elapsed. It is charged now, and a run held behind a quota can stop
on that axis having done almost no work. Corrected in the warning, in `docs/model-clients.md` §4
and in `docs/run-envelope.md` §2.1. **The rule:** changing what an axis measures means re-reading
every sentence that mentions the axis, including the ones in error messages, and the search that
finds them is for the claim rather than for the field.

### 3.12.2 Applying the rule, rather than stating it

§3.12.1 ends with a rule about re-reading every sentence that mentions an axis whose meaning
changed. It was stated and not applied: three places were corrected because a live run walked
into them, which is the opposite of a search. Applied properly, by grepping for the **claim**
rather than for the field name, four more sentences were still asserting the old semantics:

| Where | What it said |
|---|---|
| `docs/model-clients.md` §4 | A `PacedClient` wait "is not charged to the run's budget, because `max_wall_clock_ms` bounds what the agent does rather than how busy the backend was" |
| `models.py`, `ModelResponse` | "``max_wall_clock`` is charged the call without it" |
| `pacing.py`, `_held_back` | "A run's ``max_wall_clock`` budget is charged the call without it, so an evaluation behind a per-minute quota is bounded by the work it does" |
| `budget.py`, `Budget` | The three soft axes described without the step reservation, and the wall clock without saying it is elapsed |

The first carried the **rationale** for the old design as well as the claim, which is the part a
grep for `held_back_ms` would never have reached: it named neither the field nor the axis in the
clause that had gone false. Searching for "charged", "not charged" and "bounds what the agent
does" is what found it.

**What the sweep confirmed as still true**, so it is not revisited: everything about time spent
suspended being charged to nothing, in `pipeline.md` §5, `context.py` and two comments in
`nodes.py`; and everything about no axis bounding a cycle, which is a different fact about
`max_steps`.

### 3.13 What a fake client cannot show, again

Two arms both consulting, run concurrently, came back with their questions swapped: the arm asking
about fit received the answer to the size question. That is `FakeModelClient` returning a scripted
list in call order without reading the request, which is `CLAUDE.md`'s standing lesson arriving in
a new place. **A cassette does not have this property**, because an entry is found by hashing the
request, so each node's call finds its own entry whatever order the calls were made in. The
scripted fake is order-dependent exactly where the recorded one is not, which is worth knowing
before reading any concurrency measurement taken against a fake.
