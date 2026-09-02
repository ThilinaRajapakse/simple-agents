# Build log — what a run spent and produced nothing with

`P3-22`'s log, one section per stage as each shipped. **A stage that ships takes its own id**,
which `plan.md` §1's header requires, so the four are in §4 and `P3-22` itself never was.
**Every stage is built; the item's design record is
[`design/spend-that-produced-nothing.md`](../design/spend-that-produced-nothing.md#L1).**

| Stage | What | Id | Built |
|---|---|---|---|
| 1 | The figures, `node_metrics()`, the manifest counts | `P3-23` | 2026-08-19 |
| 2 | The denominator settlement | `P3-24` | 2026-08-19 |
| 3 | `simple-agents report`, the check note, the procedure line | `P3-25` | 2026-08-19 |
| 4 | FT-35 and `allow_unfinished=` | `P3-26` | 2026-08-19 |

## 1. Before any design

Everything in [`design/spend-that-produced-nothing.md`](../design/spend-that-produced-nothing.md#L34)
§2 was measured against `be78524` before anything was decided, on the library and on all 3,293
run directories of `/home/thilina/Projects/dogfood-4`. The four that decided the design:

- **An execution that ends on a budget axis produces nothing.**
  [`nodes.py`](../../src/simple_agents/nodes/agent.py#L139), `AgentNode._one`, initialises
  `outputs = None` and sets it only from a `finish` call. Probed live: the node records
  `outputs: null` and `error: null`, the successor is handed `None`, and the run completes. On
  the dogfood's data **all 289 such executions recorded `outputs: null`**.
- **289 executions ended that way and spent 5,487 model calls, 24.4% of the project's 22,475.**
  189 of them made no tool call, consultation or delegation, spending 3,407, which is
  `DF4-D5`'s 15% and reproduces its 188 / 3,384 exactly as the `max_steps`-only slice.
- **The aggregate existed and was unreachable.**
  [`per_node.py`](../../src/simple_agents/evaluation/per_node.py#L366), `per_node`, computed
  everything but the join, and `evaluation/__init__.py` exported `NodeMetrics` and not it.
- **A fan-out was blind.** Probed: an `AgentNode` with `over=` whose every item spun records
  `termination: null`, `FanOutResult.ok` is `True`, `failures` is empty and `terminations` is
  `{}`.

## 2. Design

The sitting is `runs/dogfood-4/inventory.md` §3, sitting 4, 2026-08-19, and
[`design/spend-that-produced-nothing.md`](../design/spend-that-produced-nothing.md#L1) is the
record until this item is built.

**The class is derived from contracts rather than from instances**, after Thilina's correction
that a dogfood is a toy project and cannot be used to assert a negative. What the library knows
is when a unit of spend produced nothing, because its own contracts define what producing
something is.

**One member gates and the rest report.** A cap that binds after real work is the cap doing its
job; a loop that spent its whole allowance without once acting has no such reading.

## 3. Build

**Stage 1, 2026-08-19. 2713 tests to 2741.** Trajectory `0.25` to `0.26`, manifest `0.29` to
`0.30`, results file `0.18` to `0.19`. Every conformance fixture regenerated; no cassette
invalidated, because a cassette is keyed on the request rather than on the record.

- **`item_index` on `tool_call`, `consultation` and `delegation`.** The design assumed the
  attribution existed. It did not: `model_call` carried `item_index` and the other three did
  not, so a fan-out's items could not be told apart for anything but model calls. Threaded from
  the loop that knows it, and from `NodeContext.item_index` for a `Deterministic` or `LLMNode`
  node's own calls.
- **Four figures on `NodeMetrics`**: `unfinished_executions`, `unfinished_items`,
  `unfinished_without_tool_calls`, `unfinished_model_calls`, each documented on the field the
  way [`metrics.py`](../../src/simple_agents/evaluation/metrics.py#L215), `Metric.left_out`,
  documents its own. The class docstring was at its 20-line prose ceiling exactly.
- **`unfinished_work(records)`** is the one implementation, in
  [`per_node.py`](../../src/simple_agents/evaluation/per_node.py#L366). `per_node` adds it onto
  `NodeMetrics` and `_close_manifest` writes it into the manifest, so the two cannot drift.
- **`node_metrics(run_dir)`** publishes `per_node` over a directory rather than adding a
  reader, with `role`, `live`, `since` and `last`.
- **The manifest carries `unfinished`**, read off the trajectory
  [`recording.py` `_close_manifest`](../../src/simple_agents/pipeline/recording.py#L653) already reads back at the end of
  every run for cost, so it costs no extra I/O and agrees with the file by construction:
  payload sampling has already run by then, so the manifest says what a reader of that
  trajectory can see and no more.

**Four things the build found that the design did not know.**

**A pre-`0.26` record cannot say which item called a tool**, so reading its items would report a
project that acted as one that did not. `_at_least(record["format_version"], (0, 26))` leaves
those items out of `unfinished_without_tool_calls` rather than guessing, and the count of items
is unaffected.

**A model call a tool makes inside a fan-out belonged to no item, and its seed depended on
which item got there first.** Found at the verification pass, by reading the new figure back:
`unfinished_model_calls` reported 4 where 6 calls had been made.
[`nodes.py`](../../src/simple_agents/nodes/agent.py#L1151), `_nested_call`, passed the `AgentContext`
to `_call_model` and not its `item_index`, so two items' nested calls shared one counter.
Measured with two items at `concurrency=2`, holding one item back with a sleep: holding Ubik
back gave Solaris seed 416170705, and holding Solaris back gave it to Ubik.
`docs/trajectory-format.md` §4.1 states that an item is sent the same seed whatever order the
items ran in, so that sentence was false for a call made inside a tool and is true now.
**A cassette entry is keyed on the request and the seed is in it, so a recording of a fan-out
whose tool makes model calls has to be re-recorded.** Two tests cover it, and both fail with
the one-line fix removed.

**`prose_check.py` reported a number it was not checking.** Its `long_docstring` message named
the docstring's whole length against a limit on its prose, which sends a reader counting the
wrong lines. It reports the prose count now.

**A non-pydantic `output_schema` disables validation silently, and it is not this item's.**
Found live: `AgentNode(..., output_schema=<a plain dataclass>, allow_unknown=False)` constructs,
offers the model a `finish` whose parameters are `{"type": "object", "properties": {}}`, and
accepts whatever comes back. §6 carries it.

### 3.1 Stage 2: what a rate is over

**2741 tests to 2750. Results file `0.19` to `0.20`.**

**The rule was already in the library and the entry did not need the evidence it waited on.**
[`outcomes.py`](../../src/simple_agents/evaluation/outcomes.py#L94), `Outcome.NO_RESPONSE`, puts
a rollout outside every denominator because the backend never answered, so nothing the agent did
was measured. The principle under it is that a rollout is inside when what it returned is
attributable to the agent, and that decides the other two cases without a project to look at.

- **`RolloutOutcome.left_out`** names why a rollout is outside, and
  [`outcomes.py`](../../src/simple_agents/evaluation/outcomes.py#L151), `causes_of`, reads it
  beside the outcome's own `no_response`. **Derived rather than stored** for that one: an
  invariant that has held since the field existed must not depend on a caller filling something
  in, and a rollout built by hand or read from an older file would otherwise change denominator.
- **A question to a channel declaring `nobody` leaves the rollout inside.** `unattended()`
  declares it, and a project that ships unattended is measured on how the agent behaves with no
  one to ask.
- **`Metric.no_response` became `Metric.left_out`**, keyed by cause, and `Metric` gained
  `including_left_out`: the same figure with the left-out rollouts counted as they scored,
  `None` where nothing could be counted. Thilina asked for both numbers *"just to be safe"*, and
  the report prints the second under the first so the narrower cannot be quoted alone.
- **A `no_response` rollout is in neither figure.** There is no answer to count either way,
  which is what that outcome means, and extending the second column to it would have counted a
  backend failure as an agent failure.

### 3.2 What the sitting's two open questions settled, 2026-08-19

**2750 tests to 2761.** No format moved.

**A schema shown to a model must be one the model can be shown.** Option A of the sitting, on
Thilina's ruling that B is taken only if it *"genuinely offers something that would otherwise
handicap a builder"*. It does not: pydantic is already a hard dependency, so a `BaseModel`
costs one import and expresses everything a dataclass can.
[`schema.py`](../../src/simple_agents/schema.py#L333), `require_a_schema_a_model_can_fill`,
refuses at construction for `LLMNode`, `AgentNode` and `extract_to_schema`, which failed at run
time with a model-facing error instead. **`Deterministic` is untouched**: nothing there is shown
to a model, and [`nodes.py`](../../src/simple_agents/runtime/calls.py#L440), `_validated_output`,
already validated it with `TypeAdapter`.

**Both nested-call paths carry their item.** A consultation reader's model call had the defect
found in a tool's `ModelHandle`, in the same form: `run.next_model_call(node_id)` with no item,
so two items' readings shared one counter and the seed each was sent depended on which item
asked first, with that seed in the cassette key. A search's embedding and rerank calls had the
attribution half only, since their keys are content-based.

**Three things the verification pass found**, which is what it is for.

**The refusal instructed the builder to write invalid Python.** `class dict(BaseModel):` for
`output_schema=dict`, and `class a string(BaseModel):` for a value that is not a type at all.
The example names the schema only where it is a class outside `builtins`, and `Answer`
otherwise. A parametrised test asserts the printed line for three such schemas.

**The reading's seed moved and its record did not.** The first pass threaded `item_index` into
`next_model_call` and `seed_for` and left it off the `ModelCallRecord`, so the call was seeded
per item and still reported as belonging to none. The test written before the change is what
showed it, and its cassette entry needed the same.

**`prompt_differences` was checked and is unaffected.**
[`prompts_sent.py`](../../src/simple_agents/evaluation/prompts_sent.py#L144), `_prompts_under`, keeps only
model calls whose parent is a `node_execution`, so a reading, a search and a call inside a tool
are all skipped whatever item they now name.

### 3.3 A fan-out's identical tool calls, 2026-08-19

**2761 tests to 2764. No format moved and no cassette was re-recorded.**

The defect §6 carried, fixed on Thilina's call.
[`context.py`](../../src/simple_agents/context.py#L1227), `_note_tool_occurrence`, counts within
the item as well as the node, and
[`cassette.py`](../../src/simple_agents/records/cassette.py#L594), `tool_call_key`, takes the item, so
each item's calls are their own series rather than being numbered by whichever arrived first.

**The item is in the key only where there is one.** Outside a fan-out it is absent from the
hashed material, so every call recorded before this keeps the key it had. That is what decides
whether the Mistral arms survive, since they cannot be re-recorded.

**Nothing needed re-recording, and it was checked two ways rather than inferred from a green
suite.** All 23 tool calls in the twenty committed cassettes were rekeyed under the new function
and none moved; every one carries `item_index: null`, so no recording holds a fan-out's tool
calls. Then `tools-vllm` and `suspend-vllm` were re-recorded live and the files restored: the
`document_search` key, whose arguments repeated, was unchanged, and the `consult` key moved
because the model asked *"Which fit would you like?"* where it had asked *"Which fit do you
want?"*. Content, not keying.

### 3.4 The reverification pass, 2026-08-19

Run on Thilina's instruction, over everything above. **2764 tests to 2766.** Four things, and
the first is the one that matters.

**Four members of the decided class are not built.** §7's stage 1 is *"the figures at all four
levels"*, and what shipped covers the execution and item rows of §1's table. Missing: a model
call that returned no content and no tool call, a delegation that returned `budget`, a tool
whose every call errored, and retries whose attempts all failed. Each needs a name and a home
before it is built, and names are Thilina's to settle, so this is reported rather than fixed.

**A figure whose whole denominator was left out reported nothing at all.** `_metric` returned
before computing the wider figure, so an evaluation where every rollout was left out printed
eight `undefined` lines and no number, which is the case where the wider figure is the only
information there is. Stage 2 decided that both print. Fixed, with the report printing the
second line under an undefined first one, and a test over five populations.

**`docs/evaluation.md` §8 still described `metrics` as carrying `no_response`**, which stage 2
replaced, and its `rollouts` row did not name `left_out`. Both corrected.

**Four paths were checked and are sound.** A rescore carries the same causes as the live run and
its metrics agree. `compare()` across the change reports an honestly undecided metric rather than
failing. A spun node inside a delegated pipeline is counted under its own node id, and the
delegating node counts the delegation as having acted. The manifest agrees with the trajectory
for a fan-out as well as for a plain node.

### 3.5 The rest of the class, 2026-08-19

**2766 tests to 2776. Results file `0.20` to `0.21`.** The four members §3.4 found missing,
built on Thilina's approval of the names proposed with them.

- **`empty_responses`** counts model calls that came back with no content and no tool call. It
  is the failure the handoff records costing this project twelve minutes twice: a reasoning
  model whose whole output ceiling went on the chain of thought. Reasoning is not content, which
  is the point of the figure.
- **`delegations_out_of_budget`** counts the subtasks that ran the delegated pipeline out of its
  own budget, read beside `delegations`.
- **`tools_that_never_succeeded`** names the tools a node called where every call failed, with
  how many calls each took, keyed by tool name. **The two tool rows of §1's table are one
  figure**: a retry whose attempts all failed is already `errors`, and what the second row adds
  over the first is nothing a reader acts on differently.

**The manifest is unchanged.** Its `unfinished` block is what a gate reads over many runs
cheaply, and these three report rather than gate, so they come from the trajectory through
`node_metrics` and cost the manifest no format move.

**The verification pass found three defects, one in the new figures and two beside them.**

`returned_nothing` read an embedding or a rerank as an empty response: those record what came
back in their own shape, so neither has a `content` field to be missing, and every search a node
made was counted as a call that returned nothing. Measured against `FakeEmbeddingClient` and
again against `all-mpnet-base-v2`. A call with neither field is not a completion and is not one
of these.

**`delegations` counted a resumed subtask twice**, and **`executions` counted a resumed node
execution twice.** Both predate this item and both contradict a shipped sentence:
`docs/trajectory-format.md` §3 says of `resumed_from` that *"both records describe one logical
execution, so counting executions of a node means counting the ones where this is `null`"*, and
§4.4 says the same of a subtask. `_count` already followed that rule for consultations, with the
reason in a comment beside it, and neither of the other two did. Found by reading the delegation
branch while adding a figure to it. Measured end to end on a real suspend and resume: a node
that stopped and continued reported `executions=2` and now reports 1. `docs/evaluation.md` §5.1
says so now, where a builder reads it.

### 3.6 Stage 3: the surfaces a builder reads, 2026-08-19

**2777 tests to 2817. No format moved.** `P3-25`. (§3.5 recorded 2776; the suite at that
commit collects 2777, and this session's baseline was measured rather than carried over.)

- **`simple-agents report <path>`**, in [`reporting.py`](../../src/simple_agents/cli/reporting.py#L180) `_covered`,
  `report_over_runs`, reading a directory of runs, one run, an evaluation's rollouts, or a
  results file. Over dogfood #4's 3,293 runs it reproduces the item's own table in 6.3s:
  `look_closer` 257 of 3,063 executions producing nothing, 188 of them never acting, 4,626 and
  3,384 model calls. **Every role is read by default**, with the roles counted on their own
  line, because a report that hides runs is the silent cap the item warns about.
- **The first line names how many runs were read of how many are there**, and what narrowed it.
  `--role`, `--live`, `--since` and `--last` narrow it; `runs()` gained `since=` and `last=`,
  which `node_metrics` already had, and
  [`envelope.py`](../../src/simple_agents/envelope.py#L643), `narrowed`, is what both the report
  and the gate filter with after reading each manifest once.
- **`basis_from_manifest`** in [`cost.py`](../../src/simple_agents/cost.py#L366) rebuilds the
  basis a run recorded, which is what makes a cost per node possible over runs the reader did
  not make. Where the runs read declare different bases, each node's cost reports unknown and
  the report says why. **A rate that is absent prices nothing rather than pricing free**, which
  is the rule `_add_tokens` already followed for an unreported token count.
- **`unfinished_lines(node)`** in [`per_node.py`](../../src/simple_agents/evaluation/per_node.py#L949)
  is the one renderer of these figures, so `results.report()` and `simple-agents report` cannot
  drift. `results.report()`'s per-node table said `runs` in the header and printed `executions`;
  it says `execs`, which is what the design's own sample called it.
- **`simple-agents check` prints the wider figure as a note**, and stays quiet where FT-35 has
  already named the same units, so the two surfaces never say one thing twice.
- **`docs/procedure.md` stage 4 gained the line**, at a cost of 37 words against the skill's
  word budget, which moved 1775 to 1815.

### 3.7 Stage 4: the gate, 2026-08-19

**2817 tests to 2831. Manifest `0.30` to `0.31`, results file `0.21` to `0.22`.** `P3-26`.
Eighteen checks now, and thirty-five taxonomy entries.

- **FT-35**, in [`checks.py`](../../src/simple_agents/conformance/checks.py#L1148), `ft_35`,
  over the counts [`spend.py` `unfinished_across`](../../src/simple_agents/conformance/spend.py#L186)
  reads out of each run's manifest. It opens no trajectory: the whole
  suite over dogfood #4's 3,293 runs takes 3.2s.
- **`allow_unfinished=True` on an `AgentNode`**, recorded in the manifest's node entry beside
  `allow_unknown` and, through it, in the results file's `config.nodes`. Only an `AgentNode`
  carries it, which the build confirmed: `Deterministic` and `LLMNode` return `NodeOutcome`
  with `termination=None`, and over 3,293 real runs every unfinished termination was an agent
  node's.
- **A fifth figure the design named and stage 1 did not build.** The item's table has two
  spends, 289 executions for 5,487 calls and 189 of them for 3,407, and only the first had a
  field. `NodeMetrics.unfinished_model_calls_without_tool_calls` and the manifest's
  `model_calls_without_tool_calls` are the second, which is what the gate's message quotes and
  what the report's narrow line prints. Named at the sitting of 2026-08-19.

**The decision that changed at the sitting.** The item's §6 said the check reads every run
under `runs/`. It reads **every run the pipeline as it now stands has made**, by the
`behaviour_fingerprint` each run records. The argument was the shape of the failure rather than
the rule: a project that reads the message, fixes the prompt and runs again would stay failed
for as long as it keeps its runs, and the cheapest way to a green gate is `rm -rf runs/`, which
destroys the record every other check reads. Measured on dogfood #4 before the decision: the
newest behaviour would have covered 195 of 3,261 agent runs and the newest shape 1,383, against
one run for every other check, so the coverage the item argued for survives. Thilina took it
the same day.

**Three defects the build found.**

**`tools_that_never_succeeded` was wrong, and only an aggregate showed it.**
[`per_node.py`](../../src/simple_agents/evaluation/per_node.py#L645), `_name_failed_tools`, was
called per run and wrote its count into a dict shared across runs, so a tool that failed in one
rollout and worked in the next was still named, with whichever run was read last deciding the
number. Found reading the figure back over 3,293 runs: `hunt` reported `consult 1, whats_new 1`
where `whats_new` had answered elsewhere. Counted over every run read now, and the same project
reports `consult 1` alone. The test fails with the fix removed.

**`simple-agents report` raised on a trajectory**, which is the file most likely to be pointed
at. It names the run directory instead, and a manifest gets the same message rather than
`EvalResults.read`'s version refusal, which told the reader to re-run an evaluation.

**Two manifest docstrings were on the wrong fields.** `fetch_policy`'s text sat under
`unfinished`, which stage 1 inserted between them, and `role`'s sat orphaned after `_lock`.

### 3.8 The reverification cycles, 2026-08-19

Run on Thilina's instruction, until a pass changed nothing. **Six passes**, each reading every
line the ones before it wrote, re-running the suite and both live arms. What each found got
smaller: behaviour, then arithmetic, then whether a sentence was true, then this section's own
arithmetic. The three defects §3.7 carries are not counted here: the build found those itself,
before the first pass.

**Pass one, six things.** Two are the prose the code prints, below. One is what a run in flight
said, below. The other three are gaps rather than defects: nothing tested the gate firing on a
fan-out's items, which is the member the design cares most about; two of the messages the check
can be blocked with had no test, the one about a run older than the counts and the one about a
run that is not the agent's; and `basis_from_manifest` read a rate that was absent as a rate of
zero, which prices tokens free (§3.6).

**The lines under a node did not stand on their own.** A line under a node read `of those, 188
made no tool call`, which has an antecedent in `results.report()` and none under a table row,
and a fan-out node whose items spun showed `-` in the unfinished column with that line beneath
it. Every line names what its figure is over now, and one function renders them for both
surfaces. The other was the headline: it said `90 of 102 execution(s), spending 1,689`, where
the spend covers fan-out items too, so it now counts units and says how many of them were items.

**A run still executing read as a clean run.** A manifest is written at the start with
`unfinished` empty and rewritten at every ending, so a run in flight carried an empty block that
the gate read as a run that produced everything. It is excluded from the pool and counted as
`still_running`, which the message names, the way
[`artifacts.py`](../../src/simple_agents/conformance/artifacts.py#L423), `_latest_run`, already
preferred a finished run.

**Pass two, seven things, and the accounting is the one that matters.** The figure did not say
where the runs it left out went, which is
this item's own failure one level up. The pool is anchored on the newest finished run of the
agent, and everything else was a gap between `read` and the runs on disk: `unfinished_across`
now counts `other_role`, `unreadable`, `still_running`, `other_pipeline` and `without_counts`,
and those five plus what was read account for every run under the directory. A test asserts the
sum. Two blocked messages were wrong before it: a project whose only runs carry a broken
manifest was told none of them was the agent's, and a corrupt manifest was reported as a run
still executing.

**A test of my own was order-dependent.** The accounting test picked which run to corrupt by
sorting the directory names, and a run id is a timestamp to the second plus a random suffix, so
four runs made in one second sorted at random: it passed alone and failed in the file. It names
each run as it is made now. The other four of that pass were a docstring counting four figures
where there are five, a corrupt manifest reported as a run still executing, a run whose
trajectory could not be read still deciding which cost basis priced the rest, and the same run
counted on the outcome line as one still running.

**Pass three, five things, every one about whether a sentence was true.** A message read
`none of them the agent's` where `--role labelling` had been passed and nothing matched; the
clauses under a figure agreed with a plural where the count could be one; the cost line told a
project to declare a basis it had already declared, where what it declared was a kind this
library cannot price or a basis missing a rate; a docstring counted four figures where there
are five; and `docs/conformance.md` §3.7 had drifted from the message it quotes. **Two
documented samples nothing ran are pinned by tests now**, one per document, and each fails on a
reworded line.

**Pass four found nothing in the code.** It re-read every module the three passes before it
touched, printed all eight messages the gate can emit against the states that emit them, and
re-ran both live arms. It wrote this section, which is a change, so it is not where the cycle
stopped.

**Pass five read this section and found it wrong about itself**, counting four passes where
there had been five and attributing the build's own three defects to the first of them. **Pass
six changed nothing**, which is where it stopped.

**One check no reading would have made.** `unfinished_work` over all 3,293 of dogfood #4's runs
totals 289 executions and 5,487 model calls, of which 189 units and 3,407 calls never acted:
the four figures §2 measured by hand at the sitting, and the fifth, 3,407, which the design
named and stage 1 did not build. No invariant was violated over those runs.

## 4. Verification

**Live against vLLM**, `Qwen/Qwen3-1.7B` at revision `70d244cc86cc` on port 8001, 2026-08-19.
`max_output_tokens` set on every node, as the handoff requires of a reasoning model.

**Two runs, one node that cannot act and one told to call a tool.** The first returned `None`
from the node and completed; the second answered. `node_metrics` over the pair reported
`terminations {'finish': 1, 'max_steps': 1}`, `unfinished_executions 1`,
`unfinished_model_calls 3` of 5, and `unfinished_without_tool_calls 0` — the model called
`look_up` twice and still produced nothing, which is the distinction the two figures exist to
make. Each manifest agreed with `unfinished_work` over its own trajectory, at
`trajectory_format_version 0.26` and manifest `0.30`.

**A live fan-out of three items at `concurrent_items=3`.** Every `tool_call` carried the item
that made it, interleaved: `look_up` on item 2, then `finish` on items 2, 0 and 1. Nothing in
the library could say that before this stage.

**The fan-out occurrence fix, live and end to end.** Two items of an `AgentNode` fan-out at
`concurrent_items=2`, each told to call one tool with no arguments, against `Qwen3-1.7B`, with
the interleaving flipped between the recording and the replay. Each item recorded its own entry
under its own `item_index` and the replay reproduced the pairing. The unit test is what pins the
pairing exactly, since a 1.7B model does not reliably echo what a tool returned.

**All four remaining members produced live**, against `Qwen3-1.7B` with a delegated
pipeline: `empty_responses` from an `AgentNode` given `max_output_tokens=64`, which returned
`finish_reason=length` with no content twice; `delegations_out_of_budget` from a two-node
sub-pipeline with one step between them, so the second node could not run and the delegation
recorded `budget`; and `tools_that_never_succeeded` from a tool raising `ModelFacingError` on
every call. The search path was re-checked against a real embedding model after the defect above
was fixed: two calls, no empty responses.

**The reverification pass re-ran all three live scripts against the final code**, and the
refusal caught one of them: `live_stage1.py` declared its `output_schema` as a dataclass and had
been running against vLLM producing answers nothing validated. Corrected to a `BaseModel`, all
three pass: a spun execution reported with its manifest agreeing, an undefined figure now
printing the wider one under it, and a fan-out item's calls attributed to the item.

### 4.1 Stages 3 and 4, live

**Against `Qwen/Qwen3-1.7B` on vLLM**, in one project directory, with the model offered the
tools and forbidden to call any of them, which is dogfood #4's failure at the wire.

- **Two runs of a node that spins** returned `None` from the node and completed with no error.
  `simple-agents report runs/` printed `2 (100%)` unfinished with what it spent, and **FT-35
  failed** naming `hunt`, 2 units, 6 model calls, over 2 runs.
- **The project then fixed the node and the gate passed**, reading 1 of the 3 runs and naming
  the 2 the earlier pipeline made. The old runs were still on disk. That is the decision of
  §3.7 working end to end.
- **The waiver passed the node**, and the note under the checks reported the wider figure the
  gate no longer covers.
- **A fan-out of three items at `concurrent_items=2`, every item spinning.** `FanOutResult.ok`
  was `True`, every `ItemOutcome` carried `value=None` and `termination='max_steps'`, and the
  node itself recorded none: the design's own probe, which said every figure the library
  reported called the node fine. The manifest carried
  `{'executions': 0, 'items': 3, 'without_tool_calls': 3, 'model_calls': 6,
  'model_calls_without_tool_calls': 6}`, the report named the items on their own line, and
  FT-35 failed on them.

**Against Gemini** with the published `gemini-3.1-flash-lite` rates, because the cost path is
what a builder reads in money: the per-node total derived through `basis_from_manifest` equalled
what the runs recorded for themselves, `0.00045400` both ways. Two of the four calls came back
with no content, which put `empty_responses` on the report line as well.

**Every live script was re-run against the final code after each reverification pass**, and both
arms still agree.

**The five figures were checked against every trajectory on this machine**, which is the
strongest check available for a count: `unfinished_work` over all 3,293 of dogfood #4's runs
totals 289 executions and 5,487 model calls, of which 189 units and **3,407 calls** never acted.
Those are the four figures §2 measured by hand at the sitting, and the fifth, 3,407, is the one
the design named and stage 1 did not build. No invariant was violated over those runs: no
narrow figure exceeded its wide one, no node reported more inert units than units, and no spend
was attributed to a unit that never existed.

**Stage 2, live: an evaluation of two examples whose consultation reached a channel that
answered nothing.** Both rollouts recorded `left_out=('unanswered_consultation',)`, and every
one of the eight rates printed `undefined` naming the cause rather than a figure over an agent
that was never measured. The node block reported `consulted: declined 2` and
`answered by: end_user 2` beside it. **That is the change's whole effect in one run**: before
it, the same evaluation reported `false_confidence` and `missed` as rates about the agent.

The message a builder reads there was reworded after seeing it: with one cause it said the
count twice.

## 5. Doc consequences

- **`docs/evaluation.md`** §5 gained the four figures and what separates the two of them that
  matter; **§5.5** is new and covers `node_metrics`. Its "What to reach for" table gained two
  rows, one for `results.report()` and one for `node_metrics`.
- **`docs/run-envelope.md`** §2.1 gained the `unfinished` key and **§2.8** explains it.
- **`docs/trajectory-format.md`** carries `item_index` on three more record types, and the
  version it states moved.
- **`CHANGELOG.md`** carries one entry for the stage, and
  [`design/trajectory-format-changelog.md`](../design/trajectory-format-changelog.md#L1) carries
  `0.26` with what it settled and what it cost.
- **`docs/conformance.md` §5 said sixteen entries are checked** where seventeen are registered,
  and the test guarding it asserted the stale word beside the live count. Both fixed 2026-08-19,
  and the test now spells both counts off the code.
- **Stage 3**: `docs/run-envelope.md` **§8.2** is new and covers `simple-agents report`, §8
  gained `since=` and `last=` on `runs()`; `docs/evaluation.md` §5.5 and its "What to reach
  for" table name the command, and §8.1 shows what a node that produced nothing adds under its
  row; `docs/procedure.md` stage 4 says to run it.
- **Stage 4**: `docs/failure-taxonomy.md` carries **FT-35** in Group C and its index and counts
  moved to thirty-five; `docs/conformance.md` **§3.7** is new and says which runs it reads, with
  §1, §3, §3.1, §4 and §5 counting eighteen checks; `docs/run-envelope.md` §2.6 gained
  `allow_unfinished` and §2.8 the fifth figure; `docs/pipeline.md` §2.3 covers the waiver;
  `README.md` counts thirty-five failures and eighteen checks.
- **Two documented samples nothing ran are run now.** `docs/run-envelope.md` §8.4's table is
  pinned by `tests/test_spend_report.py`, which compares its header and every line under a node
  against what the code renders, the way `tests/test_sample_report.py` pins §8.1's. Both fail on
  a renamed column and on a reworded line.

## 6. Left open

Nothing. Every stage of `P3-22` is built, and the design record moved to
[`design/spend-that-produced-nothing.md`](../design/spend-that-produced-nothing.md#L1).
