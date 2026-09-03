# Build log — the end user an evaluation answers with

`plan.md` §1 P3-9. Designed and built 2026-08-17, one sitting. Written while building.

## 1. Before any design

The item's record carried six measured assumptions. Three were checked against the machine
before anything was decided, and **two of the three did not survive**.

**Assumption 1's measurement was right and its inference was wrong.** The record says the
stand-in "cannot supply a fact", on five deflections out of five when asked for a cost centre.
Reproduced exactly, then the other arm was run: the same persona with the cost centre written
into the same prose description, `gemini-3.1-flash-lite`, five seeds.

```
-- no fact in the description                    -- fact in the description
"If you don't know which account that goes      'It is CC-4471, the same as every other
 to by now, you haven't been paying               invoice you process; try to keep up.'
 attention; figure it out."                     "It is CC-4471, and I shouldn't have to
"Check the ledger, it's clearly defined in        tell you that twice."
 the operating manual."                         "It's CC-4471, same as always."
==> supplied it in 0 of 5                       ==> supplied it in 5 of 5
```

[`DEFAULT_INSTRUCTIONS`](../../src/simple_agents/evaluation/stand_in.py#L61) says "Invent no
facts about them that **the description does not support**", and a fact in the description is
supported. So the mechanism was never broken, and what was missing is narrower and different:
nothing told a builder the description is also the knowledge base, no scoring rule could read a
fact out of prose, and nothing controlled when a fact is disclosed.

**Decision 5's design constraint was false.** The record says `consult` is `READ_ONLY` and
`concurrent_tools` refuses only `WRITES`, so two consultations in one turn can overlap.
[`_may_suspend`](../../src/simple_agents/nodes/agent.py#L911) already refuses any `ConsultTool`, verified:

```
REFUSED: AgentNode 'n' lists 'consult' in concurrent_tools, and 'consult' can stop the run to
ask someone. A run stops on a turn boundary...
```

Two consultations in one turn of one node could not overlap. Where they could is across
`concurrent_nodes` or a fan-out's `concurrent_items`, since one stand-in is bound per rollout
and shared by every node in it. Much narrower than the record assumed.

**A defect found while checking, and owned by nothing this item decided.**
[`playing`](../../src/simple_agents/evaluation/stand_in.py#L185)'s `answered` counter was
`nonlocal answered; answered += 1` with no lock, and the executor is a `ThreadPoolExecutor`
([concurrency.py](../../src/simple_agents/concurrency.py#L18)). Two nodes consulting
concurrently in one rollout could read the same value and derive the same seed for two
different questions.

**Two more measurements taken before deciding.** The ratification defect, three arms of three
seeds; and the 24-cell matcher measurement re-run with a fourth column. Both are in §2.

## 2. Design

Eight decisions. What follows is what was ruled, not the survey of options.

### 2.1 What an example carries, and whether the other end is a person (decisions 1, 2, 4)

**Ruled: a typed `EndUser` in the same field, with facts carrying a disclosure.** Decisions 1,
2 and 4 collapse into one, and [`answer-shapes.md` S4.1](../design/answer-shapes.md#L434) had
already settled that what the end user knows is a third thing rather than part of `expected`.

```python
Example(id="inv-12", inputs={...}, expected="CC-4471", split="held_out",
        end_user=EndUser(
            "An operations manager. Brusque, and short of time.",
            knows={
                "deadline": Fact("this has to be filed today", disclose="volunteer"),
                "cost_centre": Fact("the cost centre is CC-4471", value="CC-4471",
                                    disclose="on_ask"),
                "cap": Fact("anything over 5,000 needs her director", value=5000,
                            disclose="hidden"),
            },
        ))
```

`text` is what the model is told and `value` is what a scoring rule compares against, in one
place, because a value written into the description and repeated in `metadata` is two values
nothing compares.

**Where this departs from τ-Rec, and it is the part worth recording.** The three tags are that
paper's, and [S4.2](../design/answer-shapes.md#L449) records that its own barrier is advisory:
hidden constraints sit in the simulator's prompt with an instruction never to state them, and
nothing measures the leak. Here the split falls out cleanly instead. `volunteer` and `on_ask`
are stand-in prompt behaviour, still advisory and documented as such. **`hidden` is never given
to the model at all** and reaches a run only through the answer key, which P3-10 made possible
by putting `example` on every `Scoring`. The model that would leak it never sees it.

**Decision 4 falls out.** An approver applying a policy, an operator with a runbook and an
upstream system are all `EndUser` with a different description and different facts; the voice is
what decision 8's prompt seam replaces. One default and a seam, not four presets.

**Rejected: a function per example**, `end_user=lambda question, options: ...`. A closure is not
in `content_hash`, which is the argument `WithinTolerance` already makes about a tolerance
written into `matches`.

**Naming.** `description`, positional, put to Thilina against `persona` and `who`. Positional
matches the four answer keys P3-10 shipped, which is the closest family this type has, and
`description` does not claim the other end is a person.

### 2.2 History, and confirming what was never said (decisions 5, 6)

**Ruled: thread the history, append the rule, take the raciness, lock the list.** One decision,
and it is measured. The agent claims a choice the person never made, three seeds each:

```
picked : "None of those look like they're worth the price..."
claim  : 'You chose Crossroads of Ravens. Shall I order it?'

no history      : "It's cheap enough and short, so just get it."          3 of 3 ratified
history alone   : "Just buy it, provided it stays under that page limit"  3 of 3 ratified
history + rule  : "I never chose anything, so stop making things up"      3 of 3 refused
```

**History alone fixes nothing and the rule alone has nothing to check against.** The rule is
appended by the library rather than living in the replaceable prompt, so a project that
replaces the prompt keeps it.

**The ordering problem, with §1's correction applied.** Three ways were weighed: serialise
behind a lock, refuse `end_user=` on a pipeline whose consulting nodes can overlap, or take the
raciness and record nothing extra. **Taken: the third.** Refusing the shape costs a real
capability for a divergence a project can already see in its own trajectory, where consultations
are ordered by `sequence`. Replay is unaffected in every case, since a consultation is served
from the cassette by node, tool, arguments and occurrence, so the stand-in is never called
again. No trajectory field was needed for it.

**The seed stopped coming from a counter.** It derives from the question and options, so two
live runs at one seed answer the same question the same way whatever order the questions
arrived in. That removes §1's race rather than locking it.

### 2.3 The matcher, and what the stand-in declares (decision 7)

The 24-cell measurement re-run, two personas by three option shapes by four seeds:

| | read an option in |
|---|---|
| the library default, whole-answer equality | **0 of 24**, reproducing the record |
| unique containment | 7 of 24 |
| the stand-in asked to declare which option it chose | 7 of 24 |
| containment against the declaration | agreed 24 of 24 |
| the default against the declaration | **disagreed 7 of 24** |

**Ruled: ship no matcher, and ship the number instead.** The first proposal was a named opt-in,
`names_one_option`. Thilina: *"Substring matching seems way too delicate and error-prone to me.
Can we make it so that the builder has the option to implement it themselves if they want to,
but we don't ship it by default?"* The seam already existed, so that option was already true and
what the proposal added was a shipped value nobody asked for. **What ships is the documentation
instead**, including the three classes no rule over the text alone reads, measured:

| The answer | Reading its words | What it means |
|---|---|---|
| `"Anything but The Witch of Whispervale."` | that title | the opposite |
| `"I have no strong feeling either way, go ahead."` | `no` | yes |
| `"Only if it is under 400 pages; otherwise, no."` | `no` | a condition, so `unmatched` |

Word boundaries stop `"I don't know"` and `"Not now"` reading as `no`; those three survive it.

**`declared_choice` ships and never routes the run.** Routing stays on the project's own rule,
because that is the path that ships. What the declaration buys is
`per_node.consultation_misreadings`: dogfood #4's 0 of 24 would have been a line in a results
file rather than a finding that needed a dedicated probe twice.

**A judge is the right reader for the residual three and could not be built here.**
[`ConsultTool.read_answer`](../../src/simple_agents/tools.py#L1304) carries a documented
invariant, that it runs again on replay and on resume and must not do work beyond matching, so a
model-backed `match=` would make a live, unrecorded, non-deterministic call on every replay.
That is a blocker rather than a cost. It goes to [`plan.md` §2.1](../plan.md#L59) with the same
recording-and-pricing question [`answer-shapes.md` S2.2 seam 7](../design/answer-shapes.md#L279)
names for a scoring judge, because one design settles both.

### 2.4 The prompt seam (decision 8)

**Ruled: `instructions: str = DEFAULT_INSTRUCTIONS`**, following `extract_to_schema`, hashed
into `identity()` so two evaluations differing only in it resolve to different directories
rather than the second being refused after the first is paid for. One placeholder, `{end_user}`,
which the library fills with the description and whichever facts that person would state, so a
replaced prompt still gets the facts.

### 2.5 More than one answerer (decision 3)

**Ruled: key on the answerer, not on the tool.** The record proposed a refusal as the cheap
early take, and the sitting weighed tool-name keying against it. Thilina: *"I don't care about
the number of lines or how big the build is. DO THINGS THE RIGHT WAY, NOT THE EASY WAY."*
Tool-name keying fails as soon as one person is reachable through two tools, because the example
then carries that person's description twice, which is the
[criteria-set duplication](../plan.md#L105) in a new place.

```python
registry.add(consult(ask_analyst, answered_by="end_user", reaches="requester",
                     name="ask_requester"))
registry.add(consult(ask_director, answered_by="end_user", reaches="approver",
                     name="ask_approver"))

Example(..., end_user={"requester": EndUser(...), "approver": EndUser(...)})
suite.run(..., end_user={"requester": SimulatedEndUser(model=cheap),
                         "approver": SimulatedEndUser(model=cheap)})
```

`answered_by` is what kind of answerer and `reaches` is which one.

### 2.6 What J3 gets, and what it does not (the rest of decision 2)

**Ruled: the count now, the outcome deferred, and the count is what makes the outcome
decidable.** Half of J3 was already reachable and the record predates it: P3-10 put `trajectory`
on every `Scoring`, so "did it ask before answering" is a criterion today. What was not
reachable is a rollout where the answerer refused and the answer was only obtainable by asking,
which lands in `missed` or `false_confidence` and reads as an agent failure when one of them is
the answerer's.

An eighth `Outcome` was weighed and not taken. Not on "no evidence yet" grounds: whether it sits
inside or outside the denominator is genuinely unsettled, and getting it wrong costs five rates.
`RolloutOutcome.unanswered_consultations` is the number that says whether the case occurs and
how often, which is what a decision about the outcome needs.

### 2.7 Consultations that overlap, added at the sitting

Not one of the eight. Raised by §1's correction: the construction-time refusal decides a
run-time fact, and the two halves were inconsistent for no design reason. Put to Thilina with
the honest note that the parallelism gain is only the within-one-turn case, since across-node
consultation already overlapped. **Ruled: take it.** The channel declares `may_suspend`, an
undeclared channel is treated as one that can suspend, and the node refuses at construction only
what it can see. `SimulatedEndUser` and `unattended()` declare their own.

## 3. Build

**What shipped.**

| | |
|---|---|
| `EndUser`, `Fact`, `DISCLOSURE` | [`end_user.py`](../../src/simple_agents/evaluation/end_user.py#L22), exported from `simple_agents.evaluation` |
| `Example.end_user` takes all three forms | Normalised to an `EndUser` at construction; a prose-only one still **stores as a plain string** |
| Facts by disclosure | [`_describing`](../../src/simple_agents/evaluation/stand_in.py#L302); `hidden` reaches the prompt nowhere |
| History, and the rule | [`RECORD_RULE`](../../src/simple_agents/evaluation/stand_in.py#L80), appended by the library outside `instructions` |
| The seed off the question | [`_asked_about`](../../src/simple_agents/evaluation/stand_in.py#L317) |
| `instructions=` | Hashed into [`identity`](../../src/simple_agents/evaluation/stand_in.py#L170) |
| `consult(reaches=)` | On `ConsultTool`, in the manifest tool entry, on every consultation record |
| Answerers by name | [`_channel_in`](../../src/simple_agents/tools.py#L1373), `_playing`, `RunEnvelope(end_user={...})` |
| `declared_choice` | On `ModelAnswer`, on `Reply`, on the record; `per_node.consultation_misreadings` |
| `unanswered_consultations` | Per rollout, off the trajectory in the pass that already reads it |
| `may_suspend` | On the channel; `concurrent_tools` accepts a consult tool that declares it |

**Formats.** Trajectory `0.22` to `0.23`, manifest `0.25` to `0.26`, results file `0.14` to
`0.15`. [`design/trajectory-format-changelog.md` 0.23](../design/trajectory-format-changelog.md#L18).

**2403 tests**, from 2361.

**One break for every project on disk**: `example.end_user` is an `EndUser` after construction
whichever form it was given, so code comparing that field to a string stops working. The
alternative was three types in one field and a coercion at every reader. No example set's
`content_hash` moves, because a description with no facts still encodes as a bare string.

**What the build changed about the design.** `knows={"cc": "some text"}` is accepted as
`Fact("some text")`. Pydantic validated the dict before the hand-written refusal could run, so a
builder passing a string got a pydantic traceback rather than the library's message; coercing
was the better fix than a louder error.

## 4. Verification

**Two backends, both live.** `gemini-3.1-flash-lite` hosted, `Qwen/Qwen3-1.7B` through vLLM on
port 8001. Mistral is out of credits.

**The thing this item exists to fix, fixed.** An agent that had to obtain a cost centre, three
rollouts on each backend: asked, was told `CC-4471`, answered correctly **3 of 3 on both**.
§1's measurement of the same shape was 0 of 5. The `hidden` fact appeared in **0 of 6**
consultation records across the two runs.

**`consultation_misreadings` fired on its first real run**, and again on the second backend:

```
consultations=6  resolutions={'unmatched': 3, 'answered': 3}  consultation_misreadings=1

  A: I have already read Crossroads of Ravens, so pick The Will of the Many.
     options=True  chose=None  declared='The Will of the Many'
```

The default matcher read no option out of any prose answer, on either backend. **It is a floor
rather than a count of every misreading**: on a composite reply the stand-in declines to name
one option, and its disagreement with a rule that also read none is not counted. Documented as
a floor.

### 4.1 What the verification pass found after the build was green

Six defects, found by re-reading the diffs and running paths the suite did not.

**One description silently played two people.** The permissive fallback in `described()` treated
a single prose description as covering every named answerer, so a run asking a requester and an
approver with a one-person example played both from that description and recorded `simulated`
for both. **This is assumption 2's defect, re-created by the fix for it.** Reproduced, removed,
and refused in both directions.

**`declared_choice` was lost on replay.** The same run reported `consultation_misreadings` of 1
live and 0 replayed, because it was held on the call's provenance and a cassette hit never
populates one. Moved onto the answer and stored the way `Unavailable` already is, which is the
pattern `read_answer`'s own docstring describes for `chose`. Live and replay now agree.

**Fixing that swapped two variables**, so the resumed-consultation record read `result` where
only `answer` is in scope: a `NameError` on every resumed consultation. Caught by reading the
diff, not by the suite.

**A `docs/` example that parses, resolves and is refused at runtime.** The §5.4 `criteria=`
example registered a check against an example whose `expected` was a plain string.
`scripts/prose_check.py` cannot see that, which is the failure `CLAUDE.md` records for
`docs/pipeline.md` §1.4's accumulator. A script that **executes** every example this sitting
added now exists in the session scratchpad; all five run.

**`docs/evaluation.md` §1.3 never documented `end_user` in the example file**, nor
`expected_by_node`. Both added, with all three encoded forms, verified to parse and round-trip
byte-identically.

**The truncation refusal gave the wrong instruction, found on vLLM.** Qwen3-1.7B returned an
empty reply and the error told the builder to pass a model that honours `output_schema` — when
the model honoured it and had spent the 300-token ceiling on its chain of thought. The refusal
now names truncation and says `max_output_tokens=`. **This got worse with what this item built**:
history makes the prompt grow through a rollout, so a run can answer question 1 and fail on
question 3. Confirmed fixed against the live backend.

**Also verified sound**: a `Deterministic` node calling `consult` still receives a `Reply` rather
than the stored form; `compare_variants` sweeps with a mapping of answerers; `rescore`
reproduces `unanswered_consultations` off disk; nothing outside `runner.py` and the new module
reads `example.end_user`; no new line exceeds the 100-character limit.

**The conformance fixtures were stale, and the inbox had mis-sized why.** That entry said
regenerating them "touches all 14 projects and their expected outcomes, so it is its own change
rather than the tail of another". Measured instead of assumed:
`scripts/build_conformance_fixtures.py` replays a **committed** cassette, needs no backend and
no credits, and took seconds; all 132 manifests and 14 results files came current and the suite
stayed green with no expected outcome touched. **Nothing was stopping it and nothing was
noticing it**: `run_checks` parses these files itself while `EvalResults.read` refuses a
superseded version, so one reader refuses a stale file and the other accepts it silently, and
`tests/test_conformance.py` skipped a missing fixture rather than failing. Three tests now read
every version claim in the fixtures against what the writer writes, and they were run against
the pre-regeneration tree to confirm they fire. The inbox entry is retired. **Regenerating
always produces a large diff**: two consecutive runs agree on every value except record ids and
timestamps, which are minted fresh, so 260 files change and 114 differ past the timestamps.

**The fixture suite for `check_docs.py` had rotted, and could.** Retiring P3-9's queue row broke
a `SELF_TESTS` fixture that quoted `| P3-9 |`, and nothing noticed: the suite ran only under
`--self-test`, which is not in `pytest`, so a dead fixture survived a green 2403-test suite.
Two fixes: **the fixtures run on every `check_docs.py` invocation** at 1.7s against 0.1s, with a
stale anchor reported rather than crashing; and **seven fixtures now resolve their anchor out of
the tree** rather than quoting a `P3-n` id or an `items/` filename that every shipped item
retires. Both were proved by breaking them on purpose in a throwaway worktree: retiring an item
leaves 29/29 firing, and a deliberately stale anchor reports and exits 1. `CLAUDE.md` carries
the rule.

**148 citation drifts** from moved code, against a baseline measured clean at `HEAD` in a
throwaway worktree. Re-anchored with `check_citations.py --fix`, verified that every changed
line carries only an `#L` anchor and that `check_docs.py --since` reports no record shrank, plus
five placed by hand.

## 5. Doc consequences

**`docs/evaluation.md` §5.4 is rewritten** and is the schema of record for the encoded form: the
three disclosures and what each does to a run, the measurements behind them, the prompt seam,
answerers by name, and the two figures. **§1.3 gains the example-file fields** it never listed.

**`docs/tools.md`** gains `reaches` in §4.6.2, `may_suspend` in §4.6.3, and in §4.6.1 what a
project's own `match=` has to handle, with the three classes measured.

**`docs/trajectory-format.md` §4.3** gains `declared_choice` and `reaches`, and says which of
`chose` and `declared_choice` routed the run. **`docs/run-envelope.md`** carries `reaches` on the
tool entry and the per-answerer shape of the manifest's `end_user`.

**What stopped being true.** `Example.end_user` was documented as the person's description and
is now what they know as well. The three version statements moved with the formats.

## 6. Left open

- **A judge that reads a consultation answer**, blocked on the recording-and-pricing question a
  scoring judge shares. [`plan.md` §2.1](../plan.md#L59).
- **An eighth `Outcome` for a rollout with no answer to score yet.**
  [`plan.md` §2.1](../plan.md#L59), with `unanswered_consultations` named as what decides it.
- **No consultation in any run has been answered by a person.** Unchanged by this item and not
  its subject; [`runs/dogfood-4/inventory.md` DF4-Q1](../runs/dogfood-4/inventory.md#L433).
