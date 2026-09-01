# The pipeline

A pipeline is a directed graph over three kinds of node. A list is the case where each node has one successor, and it is the shape to reach for. This document covers the graph, the three node kinds, what a node receives, the output schema a node validates against, and the budget it runs under. `docs/index.md` lists the full set of documents and what each covers.

---

## 1. A graph of nodes

```python
from pathlib import Path

from pydantic import BaseModel
from simple_agents import (
    Budget, Deterministic, LLMNode, Maybe, MistralClient, NodeContext, Pipeline,
)

class Answer(BaseModel):
    answer: Maybe[str]
    source: str | None = None

def load_docs(inputs: dict, ctx: NodeContext) -> dict:
    docs = "\n\n".join(p.read_text() for p in Path(inputs["corpus"]).glob("*.txt"))
    return {"question": inputs["question"], "docs": docs}

def build_prompt(inputs: dict, ctx: NodeContext) -> str:
    return f"Answer using only these documents.\n\n{inputs['docs']}\n\n{inputs['question']}"

pipeline = Pipeline(
    [
        Deterministic(load_docs),
        LLMNode(build_prompt, output_schema=Answer, node_id="answer"),
    ],
    budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None,
                  max_wall_clock_ms=300_000),
)

result = pipeline.run(
    {"question": "What is the inseam?", "corpus": "corpus/"},
    model=MistralClient(model="mistral-small-2603"),
)
```

**A node receives what arrives on the edges into it, and nothing else.** A node that declares no successors hands its output to the next node in the list, which is what the pipeline above does. The first node receives what was passed to `run`. A node that needs a value produced two nodes back has to be handed it: the node in between returns it as well. A node reading an input it was never given fails even though both nodes are correct.

A node with more than one edge into it receives a `Join` instead of a bare value, covered in §1.3. The shape a node receives follows the edges declared into it. The one exception is a node named as both a successor and the `on_error` handler of the same node, which is a single edge carrying either that node's output or a `NodeFailure` (§3).

**What a completed run returns:**

```python
result.output           # what the node with no successors returned
result.cost             # {"value": ..., "currency": ..., "basis": ..., "is_upper_bound": ..., "reason": ...}
result.tokens           # the token classes, summed over the run
result.outcome          # "completed"
result.seed             # the seed the run used, generated if none was passed
result.paths.manifest   # runs/<run_id>/manifest.json
result.manifest         # the whole manifest, already parsed
```

A pipeline has exactly one node with no successors, and its output is the run's. In a list that is the last node; in a graph it is wherever the branches rejoin.

A `RunResult` is returned only by a run that finished. A node that raises propagates its exception unless it declares `on_error=` (§1.5), and a run budget exhausted between nodes raises `BudgetExceeded`. The manifest and the trajectory are written either way, and the manifest of that run records `error` or `stopped_early` instead.

`docs/run-envelope.md` covers the run directory, the manifest, cassettes, seeds and redaction, all of which apply whether or not a `RunEnvelope` is passed.

### 1.1 What a pipeline refuses at construction

The graph is known before the run starts, so a shape that cannot execute is refused when the pipeline is built.

| Refused | Fix |
|---|---|
| No nodes | Pass them in execution order. |
| Two nodes with the same `node_id` | Pass `node_id=` explicitly. It defaults to the function's name, so two nodes built from one function collide, and so do two lambdas. |
| A `node_id` containing a dot | Use an id with no dot. A pipeline used as a node prefixes its own nodes with its id and a dot, so `research.hunt` already means `hunt` inside `research` (§1.6). |
| A node that can call a model, with no budget | Pass `budget=`. Any axis may be `None`, and `Budget.unbounded()` says every axis is open (FT-18). |
| `max_cost` set with no cost basis declared on the envelope | Declare a basis, or set `max_cost=None`. Otherwise nothing can be derived to enforce the limit against (FT-27). |
| A successor, `on_error` or `Loop(then=)` naming a node the pipeline does not hold | Add a node with that `node_id`, or correct the name. Edges are declared by id. |
| A node no path from the first node reaches | Add it to the successors of a node that does run, or remove it. Execution starts at the first node in the list. |
| More than one node with no successors | Give every branch a successor leading to a single final node. Which one produced the run's output would otherwise depend on which path ran. |
| No node without successors | Leave `successors` off the final node, or pass `successors=[]`. Otherwise no node ends the run. |
| A node whose first parameter is annotated with a type nothing reaching it can be | Annotate it with what arrives, or change what the node before it produces (§3.1). |
| A fan-out node with more than one edge into it | `over=` reads its key off a plain dict and a node with two in-edges receives a `Join`. Put a node between them that returns a dict, or give it one in-edge (§2.2). |
| A fan-out node whose predecessor declares an output schema | That node produces a model rather than a dict. Have it return a dict carrying the key, or drop `over=` (§2.2). |
| More than one successor and no `route` | Pass `route=`, which chooses between them (§1.2). |
| A `route` with fewer than two successors | Declare the successors it chooses among, or drop `route=`. |
| A cycle with no `Loop` on the node that closes it | Pass `loop=Loop(max_iterations=..., then=...)` to that node (§1.4). No budget axis bounds a cycle, so a limit that looked set would stop nothing (FT-18). |
| A `Loop` on a node that closes no cycle | Add the successor that leads back, or drop `loop=`. |
| A `Loop(then=)` naming a node that is not a successor, or one inside the cycle | Name a successor outside the cycle, which is where the run continues once the iterations are spent. |
| `run(on_token=)` or `run(on_reasoning=)` with no node declaring `stream=True` | Declare it on the node whose output is being rendered, or drop the sink. The callback could otherwise never fire (§1.9). |
| A node declaring `stream=True` run against a model client with no `stream` method | Use a client that has one, or drop the sink and the calls are made whole (§1.9). |
| `run(on_reasoning=)` against a client whose `stream` takes no `on_reasoning` | Add the keyword to that client, or drop `on_reasoning=` and the chain of thought is still recorded once each call completes (§1.9). |

Some things cannot be checked before the run, because they depend on what a node produced. A route selecting a node it does not declare as a successor, and a route selecting nothing at all, each raise `CallerFacingError`. So does a value that cannot cross a stop (§1.8), which is a fact about the data rather than about the shape.

A resume is checked too, against what the suspended run recorded: a change of shape is refused outright, and a change of prompt, route, `Deterministic` function, tool version, model pin, cost basis or redaction rules is refused unless named in `accept_changed=` (§1.8).

Per-node metrics, ablation and the trajectory all key on `node_id`, so a node renamed between two runs reports as a different node.

### 1.2 Branching, joining and looping

**The flattest shape that expresses the work is the one to reach for.** Three shapes cover what looks like a branch and is not, and each is cheaper to read and to evaluate than a graph:

- **An amount of work that varies with the data** is `over="documents"` on any node kind, which runs the node once per item in a sequence.
- **A sequence of steps the model chooses** is an `AgentNode`, which selects tools and decides when to stop inside its own node.
- **A loop or a condition over plain data** goes inside a `Deterministic` node, which is ordinary Python.

What the graph is for is a different set of nodes running on different inputs: a step that should not run at all on some inputs, two pieces of work that both have to happen before a third, or a revision loop with a fixed bound.

**Edges are declared on the node.** `successors=` names where the output goes, and `route=` chooses between them:

```python
from simple_agents import Deterministic, LLMNode, Pipeline, RouteContext

def choose(output: Answer, ctx: RouteContext) -> str:
    return "report" if isinstance(output.answer, Unknown) else "verify"

pipeline = Pipeline(
    [
        LLMNode(hunt, output_schema=Answer, node_id="hunt",
                successors=["verify", "report"], route=choose),
        LLMNode(check, output_schema=Answer, node_id="verify", successors=["report"]),
        Deterministic(write_up, node_id="report", successors=[]),
    ],
    budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None,
                  max_wall_clock_ms=300_000),
)
```

A route is plain Python over the node's validated output. It receives a `RouteContext`, which adds `successors` and `iteration` to the `NodeContext` fields in §3, and carries no model client: a route makes no call of its own.

**The model chooses an edge by filling a field the route reads.** `choose` above branches on whether the model reported absence, which is a value in the output schema. A step where the model picks its own next action, rather than an answer a route reads, is an `AgentNode`.

**The end user chooses an edge through `on_reply`.** A node that asked them something routes on which option the answer was, with a branch required for an answer that was none of them and for a refusal. `docs/tools.md` §4.6.1.

**A route may select more than one successor**, and both arms run before anything downstream of both:

```python
route=lambda output, ctx: ["summarise", "cite"]
```

Arms run one after another, in the order the nodes appear in the list, unless the pipeline says
they may overlap (§1.10).

