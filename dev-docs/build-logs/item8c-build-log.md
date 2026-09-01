# Item 8c — build log

**Kept while building, not reconstructed at the end.** On the precedent of
`runs/checkpoint-item5/findings.md` and `runs/checkpoint-item7/findings.md`. The end-of-item report and
the shipped-document rewrites are reads of this file.

The design of record is `archive/plan-history.md` item 8c. Nothing here reopens it. §2 records where
building it sharpened a decision, §3 where it turned out not to hold, and §4 what the build
found that is nobody's design.

**Status: built, and the shipped documents written.** 2026-08-04. Baseline 571 tests at
`705d71f`; **691 tests** now. Trajectory `0.11`, manifest `0.5`, results `0.2`.

---

## 1. Doc consequences owed

Filled at the step that made each claim false, then worked through. **All rows are done**;
the table is kept as the record of what moved and why. Every example added to `pipeline.md` was
executed against the library before it was written down, and `evaluation.md` §8.1's report block
was regenerated from a real replay rather than edited by hand.

| Document | Section | What it says now | Why that is false | What it has to say |
|---|---|---|---|---|
| `docs/pipeline.md` | title line, §1 opening | "A pipeline is a list of nodes, executed in order." | It is a directed graph; a list is the case where every node has one successor. | The graph, opening with the flattest shape that expresses the work, per item 8c. |
| `docs/pipeline.md` | §1 | "**Each node receives the previous node's output, and nothing else.**" | A node with more than one in-edge receives a `Join`; a node in a cycle receives what the back edge carried. | What a node receives is a function of its declared in-edges: one edge gives the value, more than one gives a `Join`. |
| `docs/pipeline.md` | §1 | `result.output` is "what the last node returned" | It is the output of the one node with no successors, which need not be last in the list. | Name the terminal node, and say that exactly one is required. |
| `docs/pipeline.md` | §1.1 | The four construction refusals | Nine more, and one at run time. | The full table. The messages are in `graph.py` and `nodes.py` and are already written. |
| `docs/pipeline.md` | §1.2 | "The list of nodes is fixed", and the three shapes that cover what would need a branch | The whole section is superseded. | Rewritten and retitled "Branching, joining and looping" per item 8c: `successors=`, `route=`, skips, parallel arms, `Join`, `Loop`, `on_error=`, `RetryPolicy`, composition, `to_mermaid()`, `on_progress=`. |
| `docs/pipeline.md` | §2 | The three node kinds | Still three. Each gains the five graph arguments. | A row or a sentence per argument, once, since all three take them. |
| `docs/pipeline.md` | §3 | What a node receives | Does not cover `Join`, `NodeFailure`, or an `Unknown` on an unfired single edge. | The three shapes, and `RouteContext` beside `NodeContext` and `AgentContext`. |
| `docs/pipeline.md` | §5 | Budgets | A nested pipeline's budget bounds it over what it has spent since it started, and retry attempts share one node budget. | Two sentences added; the four axes are unchanged and there is no fifth. |
| `docs/trajectory-format.md` | §3 | `termination` is a closed enum of seven values; "`outputs` is `null` only when a node errored" | Nine values now, and `outputs` is `null` on a skip too. | The two new values, the `route` and `loop` fields, and the two tagged `inputs` shapes. §3.1 of this log has the `max_iterations` rule, which is not what item 8c predicted. |
| `docs/trajectory-format.md` | §2, field tables | ~~`format_version` `0.10`~~ | **Done.** Version strings bumped to `0.11` mechanically, so the suite is green. | The field table gained `route` and `loop`. |
| `docs/evaluation.md` | §1 | The example set | `Example` gains `expected_by_node`. | One paragraph and an example. |
| `docs/evaluation.md` | §5 | "**What is reported is behaviour, not accuracy.**" | Accuracy is reported per node where the set labels one. | Rewritten: `runs`, `reached`, `reach`, `accuracy`, and why reach travels beside every other figure. |
| `docs/evaluation.md` | §8 | The results file schema | `0.2` adds four node fields, `rollouts[].nodes`, and two `config.nodes[]` fields. | The schema, and `eval_format_version` `0.2` (**version string done**). |
| `docs/evaluation.md` | §9 | Between two versions | `compare()` gains `nodes` and `moved_nodes`. | Reach and accuracy as paired differences, with the reason they are reported together. |
| `docs/failure-taxonomy.md` | FT-08 | Per-node localization; "What the library provides" | Per-node accuracy now ships, so the boundary moved: the project supplies the labels and the comparison, and the library supplies the denominator and the interval. | Redraw the boundary. This is the entry item 8c names. |
| `docs/failure-taxonomy.md` | FT-12 | Ablation | Ablating a node that does not always run is a different question, and reach is what makes it answerable. | A sentence on reach. Item 8a builds the operation. |
| `docs/failure-taxonomy.md` | FT-18 | Budget axes | No fifth axis. A cycle is bounded by a construction refusal. | Add the refusal to the list of things enforced by construction, beside the loop-without-budget one. |
| `docs/run-envelope.md` | §2 | The manifest schema, ~~`format_version` `0.4`~~ | **Version string done.** The `nodes` entry gains five keys and nested pipelines are expanded. | The five keys, and what an expanded nested pipeline looks like. |
| `docs/model-clients.md` | §4 | The vLLM serve command | Not false. A reasoning model on an open-ended prompt runs to the context window, which cost this build a recording. | A sentence on `chat_template_kwargs` through `extra`, and that `extra` is in the cassette key. |
| `docs/index.md` | one-liners | What each document covers | `pipeline.md`'s line says "the pipeline, the three node kinds". | One line. |
| `README.md` | the table | One line per document | Same. | One line. |
| `CHANGELOG.md` | Unreleased | ~~`0.10` / `0.4` / `0.1`~~ | **Done.** | Written, with what each break costs a project. |

