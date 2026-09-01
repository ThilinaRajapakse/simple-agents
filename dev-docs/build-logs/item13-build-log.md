# Item 13 — build log

**Kept while building, not reconstructed at the end.** On the precedent of `item10-build-log.md`,
`item8b-build-log.md`, `item8g-build-log.md`, `item9-build-log.md` and `item8a-build-log.md`.

The design of record is `archive/plan-history.md` §3.1 item 13, which is one line: "Tool-authoring guide."
`simple-agents.md` §8.4 adds that it should be written "immediately after the failure taxonomy
and trajectory format", which was true when nothing else existed.

§1 records what was measured before the sitting, §2 the sitting, §3 where building sharpened a
decision, §4 where it turned out not to hold, §5 what the build found that is nobody's design,
§6 doc consequences, §7 existing tests that had to change.

**Status: sitting held 2026-08-06, building. Baseline 1072 tests at `16f68e3`.**

**The hypothesis this item tests before designing anything:** `docs/tools.md` shipped at item 7
with six sections and has been through Thilina's review. It may already be the tool-authoring
guide, in which case this item is a gap to name rather than a document to write.

---

## 1. What was measured, before any design

Item 10 §1 is the standard: every claim is read off a file the library produced, off a live run,
or off an artifact a cold session wrote. The entry is one line, so §1 is aimed at the hypothesis
instead: what does a coding agent writing a tool against `docs/tools.md` actually get wrong?

The best evidence available is `runs/checkpoint-item7/findings.md`, where two cold-read sessions wrote
tools against exactly that document, and their snapshots survive at
`~/checkpoint-answers/session-*-snapshot/`. **The contract-test section was in the document they
read**: `git show dad8fa0:docs/tools.md` carries §6 "What a contract test asserts" with the same
four assertions the shipped §6 has today, committed 2026-07-27, before either session ran.

The probes are `scratchpad/item13/probe_ft23.py`, `probe_tool_artifacts.py`,
`probe_tool_version.py` and `probe_version_options.py`, plus
`scratchpad/probe_shipped_descriptions.py`. Both session snapshots are unpacked at
`scratchpad/item13/s1` and `s2`.

### 1.1 Both cold sessions wrote good tools, and both wrote contract tests nothing asked them to

Session 1 declared `lookup_title`; session 2 declared `lookup_title` and its own
`document_search`. All three carry a side-effect class, a model-facing docstring of 180 to 225
words, and a `version=` parameter. Both sessions wrote a test file exercising every tool they
declared.

**Both independently invented the same convention: the sentence of the description under test is
quoted into the test's own docstring.** Neither `docs/tools.md` §6 nor anything else asks for
this.

```python
def test_lookup_title_returns_empty_rather_than_raising():
    """"Returns an empty list when no title matches." Finding nothing is a result, not an
    error: the loop records a raise in the record's error field, which would misfile a
    successful lookup."""
```

```python
def test_returns_every_entry_filed_under_the_title(lookup):
    """"the entries filed under that title ... they all come back together"."""
```

Against `docs/tools.md` §6's four assertions: both cover the result shape, both cover the
boundary, both assert the schema the model is offered and that no handle appears in it. **Neither
covers the failure the description says can happen, because neither tool raises.**

### 1.2 The evidence covers one clause of the contract's six

What the two sessions exercised, read off their source rather than off their reports:

| Clause of `docs/tools.md` §1 | Exercised |
|---|---|
| 1, the derived schema | Yes, by both |
| 2, the description | Yes, by both |
| 3, how failures are signalled | **No. Neither tool raises `ModelFacingError` or `CallerFacingError`** |
| 4, the side-effect class | Only `READ_ONLY`. No `writes`, `spends_money` or `irreversible` |
| 5, declared cost | **No. Not required on a read-only tool, so neither declared one** |
| 6, a contract test | Yes, by both |

`ModelHandle`, `Workspace`, `SecretStr` and the `parameters=` escape hatch were reached by
neither, which `runs/checkpoint-item7/findings.md` §7 already records for the two handles. **So the
checkpoint tells us that the read-only-retrieval corner of the contract works, and says nothing
about the other five-sixths.** Any claim that `docs/tools.md` is already the tool-authoring guide
rests on that corner.