**A node nothing reached does not run.** When every edge into a node resolves absent, the node is skipped: its function is never called, no model call is made, and it emits a `node_execution` record with `termination: "skipped"` and `outputs: null`. That record's `inputs` hold an `Unknown` per absent edge, saying why each did not fire. Skipping propagates, so the nodes downstream of a skipped node are skipped too unless something else reaches them.

That record is what makes a skip visible. `docs/evaluation.md` §5 reports how often each node ran, as `reach`, and every other per-node figure is over the runs that reached it.

### 1.3 Joins

A node with more than one edge into it receives a `Join`, keyed by the node each value came from:

```python
def write_up(inputs: Join, ctx: NodeContext) -> str:
    if "verify" in inputs.absent:
        return f"Unverified: {inputs['hunt'].answer}"
    return f"Verified: {inputs['verify'].answer}"
```

Every declared in-edge is a key whether or not it fired, so the shape follows the graph and not the run:

```python
inputs.fired      # ('hunt',)
inputs.absent     # {'verify': Unknown(reason="'hunt' routed to 'report'")}
inputs["verify"]  # the value, or an Unknown saying why that edge did not fire
```

**`absent` is what says an edge did not fire.** A node whose own answer was that the value is not there returns an `Unknown` and its edge fires normally, so testing the value with `isinstance` reads that answer as a branch that never ran. Reading a key that is not a declared in-edge raises rather than returning `None`, because a misspelled node id would otherwise look like an edge that did not fire.

**A node receives what its edges hand it, and a node's output is the whole of what travels.** Two kinds of node narrow what comes out of them:

- **A node that calls the model produces what its `output_schema` describes.** A value that arrived at it does not come out of it.
- **A node that fans out produces the outcomes**, so anything that arrived beside the sequence stops there.

A value produced before one of those and needed after it is either derived again, or sent to the later node on its own edge. A route selecting more than one successor is what sends it:

```python
Deterministic(plan_searches, node_id="plan",
              successors=["find_pages", "report"],
              route=lambda output, ctx: ["find_pages", "report"]),
Deterministic(find_pages, node_id="find_pages", successors=["read_specs"]),
LLMNode(read_one, output_schema=Reading, node_id="read_specs",
        over="pages", successors=["report"]),
Deterministic(write_up, node_id="report", successors=[]),
```

`report` now has two edges into it and receives a `Join`: the plan under `"plan"`, and the fan-out's outcomes under `"read_specs"`. The plan is in `report`'s recorded `inputs`, and §3 says what happens to a value that travels any other way.

**An edge carries the whole of what its node produced**, so forking one small value out of a node that also produced a large one carries both. Where the value is a key of a fan-out's own input, `keep=` carries that key alone:

```python
LLMNode(read_one, output_schema=Reading, node_id="read_specs",
        over="pages", keep=["queries", "unreadable"]),

def match(readings: FanOutResult, ctx: NodeContext) -> Summary:
    for blocked in readings.kept["unreadable"]:
        ...
```

`keep=` names input keys, and a key that is not there is refused rather than dropped. §2.2 covers the rest of the fan-out.

### 1.4 Bounded cycles

A node whose successors include a node that already ran closes a cycle, and it carries the bound:

```python
from simple_agents import Loop

LLMNode(critique, output_schema=Verdict, node_id="critique",
        allow_unknown=False, successors=["draft", "publish"],
        route=lambda output, ctx: "publish" if output.accepted else "draft",
        loop=Loop(max_iterations=3, then="publish"))
```

`max_iterations` counts executions of that node per entry to the cycle, so the counter starts again each time the cycle is entered from outside it. A loop bounded at 3 nested inside one bounded at 10 gets three iterations on every outer pass rather than three for the whole run.

When the count is reached, the run takes `then` whatever the route would have said, and that execution's record carries `loop.exhausted: true`. `then` has to be a successor of the node and outside the cycle.

**The node a cycle returns to has an extra edge into it**, so it receives a `Join` carrying the value that entered the cycle and the value that came back round, and the second holds an `Unknown` on the first pass. Where that node is the first in the list, every edge into it closes the cycle, and it receives what was passed to `run` on its first execution and the cycle's value afterwards.

**The edge from outside the cycle keeps the value that entered.** It resolves once, on the pass that entered the cycle, and every later iteration reads that same value. A node that folds each iteration's result into what arrived on that edge folds into the value from before the first iteration every time, and each fold is lost when the next one starts from the original again.

**A value that accumulates travels on the edge that closes the cycle.** The node closing it receives both the working set and the latest result, and hands the two folded together back round:

```python
def seed(inputs: dict, ctx: NodeContext) -> dict:
    return {"pending": inputs["candidates"], "resolved": []}

def select(inputs: Join, ctx: NodeContext) -> dict:
    state = inputs["seed"] if "fold" in inputs.absent else inputs["fold"]
    pending = list(state["pending"])
    return {**state, "pending": pending[1:],
            "current": pending[0] if pending else None}

def fold(inputs: Join, ctx: NodeContext) -> dict:
    state = inputs["select"]
    return {**state, "resolved": [*state["resolved"], inputs["chase"]]}

Deterministic(seed, node_id="seed", successors=["select"]),
Deterministic(select, node_id="select",
              successors=["chase", "fold", "finalise"],
              route=lambda output, ctx: (
                  ["chase", "fold"] if output["current"] else "finalise")),
AgentNode(chase_prompt, tools=registry, budget=chase_budget,
          output_schema=Finding, node_id="chase", successors=["fold"]),
Deterministic(fold, node_id="fold",
              successors=["select", "finalise"],
              route=lambda output, ctx: "select",
              loop=Loop(max_iterations=8, then="finalise")),
```

`select` routes to both `chase` and `fold`, so `fold` is handed the working set and the model's finding and can fold one into the other. The bound goes on `fold`, which is the node that closes the cycle. Every iteration's working set is then in a recorded `inputs`.

**`seed` is what gives `select` a `Join` to read.** The paragraph above applies to it: a node first in the list receives what was passed to `run` rather than a `Join`, so the working set enters on an edge of its own and `select` reads two edges on every pass.

`finalise` has two edges into it and receives a `Join`. The accumulated value arrives from `select` where the work ran out, and from `fold` where the bound was reached first, so it reads whichever fired:

```python
def finalise(inputs: Join, ctx: NodeContext) -> Report:
    state = inputs["select"] if "fold" in inputs.absent else inputs["fold"]
```

A cycle with no `Loop` is refused at construction. No budget axis bounds one: `max_steps` counts model calls and a cycle of `Deterministic` nodes makes none, and a limit that looks set and stops nothing is FT-18.

### 1.5 Errors and retries

A node that raises ends the run, unless it declares where the failure goes:

```python
from simple_agents import NodeFailure, RetryPolicy

Deterministic(look_up, node_id="lookup", successors=["report"],
              retry=RetryPolicy(attempts=3, backoff_ms=200), on_error="fallback")

def fallback(failure: NodeFailure, ctx: NodeContext) -> Answer:
    return Answer(answer=Unknown(reason=f"{failure.node_id} failed: "
                                        f"{failure.error['message']}"))
```

`attempts` counts every execution, so `attempts=1` is no retry and `attempts=3` is one execution plus two more. Every attempt emits its own `node_execution` record, and the failed ones carry `termination: "error"`, so a node that worked on its third try says so.

Attempts share one node budget, so retrying does not multiply what a node may spend. A cassette miss and an exhausted budget are never retried: neither is the node's own failure.

A failure that survives the last attempt travels along `on_error=` as a `NodeFailure`, carrying `node_id`, the `inputs` the failed node received, the `error` object `docs/trajectory-format.md` §5.2 defines, and `attempts`. Where the node declares no `on_error`, the exception propagates and the run ends. The error edge is an edge like any other: on a run where the node succeeded it resolves absent, and the handler is skipped.

### 1.6 Pipelines inside pipelines

A `Pipeline` given a `node_id` is a node in another pipeline:

```python
research = Pipeline([...], budget=..., node_id="research")
outer = Pipeline([research, LLMNode(write, output_schema=Report)], budget=...)
```

Its nodes record under ids prefixed by it, so `hunt` inside `research` is `research.hunt` in the trajectory, in the manifest and in per-node metrics. Two copies of one pipeline under different ids do not collide. The container itself emits no `node_execution` record: every record names one of the three node kinds.

A nested pipeline's budget bounds what it spends, measured from the point it started, and the run budget still applies over everything.

It declares its own edges the way any node does, and takes `tools=` and `fetch_policy=` the way the outer pipeline does. All of that is recorded under `containers` in the manifest, beside the `nodes` array holding its children (`docs/run-envelope.md` §2.5). The `graph_fingerprint` is a digest of shape, so a change to a container's edges moves it and a change to its `tools=`, `fetch_policy=` or budget does not (`docs/run-envelope.md` §2.1).