Rows are added for anything the build touches that item 8c's list does not name; `pipeline.md`
§2 and §5, `evaluation.md` §9, and `model-clients.md` §4 are those.

---

## 2. What building it changed about the design

### 2.1 The seven construction refusals are nine, and both additions are mirrors

Item 8c names seven. Two more are needed for the scheduler to be well defined, and each is the
mirror of one already on the list:

- **A `Loop` on a node that closes no cycle**, the mirror of "a cycle with no `loop=`". Without
  it, `Loop(then=)` has no cycle to be checked against and the declaration is silently inert.
- **No node with no successors**, the mirror of "more than one node with no successors". The
  refusal exists for the same reason: `result.output` is the terminal node's output, so the run
  needs exactly one, and "exactly one" is two checks rather than one.

### 2.2 Back edges are found by depth-first search, not by reachability

The first implementation asked "which of this node's successors can reach it again", which is
wrong as soon as two loops nest. With

```
start -> a -> b -> {a, c},  b: Loop(2, then="c")
              c -> {a, end}, c: Loop(3, then="end")
```

`c` can reach `b` through the *outer* loop's own back edge, so `b`'s forward exit read as a
second back edge and `b`'s cycle body swallowed `c`. `Loop(then="c")` was then refused for
naming a node inside the cycle it bounds, which is a legitimate nested loop refused.

A depth-first back edge is an edge pointing at a node on the current path, which is the
property actually wanted, and each cycle body is measured over the graph with every back edge
removed. This also **replaced the "cycle with no `loop=`" check with a stronger one**: a back
edge leaving a node that declares no `Loop` *is* the unbounded cycle, so the refusal names the
cycle it found rather than scanning for one separately. Locked down by
`tests/test_graph.py::TestCycles::test_the_innermost_cycle_is_the_smaller_one`.

### 2.3 `visit` did not earn its place as an integer, and `loop` did

The brief asked whether `visit` earns its place once the scheduler exists. As a bare count it
does not: outside a cycle it is always 1, which is noise on every record, and inside one it has
two readings, the executions of this node in this run and the iteration since the cycle was
entered. Only the second is undecidable from the file, because the counter resets per entry.

What ships is a `loop` object, `null` for a node in no cycle:

```json
"loop": {"node_id": "critique", "iteration": 3, "max_iterations": 3, "exhausted": true}
```

`node_id` names the loop the iteration belongs to, which matters under nesting where a node is
inside two. `exhausted` is stated rather than inferred, for the reason given in §3.1.

### 2.4 An `on_error` target is an edge everywhere except in routing

Reachability, cycle detection and the terminal check all count it. Only route selection does
not, so a node with one successor and a handler declares no route and is not refused for having
two edges. That makes an error handler an ordinary node: it is skipped on a run where nothing
failed, because its one in-edge resolved absent.

---

### 2.5 A join tells "did not fire" from "answered absence" by a flag, not by the value

Item 8c settles that a join delivers `Unknown` on an edge that did not fire. That collides with
`unknown` being a first-class **value**: a node whose own answer is that the information is not
there returns an `Unknown`, and its edge fired.

So the scheduler tracks whether an edge fired apart from what it carried, and `Join.absent`
reads the flag. `Join.fired` and the skip decision read it too; testing the value would read a
reported absence as a branch that never ran, which is the failure FT-10 is about arriving by a
new route. The delivered value is still an `Unknown` carrying a reason, as 8c says, so nothing
about the call site changes. `Join`'s docstring says which test to use and why.