### 1.3 A changed tool answers with the old value on replay, and nothing says so

`probe_tool_version.py`. A tool named `price_of` returns `£40`; the run is recorded. The
implementation is edited to return `£55`, with the name and the version unchanged, and the run
is replayed against the same cassette.

| | What the trajectory records |
|---|---|
| live, tool returns `£40` | `'£40'`, `replayed=False` |
| **replay, tool now returns `£55`** | **`'£40'`, `replayed=True`** |
| replay, version bumped to `"2"` | `CassetteMiss`, naming the re-record command |

**A run reports a price the current code does not produce, and the trajectory says the tool was
called.** Bumping the version is what turns it into a loud miss, and `version=` is the author's
only control over it.

**`docs/tools.md` names `version` once**, in §3.1's sentence listing what a tool call is keyed on.
No shipped document says what it is for, when to change it, or what happens when it is left
alone. By contrast `docs/run-envelope.md` §1 gives `prompt_version` a paragraph, and a prompt
that declares none gets one **derived from the function's source** by `manifest.source_version`,
so the model-call side of this failure is closed by construction and the tool side is left to a
declaration nobody is told about.

### 1.4 The obvious fix is half a fix, and the objection to it is already false

`probe_version_options.py` prices deriving a tool's version from its source, the way prompts
already work.

| Edit | What happens today |
|---|---|
| only the description changes | **`CassetteMiss` already**, through the model call, whose key holds the description |
| only the closed-over data changes | `'£40'` returned, `replayed=True`, silent |

So the objection that a source-derived version would force re-recording on a docstring edit is
false: **a docstring edit already forces one**, because the description is in every model call's
key. And the fix is partial rather than complete: `inspect.getsource` is byte-identical for the
two tools above, because what changed was a dict the closure captured. Both cold sessions' tools
close over a corpus, so both are that shape.

### 1.5 The registry is invisible to every artifact a check reads

`probe_tool_artifacts.py`. A project holds `ToolRegistry([used_by_a_node, registered_but_unused])`
and gives one node `[registry.get("used_by_a_node")]`. The manifest lists **one** tool, and is
byte-identical to the manifest of a project holding a plain list.

`simple-agents.md` §8.3 gives the registry's reason for existing as the static checks FT-19 and
FT-23 needing "somewhere to enumerate *every declared tool*, including one no node uses yet".
`Pipeline._node_entries` walks `node.tools`, and `ToolRegistry.to_manifest` has no caller in
`src/`. **The thing the registry was built to provide reaches no artifact.**

### 1.6 A tool's description is in the manifest, and it got there for another reason

The same probe, reading `manifest.schemas`:

```
sha256:12658b65286d7977: [{"name": "used_by_a_node",
  "description": "Search the catalogue. Returns matching items, or an empty string.",
  "input_schema": {...}}]
```

Item 8b added the register so a trajectory would stop re-writing the tool block on every call
(`item8b-build-log.md` §3.2). The effect is that **the text FT-23 is about is now an artifact**,
for any run written by trajectory format `0.15` or later. Neither cold session's runs carry it;
they predate the register by ten days.

### 1.7 FT-23's declared surface is `static`, and a static read gets the name wrong for all eight shipped tools

`probe_ft23.py` walks every project on this machine for `@tool` decorators and compares what it
finds against the manifest.

| Project | Tools in the manifest | Tools an AST walk finds |
|---|---|---|
| session 1 | 2 | **1** |
| session 2 | 2 | 2 |
| item 10's trivial agent | 1 | **0** |
| eleven conformance fixtures | 1 each | **0 each** |

Two mechanisms, both structural:

- **A project using a built-in has no `@tool` in its own source.** Session 1 used the library's
  `document_search`, and the trivial agent and all eleven fixtures use built-ins only.