### 1.7 Seeing the graph and watching a run

```python
print(pipeline.to_mermaid())
```

renders the declared graph as a Mermaid flowchart, which is how the shape gets checked against what was meant. A routed edge is dashed, an error edge is labelled, the edge closing a cycle carries its bound, and a node declaring `suspend_before` is labelled `stops before`.

**`ProgressBar` is the display, and it takes no writing:**

```python
from simple_agents import ProgressBar

with ProgressBar() as bar:
    pipeline.run(inputs, model=client, on_progress=bar)
```

A run gets a counter rather than a bar, because loops and routes decide how many nodes run while it is running. A fan-out inside it gets a bar as soon as its first item lands, since the node says how many items it has. The same object goes to `EvalSuite.run(on_rollout=)`, which does get a proportion and a time remaining (`docs/evaluation.md` §6.6). Nothing is written where the stream is not a terminal, so a run under CI is unchanged.

`on_progress=` takes any callback that receives a `NodeEvent` as each node starts, completes, is skipped or fails:

```python
def show(event: NodeEvent) -> None:
    print(f"{event.phase:<9} {event.node_id} {event.route}")

pipeline.run(inputs, model=client, on_progress=show)
```

`phase` is `started`, `completed`, `skipped`, `failed` or `item`. `route` is filled on `completed` and names where the output went. An exception from the callback ends the run like any other, so a progress display that breaks does not pass unnoticed.

**An `item` event fires as each item of a fan-out finishes**, carrying its `item_index`, the `item_total` it is one of, and its `error` where it failed. `item_index` is a position in the whole collection, so a resumed fan-out announces the items it still had to do and their indices are where they were. A fan-out hands its whole result to the next node when the last item is done, so a project writing each item as it lands writes on this rather than on the node completing:

```python
def store(event: NodeEvent) -> None:
    if event.phase == "item" and event.error is None:
        db.write(event.node_id, event.item_index)
```

It is a phase of its own, so a caller counting `completed` events counts nodes whether or not any of them fans out.

### 1.8 Stopping a run and starting it again

A run can stop, write down where it got to, and be continued in another process. The case that
needs it is an agent asking the end user something when the terminal is unattended: the answer may
arrive tomorrow, and the process cannot wait. The same machinery serves a planned human review,
an end user pressing pause, work parked before a redeploy, and a run waiting out a token quota.

**There are three ways a run stops before its last node, and one way to continue from any of
them.**

```python
# 1  something the run called cannot answer now
def ask_by_email(question, options, about):
    send_email(question, options)
    raise Suspend(waiting_for=question, options=options)

registry.add(consult(ask_by_email, answered_by="end_user"))

# 2  a stop planned in advance, and drawn by to_mermaid()
LLMNode(review, output_schema=Verdict, allow_unknown=False, suspend_before=True)

# 3  the caller's own reason, checked before each node
pipeline.run(inputs, envelope=env, model=client, stop_when=paused.is_set)
```

`Suspend` may be raised from a tool, from a `Deterministic` function, from an `LLMNode` prompt
function, or from a `ModelClient`. It is never retried and never follows `on_error=`: the node
did not fail.

**It derives from `BaseException`**, as `SystemExit` and `KeyboardInterrupt` do, so an
`except Exception` wrapped around a call does not catch it. A run that reaches its end after one
was raised is refused: the question is on record as `pending`, no state was written, and the run
cannot be continued, so reporting it as finished would be reporting an answer built without one.
Where a node has to keep going when there is nobody to ask, the channel returns `Unavailable` or
`Shelved` instead of raising, and the node reads the reply (`docs/tools.md` §4.6.3).

**`Pipeline.run` raises `RunSuspended`** rather than returning a result whose output is `None`.
The manifest and the trajectory are written, as they are for a run stopped by its budget.

```python
try:
    result = pipeline.run(inputs, envelope=env, model=client)
except RunSuspended as stop:
    queue.put({"run_id": stop.run_id, "question": stop.waiting_for})

# later, in another process, against the same pipeline
result = pipeline.resume(stop.run_id, envelope=env, model=client, answer="slim")
```

`answer` is what the call that suspended returns. A run that stopped at a node boundary takes
none. The run keeps its id, its trajectory and its manifest, so what comes out is one run that
stopped rather than two runs to join up.

**Both halves are the design, and the first one works on its own.** A project that raises
`Suspend` and never calls `resume` shows the question on its surface and leaves the run on
disk, where it raises no error. The manifest records a `suspensions` entry per stop, each
gaining `resumed_at` when the run continues, and FT-41 fails a project at `ship` whose runs
stopped and were never continued. Where a run should finish without the answer instead, the
channel returns `Shelved` or `Unavailable` and never stops it (`docs/product.md` §4).

**What a resumed node picks up.** An `AgentNode` continues its loop with the conversation, the
tool calls it had made and its own spend intact, and makes only the model calls it had not made.
A fan-out continues at the item it stopped on, and an item that was part-way through continues from what it was holding rather than starting again. Where several items stopped together, one suspension asks one question: the lowest of them is answered and the rest ask on the next resume. A `Deterministic` node runs again
from the beginning: the tool calls it made before the one that stopped are made a second time,
and the call that stopped is handed the answer rather than being made again. A function that
takes a different path on the way back and does not reach that call is refused, naming the node,
so a dropped answer is reported rather than lost inside a run that completes.

**Time spent suspended is charged to no budget.** A node's wall clock is stored as elapsed and
restarted, so a consultation answered a day later does not trip `max_wall_clock_ms`. The
manifest records each interval, so the wait is auditable rather than invisible.

#### What may cross a stop

A value in flight is rebuilt from the `output_schema` of the node that produced it, so the node
that receives it gets an `Answer` and not a `dict`. No type name is written to the file, so
renaming a class changes nothing.

`Deterministic` takes an optional `output_schema=` for this. A value from a node that declares
none must be plain data: `None`, a string, a number, a boolean, or a list or dict of those.
Anything else is refused at the point the run would have stopped, naming the node.

```python
Deterministic(load_notes, output_schema=Notes)
```

The same rule reaches a tool: a finish check reads what each tool returned, so a tool whose
result has to survive a stop returns plain data.

#### Waiting on a clock

```python
raise Suspend(waiting_for="monthly token quota",
              resume_not_before="2026-09-01T00:00:00Z")
```

`resume()` refuses before that time and says how long is left. `resume(wait=True)` blocks in the
calling process instead. Nothing in the library counts the time down or wakes a run up, so
what restarts the process is the project's:

```python
for state in Pipeline.suspensions("runs/"):
    if state.ready:
        rebuild(state.run_id).resume(state.run_id, envelope=env, model=client)
```

#### Resuming against the right pipeline

The code is the caller's to reconstruct, so a resume checks it against what the run recorded
before restoring anything.

- **A change of shape is refused and cannot be waived.** Node ids, kinds, edges, loop bounds,
  error edges, retry policies and output schemas. The stored state is keyed on node ids, so a
  different graph makes it meaningless rather than stale.
- **A change of version is refused unless it is named.** Prompts, routes, `Deterministic` node
  functions, tool versions, the model pin, the cost basis, the redaction rules. What is compared
  is the declared version, so an edit made under a `prompt_version=` or a `version=` that did not
  move is not refused here; `resume_from` and `rescore` report it instead
  (`docs/evaluation.md` §6.7).

```python
pipeline.resume(run_id, envelope=env, model=client, answer=answer,
                accept_changed=["prompts.hunt"])
```

The waiver is recorded in the manifest, so a number that moves has something to be traced to.

**A resume claims its suspension before running anything**, so two workers reading one run
directory cannot both continue the same run.

**An evaluation never suspends.** A consultation is served from the cassette on a replay, and
answered by the stand-in end user the evaluation was given otherwise, so k rollouts do not stop
k times to ask a person (`docs/evaluation.md` §5.4).

### 1.9 Delivering a node's output as it is produced

A node declares that its output may be streamed; the run says where the pieces go.

```python
answer = LLMNode(reply, output_schema=Answer, stream=True)

pipeline.run(inputs, envelope=env, model=client,
             on_token=lambda event: sys.stdout.write(event.text))
```

`on_token` receives a `TokenEvent` carrying `node_id`, `node_kind`, `call_index`, `kind`, `text`, and
`item_index` inside a fan-out. **A token event always falls between the `started` and the
`completed` or `failed` `NodeEvent` of the node that produced it**, and carries the same
`node_id`, so a caller watching both channels attributes tokens to a node without correlating
anything. `on_progress` fires about four times per node and `on_token` thousands of times, which
is why they are separate callbacks.