Locked down by
`tests/test_graph_execution.py::TestJoin::test_a_node_that_answered_absence_still_fires_its_edge`.

### 2.6 `prompt_version()` is `source_version()`

A route decides which nodes run at all, so an edit to one moves numbers the way a prompt edit
does and FT-15 should see it the same way. The manifest and `config.nodes[]` record a route's
version through the function that already derives a prompt's, which is now named for what it
does. The `prompt_version=` argument on a node is unchanged.

---

## 3. What in item 8c turned out to be wrong

### 3.1 `termination: "max_iterations"` cannot always be set, and `loop.exhausted` is why

Item 8c says the final iteration's record carries `termination: "max_iterations"`. That holds
for a `Deterministic` or `LLMNode` closing a cycle, whose `termination` was `null`. It cannot
hold for an `AgentNode`, which always sets its own: `finish`, `finish_rejected`, or a budget
axis. One execution would have two true answers in one field, and overwriting `finish` loses
why the node's own loop stopped.

**What ships:** the node's own reason wins where it has one, `max_iterations` is set where the
node has none, and `loop.exhausted` is the authoritative signal in both cases. A reader asking
"did the cycle run out" reads `loop.exhausted` and never has to know which kind closed it.

This is the only place item 8c did not hold as written. The rule it states is right for two of
the three node kinds, and the third needed the field the answer to §2.3 was already adding.

### 3.2 The seven refusals are nine

Recorded as a design change in §2.1 rather than an error in 8c: both additions are mirrors of
refusals it names, and neither was reachable from the design without building the scheduler.

---

## 4. Findings

### 4.1 The order of the graph refusals decides which one a reader sees, and one was dead

`_terminal`'s "every node names a successor, so no node ends the run" was unreachable behind
the `Loop(then=)` checks: every graph with no terminal node that also passes the earlier checks
has some loop whose `then` re-enters its own cycle, so the `then` refusal always fired first.
Two nodes pointing at each other reported that `then` was inside the cycle, which is the same
fault seen from inside and gives a reader nothing to act on.

Reachability and the terminal check now run before the `Loop` checks. The `then` refusals still
fire for every graph that reaches them.

**Found by writing the test for the refusal and watching it fail against the wrong message.**

### 4.2 The refusal mutation pass

All sixteen refusals added so far were disabled one at a time and their tests re-run. Every one
failed with its check removed, so none is shadowed by an earlier refusal and none passes
vacuously. The script is throwaway; what it proved is recorded here.

### 4.3 `prose_check` runs over `tests/`, and bans the phrase this project uses for this

"broken deliberately once" trips the `DEFENSIVE` list on `deliberately`. The test docstring says
"broken once, and watched to fail" instead. No rule was weakened.

### 4.4 Existing tests that had to change, and why each is a declared consequence

Four assertions, all of them the format bumps landing where they should. None is a behaviour
break, and nothing else in the suite needed touching.

| Test | What changed |
|---|---|
| `test_run_envelope.py::test_it_records_the_node_shape_and_the_unknown_waivers` | A manifest `nodes` entry gains five keys. Manifest `0.5`. |
| `test_run_envelope.py::test_it_names_the_trajectory_it_belongs_to` | `trajectory_format_version` is `0.11`. |
| `test_eval_runner.py::test_the_config_says_what_was_measured` | `config.nodes[]` gains `successors` and `route`. Results `0.2`. |
| `test_trajectory_conformance.py::test_format_version_is_declared_on_every_record` | `0.10` becomes `0.11`. |

**The whole suite passed with the executor replaced before any of the graph features were
added**, which is the checkpoint that says every existing pipeline keeps its meaning. 571 tests
green against a scheduler that resolves edges, with every node taking the default successor of
the next in the list.

### 4.5 The trajectory conformance check catches drift in one direction only

`tests/test_trajectory_conformance.py` transcribes each record type's fields from the document
and asserts `NODE_FIELDS - record.keys()` is empty. That catches a field the document names and
the writer dropped. It does not catch the reverse: `route` and `loop` were added to every
`node_execution` record and the check stayed green with the document naming neither.

Same shape as the `§n` renumber hole found at the run-envelope sitting: the check verifies one
direction of a correspondence that has to hold both ways. **The fix is one character per
record type**, `-` to `^`, making it a symmetric difference, and it belongs at the doc sitting
because it fails until §3's field table gains the two fields. Recorded here so it is not
forgotten, since the check passing is what would otherwise let it be.

### 4.6 Two live-backend observations a fake client would not have produced

**Mistral reasoned out an answer and reported `unknown` anyway.** The first `graph` recording
had the classify node answer `unknown` to "Which retailer ships from Leeds?" with the reason
"The notes mention that 'Kirkwall ships from Leeds', but no other retailer is stated to ship
from Leeds." The route read that as absence and skipped three nodes, so the recording covered
the skip twice and the parallel branch not at all. The prompt now says to report `unknown` only
when nothing in the notes bears on the question, and both paths record.