- **Every one of the eight built-ins passes `name=` a variable.** The decorated functions are
  called `search`, `read`, `write`, `clock`, `fetch`, `listing`, `extract` and `ask_the_user`;
  the names the model sees are `document_search`, `workspace_read`, `workspace_write`, `now`,
  `http_fetch`, `workspace_list`, `extract_facts` and `consult`. **An AST walk reads the wrong
  name for every shipped tool**, and both cold sessions used the same factory shape.

### 1.8 Nothing records that a contract test exists, and matching on the name does not stand in for it

No artifact carries it, so the other half of FT-23 reads source whatever the first half does.
Matching a tool's name against the project's test files, measured on the library:

| Tool | Test files naming it | Contract tests among them |
|---|---|---|
| `now` | 8 | 1 |
| `search` | 9 | 1 |
| `read` | 19 | 1 |
| `write` | 12 | 1 |
| `document_search` | 3 | 1 |
| `http_fetch` | 1 | 1 |

The precision is a function of how common the tool's name is as an English word. **A project
would pass FT-23 by naming its tool `read` and never testing it, and fail by naming it
`fetch_supplier_page` and testing it through a fixture variable.**

### 1.9 Eleven fixtures and the trivial agent declare a tool and hold no test file at all

`probe_ft23.py`'s third column. Every conformance fixture and item 10's trivial agent have zero
files under a `tests/` path. **An FT-23 check at tier `prototype` fails all twelve**, including
the project item 10 built to measure what a passing project looks like.

### 1.10 The failure that actually happened is one a contract test passes

`runs/checkpoint-item7/findings.md` §4's D5. Session 2's `document_search` docstring told the model
that if the top hits are not what it wanted, "the collection does not cover that subject". The
tool did exactly what the description said. **A contract test asserting the described behaviour
passes**, and session 2 wrote one that does.

What was wrong is that the description teaches the model an inference the tool cannot support: a
lexical retriever finding nothing has established that these words did not reach a passage, not
that the collection lacks the fact. It was caught by Thilina reading the text.

**FT-23's premise is that the contract test is what catches a description that has drifted from
the behaviour.** That is true of drift and false of a description that is faithful to the code
and wrong about the world, which is the one instance on record.

### 1.11 The shipped descriptions are written for the model, and no parameter carries one

`scratchpad/probe_shipped_descriptions.py` prints `Tool.to_wire()` for all nine built-in
factories. Mean 54 words, 484 in total when every one is registered. Eight of nine say what comes
back; seven say when not to reach for the tool; three name a failure.

**No parameter of any shipped tool carries a `description` in its JSON schema.** `document_search`
offers `top_k` as a bare integer with a default. `docs/tools.md` §1.1 tells an author that
"a description anywhere in that schema is prompt text: `Field(description=...)` on a parameter",
and the library's own eight tools demonstrate it nowhere.

### 1.12 No elicitation question reaches a tool, and no stage boundary is where one is written

The sixteen questions of `conformance/elicitation.py` are `ground_truth`, `answer_form`,
`absence_vs_error`, `agency_boundary`, `consultation`, `backend`, `budget`, `unproven_answer`,
`unknown_literal`, `context_limit`, `rerun_cost`, `reproduce`, `who_labels`, `improvement`,
`leakage` and `prices`. **None asks what the agent may do to the world**, which is the
side-effect class, and the class is what FT-20 reads to refuse an evaluation.

`docs/procedure.md` names `docs/tools.md` once, in one clause of stage `build`: "`docs/tools.md`
covers the tool contract and the built-in set". Writing a tool is inside `build` and has no gate
of its own, which §1.1 of `item10-build-log.md` already measured as unobservable: writing the
agent changed nothing in the report.

### 1.13 No tool on this machine has ever recorded a version, and a built guard is waiting on one

Every `manifest.json` under the two session snapshots, the eleven fixtures, item 10's trivial
agent and the library's own `runs/`: **13 distinct tool entries, and `version` is `null` on all
13.** Neither cold session passed one, though both wrote a `version` parameter into their
factories.

`pipeline.py:533` already compares `tools.<name>.version` between a suspended run and the one
resuming it, and refuses an unwaived change with a message naming what moved. **That guard has
never fired and cannot fire**, because the value it compares is `None` on both sides for every
tool anyone has written.