**Passing `on_token` is what turns streaming on.** Without it the same calls are made whatever a
node declares, so an evaluation of a streaming pipeline sends what a non-streaming one sends.
Declare `stream=True` only on the nodes whose output is being rendered: a streamed call can
carry weaker token counts than one made whole, and confining it confines that.

**A node with an `output_schema` streams fragments of JSON.** That is what the model emits under
constrained decoding, and it is the answer that gets validated, not the pieces.

**`on_reasoning=` is the second channel**, taking the same events for a chain of thought the
backend reports separately. `kind` is `"content"` on one and `"reasoning"` on the other, and
either sink alone turns streaming on:

```python
pipeline.run(inputs, envelope=env, model=client,
             on_token=render, on_reasoning=lambda event: status.update(event.text))
```

A reasoning model sends its chain of thought first, so a run given only `on_token` shows nothing
until the answer begins. `docs/model-clients.md` §6 covers what is recorded either way.

Three refusals, all before the run starts: a sink with no node declaring `stream=True`, a
declaring node run against a model client that cannot stream, and `on_reasoning=` given to a
client whose `stream` takes no such keyword. `docs/model-clients.md` §5 covers what each backend
delivers and what a streamed call records.

### 1.10 Running work at the same time

Nothing in a run overlaps until something says it may. Three things can, each declared where the
knowledge is, and `Pipeline.run(concurrency=N)` is the most calls the whole run may have in
flight at once:

```python
pipeline = Pipeline(
    [plan, read_specs, fetch_reviews, report],
    budget=budget,
    concurrent_nodes=[["read_specs", "fetch_reviews"]],
)
pipeline.run(inputs, envelope=env, model=client, concurrency=8)
```

| Declared | Where | What overlaps |
|---|---|---|
| `concurrent_nodes=[["a", "b"], ["b", "c"]]` | `Pipeline` | Two nodes run at the same time when a group lists both |
| `concurrent_items=8` | Any node with `over=` | That many items of one fan-out. On an `AgentNode` an item is a whole loop, so this bounds loops in flight rather than calls |
| `concurrent_tools=[search, fetch]` | `AgentNode` | Those tool calls, when the model asks for several in one turn |

**A node may declare more than the run permits, and the run says so.** The effective width is the smaller of the two, so `concurrent_items=8` under the default `concurrency=1` runs one item at a time. That is not an error, and the difference reads as the model being slow rather than as the declaration being ignored, so the run warns at the start naming each node and both numbers:

```
This run permits 1 call(s) in flight and judge declares 14, so those items run 1 at a
time. Pass Pipeline.run(concurrency=14) to give the declarations room, or lower them to
what the run permits.
```

A replay is silent, since a cassette serves the calls and nothing is waiting on a backend.

**A group is a claim about a pair.** Any number of groups, of any size, and a node may appear in
several: `[["a", "b"], ["b", "c"]]` overlaps `a` with `b` and `b` with `c`, and never `a` with
`c`. A group naming a node the pipeline does not have is refused, and so is a group of one.

**What listing two nodes asserts.** That neither interferes with the other. The library cannot
check it: a `Deterministic` node writing to `ctx.workspace` is plain Python, and every node is
handed the same directory. A tool declares its side-effect class, which is why
`concurrent_tools` refuses a `WRITES` tool by name; nothing declares what a node's own function
does.

**`finish` and anything that can stop the run are made after the calls that overlap**, so a
finish check sees the reads made in the turn it is judging and a stop lands on a turn boundary.

### 1.11 What a stop does to work already running

Work already running finishes, is recorded and is charged. Work not yet started does not start.
That is the same rule for all three ways a run stops: a budget axis exhausted, a node stopping to
ask someone, and a node raising.

**A budget bounds what a run spends, and overlapping calls change how exactly.** `max_steps` is
exact: one call is one step, the step is taken before the call, and a call does not start unless
one remains. `max_tokens`, `max_cost` and `max_wall_clock_ms` are measured by what a call turns
out to consume, so a run at `concurrency=N` can pass its limit by what the other N−1 calls were
already spending. At `concurrency=1` that is one call, which it has always been.

**A run that stopped in more than one node at once is continued with `answers`**, keyed by the
node each answer belongs to:

```python
stop = None
try:
    result = pipeline.run(inputs, envelope=env, model=client, concurrency=4)
except RunSuspended as suspended:
    stop = suspended

while stop is not None:
    answers = {each["node_id"]: ask_someone(each["waiting_for"], each["options"])
               for each in stop.stops}
    try:
        result = pipeline.resume(stop.run_id, envelope=env, model=client, answers=answers)
        stop = None
    except RunSuspended as suspended:
        stop = suspended
```

**A resume can stop again, so this is a loop rather than one call.** An arm that had not begun
when the run stopped is left unstarted, and nothing it would have spent is spent. It runs on the
resume, and a node in it that consults stops the run there. Whether a sibling arm had begun
depends on how long the first one took, so the same pipeline can report one stop on one run and
two on the next.

`stop.stops` holds one entry per stopped node. A run that stopped in one node still takes
`answer=`, and passing `answer=` to a run that stopped in several is refused, because nothing
says which node it is for.

`node_id` is the same id the trajectory, the manifest and per-node metrics use, so a node inside
a pipeline used as a node is `research.ask`, not `ask`. Two nested pipelines each holding a node
named `ask` therefore produce two stops that can be told apart and answered separately.

### 1.12 What overlapping does not change

**A run makes the same calls whatever order they run in, and the cassette answers each the same
way.** Every call's identity comes from its position rather than from when it started: a fan-out
item is seeded by its index, and a tool call takes its number from its place in the turn. So a
cassette recorded from a run at `concurrency=1` replays against the same pipeline at
`concurrency=8`, and an evaluation's numbers do not depend on how much overlapped.

**What does differ is the order records were written**, and therefore `sequence` and the
timestamps in the trajectory. `sequence` says which record was written first, not which thing
happened first; `parent_id` is what says where a record belongs. `docs/trajectory-format.md` §2
covers reading a trajectory back.

**`FakeModelClient` needs `answer=` under overlap.** A scripted list hands out whatever is next,
so which call gets which response depends on which arrived first. Pass a function of the request
instead, and the client refuses rather than answering the wrong call:

```python
client = FakeModelClient(answer=lambda request: fake_response(content="..."))
```

### 1.13 Running again what a dead run was given

A process can end without the run ending: an out-of-memory kill, a container eviction, a deploy
restart, a `pkill` that matched more than it meant to. The manifest is written when the run starts
and rewritten when it ends, so a run whose process died leaves the start copy, and
`RunHandle.liveness` reads `abandoned` on it (`docs/run-envelope.md` §8.3).

`rerun` runs again what that run was given, serving the calls it already made from its own
cassette:

```python
from simple_agents import runs

for dead in runs("runs/"):
    if dead.liveness == "abandoned":
        result = pipeline.rerun(dead.path, envelope=env, model=client)
```

The inputs and the seed come off the run's `run_start` record (`docs/trajectory-format.md` §1.3),
and the cassette is that run's own file in `update` mode, so a node that finished re-executes its
Python and its calls are served from disk. Only what never finished is paid for. Anything `run`
takes may be passed through, and `envelope` is required because the new run needs somewhere of its
own to write.

**The result is a new run.** It takes its own id and its own directory, and its record says a run
that replayed most of its calls. The dead run stays on disk as it was.

**A node body that reads a clock or `random` directly rather than through a tool diverges.** From
that point its calls hash to keys the cassette has no entry for and are made live, which costs
money rather than producing a wrong answer.

**A run whose payloads were sampled out has no inputs to read**, and `rerun` refuses naming what to
pass instead (`docs/run-envelope.md` §7). So does a run written before trajectory format `0.29`.

### 1.14 Part of a pipeline as a pipeline

`slice` returns part of this graph as a pipeline of its own. It runs, writes a trajectory and a
manifest, and is evaluated like any other. Evaluation is what it is for: scoring one step on
ideal inputs, then two, and so on, so a number that drops names the step it dropped at
(`docs/evaluation.md` §5.6).

```python
rung = pipeline.slice(start="judge")             # judge to the end
pipeline.slice(end="select")                     # the head up to select
pipeline.slice(start="select", end="judge")      # between them
pipeline.slice(nodes=["select", "judge", "present"])
```

`start` and `end` are inclusive and either may be left out. `nodes` names the set instead, for a
branching graph where two bounds cannot say which arm is wanted, and cannot be combined with
them.

**An edge whose other end is outside the slice stays declared.** A node that took a `Join`
still receives one, with the arm that was cut in `Join.absent`, so the nodes that remain see the
graph they saw before:

```python
def present(inputs: Join, ctx: NodeContext) -> str:
    if "apologise" in inputs.absent:
        return f"Recommended: {inputs['judge']}"
```

A route may still select an arm the slice does not hold. The run ends there rather than going
down a surviving arm, raising `LeftTheSlice`; its manifest records `outcome` as `stopped_early`
and `stopped_early` as `left_the_slice`, and the node's record carries the same `termination`.
An evaluation leaves that rollout out of every figure and reports the count beside each one.

`slice_of` says what the result is a slice of, and every run it makes records the same under
`slice` in its manifest (`docs/run-envelope.md` §2.1).

A slice keeps the pipeline's budget, tools and fetch policy, and its `node_id` is `None`. It is
refused for a node id the pipeline does not hold, for a set whose nodes are not all reachable
from the earliest of them, and for a set with more than one node that ends it. A dotted id names
a node inside a pipeline used as a node, which is a different graph: slice that one.

---

## 2. The three node kinds

| Kind | What it is | Model calls | Who chooses a tool call |
|---|---|---|---|
| `Deterministic` | Plain code | None, and no way to make one | The node, through `ctx.call_tool` |
| `LLMNode` | A model call at a fixed point in fixed control flow | One | The node, through `ctx.call_tool` |
| `AgentNode` | The model deciding what happens next | Not known in advance | The model |

One step is one model call, whichever kind made it.

**All three take the same graph arguments**, since routing is a property of a node rather than a fourth kind: `successors=`, `route=`, `loop=`, `on_error=` and `retry=`, covered in §1.2 through §1.5. A `Pipeline` takes them too, which is what lets one sit inside another (§1.6).

**All three take `over=` as well**, which runs the node once per item of an input sequence and is a property of a node in the same way. What one item is differs by kind: one model call for an `LLMNode`, one agent loop for an `AgentNode`, one call of the function for a `Deterministic` node. §2.2 covers the fan-out, and everything in it applies to all three.

### 2.1 `Deterministic`

```python
def load_docs(inputs: dict, ctx: NodeContext) -> str:
    return Path(inputs["corpus"]).read_text()

node = Deterministic(load_docs)
```

`over=` calls the function once per item of an input key holding a sequence, returning a `FanOutResult` like any other fan-out (§2.2):

```python
node = Deterministic(parse_one, over="pages", max_failures=2)
```

The function receives a `NodeContext`, which carries no model client and no tools. Parsing, filtering, arithmetic and I/O belong here, and this is the cheapest kind.

`version=` is what the manifest records for the function, and what an evaluation of the pipeline is filed under. Left unset it is a hash of the source, so an edit names a different evaluation directory. Declare one where the function reads a corpus, a table or a store, since that data changes without the source changing (`docs/evaluation.md` §6.7):

```python
node = Deterministic(read_library, version="characterised-2026-08")
```

### 2.2 `LLMNode`

```python
node = LLMNode(build_prompt, output_schema=Answer)
```

The supplied function builds a prompt and returns it. The library makes the call and validates the response against `output_schema`. A step whose next action depends on what the model returned is an `AgentNode` instead.

`temperature`, `max_output_tokens` and backend-specific options in `extra` are set per node. `prompt_version` records which version of the prompt ran (FT-15). `context=` sets what of the conversation is sent on each call, and defaults to sending all of it; `docs/context.md` covers it.

**Fan-out with `over=`** names an input key holding a sequence and runs the node once per item. Any node kind takes it, and what one item is follows from the kind:

```python
LLMNode(summarise, output_schema=Summary, over="documents", max_failures=2)
Deterministic(parse_one, over="documents", max_failures=2)
AgentNode(read_one, tools=[look_up], output_schema=Reading, over="documents",
          budget_per_item=Budget(max_steps=8, max_tokens=20_000,
                                 max_cost=None, max_wall_clock_ms=60_000))
```

**The prompt function receives the whole input, with the named key holding one item rather than
the sequence.** Everything else the node was given arrives unchanged, so a prompt that reads
another key keeps working:

```python
def summarise(inputs):
    return f"Summarise this for {inputs['audience']}:\n\n{inputs['documents']}"
```

Here `inputs["documents"]` is one document, not the list. A function written to receive the item
on its own raises `KeyError` on the first item.

The node returns a `FanOutResult`, which separates the two outcomes an item can have:

```python
result.outcomes   # one ItemOutcome per input item, in input order
result.failures   # the outcomes that did not succeed
result.ok         # whether every item succeeded
```

An `ItemOutcome` carries `index`, `item`, and either `value` or `error`, and `termination` where the kind decides for itself why an item stopped: an `AgentNode` item that ran out of steps is a success whose `termination` is `"max_steps"`. `docs/trajectory-format.md` §5.2 defines the error shape. Iterating a `FanOutResult` yields its outcomes, so it stays lined up with the input sequence:

```python
summaries = [outcome.value for outcome in result if outcome.ok]
retry = [outcome.item for outcome in result.failures]
```

An item whose value is `unknown` is a success. An item whose call failed is a failure. `max_failures` is how many failed items the node tolerates. The next failure after that raises `CallerFacingError` and ends the run, so nothing is returned. Without it, every item is attempted and every failure is collected.

**Two failures are the node's rather than an item's, and both raise whatever `max_failures` says.** The first is a failure that says the run is invalid: a `ConfigurationError`, a cassette miss, a budget exhausted, a `StreamUsageMissing` or a `LeftTheSlice`. None is answered by running the next item. A response that does not match the node's `output_schema` is not one of them: that is one item's, and it is collected. The second is every item failing with the same exception type and the same message, over two items or more:

```
Node 'summarise' fanned out over 37 items and every one of them failed with the same
KeyError: 'shows'
```

A failure every item shares is not about the items. The node produced nothing, and the step after it reads an empty result as a shortfall the node measured rather than as a node that never ran. A failure that really is one item's names that item, so the messages differ and the run continues under `max_failures` as before. An item stopped because it ran out of the budget the node declared is outside this, as it is outside `max_failures`: the node was given a bound and reached it.

**`retry=` and collecting are alternatives, and a node declaring both is refused.** A retry re-executes a node when the node raises, and collecting is what stops it raising, so a fan-out that collects every failure never reaches its own retry. `max_failures=0` makes the first failed item raise and the retry re-execute the node, which re-attempts every item including the ones that succeeded; leaving `retry=` off keeps the failures on the result to be read and re-sent as the project decides. Retrying one item alone is the second of those, written by the project.

**A fan-out returns the outcomes and nothing else.** `keep=` names input keys that travel on with them, and they arrive at the next node under `FanOutResult.kept`:

```python
node = LLMNode(read_one, output_schema=Reading, over="pages",
               keep=["queries", "unreadable"])

readings.kept["unreadable"]   # what the node before this one put under that key
```

A key named in `keep=` that is not in the input raises `CallerFacingError` naming the keys that are, and naming the key the node fans out over is refused at construction. `kept` is empty on a node that declared no `keep=`. §1.3 covers the other way a value reaches a node further on, and what `kept` holds is written to the record beside the items (`docs/trajectory-format.md` §3.4).

### 2.3 `AgentNode`

```python
from simple_agents import AgentContext, AgentNode, SideEffectClass, tool

@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str) -> str:
    """Search the document set. Returns matching passages."""
    return index.search(query)

def build_prompt(inputs: dict, ctx: AgentContext) -> str:
    return f"{inputs['question']} Available tools: {ctx.describe_tools()}"

node = AgentNode(
    build_prompt,
    tools=[look_up],
    output_schema=Answer,
    budget=Budget(max_steps=8, max_tokens=50_000, max_cost=None,
                  max_wall_clock_ms=120_000),
)
```

The only kind whose number of model calls is not known in advance, and the only one that owns a loop. A budget is required at construction (FT-18).

**A tool an `AgentNode` offers can read the node's own input**, through `NodeInput` (`docs/tools.md` §3.2.1). A retrieval tool over a pool the previous node produced asks for it that way; a closure built when the pipeline was built reaches whatever it was built with, and an evaluation builds one pipeline for every rollout.

**A bounded cycle is the other shape for work that repeats.** A set of nodes with an edge back, the model steering by filling a field a route reads, and `Loop(max_iterations=3, then=...)` bounding it (§1.4):

```python
pipeline = Pipeline(
    [
        LLMNode(propose, output_schema=Draft, node_id="draft",
                allow_unknown=False, successors=["critique"]),
        LLMNode(critique, output_schema=Verdict, node_id="critique",
                allow_unknown=False, successors=["draft", "publish"],
                route=lambda output, ctx: "publish" if output.accepted else "draft",
                loop=Loop(max_iterations=3, then="publish")),
        Deterministic(publish, node_id="publish", successors=[]),
    ],
    budget=Budget(max_steps=12, max_tokens=100_000, max_cost=None,
                  max_wall_clock_ms=300_000),
)
```