**Qwen3-1.7B put the word "unknown" in the string field.** On the vLLM recording it answered
the literal string `"unknown"` rather than the tagged object, so `isinstance(answer, Unknown)`
was false and the route took the found path for a question the notes do not answer. That is the
failure `Maybe`'s field description exists to prevent ("Send the object, not the word
'unknown'"), observed on a real backend. The vLLM replay test asserts what that backend did
rather than what the larger one did, and says so.

**A third, on cost rather than correctness:** Qwen3 emits a reasoning chain, and on open-ended
prompts one call ran for over four minutes without finishing. The recording passes
`extra={"chat_template_kwargs": {"enable_thinking": False}}` for vLLM only, which is what
`extra` is for. The Mistral recording carries no `extra`, so the two cassettes are keyed
differently and each test constructs the pipeline the way its recording did.

Existing tests or behaviour that had to change, and any live bug the build exposed. Kept
apart from §2 and §3 so nothing is quietly folded into a design note.

*(appended as it happens)*


---

## 5. The shipped-document pass

Written 2026-08-04, straight after the build. `uv build` was re-run, since the wheel
force-includes `docs/`.

### 5.1 What moved

`pipeline.md` is the bulk: §1's edge rule, `result.output` naming the terminal node, §1.1's
refusal table going from four rows to thirteen plus two run-time, and §1.2 rewritten and
retitled "Branching, joining and looping" with §1.3 to §1.7 under it for joins, cycles, errors
and retries, composition, and rendering. §2 gained one sentence saying all three kinds take the
same five graph arguments. §3 gained the four input shapes and `RouteContext`. §5 gained the
retry and nesting rules and the statement that no axis bounds a cycle.

`trajectory-format.md` §3 gained `route` and `loop` in the field table, the nine-value
`termination`, and three new subsections: §3.2 what `inputs` holds, §3.3 the `loop` object, §3.4
what a fan-out records. `run-envelope.md` gained §2.5, the declared edges. `evaluation.md`
gained `expected_by_node` in §1, reach and per-node accuracy as §5.1 and §5.2, and per-node
comparison in §9. `failure-taxonomy.md` FT-08 redrew its boundary now that per-node accuracy
ships, FT-12 gained the reach caveat, FT-18 gained the cycle refusal. `model-clients.md` §4
gained the reasoning-model note. `index.md` and the README each gained two one-liners.

### 5.2 Findings from the pass

**`evaluation.md` §8.1's report example had been stale since 2026-08-02.** It showed accuracy
88.9%, 20 model calls on `hunt`, and `correct 5, missed 1`. The eval cassette was re-recorded at
the tools sitting, when the docstring change altered what the agent answered, and the block was
never regenerated. The real numbers are 44.4%, 18 calls, and `correct 1, missed 5`.

Checked against `HEAD` before changing it, by stashing this item's source changes and replaying
the same cassette: `HEAD` produces the same figures this item does, so the drift is the tools
sitting's and not this one's. **The same hole as the renumbering ones: a worked example in a
document is a claim about the code that nothing checks.** Regenerating from a replay rather than
editing by hand is what closed it here, and it is cheap to repeat, because the cassette makes it
a function with no network in it.

**The fan-out record kept a shape the API had already been fixed for.** Raised by Thilina while
reading the §3 field table. `FanOutResult.values`, the Python property, was removed at trajectory
`0.10` for returning a list of successes that mispairs against the input sequence. The record
kept exactly that: `{"items": 3, "values": ["A", "C"], "failures": [{"index": 1, ...}]}`. It is
now one entry per input item in input order, each carrying `value` or `error`. Folded into `0.11`
at his call, since the bump was already breaking.

**Defensive prose went in and had to be taken out again.** Eight passages, all the same shape:
a clause explaining why the alternative design would be worse, to a reader who had not proposed
it. "A list holding the successes alone would be shorter than the input sequence, so pairing it
back against the inputs would mispair them" is the one he caught; the other seven were mine to
find once he named it. **The tell is that the sentence answers "why is it not X" rather than
"what happens to me".** `prose_check` passes all eight, and the `CLAUDE.md` rule says so: this
is the one judgement call a check cannot make.

### 5.3 The conformance check that only fired one way, now closed

§4.5 recorded that `NODE_FIELDS - record.keys()` catches a field the document names and the
writer dropped, and not the reverse. Now that §3's table names `route` and `loop`, the check is
a symmetric difference. Broken once in each direction to prove it: a field added to the document
alone fails, and a field added to the writer alone fails.