### 1.14 Seven of twenty-eight entries have a check, and all seven are `artifact`

| | Entries | With a check |
|---|---|---|
| all | 28 | 7 |
| tier `prototype` | 15 | 3 |

By surface: 15 `artifact`, 3 `static + artifact`, 2 `static`, and the rest runtime or enforced.
**No `static`-surface check has ever been built.** FT-23 is one of the two pure-`static` entries,
and the other is FT-09, which the library enforces by refusing to construct the schema.

So FT-23 having no check is the ordinary case rather than an exception. What is specific to it is
that the surface it declares has never been implemented for anything.

### 1.15 A tool called at a fixed point is invisible to everything the tool contract is for

Measured after Thilina asked whether a `Deterministic` node can just call a tool
(`probe_tool_at_a_fixed_point.py`). It can: the body is plain Python and nothing stops it.

```python
@tool(side_effect_class=SideEffectClass.SPENDS_MONEY,
      declared_cost=DeclaredCost(currency="GBP", per_call=40.0))
def charge_the_card(amount: str) -> str: ...

def step(inputs, ctx):
    return {"receipt": charge_the_card.fn(amount=inputs["amount"])}
```

| | |
|---|---|
| the tool ran | once, charging £40 |
| `tool_call` records | **0** |
| record types written | `['node_execution']` |
| `manifest.tools` | **`[]`** |
| cassette file after `Cassette.record(path)` | **never created** |

The charge survives only as `outputs: {"receipt": "txn-1"}` inside a node record. No side-effect
class, no declared cost, no cassette key, so no replay; and the eval runner enumerates the tools
nodes were given, so FT-20 has nothing to refuse.

**The whole tool contract is reachable only from inside an `AgentNode`**, so a builder who knows
a call has to happen at a known point either pays a model call to decide something already
decided or writes the code above.

`Deterministic`'s docstring says its context "carries no model client and no tools", which reads
as a refusal and is a description of what is not supplied. **Filed as a defect.**

### 1.16 Four API errors were made writing the probes, none of them about tools

Recorded against the maintainer on the item 10 §1.10 precedent. `Budget(max_steps=2)` (three
further arguments are required and have no defaults), `RunEnvelope` used as a context manager,
a prompt function written `(ctx)` rather than `(inputs, ctx)`, and `FakeModelClient` given
dicts rather than `fake_response(...)`. **All four were refused at construction or raised
immediately**, and two of the refusals named the exact call that fixes them. The tool surface
produced no error at all in the same sitting.

---

## 2. The sitting, and what it settled

Held 2026-08-06, after §1's measurements. Six questions were put. Two were sent back: Q2 was
put unintelligibly and re-presented (§2.2), and Q5 was argued from a rule rather than from the
situation and re-argued (§2.5).

**The entry's framing did not survive §1 and the item did.** `docs/tools.md` is the
tool-authoring guide, so nothing here writes a thirteenth document. What §1 found instead is a
silent wrong-answer defect, a guard that has never fired, and a contract that is reachable from
one node kind out of three.

### 2.1 A tool's version is derived from its source, and the document says what that misses

**Settled: both. Document `version`, and derive it from the function's source where the author
declares none, as `manifest.source_version` already does for prompts.**

§1.3 measured a changed tool replaying `£40` when the code returns `£55`, with
`replayed=True` in the trajectory. §1.13 measured that `version` is `null` on all 13 tool
entries anywhere on this machine, and that `pipeline.py:533`'s resume guard on
`tools.<name>.version` therefore cannot fire.

The objection that a derived version would force re-recording on a docstring edit was measured
and is false: **a docstring edit already raises `CassetteMiss`**, through the model call, whose
key holds the description (§1.4).

**Thilina's ruling on what it misses:** a change to data the tool closes over is not caught, and
that is not the library's problem. The document states the bound rather than implying more.

### 2.2 FT-23 is kept and narrowed, and no check is built for it

**Settled after the question was put badly and re-put.** The first presentation was
unintelligible and was withdrawn.