Each iteration is a node execution of its own, so each one's inputs and outputs are on the record and `docs/evaluation.md` §5's per-node figures cover it. Reach for it where the steps are the same every time round and what varies is how many times. Reach for an `AgentNode` where which step happens next depends on what the last one returned, and the sequence is not known before the run.

**A fanned-out `AgentNode` declares two budgets.** `budget=` bounds one execution of the node, which under `over=` is every item together; `budget_per_item=` bounds one item. `budget_per_item=` on a node with no `over=` is refused, since there are no items for it to bound. A fan-out that declares neither is refused like any other unbounded loop, and one that declares a single budget is constructed with a warning naming the axis left open:

```python
node = AgentNode(
    read_one,
    tools=[look_up],
    output_schema=Reading,
    over="documents",
    budget_per_item=Budget(max_steps=8, max_tokens=20_000, max_cost=None,
                           max_wall_clock_ms=60_000),
    budget=Budget(max_steps=200, max_tokens=400_000, max_cost=None,
                  max_wall_clock_ms=600_000),
)
```

With `budget=` alone, one runaway item can consume the whole allowance and every item after it terminates having done nothing. With `budget_per_item=` alone, the node's total is the item count times the item's allowance, bounded by the run and by nothing nearer. The manifest's node entry records both, so a reader of the results sees which was left open. An item that never ran because the node's total was gone is collected as a failed item saying so, and the run continues.

The library supplies the `finish` tool itself, validated against `output_schema`, so `tools` holds the node's own tools and the name `finish` is reserved. `tools` takes a list or a `ToolRegistry`.

`finish_check` runs after an answer validates against the schema and can reject answers the schema cannot describe. `docs/tools.md` §5 covers it, including what a check that refuses the same answer twice does to a run.

Every model call and tool call inside the loop gets its own trajectory record, so which decisions the node makes identically every time is readable from a run. Those are the ones that can be frozen into an `LLMNode` or a `Deterministic` node (FT-12).

**A loop that ends on a budget axis produces no output**, since the output comes from the `finish` call. The node after it is handed `None`, the run completes, and no error is recorded. Each run's manifest counts those executions and what they spent, `simple-agents report runs/` prints them, and `simple-agents check` fails a node that spent a whole allowance without calling a tool, consulting or delegating (FT-35). Where that is what a node is for, `allow_unfinished=True` declares it:

```python
node = AgentNode(
    watch_for_it,
    tools=[poll],
    output_schema=Answer,
    budget=Budget(max_steps=20, max_tokens=50_000, max_cost=None,
                  max_wall_clock_ms=120_000),
    allow_unfinished=True,
)
```

The waiver is recorded in the run manifest beside `allow_unknown`, so the gate reads what the run declared. It changes nothing the node does.

### 2.4 Which model a node calls

`Pipeline.run(model=...)` serves every node that declares none. A node that declares one calls it whatever the run was given, so a cheap model for a reduction step and a strong one for the answer are one pipeline:

```python
cheap = VLLMClient(model="Qwen/Qwen3-1.7B", model_revision="a1b2c3d", base_url="http://localhost:8001/v1")
strong = MistralClient(model="mistral-large-2512")

pipeline = Pipeline(
    [
        Deterministic(load_docs),
        LLMNode(reduce_notes, output_schema=Notes, model=cheap),
        LLMNode(answer, output_schema=Answer),
    ],
    budget=Budget(max_steps=None, max_tokens=200_000, max_cost=None, max_wall_clock_ms=300_000),
)

pipeline.run(inputs, envelope=env, model=strong)
```

`reduce_notes` calls `cheap`, and `answer` calls `strong`. A `Deterministic` node takes no `model`, because it makes no model call.

**Resolution has two levels: the node's own client, then the run's.** A pipeline used as a node does not declare one for the nodes inside it, so each of those declares its own or takes the run's.

**A node that can call a model and has neither is refused before the run starts**, rather than when that node is reached, so nothing is spent first.

**What the run records.** `nodes[].model` in the manifest holds what each node declared, and `null` where it takes the run's client, which `models.configured` holds (`docs/run-envelope.md` §2.2). Every `model_call` record carries the identity that served it either way. FT-14 checks each of them, so pinning one model and leaving another floating fails and names the node.

**What follows from it.** The cassette key covers model identity, so a node whose model changed finds no recorded response rather than the previous model's. Two nodes on different backends need a cost basis per model (`docs/run-envelope.md` §4.1). A model swap on one node is an ordinary variant, which is what makes "which step actually needs the expensive model" measurable (`docs/evaluation.md` §10).

### 2.5 Delegating a subtask to a pipeline

A pipeline given a `node_id` is a node in another pipeline (§1.6), which is the case where the builder fixes the decomposition. A `Delegation` is the case where the model chooses it: the model decides what each subtask is, and how many to send.

```python
from simple_agents import Delegation

class Subtask(BaseModel):
    """One question to research."""
    question: str

def widen(inputs: Subtask, ctx: NodeContext) -> str:
    return f"Find out: {inputs.question}"

research = Pipeline(
    [Deterministic(widen), LLMNode(hunt, output_schema=Notes)],
    budget=Budget(max_steps=6, max_tokens=20_000, max_cost=None, max_wall_clock_ms=60_000),
    node_id="research",
)

orchestrate = AgentNode(
    plan_the_work,
    tools=[read_page],
    delegates=[Delegation(research, description=(
        "Research one question and return sourced notes. Send one question per subtask. "
        "Do not send a question the notes already answer."))],
    output_schema=Report,
    budget=Budget(max_steps=20, max_tokens=200_000, max_cost=None, max_wall_clock_ms=600_000),
)
```

**What the model is shown.** The delegation reaches the backend as one more tool declaration, named for the pipeline's `node_id`. `description` is prompt text and is required. The arguments are the type the pipeline's entry node reads, so `research` above is offered as taking a required string called `question`, and the entry node receives a `Subtask` rather than a dict.

**A delegated pipeline's entry node has to annotate its first parameter with a pydantic model**, because the model fills those arguments in. Anything else is offered as an object with no properties, which is how a delegation gets sent arguments the entry node cannot read (FT-23). Arguments that do not satisfy the type come back to the model as a failed call, so a malformed subtask is corrected rather than ending the run.

**Its nodes record under ids prefixed by the calling node as well.** `hunt` inside `research` delegated from `orchestrate` is `orchestrate.research.hunt`, so two nodes delegating to the same pipeline do not collide. Those ids appear in the manifest's `nodes` array, and the delegated pipeline appears in `containers` with a `reached_by` naming the node whose model sends it (`docs/run-envelope.md` §2.5).

**Which node id a delegation's executions belong to does not change between subtasks.** Two subtasks both produce an `orchestrate.research.hunt` execution, and each carries the `record_id` of the `delegation` it ran inside. That is what separates them, and it is why per-node metrics report one node with two executions rather than two nodes (`docs/trajectory-format.md` §4.4).

#### What bounds a delegation

**What a delegate spends counts against the calling node's budget.** One step is one model call wherever it was made, so a worker making three calls per subtask spends three of the orchestrator's `max_steps`. That is what bounds how many subtasks the model can send.

**`max_calls` is required only where the delegated pipeline makes no model call.** A pipeline of `Deterministic` nodes spends no `max_steps`, so nothing would bound how often the model sends it work, which is the same hole a cycle carries its own `Loop(max_iterations=)` for (§1.4). Where a worker does call a model, `max_calls` is an optional second ceiling:

```python
Delegation(tabulate, description="Total one column of the table.", max_calls=6)
```

**A delegation runs under three limits, and only one of them ends the run.** The delegated pipeline's own budget running out is returned to the model as an observation naming the axis, because the model chose that subtask and can send a smaller one or answer with what it has. Reaching `max_calls` is returned the same way. The run's budget running out raises `BudgetExceeded` and the run stops, the same as anywhere else.

**A delegation can be one call over the calling node's budget**, because the node's axes are checked between its turns. This is the same property as "a single node can overrun the run budget by whatever one of its calls consumes" (§5).

#### What else it reaches

**Everything inside a delegate is declared, not hidden.** The eval runner refuses a rollout over a tool that reaches outside the run, and it reads the tools a delegated pipeline can reach along with the rest (FT-19, FT-20). A pipeline run from inside a tool body instead is invisible to that check, writes its own separate run directory, and spends nothing the outer run's budget bounds.

