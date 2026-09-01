# Build log — what an agent may do alone

`plan.md` §1 `P3-36`. Started 2026-08-26. Written while building, not afterwards.

Two candidates from dogfood #5's sitting 3, built together because both are about the same
seam: what a step settles for itself. [`DF5-I14`](../runs/dogfood-5/inventory.md#L124) is the
handle that lets an agentic step reach the node's own input;
[`DF5-I15`](../runs/dogfood-5/inventory.md#L125) is the question nobody asked about what the
builder wanted that step to do alone.

## 1. Before any design

**The framework survey behind `DF5-I14` was re-measured rather than recalled**, which the row
asked for. Installed into a scratch venv on 2026-08-26 and introspected: `langgraph 1.2.11`
with `langchain-core 1.6.0`, `pydantic-ai-slim 2.34.0`, `openai-agents 0.22.0`.

| Framework | The mechanism | Hidden from the model | Carries |
|---|---|---|---|
| LangGraph | `Annotated[T, InjectedState]`, and `InjectedState.__init__(field: str \| None = None)` | `tool_call_schema` holds `query` alone; `get_input_schema` holds both | the node's own graph state, whole or one key |
| Pydantic AI | `RunContext[DepsT]` as the first parameter, `takes_ctx=True` | `function_schema.json_schema` holds `query` alone | `ctx.deps`, one object set at run start |
| OpenAI Agents | `RunContextWrapper[T]` as the first parameter | `params_json_schema` holds `query` alone | `ctx.context`, one object set at run start |

**The row's summary is right about the schema and narrower than it reads about the value.**
All three hide the parameter. Only LangGraph's carries the node's own input and only
LangGraph's takes a key; the other two carry a run-scoped object the caller passed at the
start, which is what a closure already gives a Simple Agents project. The need `DF5-D8`
measured is the node's input, so `InjectedState` is the precedent and the other two are
evidence that hiding an injected parameter from the schema is the settled shape.

Ran a `ToolNode` inside a compiled `StateGraph` to see it filled rather than only declared:
`Annotated[dict, InjectedState]` arrived as `state keys=messages,pool` and
`Annotated[list, InjectedState("pool")]` as `pool=[1, 2, 3]`.

**What the library does today.** Six handles in
[`tools.py` `HANDLE_TYPES`](../../src/simple_agents/tools.py#L651), detected in
[`_handles_in_signature`](../../src/simple_agents/tools.py#L1086) by the parameter's own type
after `Annotated` metadata is stripped. Four of them in
[`RE_EXECUTED_HANDLE_TYPES`](../../src/simple_agents/tools.py#L668), which
[`context.py` `call_tool`](../../src/simple_agents/context.py#L1033) reads to return before
keying anything. Three places fill them:
[`_handles_for`](../../src/simple_agents/nodes/agent.py#L1117),
[`_FixedPointCaller`](../../src/simple_agents/runtime/tooling.py#L30)'s own closure for a tool a node
body calls, and [`_deterministic_handle`](../../src/simple_agents/runtime/handles.py#L45). All three
had the node's input in scope already and none of them passed it.

**The brief side.** 46 questions in
[`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L33) `Question`, none open-ended.
[`BriefEntry`](../../src/simple_agents/conformance/brief.py#L62) carries `status`, `answer`,
`deferred_to` and `source`. `understanding_confirmed_at`, `design_confirmed_at` and
`research_confirmed_at` are brief-level keys naming a stage, read by
[`_account_reason`](../../src/simple_agents/conformance/checks.py#L601) and its two siblings;
[`_settled`](../../src/simple_agents/conformance/checks.py#L533) is what FT-24 asks per
question and it read a name rather than a `Question`.

## 2. Design

### `NodeInput`, the seventh handle

**A handle is a parameter the library fills and the model never sees.** Six name something the
library owns and are the parameter's type. `NodeInput` names the node's own input, and is
annotation metadata because the type of that value belongs to the project:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[str]:
    """Rank this node's shortlist against a query. Returns the titles that match."""
```

`NodeInput("pool")` is the value under that key; `NodeInput` with no key is the whole input.
Both forms of the marker are read, the instance and the bare class, as `InjectedState` reads
both. **A bare `NodeInput` as the parameter's own type is refused**, naming the `Annotated`
form: the parameter has to keep the type of the value or the model's schema and the tool's
signature disagree about what it holds.

**It joins `RE_EXECUTED_HANDLE_TYPES`.** The node's input is not in the call's key, so a
stored answer would be served to a rollout that was handed something else. That also puts it
under the existing refusal: a tool taking one may not declare `spends_money` or
`irreversible`, because a re-run tool repeats whatever it does.

**Weighed and not taken.** A `Tool.handles` value of `type | NodeInput`, so the marker
instance could carry its own key: eight `issubclass(kind, ...)` sites break for one field
saved. `handles` stays `dict[str, type]` and a second `Tool.node_inputs` maps the parameter to
its key. A parameter absent from that map reads the whole input, so a `Tool` built by hand
needs nothing.

**A wrong key is a `ConfigurationError`, not a `CallerFacingError`.** The key is declared where
the tool is, so it fails identically on every rollout, and an evaluation stops on the first
rather than recording k×n agent failures. That is `LLMNode.execute`'s own reason for the same
choice about a missing model client.

### The bounded loop, named as the pattern where it is right

`DF5-D8`'s project replaced the withdrawn `AgentNode` with a cycle of `LLMNode` and
`Deterministic` under `Loop(max_iterations=3)` because the tool contract left it no choice.
That reason is gone, so `docs/pipeline.md` §2.3 says when each shape is right on its merits:
the cycle where the steps are the same every time round and what varies is how many times, the
`AgentNode` where which step happens next depends on what the last one returned.

### `anything_else`, and `agency_boundary` as a want

**`anything_else` is required and put again at every stage.** Every other question is the
library's; this one is the builder's. `Question` gains `re_asked_each_stage`, `BriefEntry`
gains `asked_at`, and FT-24 refuses while `asked_at` is absent or names an earlier stage than
the project is at. This is `understanding_confirmed_at`'s mechanism moved from a document
being re-read to a question being re-asked, and it carries the same limit: it cannot tell an
answer that followed a re-asking from an `asked_at` moved on its own.

**The answer accumulates as prose, labelled by stage.** No structured per-stage field: every
other entry holds one answer string, and the scaffold is what says to append rather than
replace. `"Nothing"` is an answer; a blank is not.

**A deferral on it is refused at `Brief.read`.** There is no later stage to defer to, so a
deferral would silence the question at every stage after this one, which is the failure the
`source = "coding_agent"` rule exists to stop in the other direction.

**It is not `about_what_is_wanted`.** That flag drives the report's list of wants no shape
decision rests on, and an entry answered at every stage would sit in that list forever, which
is `DF5-L3`'s "taught to the next session as noise" by construction. What gets it read is the
re-asking itself, and the scaffold's last paragraph, which says to read what came back against
what is already recorded.

**`agency_boundary` is asked as a want and put together with `consultation`.** Its old
scaffold framed agency as a cost to justify. It now asks what the builder would like the agent
to work out for itself, in the terms of their own work, written down before any node kind is
named; the reading back into `Deterministic`, `LLMNode` and `AgentNode` follows it, and where
a step the builder wants working alone comes out fixed the coding agent says so. It gains
`about_what_is_wanted=True`, so a `shape` decision names it under `from` and the report says
when none does.

## 3. Build

**No format moved.** `brief.toml` gains an optional key on an entry, which every brief already
on disk reads without change; what breaks such a brief is the new required entry rather than
the field.

**Surfaces touched.** `tools.py` (`NodeInput`, both handle tuples, `Tool.node_inputs`,
`_handles_in_signature`, `_node_input_in`); `nodes.py` (`_node_input`, three fill sites, and
`inputs` threaded to `AgentNode._handles_for`, `AgentNode._overlap` and `_FixedPointCaller`);
`__init__.py`; `evaluation/runner.py`'s divergent-recording refusal;
`conformance/elicitation.py`, `brief.py`, `checks.py`; `cli.py`'s `questions` output.

**What the build found that the design did not know.**

- **A fanned-out node's `over=` key holds the item.** `_fan_out` builds `{**inputs, over: item}`,
  so a tool over a fanned-out node names the `over=` key and gets one row. Found by writing a
  test that named the row's own key and watching every item fail.
- **A `Join` is a `Mapping`**, so a `NodeInput` key on a joined node names the node the value
  came from, and an edge that did not fire delivers the `Unknown` the `Join` holds. A
  `NodeFailure` is not a mapping, so a key there is refused and the whole-input form is what a
  handler's tool takes.
- **`inputs` defaulted to `None` on two private signatures** while I was threading it, which
  would have handed a tool `None` from a call site that forgot. Both are required now.

**Tests.** 3086 to 3132. [`tests/test_a_tool_over_the_nodes_input.py`](../../tests/test_a_tool_over_the_nodes_input.py#L1)
is new and holds 25; the rest are additions to `test_procedure.py` and
`test_conformance.py`. The conformance fixtures are generated from the shipped question set, so
[`build_conformance_fixtures.py` `_brief`](../../scripts/build_conformance_fixtures.py#L409)
learned to write `asked_at`, and every fixture brief gained the entry.

## 4. Verification

**Nine full cycles**, each one a reading of the code, a reading of the documents, the suite,
the four scripts, and a live run against vLLM. Eight of the nine found something, and most of
it was prose: what the shipped documents said about the code, what the code's own docstrings
said about the mechanism, and what these records said about the build.

**Live, against vLLM `Qwen/Qwen3-1.7B` on port 8001**, `--gpu-memory-utilization 0.6`, tool
and reasoning parsers on, `max_output_tokens=4000` per the handoff's ceiling note. A probe of
twenty-six assertions over five sections, run to completion in every cycle. Nothing in it
replays.

What only the live run showed: **a real model chose the query and each run searched its own
pool.** Two runs of one pipeline over different shortlists answered `The Blue Planet` and
`Green Valley`; across both, every argument the model supplied was `query` and none was
`pool`; the call recorded `re_executed: true` and `cassette_key: null`; the node's own record
holds the pool the tool read; and the manifest's tool entry says `re_executed`. A wrong key
raised naming both the key asked for and the keys the node was handed. `simple-agents check`
over the frozen fixture tree passes as built, fails naming `anything_else` on a stale
`asked_at` and on none at all, and `Brief.read` refuses the deferral. `simple-agents questions`
prints the entry last at all six stages with that stage's `asked_at`.

**Cycle 1, four defects.** `AgentNode._overlap` and `_FixedPointCaller` took `inputs` with a
`None` default, so a call site that forgot would hand a tool `None` silently; both are
required now. The `Join` and `NodeFailure` cases were neither documented nor tested, and a
fanned-out `LLMNode` was untested where the `Deterministic` one was.

**Cycle 2, three defects, all counts and instructions with nothing reading them.**
`docs/tools.md` §3.2 says how many handles there are and how many re-run, and holds a table
of them; nothing compared any of the three to the tuples. `docs/procedure.md` names
`anything_else` at each of the six gates, which is `DF5-L3`'s lesson applied, and nothing read
that either. Both are checked now, each guard run against the defect it was written for. The
third was two `§n.n` references in the new test file naming no document, which `prose_check`
caught.

**Cycle 3, four defects, all in the elicitation text.** `agency_boundary`'s scaffold ended
"the manifest's node kinds are what it produced", which is `P3-29`'s `produces` and does not
exist; it names what `simple-agents check` prints today instead. It described `consultation`
without naming it, so the coding agent had no key to record under. `anything_else`'s scaffold
wrote `*Nothing*`, which reaches a terminal as asterisks. Its `ask` said "nothing here has
asked", and the builder does not see the list.

**Cycle 4, two defects, both in FT-24's own text.** The Check paragraph and the failure
message described a stale `asked_at` and not a missing one, which is the commoner case. And
the message ends by offering a deferral, which `Brief.read` refuses for this entry: it now
says which entries that offer covers.

**Cycle 5, four defects, and one of them was shipped.** The new §2.3 example named `publish`
and did not include it, and it did not build: `Draft` and `Verdict` have no `unknown` variant,
which FT-09 refuses at construction. **`docs/pipeline.md` §1.4's own example has had the same
defect since it shipped**, measured by building it. Both carry `allow_unknown=False` now. The
paragraph also said "a tool this node calls", and an `AgentNode`'s tools are called by the
model, and claimed resume as a difference between the two shapes when both resume.

**Cycle 6, four defects.** `brief.py` imported `QUESTIONS` inside a function for a cycle that
does not exist. Two docstrings described the stale `asked_at` and not the missing one, which
is cycle 4's defect in the source. And a section banner was four dashes short.

**Cycle 7, three defects, all in the new tests.** A test named "has no keys" asserted only
that the whole-input form works, so nothing checked that a key on a `NodeFailure` is refused.
The claim that an absent `Join` edge delivers an `Unknown` was written into `docs/tools.md`
and tested nowhere. And the module docstring said one test "is the test that failure would
fail", where what it means is that a closure would fail it.

**Cycle 8, four defects, two of them older than this item.** `docs/conformance.md` §2 said
**"Three keys record when the project's written account of itself was last checked against the
code"** and then named two of them plus `confirmed_against`, which dates the entries against
the code rather than against a stage. `research_confirmed_at` shipped at `P3-28` and never
reached that paragraph. My new §2.1 sentence pointed at "the three `*_confirmed_at` keys
above", which made a false paragraph load-bearing. The paragraph now names three and calls
`confirmed_against` a fourth key of a different kind, and a test reads it against `Brief`'s own
fields. The third was §2.1 describing the stale `asked_at` and not the missing one, the same
defect in a third place. **The fourth came out of reading §7.4.1 for the `ConfigurationError`
choice above**: it says such an error fails identically on every rollout so the other k×n are
not paid for, and a fan-out collects it as one item's failure instead. Measured on one
misconfigured tool over three examples at k=2: with no `over=` the suite stopped on the first
rollout, and fanned out it completed and scored six. §6 carries it.

**Cycle 9, one defect, and it was in this log.** §3 and `plan.md`'s §4 line said the suite was
at 3134, which is what `--collect-only` reports and includes the two skipped. The figure every
other entry in §4 states is the passing count, so it is 3086 to 3132.

**Cycle 10 found nothing**, which is what ends this.

**After cycle 10, on Thilina's direction**, two things moved and both were re-run against the
suite and the four scripts. `docs/pipeline.md`'s remaining `Verdict` example gained the waiver
(§6). And `handoff.md` lost its list of shipped changes that break a project on disk, and the
paragraph on what `simple-agents.md` §9 gained, on his challenge: *"Aren't those already
recorded elsewhere?"* Measured, and they are. Every one of the fifteen has a `CHANGELOG.md`
entry and a fuller one; §9 item 8's amendment is in `simple-agents.md` with its argument and a
link to its build log; and the file's own rule says a feature list is a second copy. Four lines
replace twenty-one, and `handoff.md` is 120 lines to 100. One fact in the deleted list lived
nowhere else and was not a breaking change: `uv sync` without `--extra semantic` prunes it and
one pacing test needs it, which is now a row in the machine table.

**Stability.** Ten cycles, twenty-nine defects, and the tenth was clean. **What the
code does moved in cycle 1 alone.** Cycle 3 moved prompt text and cycle 6 an import; everything
else the later cycles found was a statement about the code, in a shipped document, a docstring
or these records. The suite at 3132, the live probe over every cycle, `prose_check`,
`shape_check`, `check_citations` and `check_docs` clean.

## 5. Doc consequences

`docs/tools.md`: §3.2 reframed from "six types" to what a handle is, with `NodeInput` in the
table and both counts moved; §3.2.1 new, covering the key, the whole-input form, `over=`, a
`Join`, a `NodeFailure`, why a closure does not work, and the two refusals; §3.3's rule
rewritten so it names the handle that answers it.

`docs/pipeline.md`: §2.3 gains the tool that reads the node's input and the bounded cycle as
the other shape, with a complete example and what decides between them. §1.4's example gains
`allow_unknown=False`.

`docs/conformance.md`: §2's brief sample gains the entry, the keys paragraph is corrected, and
§2.1 gains `asked_at`.

`docs/procedure.md`: the standing instruction to ask `anything_else` at every stage, the same
named at each of the six gates, and the question counts at `brainstorm` and `research`.

`docs/failure-taxonomy.md`: FT-24's *What the library provides*, *Check* and failure message.

`docs/evaluation.md`: §7.6's quoted refusal, which now names `NodeInput` as the handle for a
tool whose answer depends on which rollout is running; and §7.4.1's carve-out for a
`ConfigurationError` raised inside a fan-out item.

`CHANGELOG.md`: the entry above the checks one.

**Shipped statements that stopped being true**: `docs/tools.md` §3.2 said six types and four
that re-run, and §3.3 said a tool may read what is in its key and what a handle gives it and
nothing else; `docs/conformance.md` §2 said three keys and named two;
`docs/pipeline.md` §1.4's revision-loop example did not build; `docs/evaluation.md` §7.6's
refusal named three handles for a tool whose answer varies and not the one that varies per
rollout, and §7.4.1 said a configuration error is never paid for k×n times, which a fan-out
makes false.

## 6. Left open

- **A `ConfigurationError` raised inside a fan-out item is collected as that item's failure**,
  which makes `docs/evaluation.md` §7.4.1 false for that shape. Measured at cycle 8 on one
  misconfigured tool over three examples at k=2: with no `over=` the suite stopped on the first
  rollout, and fanned out it completed and scored six. The document carries the carve-out now;
  the code does not, because adding `ConfigurationError` to the tuple `_fan_out`'s `unit`
  re-raises changes behaviour for every such error and `_fetch_policy_for` reaches the same
  path. Not taken here because it was not what the sitting decided. →
  [`plan.md` §2.1](../plan.md#L42).
- **A `docs/` example that parses, resolves and does not build.** Nothing executes one, so
  `prose_check` cannot see it. Four examples name a schema called `Verdict` and none of the
  four defines it, and three of them meant a closed decision, which FT-09 refuses without
  `allow_unknown=False`. All four build now, measured by constructing each with the schema its
  own document implies: the fourth, `docs/evaluation.md`'s labelling pass, always did, because
  a labelling judge's verdict carries an absent state and
  [`tests/test_labelling_pass.py`](../../tests/test_labelling_pass.py#L46) (`Verdict`) defines it that way
  and runs it. **A sweep of every other example against the same question is not done.** →
  [`plan.md` §1](../plan.md#L1), `P3-3`.
- **`anything_else`'s accumulated answer is prose and nothing reads its shape.** A gate can
  see that `asked_at` moved and not that a stage's answer was added beside the earlier ones.
  Destination: nothing, until a project's answers show the convention is not followed.