No check ships. §1.7 measured that the surface FT-23 declares reads the wrong tool name for all
eight shipped tools and finds none at all in twelve of the fourteen projects on this machine;
§1.8 measured that the only remaining signal for "a contract test exists" matches 8 test files
for `now` and 19 for `read`; §1.9 measured that shipping it fails all eleven fixtures and item
10's trivial agent.

**What decided the shape is that the entry is cited at eight live sites and two of them are
error messages that fire today.** Its first half, the description as prompt text, is enforced at
registration. Its second half is not checkable by anything. So the entry is narrowed to the half
that is real, and the contract test stays as stated practice with §1.10's bound written down:
it catches drift between a description and the code, and does not catch a description faithful
to the code and wrong about the world.

Removing the entry was live and was declined. `docs/failure-taxonomy.md` says IDs are permanent,
and 20 other entries have no check either.

**The inner names are left alone.** Each built-in is a factory passing `name=` a variable so two
searches over different corpora do not collide, and the only reader that sees `search` rather
than `document_search` is something reading source text, which is the check not being built.

### 2.3 One required question at `build`, on what the agent may do to the world

**Settled.** §1.12 measured that none of the sixteen questions reaches a tool, and the
side-effect class is what FT-20 reads to refuse an evaluation. Today the builder meets that
decision as a refusal at the evaluation gate rather than as a question, which is
`runs/checkpoint-item5/findings.md` §7's wall.

Required rather than optional: the scaffold lists the tools the agent will be given with the
class each declares, so it is answerable cold, which is item 10 §2.2's condition. FT-24 enforces
it with no new check.

### 2.4 The four `docs/tools.md` edits are taken

**Settled: all four**, presented as diffs rather than made, since the document is signed off. The
§6 one is contingent on §2.2 and is now unblocked.

### 2.5 A tool call at a fixed point, as `tools=` on `Deterministic`

**Settled: option (a).** `Deterministic(fn, tools=[...])` with `ctx.call_tool(name, **arguments)`
in the body, rather than a fourth node kind.

**The first presentation cited `simple-agents.md` §9.12 as a reason to fence this off, and
Thilina rejected the citation rather than the conclusion:** a rule recorded earlier is evidence
about what was known then. Re-argued from §1.15, the case is that the second-best option
available to a builder today writes a £40 charge into a trajectory as an opaque string.

Why the node argument rather than a fourth kind: a fixed sequence is usually several calls with
logic between them, which one node expresses and three nodes do not; and the tools go on the
node rather than being reached as globals because that is what lets the eval runner enumerate
them and refuse a `spends_money` rollout.

**What makes it cheap:** `RunContext.call_tool` and `nodes._run_tool` are already generic and
key the occurrence counter per `node_id`, so the cassette key, the record, the manifest entry
and the resume guard come free. A tool call charges no step, since `budget.py` defines one step
as one model call.

**Thilina's ruling on the handle:** a tool taking a `ModelHandle` is refused on a `Deterministic`
node. The guarantee that the node kind makes no model call is load-bearing, and FT-07's check
reads it: a `deterministic` node is treated as one that does not sample.

### 2.6 The manifest records every registered tool, and §8.3 stops being wrong

**Settled, as part of §2.5 rather than on its own.** §1.5 measured that a project holding a
registry produces a manifest byte-identical to one holding a plain list, so
`simple-agents.md` §8.3's stated reason for the registry existing reaches no artifact.

The honest accounting was put and accepted: **this does not fix FT-23**, whose missing half is
the contract test rather than the enumeration. What it fixes is that §8.3 claims a capability
that does not exist, and that §2.3's new question has no artifact to read its scaffold off. On
its own the format bump was not worth it; with §2.5 the registry becomes the one place a
project's whole tool surface is stated.

### 2.7 Scope

`docs/evaluation.md` **is** touched this time, on Thilina's instruction, which reverses the
precedent items 8g, 8b and 10 each set: "If something needs to go into evaluation.md, do it.
I'll review when I review." Two things item 10 left open are in scope with it: FT-13's fixed
message text, and the sentence on how an evaluation names its run directory.


---

## 3. What building it changed about the design

### 3.1 The fixed-point caller is a node argument and a context method, and the record path was already there