**A run can stop and continue inside a delegate.** A `consult` in a worker suspends the whole run, and the resumed run finishes that subtask before the orchestrator's next turn. Both conversations survive: the orchestrator's, waiting on the subtask, and the worker's, waiting on the end user (§1.8).

**`suspend_before=True` on a delegated pipeline is refused.** It is read by the walk of the graph a node sits in, and a delegate sits in none. Declare it on the first node inside that pipeline instead.

---

## 3. What a node receives

A node function is handed its inputs and a context object. `Deterministic` and `LLMNode` receive a `NodeContext`; an `AgentNode` receives an `AgentContext`; a `route` receives a `RouteContext`. None carries a model client or tool dispatch.

**The inputs take one of four shapes, decided by the edges declared into the node:**

| Edges into the node | What arrives |
|---|---|
| None, or every one of them closes a cycle back to the first node | What was passed to `run` (§1.4) |
| One | What that node returned |
| More than one | A `Join`, with a key per declared in-edge (§1.3) |
| The edge is an `on_error` that fired | A `NodeFailure` (§1.5) |

A node named as both a successor and the `on_error` handler of one node has a single edge into it, carrying that node's output where it succeeded and a `NodeFailure` where it did not.

### 3.1 Saying what a node reads

A node function's first parameter is what it accepts, and annotating it is how the node says so:

```python
def verify(inputs: Notes, ctx: NodeContext) -> str:
    return f"Check this: {inputs.notes}"
```

That annotation is checked against what reaches the node. A node whose predecessor produces something else is refused at construction, and a value that turns out to be something else is refused when it is handed over, naming both nodes. Nothing has to be annotated: what is written down is read, and a pipeline that annotates nothing is refused nothing.

**A mistyped input does not fail on its own.** A prompt function that interpolates whatever arrived produces a different prompt and a run that completes, so inserting a node between two others changes what the model is asked and reports nothing. The annotation is what turns that into a refusal.

**What is compared.** A refusal needs both sides declared and no value able to satisfy both. `output_schema` is what the node before declared it produces, and a `Deterministic` node that declares none falls back to its function's return annotation. Two different pydantic models disagree, and so do a model and a `dict`. A `Join` read as a `dict` does not, because a `Join` reads by key. A union disagrees only where every member does. Anything unannotated, `Any`, or naming a type that cannot be imported is read as undeclared.

**What it does not see.** A node whose predecessor declares nothing and whose own first parameter is unannotated is not checked, and neither is what was passed to `run` before the run starts. Declaring an `output_schema`, a return annotation, or a first-parameter annotation is what buys coverage on that edge.

`NodeContext`:

| Field | Notes |
|---|---|
| `run_id`, `node_id` | Identify the run and the node. |
| `workspace` | A fresh directory per run. Files the run produces go here, beside the trajectory that records what it did with them. Input data is read from wherever the project keeps it. `docs/tools.md` §4 covers the scoped file I/O built on it. **It is not a way to pass a value between nodes**: see below. |
| `seed` | The run seed, and `None` on a `Deterministic` node, which does not sample. |
| `budget` | What is left of the run budget, narrowed by the node's own where it has one. |
| `item_index` | Which item is being processed under `over=`, and `None` otherwise. |
| `last_input_tokens`, `last_input_chars`, `last_call_index` | What the previous call in this node measured. Filled for a context builder and `None` everywhere else. `docs/context.md` §4 covers reading them. |
| `now()`, `now_ms()` | A UTC timestamp, and monotonic milliseconds for measuring elapsed time. |
| `call_tool(name, **arguments)` | Call one of the tools this node declared. The only route to one, and the call is recorded and served from the cassette. `docs/tools.md` §2. |
| `record_access(resource, direction, inputs=, outputs=)` | Record what this node's own code did to a resource it declared in `touches=`. See below. |

`AgentContext` adds what a loop has:

| Field | Notes |
|---|---|
| `tool_names`, `describe_tools()` | The tools available, so a prompt can describe them. |
| `step` | `0` for the prompt function, which runs once before the loop, and from `1` for a context builder, which runs once per iteration. |
| `tool_calls` | Every call this node has made, what each returned, and whether it succeeded. |
| `finish_attempts` | The `finish` calls a check has already rejected. |

`RouteContext` adds what a route chooses on:

| Field | Notes |
|---|---|
| `successors` | The ids this node declared. A route returning anything else raises. |
| `iteration` | Which time round the enclosing cycle this execution is, counting from 1 per entry, and `None` for a node in no cycle. |

The library records the node, and every model call and tool call made inside it, including when the node raises (FT-13). The one thing a node function adds to the trajectory itself is a resource access, and it adds nothing else.

**A node reaching a store in its own code records the access.** A store reached through a tool is a `tool_call` record holding what was asked for and what came back. The same store reached directly is invisible unless the node says so, and `touches=` alone names it without saying what happened:

```python
def gather(inputs, ctx):
    rows = catalogue.eligible()
    kept = rank(rows)[:12]
    ctx.record_access("catalogue", "read", inputs={"eligible": True},
                      outputs={"rows": len(rows), "kept": len(kept)})
    return kept

node = Deterministic(gather, touches="catalogue")
```

The direction is `"read"` or `"write"`, and a step that does both records one each way. `inputs` and `outputs` are payload fields: the run's redaction applies and sampling drops them, and what they hold is the node's choice, so a step reading 67,353 rows records the count rather than the rows. A resource the node did not declare raises `ConfigurationError` naming what to add. All three node kinds take `touches=` and can record, since a prompt function is plain code too. `docs/view.md` §4.1 covers what the page draws from these, and `docs/trajectory-format.md` §4.5 is the record.

**A value one node writes to the workspace and another reads back is not in the reading node's `inputs`.** Every value that travels on a declared edge is written to the record, which is what lets a node's behaviour be explained from its trajectory and what per-node metrics are computed over. A value routed through a file arrives from nowhere the record names: the reading node's `inputs` do not hold it, and its `outputs` can then carry material that appears in no input of any node. Carry the value on an edge instead, and use the workspace for what a run produces rather than for what a later node needs. §1.3 covers reaching a node further on, `keep=` covers a value that would stop at a fan-out, and §1.4 covers one that accumulates round a cycle.

---

## 4. The output schema, and `unknown`

An `LLMNode` and an `AgentNode` each validate their answer against `output_schema`, a pydantic model.

**A type that is not one is refused at construction.** Pydantic is what renders the schema into the JSON the model is offered and what validates what comes back, so a dataclass or a `TypedDict` would be offered as an object with no properties, telling the model the call takes no arguments, and whatever came back would be accepted unvalidated. `Deterministic(output_schema=...)` takes either, since nothing there is shown to a model.

**The schema has to admit `unknown`.** `Maybe[T]` is `T | Unknown`, and one field typed that way is enough:

```python
from simple_agents import Maybe, Unknown

class Answer(BaseModel):
    answer: Maybe[str]
    source: str | None = None
```

A schema with no `unknown` branch is refused at construction, before any call is made. An agent that cannot report absence reports a guess instead, and in a trajectory a guess and an answer look the same (FT-09).

**Where an output has no absent state**, such as a classification over a fixed label set, `allow_unknown=False` waives the requirement. The waiver is recorded in the run manifest, so a reader of the results can see it was taken.

**A fixed label set unioned with `Unknown` warns at construction.** `Maybe[Literal["a", "b"]]` offers the model a closed list of words and a tagged object, and the word `unknown` belongs to neither, so a model reaching for it produces a response that fails validation and costs a step rather than one recorded as a wrong answer. Naming the tag in the description does not prevent it, so the warning is on the shape:

```python
source: Literal["product_page", "brand_chart", "not_found"]   # and allow_unknown=False
```

Keep the union where the reason for an absence has to travel with it, and expect the retry.

Where the information can genuinely be missing, the branch stays even for a project that needs an answer every time. A schema without it still produces an answer, because the model has a required field and fills it, and nothing in the output separates what it filled in from a fact (FT-09). With the branch, an absence arrives labelled and the project decides what to do with it: ask the end user through `consult`, retry with more context, or count it. `docs/evaluation.md` §3 reports how often it happened, as `abstention_rate`.

**`Unknown` is a successful value reporting an absence:**

```python
Unknown(reason="not published on the product page")
```

`reason` is free text and may be `None`. `Unknown` is falsy, so `if value:` does not treat it as an answer, and `isinstance(value, Unknown)` is the test for it. `null` and `""` are not substitutes: both are compared as answers, which is what separates the rate at which an agent asserts something incorrect from the rate at which it finds nothing (FT-10).

Where a fallback is wanted rather than a branch, `value_or` returns the value or a default:

```python
from simple_agents import value_or

chest_cm = value_or(finding.chest_cm, 0.0)
```

