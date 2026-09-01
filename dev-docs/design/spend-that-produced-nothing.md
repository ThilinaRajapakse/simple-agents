# Spend that produced nothing

**Design of record for what the library knows about a unit of spend that produced nothing.**
Designed 2026-08-19 at dogfood #4's sitting 4 as `P3-22`, and **built the same day** in four
stages, `P3-23` to `P3-26`.
[`build-logs/unfinished-work-build-log.md`](../build-logs/unfinished-work-build-log.md#L1) is
how it was built and what that found.

**Two things below were settled differently at the build**, and the build log is where each was
argued. §6 said the check reads every run under `runs/`; it reads every run the pipeline as it
now stands has made, so a project that fixes the node is measured on the runs since the fix
rather than having to delete the ones that prompted it. And §1's table owed a fifth figure that
stage 1 did not build: what the units that never acted spent, which is
`NodeMetrics.unfinished_model_calls_without_tool_calls`.

`docs/` is authoritative on what any of this does today: `docs/conformance.md` §3.7 for the
gate, `docs/run-envelope.md` §2.8 and §8.2 for the counts and the report,
`docs/evaluation.md` §5 for the figures.

## Where it came from

Three candidates of [`runs/dogfood-4/inventory.md`](../runs/dogfood-4/inventory.md#L1) §3, taken
together as sitting 4: `DF4-I21` a report line, `DF4-I22` a check, `DF4-I36` the general question
behind both. The general question is Thilina's own note from the run, `DF4-N12`, verbatim:

> Can the library check for stupid shit that happens? Like a node that just spins in the air doing
> nothing until it hits max steps? More verification? I know it's hard to judge correctness of
> arbitrary projects and their decisions.

**Two more things were pulled into it at the sitting, on Thilina's call.**

`plan.md` §2.1's *An outcome for a run that consulted and got no answer*, accepted 2026-08-17 and
holding two figures, `unanswered_consultations` and `unreached_items`, each shipping as a count
that reclassifies nothing. It waited on *"a project whose `unanswered_consultations` or
`unreached_items` is nonzero often enough to say whether it belongs inside a denominator or outside
it"*. Thilina, 2026-08-19: *"This feels like the point to pull in the entry from 2.1 into this
sitting, rather than to push something out to it."*

The inbox entry of 2026-08-18, which leaves `random-thoughts-questions.md` into this item: *"We
store a lot of runs and evaluations. I think something to visualize those results and outcomes
would be super useful. Right now, the builder has no easy to way to analyse any of them."*

**The framing came from a correction.** The first pass argued a member out of the class because
dogfood #4 produced zero instances of it. Thilina, 2026-08-19: *"dogfoods are small, toy projects.
Using them to find issues and gaps is helpful, using them to assert the negative, i.e., say
something is not needed is short sighted. We have to reason from logic."* Everything in "What was
decided" is derived from a library contract rather than from an instance count.

## What the problem is

Measured 2026-08-19 against `be78524`, on the library and on all 3,293 run directories of
`/home/thilina/Projects/dogfood-4`.

**An `AgentNode` produces output only from a `finish` call**, so an execution that ends on a budget
axis produces nothing at all. Probed live: the node records `outputs: null` and `error: null`, the
successor node is handed `None`, and the run completes normally.
[`tests/test_loop_and_budgets.py`](../../tests/test_loop_and_budgets.py#L99),
`test_a_response_with_no_tool_call_does_not_end_the_loop`, is the shipped statement of the same
contract: termination is an explicit `finish` call and never a heuristic on prose. On the dogfood's
real data **all 289 such executions recorded `outputs: null`**.

| | executions | model calls | share of the run's 22,475 |
|---|---|---|---|
| ended on a budget axis, so produced nothing | 289 | 5,487 | **24.4%** |
| of those, made no tool call, consultation or delegation | 189 | 3,407 | **15.2%** |

`DF4-D5`'s 188 / 3,384 / 15% is the `max_steps`-only slice of the second row and reproduces
exactly. The first row is 1.6× larger and was in no record.

**The two rows are different failures.** `hunt` acted in 27 of its 28 budget-ended executions and
still spent 54.7% of its own model calls on executions that returned nothing: the cap cut off work
that was under way. `look_closer` made no call at all in 188 of its 257, each spending exactly its
cap of 18 calls: the loop never started. The remedy for the first is the cap or the task; for the
second it is the prompt or the tool declarations, and in this project it was measured as a
malformed `<tool_call>` block the server would not parse, one closing brace short.

**The figure was on disk and nothing printed it.** Fifteen of the project's results files carry a
`max_steps` count on `look_closer`, `eval_1bd4d0b7c852.json` showing 90 of 102 executions and 1,689
model calls. [`results.py`](../../src/simple_agents/evaluation/results.py#L194), the `ended:` line
of `report()`, would have printed it. **The project never called `results.report()` and never read
`results.nodes`**: `evaluate.py` loops over `results.metrics` and prints the headline rates by
hand. `results.report()` is named once in all of `docs/`, at line 1749 of a 1,900-line document,
is absent from that document's "What to reach for" table, is absent from
[`docs/procedure.md`](../../docs/procedure.md#L187)'s `measure` stage, and has no CLI command.

**The aggregate exists only inside an evaluation.**
[`per_node.py`](../../src/simple_agents/evaluation/per_node.py#L366), `per_node`, computes every
figure here and is **not exported**: `evaluation/__init__.py` publishes `NodeMetrics` and not the
function that fills it. A project holding 3,293 run directories has `runs()` and
`read_trajectory()` and no supported way to aggregate across them.

**A fan-out is blind.** Probed live: an `AgentNode` with `over=` whose every item spun records
`termination: null` on the node, `FanOutResult.ok` is `True`, `failures` is empty, and
`per_node`'s `terminations` is `{}`. Nine model calls, three `null` values, and every figure the
library reports says the node was fine. Dogfood #4's judging pass is a fan-out.

**A single run does not show it.** 8.8% of the project's runs hold an execution that produced
nothing and 5.7% hold one that also never acted, so a check reading the newest run alone would
have passed nine times in ten on a project spending a quarter of its calls this way.

## What was decided at the sitting

### 1. The class, derived from contracts rather than from instances

The library cannot know whether an answer is good. It does know when a unit of spend produced
nothing, because its own contracts define what producing something is. That fact exists at four
levels, and at each the library also knows what it cost.

| Level | Member | Read from | Report or gate |
|---|---|---|---|
| Call | A model call returning no content and no tool call | `finish_reason`, `outputs` | Report |
| Execution | Ended on a budget axis or on `finish_rejected`, so `outputs` is `null` | `termination` | Report |
| Execution | The same, having made no tool call, consultation or delegation | joins on `parent_id` | **Gate** |
| Item | Both figures per fan-out item | `outputs.items[].termination` | Report |
| Subtask | A delegation that returned `budget` | `delegation.termination` | Report |
| Tool | A tool whose every call errored | `tool_call.error` | Report |
| Tool | Retries whose attempts all failed | `attempts` | Report |
| Rollout | Scored on something it could not control | §3 below | Denominator |

**What is excluded, and why it is a contract rather than a missing instance.** Repeated identical
tool calls are not evidence of waste: the library already models two identical calls as two
occurrences, through `reserve_tool_occurrences` and per-occurrence cassette replay, because such a
call can legitimately return different things. A node whose output nobody read is not visible: the
library sees the declared type a node accepts (FT-28) and never what its function does with it. A
tool whose every call errored is reported and never gated, because
[`docs/tools.md`](../../docs/tools.md#L122) makes `ModelFacingError` the way a tool says "no
match", so a search tool that legitimately finds nothing on every input is indistinguishable from a
broken one.

**Only one member gates**, and the reason is that it alone has no benign reading. A cap that binds
is sometimes the cap doing its job, which is why `produced nothing` reports. A loop that spent its
whole budget without once calling a tool, consulting or delegating produced nothing and did
nothing, and on the wire every one of those three is a tool call in one namespace shared with
`finish`: see [`nodes.py`](../../src/simple_agents/nodes/agent.py#L125), `wire_tools`.

### 2. Names

The vocabulary is the library's own contract. An execution that produced nothing is one that did
not `finish`, which is mechanical rather than a judgement about the node.

| Name | What it is |
|---|---|
| `NodeMetrics.unfinished_executions` | Executions that ended without a `finish`. Excludes `error`, which `errors` counts, and `skipped` |
| `NodeMetrics.unfinished_model_calls` | What those executions spent, beside `model_calls` and `paid_tool_calls` |
| `NodeMetrics.unfinished_without_tool_calls` | The subset that made no tool call, consultation or delegation |
| `node_metrics(run_dir)` | Public, returning `dict[str, NodeMetrics]`, beside `runs()`, `progress_of()` and `prompt_differences()` |
| `allow_unfinished=True` | On an `AgentNode`. Reads beside `allow_unknown=False` |
| FT-35: Steps spent without a tool call | Group C, beside FT-11 and FT-12 |

**`node_metrics` publishes `per_node` rather than adding a reader.** The computation exists;
what is missing is a path-taking entry point. `totals_of(nodes)` at
[`results.py`](../../src/simple_agents/evaluation/results.py#L861), `totals_of`, already derives the run-level
totals from the same dict, so the per-node figure is the primitive and the whole-run view is
derived from it. Thilina asked whether the name fits something that is about a whole run: the
function is about nodes, and the **command** is what is about the runs.

### 3. The denominator, which closes `plan.md` §2.1's entry

The entry waited on evidence and needed a rule, and the rule is already in the library.
[`outcomes.py` `Outcome.NO_RESPONSE`](../../src/simple_agents/evaluation/outcomes.py#L103) puts a
rollout outside every denominator because *"the backend never answered, so the agent produced
nothing to sort"*. The principle underneath is that **a rollout is inside a denominator when what
it returned is attributable to the agent.**

| Case | Attributable | Verdict |
|---|---|---|
| `unreached_items`: items lost to a call the backend never answered | No. `no_response` at item granularity | Outside |
| A consultation answered by a channel declaring `nobody`, which `unattended()` declares itself | Yes. Nobody answering is the designed path | Inside |
| A consultation to `end_user` or `builder` that came back declined | No. The agent asked and the answer never arrived | Outside |
| A fan-out item that spun to its own cap | Yes. It had the steps and did not finish | Inside |

Rows 2 and 3 are separable today: `answered_by` has six values and
[`docs/tools.md`](../../docs/tools.md#L944) is the table.

**Both figures print, on Thilina's call.** A rate over the measurable rollouts, and under it the
same rate with the left-out rollouts counted as they scored, so the narrower number cannot be
quoted without the wider one:

```
  accuracy                   94.7%  [88.2%, 97.7%]  n=95 over all rollouts, less 5 whose question went unanswered
                             90.0%  [82.4%, 94.7%]  n=100 with those 5 counted as they scored
```

`Metric.no_response` becomes `Metric.left_out`, keyed by cause,
`{"no_response": 9, "unanswered_consultation": 5, "unreached_items": 2}`, and `Metric` gains
`including_left_out: Interval | None`, `None` where nothing was left out. This is the one shipped
field the item renames rather than adds. A metric with nothing left out prints one line, as today.

### 4. Where the figure appears

`results.report()` carries it under the node it belongs to, and `simple-agents check` prints it as
a note, because the gate is the one surface [`docs/procedure.md`](../../docs/procedure.md#L187)
forces the coding agent through: stage 4 ends with `simple-agents check` exiting 0.

**`simple-agents report <path>`**, text and JSON, reading whatever it is pointed at: a results
file, an evaluation directory, one run, or a directory of runs. The last is what dogfood #4 never
had, and it is what the inbox entry asks for. Thilina, 2026-08-19, on scope: *"text and JSON is
fine. The coding agent can show both/either to the builder if needed."*

```
simple-agents report runs/

  3,293 runs, 2026-08-11 to 2026-08-14, role agent
  22,475 model calls, 4,401 tool calls, 3.82 USD
  completed 3,291, stopped_early 2

  node        kind     execs  calls  tools  unfinished  its calls  cost
  look_closer agent     3071  15610   4293    257 (8%)       4626  1.9102 USD
              of those, 188 made no tool call at all, spending 3,384 calls
  hunt        agent      104   1411    336   28 (27%)         772  0.2214 USD
```

`docs/procedure.md` stage 4 gains a line saying to run it and read it. Whether it was read is not
checkable, which [`docs/failure-taxonomy.md`](../../docs/failure-taxonomy.md#L609) §10 already says
of every artifact of that kind.

### 5. The waiver

**`allow_unfinished=True` on the `AgentNode`**, defaulting to false, recorded in the manifest and
in the results file's `config.nodes`, read by FT-35. Thilina asked for an option to skip in the
narrow cases where spinning is expected. It is per node rather than per run because that is what
the library's four existing waivers do: `allow_unknown=False` on a node turns FT-04 off and is
recorded in both artifacts, `stream_without_usage=True` lands in `stream_waivers`, `exhaustive=True`
waives three consultation branches, and a resume's accepted differences land in `resume_waivers`.
A per-node declaration also leaves the gate live for every other node, and a run-level argument
would reach the check only once something recorded it, at which point it is this design attached to
the wrong scope.

### 6. What the check reads, and what that changes

**Every run under `runs/`**, which makes FT-35 the first check to do so.
[`docs/conformance.md`](../../docs/conformance.md#L115) §3.1 says the checks read the newest run
and the newest results file, and that section has to say what FT-35 does instead. FT-13, FT-14 and
FT-15 are unchanged.

**The counts go in each run's `manifest.json`**, which is what makes reading every run affordable
at any size. The manifest already carries `counts`, one per record type, and `totals`, both derived
from the trajectory and stored so a reader never parses it. Measured: parsing every record of 3,293
trajectories is 1.1s over 604MB; reading 3,293 manifests is 0.9s over about 6MB. The gate then
never opens a trajectory, and cost grows with the number of runs rather than with their size.

**Scoping**, on `report` and on `check`: `--last N`, `--since <date>`, and the `role` and `live`
filters `runs()` already takes. **What was read is named in the output**, on the report, on the
note and in the failure message, so a scoped figure says what it covered. A run written before this
ships carries no counts and is named as unread rather than counted as clean.

### 7. Stages

| Stage | What | Moves |
|---|---|---|
| 1 | The figures at all four levels, `node_metrics()`, the manifest counts | Results file, manifest |
| 2 | The denominator settlement, with both figures printed | Results file |
| 3 | `simple-agents report`, the `check` note, the `report()` block, the `procedure.md` line | Nothing on disk |
| 4 | FT-35, registered, with `allow_unfinished=` | Manifest |

## What has to be decided

Nothing blocking. Three things the build will settle and record here:

- **The exact `left_out` cause keys**, which become results-file vocabulary.
- **Whether `simple-agents report` defaults to every run** or to a scope. A silent cap reads as
  coverage, so the default has to name what it read either way.
- **Where FT-35 sits by tier.** It reads runs rather than a results file, so `prototype` can carry
  it, and every other run-reading check is `prototype`.

**All three were settled at the build, 2026-08-19.** The cause keys are `no_response`,
`unanswered_consultation` and `unreached_items`. The report reads every run and every role by
default and names how many it read of how many are there, with `--role`, `--live`, `--since` and
`--last` narrowing it. FT-35 is `prototype`.

## What it waits on

Nothing. `P3-1` is the item it came out of, and it was built beside it the same day.