§2.5 settled `Deterministic(fn, tools=[...])` with `ctx.call_tool`. Building it confirmed the
sizing given at the sitting: `nodes._run_tool` and `RunContext.call_tool` took `run`,
`parent_id`, `node_id` and `tool` already, and the occurrence counter that makes a tool's
cassette key work is keyed per `node_id`. **Nothing in the recording, keying or replay path
changed.** What was added is a lookup by name, a `Workspace` handle fill, and one re-raise.

The re-raise is the one behavioural difference from an `AgentNode`'s call. `_run_tool` returns a
`ModelFacingError` as `outcome.error` for the loop to hand to the model. At a fixed point there
is no model, so `ctx.call_tool` raises it. The record is written either way, carrying
`error.class == "model_facing"`.

### 3.2 A node entry records its tools whatever its kind

`_node_entries` set `entry["tools"]` inside the branch that runs for a node which can call a
model, so a `Deterministic` node with tools would have recorded none. Moved out of the branch.
The manifest's per-node `tools` is now the tools any node was given.

### 3.3 A run whose only tool takes a handle writes no cassette file

Found writing the workspace test, which recorded and then replayed. `Cassette.record` had
nothing to store: a handle-taking tool is re-run rather than filed, and the pipeline made no
model call, so the file was never created and the replay refused with the message that says so.

The test asserts the property that matters without a cassette: **two runs each wrote
`receipt.txt` into their own fresh workspace**, which is what re-running rather than serving a
stored value buys.

---

## 4. What in the settled design turned out to be wrong

### 4.1 Fifteen guards, disabled one at a time, and the one that stayed quiet was the test

Fourteen of fifteen failed the test named against them on the first pass. The quiet one is item
8g §4.1's shape a sixth time: **the test could not observe the guard.**

| Disabled | Why the test still passed | What it was |
|---|---|---|
| `derived_version` hashing the source rather than the name | the fixture's two functions were called `one` and `two`, so a hash over `fn.__name__` also differed | a test that never separated the two |

The fixture is now two functions **sharing the name `price_of`** and differing in their bodies,
with an assertion that the names are equal so the separation cannot quietly disappear again.
**15 of 15 fire.**

The pass ran each case with `PYTHONDONTWRITEBYTECODE=1` and cleared every `__pycache__` after
restoring, per item 8g §4.2. `scratchpad/guard_pass_item13.py` is the script.

---

## 5. Findings

### 5.1 Deriving a tool's version invalidated every cassette holding a tool call, and that is the feature working

Six cassettes were re-recorded live: `agent`, `tools`, `eval` and `suspend` against Mistral
`mistral-small-2603`, and `tools-vllm` and `suspend-vllm` against a local vLLM serving
`Qwen/Qwen3-1.7B` on port 8001. Every one of them missed before re-recording, which is §1.3's
silent stale replay becoming loud.

### 5.2 Six tests transcribe numbers a live recording produced, so any re-recording moves them

`TestEvaluation` in `test_adapter_integration.py` asserts what the committed evaluation
recording contains. Re-recording it against the same model at the same seed and
`temperature=0.0` produced different numbers:

| | Before | After |
|---|---|---|
| accuracy | 5/9 | **7/9** |
| recall | 2/6 | **4/6** |
| `hunt` tool calls | 22 | **19** |
| model-call cassette entries | 31 | **28** |
| tool-call cassette entries | 5 | **4** |
| e1 and e2 across three rollouts | `missed, missed, correct` | **`missed, correct, correct`** |

**The claim each test makes survived and the literal in it did not.** The point of the third row
is that one example answers differently across rollouts at a fixed seed, and it still does. This
is `docs/run-envelope.md` §5's best-effort seed measured again, on a re-recording nobody made to
test it.

### 5.3 A `Deterministic` node with tools still records itself as making no model call

Pinned by a test rather than assumed, because FT-07 reads it: the node record carries
`node_kind: "deterministic"` and `seed: null`, and no `model_call` record is written. The
`ModelHandle` refusal at construction is what keeps that true.

---

## 6. Doc consequences

Written after the build.