Both shapes of an absence are replaced: the `Unknown` a node returned, and the `{"type": "unknown", "reason": ...}` it becomes through `model_dump()` or a stored artifact. `None`, `""` and `0` come back as they are, and so does the bare word `"unknown"`, which is a value like any other string.

**An absence rendered into text says the word.** `str(Unknown(reason="the schedule does not say"))` is `unknown (the schedule does not say)`, so a template, a log line or a prompt built with an f-string cannot make an absence read as an answer:

```python
f"Airs: {finding.airs}"      # 'Airs: unknown (the schedule does not say)'
```

`repr` still shows the fields, which is what a traceback wants and what a model holding this one renders its own fields with.

**Every description in the schema is sent to the model.** Pydantic takes one from `Field(description=...)` on a field and one from a model's class docstring, and both go on the wire, including the docstring of a model used as a field's type. `json_schema_extra={"description": ...}` on a model replaces the one taken from its docstring.

```python
class Answer(BaseModel):
    """Sent to the model."""

    answer: Maybe[str] = Field(description="Sent to the model.")
```

`Maybe[T]` supplies its own description, saying to send either the value or `{"type": "unknown", "reason": "..."}`. A model shown a union of a string and an object has no other way to tell which one an absence goes in. Pydantic's rule is that a `Field(description=...)` on the field replaces that rather than adding to it, and wrapping the annotation in another union such as `Maybe[str] | None` drops it too.

**A field that can hold an absence is always told how to send one.** Where what the field says names neither branch, the library appends the sentence that does, so the description on the wire says what the value is and then how to send an absence. A description already naming the `unknown` tag is sent as it was written. Writing both is still the clearer thing to do:

```python
answer: Maybe[str] = Field(
    description='The shortest span that answers the question. If the documents do not '
    'answer it, send {"type": "unknown", "reason": "..."}.'
)
```

A node built over a description that names neither warns at construction, and is quiet once the description names the `unknown` tag.

**A field with a default reaches the model as one it must send.** Both adapters ask the backend to constrain the response to the schema, and that request carries a contract: every property listed as required, and no property outside the schema. Pydantic leaves a field with a default out of `required`, so the library puts it back and drops the default before the schema goes on the wire. A nullable field is then one the model has to send holding either a value or `null`, and a field whose type cannot hold `null` is one it has to produce a value for rather than one it may leave to the default.

```python
source_doc: str | None = None      # reaches the model as required, holding a string or null
attempts: int = 1                  # reaches the model as required, and it must choose a number
```

This is what the constraint is worth. A schema sent without it is not rejected, and `mistral-small-2603` answers one by returning field names padded with punctuation, such as `"source_doc "` and `"source_doc: "`, which validate as unknown fields and are dropped: the response parses, the field is missing, and nothing distinguishes that from a model that declined to fill it.

`docs/trajectory-format.md` §5.1 defines how `unknown` is written to a record, and `docs/evaluation.md` §1 covers labelling an example whose correct answer is absent.

---

## 5. Budgets

```python
Budget(max_steps=8, max_tokens=50_000, max_cost=None, max_wall_clock_ms=120_000)
Budget.unbounded()
```

All four arguments are required, so an axis cannot be set by omission. `None` on an axis means unbounded on that axis, and what a pipeline refuses is the absence of a decision rather than an open axis.

**A budget is set in three places.** A budget on a `Pipeline` bounds the whole run. `budget=` on an `AgentNode` bounds one execution of that node, and is required at construction (FT-18). `budget_per_item=` bounds one item of a fan-out, and is refused on a node with no `over=`. `Deterministic` and `LLMNode` take no budget argument and run under what the pipeline allows. A node is held to whichever budget is tighter, and an unbounded axis on either side yields the other side's value, so a node can narrow what the run allows and cannot widen it. The result is what the node's trajectory record carries as its `budget`.

A node's own budget bounds it including its retries, so three attempts of an eight-step `AgentNode` spend eight steps between them rather than eight each. Under `over=` it bounds every item together, so ten items sharing `budget=Budget(max_steps=30, ...)` make thirty calls between them rather than thirty each; §2.3 covers what happens to the items that are left when it runs out. A `Pipeline` nested inside another is bound the same way, over what it has spent since it started.

**Time spent suspended is charged to nothing.** A run that stopped and was continued keeps what it had spent, and its wall clock restarts, so a consultation answered a day later does not exhaust `max_wall_clock_ms` on the first check after the resume (§1.8).

**`max_wall_clock_ms` is elapsed time while the run is executing.** Not the sum of what each call took: a run whose calls overlap is charged the time that passed. Everything the run waits for while it is executing counts, including retry backoff inside an adapter and rate-limit pacing in a `PacedClient`, so a run held behind a quota for forty seconds is charged those forty seconds.

**A tool's execution time counts for the same reason.** A fetch that takes a minute binds `max_wall_clock_ms` the way a minute of model work does, on every node kind, and so does a wait the tool performs internally.

**The per-node `wall_clock_ms` figures in the trajectory are per node.** Once calls overlap the run's total is less than their sum, because the run's is elapsed and each node's is its own duration.

**No axis bounds a cycle.** `max_steps` counts model calls and a cycle of `Deterministic` nodes makes none, so a cycle carries its own bound as `Loop(max_iterations=...)` and one without it is refused at construction (§1.4).

**One step is one model call, and `max_steps` is exact.** The step is taken before the call and a call does not start unless one remains, whether or not calls overlap.

**The other three axes are measured by what a call turns out to consume**, and are checked at the run level between nodes, so a run can pass them by what was already in flight: one call's worth at `concurrency=1`, and up to N−1 calls' worth at `concurrency=N` (§1.11). `max_output_tokens` on the node bounds one call.

**What happens when an axis is exhausted** depends on where it fires:

- Inside an `AgentNode`, it is ordinary termination. The loop stops and the node's record says which axis in its `termination` field.
- At the run level, `BudgetExceeded` is raised, the remaining nodes do not execute, and the manifest records the run as `stopped_early` naming the axis. The trajectory and manifest are still written, so the records from before the stop survive it.

`max_cost` bounds model spend and what the run's tools spend, together. A paid tool call is refused before it is made, model-facing, against the most one call can cost. `docs/run-envelope.md` §4 covers the two cost bases, what a tool reports, and why a figure that is an upper bound ends the run rather than being enforced against.

---

## 6. Running the pipeline without a backend

`FakeModelClient` returns scripted responses without reading the request, so a whole run costs
nothing and takes milliseconds. A run whose calls overlap passes `answer=` instead, a function of
the request, because a queue hands out whatever is next and which call gets which response would
depend on which arrived first (§1.12).

```python
from simple_agents import FakeModelClient, RunEnvelope, fake_response

client = FakeModelClient(responses=[fake_response(content='{"answer": "32 inches"}')])
result = build_pipeline().run(
    {"question": "what is the inseam?"}, envelope=RunEnvelope(run_dir=tmp), model=client
)

client.requests    # every ModelRequest the pipeline sent, in order
```

One response is scripted per model call, in order, and running out raises `AssertionError`
naming how many calls were made. A tool call is scripted the same way:

```python
from simple_agents.models import ToolCallRequest

fake_response(tool_calls=[ToolCallRequest(id="c1", name="search", arguments={"q": "inseam"})])
```

**This exercises what a test over a node's own function does not**: the graph walking, a node
receiving what the one before it produced, the output schema validating, a budget binding, a
route choosing, and the tools actually being called. A crash on an absent value, a `Join` read
wrongly and a budget sized for an earlier shape are all found here rather than on a paid run.

**A node that declares its own model is not reached by this.** `model=` on a node beats the
client passed to `run`, so `LLMNode(build_prompt, model=cheap)` calls `cheap` while the rest of
the pipeline is scripted, and a pipeline whose every node declares one goes nowhere near
`FakeModelClient`. A run meant to cost nothing checks that, since the failure is a full-price
run reported as free. `docs/model-clients.md` §1 covers declaring a model per node.

**The tools are called for real, including the ones that reach a person.** A `consult` channel
that reads a terminal blocks a run that was supposed to take milliseconds, and one that reaches
a network spends. `env.with_end_user(unattended())` answers nothing and blocks nothing, which is
what a fake run wants, and the questions are still recorded so the run says what it would have
asked. Pass a registry whose other tools read fixtures for the same reason the model is scripted
(`docs/tools.md` §4.6.3).

**It cannot show what a backend accepts.** The client does not read the request, so a tool
schema the provider rejects, a conversation shape it refuses, and a model that answers
differently from the script all pass. A run against a real backend is what settles those, and
`Cassette.record` makes the second one free (`docs/run-envelope.md` §3).