| Document | What it said | What it says now |
|---|---|---|
| `docs/failure-taxonomy.md` FT-23 | "Tool description written for a human; no contract test", surface `static`, with a check over every registered tool's tests | "Tool description written for a human", surface `static (enforced at registration)`. A new paragraph on what a contract test does not catch, with D5 as the instance. The failure message is about the description |
| `docs/failure-taxonomy.md` FT-13 | the message ended "Run the agent inside the run envelope, which records by construction" | "A run inside the run envelope records by construction; the reason above says whether one was found and where" |
| `docs/failure-taxonomy.md` index | FT-23's row | the narrowed name and surface |
| `docs/run-envelope.md` §2 | manifest `0.10` | `0.11` |
| `docs/run-envelope.md` §2.1 | the `tools` row's five keys | Six, with what `offered` means and where it comes from |
| `docs/evaluation.md` §6.1 | the run directory under `<run_dir>/<eval_id>/`, with no claim about the name | What `eval_id` derives from, that a repeated evaluation overwrites as a repeated run already does, and why the prompt versions are in it |
| `docs/procedure.md`, stage `build` | the three node kinds against `agency_boundary` | Plus: a step that has to call a tool but chooses nothing is `Deterministic(fn, tools=[...])` |
| `CHANGELOG.md` | Unreleased | The fixed-point call, the derived version and what it costs a cassette, manifest `0.11`, the `tool_effects` question, and the two taxonomy changes |

**Presented rather than made**, since the document is signed off: four edits to `docs/tools.md`,
at §7 of this log.

**Not touched.** `docs/pipeline.md`, `docs/context.md`, `docs/trajectory-format.md`,
`docs/conformance.md`, `docs/index.md`, the model-client pages and the README own nothing this
item changed. `docs/evaluation.md` **was** touched, on Thilina's instruction at §2.7, which
reverses the precedent items 8g, 8b and 10 each set.

**One format moved.** Manifest `0.10` to `0.11`. Trajectory `0.15`, results `0.4`, suspension
`0.1` and variant `0.1` are untouched: a `tool_call` record's fields did not change, and a
fixed-point call writes the record that already existed.

---

## 7. Existing tests that had to change

Ten, and none is a defect in the library.

| Test | What it asserted | Why it changed |
|---|---|---|
| `test_adapter_integration.py::TestEvaluation::test_the_two_nodes_report_separately` | `hunt.tool_calls == 22` | §5.2. The recording moved |
| `TestEvaluation::test_the_same_question_answered_differently_across_rollouts` | `["missed", "missed", "correct"]` | §5.2 |
| `TestEvaluation::test_the_metrics_are_what_the_live_run_produced` | accuracy 5/9, recall 2/6 | §5.2 |
| `TestEvaluation::test_each_rollout_is_its_own_request_to_the_backend` | 31 model-call entries | §5.2 |
| `TestEvaluation::test_an_identical_tool_call_across_rollouts_is_stored_once` | 22 tool calls, 5 entries | §5.2 |
| `test_tool_contract.py::TestToolRegistry::test_the_manifest_reports_the_declarations` | `version: None` | The version is derived. It reads the shape rather than the literal now |
| `test_run_envelope.py::TestManifest::test_it_records_the_tools_and_their_side_effect_classes` | five keys per tool | Six. `offered` |
| `test_run_envelope.py::TestManifest::test_it_records_the_node_shape_and_the_unknown_waivers` | a `Deterministic` node entry of nine keys | Ten. §3.2 |
| `test_packaging.py::test_every_format_version_is_pinned_to_a_literal` | manifest `0.10` | `0.11` |
| `test_procedure.py::TestTheElicitationGate::test_an_optional_question_is_never_required` | eight required `build` names, transcribed | Nine. `tool_effects`, and item 10 §4.1 made this transcription deliberate so it would fail here |

**The eleven fixture projects were rebuilt**, since their briefs are generated from the required
question set and their manifests now carry `offered`. **Six cassettes were re-recorded** (§5.1).

**Total: 10 existing tests changed, 29 added. 1091 tests**, from 1072 at `16f68e3`.
