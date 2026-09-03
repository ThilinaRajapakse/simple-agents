# The run envelope

Every run happens inside an envelope, and the envelope records by construction. This document specifies what the envelope produces (the **run directory**, the **manifest** and the **cassette**), what it applies to every run (**redaction** and **seeds**), and how **cost** is derived from what a run recorded.

---

## 1. The shape

A `RunEnvelope` holds what stays the same across runs of one project. What changes from run to run, the input and the seed, is an argument to `Pipeline.run`. No setting appears in both places, so no value has two sources.

```python
from simple_agents import (
    Cassette, PriceBasis, Pipeline, Redaction, RunEnvelope, Trajectory
)

env = RunEnvelope(
    run_dir="runs/",
    cost_basis=PriceBasis(
        currency="USD", input_uncached_per_mtok=3.00, output_per_mtok=15.00
    ),
    redaction=Redaction(secret_env=["MISTRAL_API_KEY"]),   # names, not values
    cassette=Cassette.record("cassettes/qa.jsonl"),
    trajectory=Trajectory.full(),                          # every payload, every run
)

result = pipeline.run({"question": "..."}, envelope=env, model=client, seed=41)
```

Every argument has a default, so a first run needs none of them:

```python
result = pipeline.run({"question": "..."}, model=client)
```

That writes under `runs/`, applies the built-in redaction rules, makes live calls, records them, generates a seed and records that too.

Two of its settings vary by what a run is for rather than by project, and have a copy method each. `role` says the runs through it are not the agent's (§2.1), and `end_user` says who answers a consultation in them, in place of the channel the `consult` tool was registered with:

```python
labelling = env.with_role("labelling")
smoke = env.with_end_user(unattended())        # a run with nobody to ask
```

`docs/tools.md` §4.6.2 covers who a channel may declare, and `docs/evaluation.md` §5.4 the stand-in an evaluation sets here per rollout.

### 1.1 The run directory

```
runs/<run_id>/
    manifest.json      what was configured
    trajectory.jsonl   what happened
    cassette.jsonl     every call, so the run can be replayed (§3)
    workspace/         scoped file I/O for the run's tools
```

`run_id` is generated per run and joins the manifest to the trajectory. `workspace` is what a node's `ctx.workspace` points at, so a tool that writes a file writes it inside the run rather than beside the source.

A generated id carries the UTC time the run started, to the second, and eight characters that separate runs starting inside one second: `run_20260809T014233Z_a3f92c1d`. The parts are fixed width, so a directory listing reads in the order the runs happened. Passing `run_id=` to `Pipeline.run` names the directory instead, which is what an evaluation does when it calls its rollouts `e1-0` and `e1-1`.

An evaluation reuses one envelope across every rollout and varies the seed, which is why the seed is not on the envelope.

---

## 2. The manifest

**The organizing rule: the trajectory records what happened; the manifest records what was configured.** A value that is the same for every record in a run belongs here.

The manifest is written when the run starts and rewritten when it ends. A run that crashed still has one, carrying `outcome: "error"` and the records that were written before the failure.

**Current version: `0.40`**, in the `format_version` field. `CHANGELOG.md` records what changed between versions.

### 2.1 Fields

| Field | Type | Notes |
|---|---|---|
| `format_version` | string | This document's version. |
| `trajectory_format_version` | string | Which version of `docs/trajectory-format.md` the sibling trajectory is written in. |
| `library_version` | string | The version of Simple Agents that produced the run. |
| `run_id` | string | Joins to every record in the trajectory. |
| `role` | string | What the run was for, from `RunEnvelope(role=...)`. `agent` unless the envelope said otherwise, and the only value the conformance checks read. |
| `live` | boolean | Whether an end user was on the other end, from `RunEnvelope(live=True)`. False on a run made while building, which is what the conformance checks read (`docs/shipping.md` §1). |
| `end_user` | object \| null | `answered_by` for the channel this run was given through `RunEnvelope(end_user=...)`, and `null` where the run used the one the pipeline registered. A run given one channel per answerer carries `reaches` instead, an `answered_by` per name, with `answered_by` itself `null`. The `tools` entries carry the registered declaration; this carries the run's. |
| `evaluation` | object \| null | Which rollout of which evaluation this run is: `eval_id`, `example`, `rollout` and `turn`. `turn` is which turn of the rollout's conversation this run was, and 1 for a rollout that is one run. `null` on a run of the agent. A rollout says what it is here, so a reader tells one from a run of the agent without knowing where the directory sits (§1.1). |
| `conversation` | object \| null | The conversation this run is a turn of, from `Pipeline.run(conversation_id=...)`: the store's `directory`, the `id` as the project gave it, the `turn` this run was, `carried_in` (how many earlier messages a node read) and the `node_id` that read them. `null` on a run that is not part of one. `carried_in` of zero past the first turn is a conversation being written and not read (`docs/conversation.md` §6). |
| `started_at` / `ended_at` | string \| null | ISO 8601, UTC, millisecond precision. `ended_at` is `null` in the manifest written at the start of the run. |
| `outcome` | enum | `completed` / `suspended` / `stopped_early` / `error`. |
| `stopped_early` | string \| null | The budget axis that ended the run, `left_the_slice` where the run reached the boundary of a slice, or `null`. |
| `seed` | integer | The run seed. Every call seed derives from it (§5). |
| `concurrency` | integer | The most calls this run could have in flight at once, from `Pipeline.run(concurrency=...)`. `1` means nothing overlapped. |
| `budget` | object | All four axes, `null` meaning unbounded. |
| `cost_basis` | object \| null | `price`, `compute` or `device` with what each declares, or `by_model` holding one of those per model (§4). `null` means cost is unknown for this run. |
| `models` | object | `configured` and `observed` (§2.2). |
| `prompts` | object | Per node: `version` and `source` (§2.3). |
| `slice` | object \| null | What this run's pipeline is a slice of, from `Pipeline.slice`, and `null` where the run is of a whole pipeline. Carries `of`, the source pipeline's `graph_fingerprint`; the `nodes` the slice holds; the `start` and `end` it was taken with, both `null` where the set was named; the ids it `dropped`; and one entry per cut edge under `cut_edges`, each a `from`, a `to` and a `kind`. Two evaluations of two rungs of one pipeline are joined on `of` (`docs/evaluation.md` §5.6). |
| `nodes` | array | One entry per node that can emit a record: `node_id`, `node_kind`, the declared edges (§2.5), a `consultation_route` of what a route built by `on_reply` maps, a `schema` digest of what the node declared it produces, an `accepts` digest of what it reads, the `tools` it offered (§2.6), and on nodes that can call a model, `allow_unknown`, `context_builder` (§2.4), `stream`, `model`, `sampling`, `finish_check`, `node_budget`, `node_budget_per_item` and `fan_out` (§2.6). |
| `containers` | array | One entry per pipeline used as a node: `node_id`, `node_kind`, `nodes` naming its direct children, its own declared edges, and its `budget` (§2.5). Empty where the pipeline nests none. |
| `constants` | array | Every module-level number the project's own code defines, reached from the node callables: `module`, `name` and the `value` the run started with (§2.9). Empty where none were found. Outside `behaviour_fingerprint`. |
| `tools` | array | Per tool: `name`, `version`, `derived`, `side_effect_class`, `declared_cost`, `re_executed`, `offered`, `answered_by`, `reaches`, `permission`. `derived` is a hash of the tool's function, present where `version` is not already it, read the way §2.3 reads a prompt's. `offered` is false for a tool the project registered and gave to no node, which reaches the manifest through `Pipeline(tools=registry)` and through nothing else. `answered_by` is set on a consultation tool and `null` on every other kind, so which tools reach a person is read here rather than guessed from a name (`docs/tools.md` §4.6.2); `reaches` names which answerer the tool asks, for a pipeline that asks more than one, and is `null` where it asks the only one. `permission` carries the builder's agreement where the answerer is the coding agent. Both are the registered channel, and a run given another through `RunEnvelope(end_user=...)` records that on each consultation instead. |
| `redaction` | object | The rules that were in force (§6). |
| `recording` | object | `payload_rate`, and `payloads` as `kept` or `omitted` for this run, with a `reason` where they were omitted (§7). |
| `schemas` | object | The tool declarations and output schemas the run's model calls offered, each under the reference its records carry (§2.7). |
| `mcp` | array | One entry per MCP server the run declared tools from: `server`, `read` saying whether the run read the server or was served a recording, `drift` naming each way the server now differs from what a recording holds, and `undeclared` for the tools it offers that the project did not declare (§2.10). Empty where the project declared none. |
| `fetch_policy` | array | One entry per pipeline that declared a `HostPolicy`, holding what it permitted and what the run admitted while it proceeded: `declared_by`, `hosts`, `admitted` with a reason each, `max_admitted`, `max_fetches` and `fetches`. `declared_by` is the node id of the pipeline that declared it, and `null` for the pipeline the run was started with. Empty where the project declared none. A reachable set that grows during a run is not knowable from the tool declarations alone (`docs/tools.md` §4.3). |
| `graph_fingerprint` | string | A digest of the pipeline's shape: node ids, kinds, edges, loop bounds, error edges, retry policies and output schemas, for the leaves and for every pipeline used as a node. A suspended run refuses to resume against a pipeline whose fingerprint differs. Budgets are outside it and are compared separately. |
| `behaviour_fingerprint` | string | A digest of the shape, every prompt's version, every `Deterministic` node's function version, sampling parameters, every tool's version and declared cost, the model each node calls, `allow_unknown` and the budgets. Wider than `graph_fingerprint`, which is shape alone: an edited prompt, a changed temperature, an edited tool body or a swapped model moves this and none of them move that. **The client passed to `Pipeline.run(model=...)` is in it**, where any node takes it rather than declaring its own, so a project computing the value itself passes the same client: `pipeline.behaviour_fingerprint(model=client)`. A pipeline whose model-calling nodes all declare their own needs no argument, and one with a node that takes the run's refuses rather than returning a value that would not move when the model changed. A project that keeps results beyond the run writes it beside each one, and reads it back from here to say which pipeline produced which stored value (`docs/shipping.md` §6). |
| `resume_waivers` | array | The differences a resume was told to accept, such as `prompts.hunt`. Empty on a run that never suspended. |
| `stream_waivers` | array | Model clients built with `stream_without_usage=True`, by class name. Streamed calls made through them record `unknown` token counts, so a figure that looks low has this to be traced to. Empty otherwise. |
| `unfinished` | object | Per node, the units of work that ended without producing an output: `executions`, `items` (of a fan-out), `without_tool_calls` (of those two, the ones that made no tool call, consultation or delegation) and `model_calls`, what they spent. Read off this run's own trajectory when it ends, so aggregating many runs opens one small file each. A node with nothing to report is absent, so `{}` is a run in which every unit of work produced something (§2.8). |
| `suspensions` | array | One entry per node that stopped: `suspended_at`, `node_id`, `waiting_for`, and `resumed_at`. A run whose overlapping arms stopped together has an entry each, so the manifest names every question the run was waiting on. A resume closes every open entry, and the gap between the last two fields is time no budget was charged for. |
| `cassette` | object | `mode`, `path`, `dropped`, and the run's `hits`, `misses`, `recorded`, `diverged`. `diverged` counts requests already on file whose response came back different, so a non-zero count means the backend does not reproduce its own sampling (§5). `dropped` is `null` while the file is on disk and names the reason where the run deleted it, which is a default recording on a run whose payloads were sampled out (§7). |
| `memory` | object | The memory this run reached: the store's `directory`, a `scope_digest` of the scope the run named, and `entries`, how many facts it held when the run ended. `null` where the envelope declared no store or the run named no scope. The scope itself is not recorded, since it usually identifies a person (`docs/memory.md` §1). |
| `retrieval` | array | One entry per tool that searched a `DocumentIndex`, counted when the run ended: the `tool`, how many `documents` the index held, how many of them have `vectors`, the `store` those are in and whether it is `exact`, and `embedded_by`. A run that added documents leaves the count it finished with. How the index ranks is on the tool's own entry under `tools`, since that decides what a search returns and this does not (`docs/retrieval.md` §4.4). |
| `paths` | object | `trajectory` and `workspace`. |
| `counts` | object | `records`, and one count per record type, including the types this run wrote none of. |
| `totals` | object | `tokens`, `cost`, `tool_spend`, `charged_cost` (all §4), and `held_back_ms`. The last is how long the run's model calls spent waiting before the attempt that succeeded, summed: retry backoff after a rate limit, and any wait a `PacedClient` imposed. The waiting is elapsed time and `max_wall_clock_ms` is charged for it, so comparing this total against the wall clock is what separates a throttled run from a slow one. A call that exhausted its retries counts here too, on the run that its failure ended: the run waited, and the wait is what explains its wall clock. |

**`role` separates the agent from work the project does for itself.** A labelling pass and a
model judging another model's answers are both model calls a project makes, and running each
through the envelope is what gives it a manifest, a cost and a model pin. They are not runs of
the agent, so they say what they are:

```python
env = RunEnvelope(run_dir="runs/", cost_basis=PRICES)
labelling = env.with_role("labelling")
```

The value is any non-empty string the project chooses. Every conformance check that reads a run
reads the newest run whose role is `agent`, so these can be written into `runs/` beside the
agent's own and none of them is read as one. The report's header names the run those checks
read by its nodes, so a pass that was left undeclared shows there (`docs/conformance.md` §4).
A project whose only runs declare another role fails FT-13, and the reason says what was found.
`runs("runs/", role="labelling")` reads them back, and a run written before this field existed
counts as `agent`.

**The library declares one role itself.** Every arm of a `compare_variants` sweep but the
baseline runs under `role="variant"`, since an arm is a pipeline the project does not have
(`docs/evaluation.md` §10). Everything else is the project's own to declare.

**A resumed run keeps the role its manifest records**, not the one the resuming envelope
declares, because a resume continues one run rather than starting a second (§8). A labelling
pass that stopped to wait for a person is still a labelling pass when it continues, and one
envelope can resume whatever it finds.

### 2.2 `models`

```json
{
  "configured": {"backend": "self_hosted",
                 "request_model": "Qwen/Qwen3-8B",
                 "model_revision": "a1b2c3d"},
  "observed": [{"backend": "self_hosted",
                "request_model": "Qwen/Qwen3-8B",
                "response_model": "Qwen/Qwen3-8B",
                "model_revision": "a1b2c3d",
                "calls": 4}]
}
```

`configured` is what the client passed to `Pipeline.run(model=...)` reports before any call is made. `observed` is what actually served each call, gathered as the run proceeds. The two differ when a provider serves a different model from the one requested.

**A node can declare its own client** (`docs/pipeline.md` §2.4), and `nodes[].model` holds what each node declared, `null` where it takes the run's. So the model that served a node is its own `nodes[].model` where it has one, and `models.configured` where it does not. `configured` is `null` on a run whose nodes all declare their own.

FT-14 reads every identity that resolution produces, and reports one failure per unpinned one, naming the nodes it serves.

**What counts as pinned depends on the backend.** A dated model string is a hosted provider's promise that the identifier keeps resolving to the same weights. A commit SHA is proof that it did. A bare repo ID, or a branch name such as `main`, is an alias and fails FT-14.

### 2.3 `prompts`

```json
{
  "extract_inseam": {"version": "v3", "source": "declared", "derived": "sha256:e08ba8d1f3e1"},
  "summarise":      {"version": "sha256:9f2c1a4b0e77", "source": "derived"}
}
```

`source` is `declared` where the node was constructed with `prompt_version="v3"`, and `derived` where it was not, in which case the version is a hash of the prompt function's source. `unavailable` means the source could not be read, which happens for a prompt defined in a REPL, and leaves a regression with nothing to trace it to (FT-15).

**`derived` is that hash where a version was declared**, and absent where it would repeat `version`. Only `version` decides what an evaluation directory is named and what `behaviour_fingerprint` covers, so declaring one means a cosmetic edit moves no figure. `derived` is what says the edit happened: a declared version that stayed put over a moved source is reported when rollouts are resumed or rescored, and `simple_agents.prompt_differences(run_dir, against=...)` names it across two evaluations (`docs/evaluation.md` §6.8).

### 2.4 `context_builder`

```json
{"node_id": "hunt", "node_kind": "agent", "allow_unknown": true,
 "context_builder": {"name": "AppendAll", "config": {"max_input_tokens": 200000}}}
```

Which context builder each node ran with, and how it was configured. `config` is whatever that
context builder reports about itself, and `{}` for one that reports nothing. `docs/context.md`
§4 covers writing one, and §5 covers what a call records.

Swapping a context builder changes what the model is sent without changing the prompt
function's source, so `prompts` does not move. This entry is what a score change after a swap
is traced to (FT-17).

### 2.5 The declared edges

```json
{"node_id": "critique", "node_kind": "llm",
 "successors": ["draft", "publish"],
 "route": {"version": "sha256:41ab7c0d9e12", "source": "derived"},
 "loop": {"max_iterations": 3, "then": "publish"},
 "on_error": null,
 "retry": null}
```

The graph the run was configured with. `successors` is the resolved list, so a node that took
the default of the next node in the list reads the same as one that named it, and a node that
ends its pipeline has `[]`. `route` is versioned the same way a prompt is (§2.3) and is `null` on
a node that declares none. A route decides which nodes run, so a routing change is traced the
same way a prompt change is (FT-15). Every id an entry names is written under the id that node
records, so an edge inside a nested pipeline reads as `research.verify` rather than `verify`.

**A nested pipeline is expanded into its own nodes** in `nodes`, under ids prefixed by the
containing node's. So `nodes` names what the trajectory will hold and per-node metrics will be
keyed on, and a pipeline used as a node is not there because it emits no `node_execution` record.
`docs/pipeline.md` §1.6 covers composition.

**What that pipeline declares is in `containers`**, and reading the two arrays together is what
gives the whole graph:

```json
{"node_id": "research", "node_kind": "pipeline",
 "nodes": ["research.hunt", "research.verify"],
 "successors": ["write"],
 "route": null, "loop": null, "on_error": null, "retry": null,
 "suspend_before": false,
 "budget": {"max_steps": 6, "max_tokens": 20000, "max_cost": null, "max_wall_clock_ms": null},
 "reached_by": null}
```

`nodes` is the direct children in declaration order, and the first is where a value arriving at
this pipeline goes. The edges are here rather than on any child: an error edge fires from
wherever inside the pipeline the failure happened, and a child may declare a `retry` of its own,
which re-executes that child rather than the whole pipeline. `budget` is the bound this pipeline
holds beside the run's, and is not in the `graph_fingerprint`.

So `research.verify` has `successors: []` and `research` has `successors: ["write"]`. What
`research.verify` produced goes to `write`, and the two entries are what say so.

**A pipeline a model may delegate to is in `containers` too, and declares no edges**, because a
model call is what reaches it rather than an edge. `reached_by` is what joins it to the rest of
the graph:

```json
{"node_id": "orchestrate.research", "node_kind": "pipeline",
 "nodes": ["orchestrate.research.widen", "orchestrate.research.hunt"],
 "successors": [], "route": null, "loop": null, "on_error": null, "retry": null,
 "suspend_before": false,
 "budget": {"max_steps": 6, "max_tokens": 20000, "max_cost": null, "max_wall_clock_ms": null},
 "reached_by": {"kind": "delegation", "node_id": "orchestrate", "max_calls": null,
                "description": "sha256:342bc0c83fb728b6",
                "input_schema": "sha256:7d85bde0592bafde"}}
```

`node_id` under `reached_by` is the node whose model sends the subtasks. `description` and
`input_schema` are digests of what the model was shown, so a reworded description is traced the
way a prompt edit is (§2.3) rather than counting as a change of shape: they are outside the
`graph_fingerprint`, and which node reaches the delegate is inside it. `docs/pipeline.md` §2.5
covers declaring one.

The trajectory says which of these edges each execution actually took, as `route` on a
`node_execution` record (`docs/trajectory-format.md` §3). The manifest says what was possible;
the trajectory says what happened.


### 2.6 What a node declared

`node_kind` and the edges say what the pipeline looks like. These say how the node was configured, which is what a metric that moved has to be traced against (FT-15).

| Field | Holds |
|---|---|
| `sampling` | `temperature`, `max_output_tokens` and any backend passthrough in `extra`, as declared on the node |
| `finish_check` | a source version of the node's finish check, or `null`. Editing one moves terminations and step counts |
| `node_budget` | the node's own budget, bounding one execution of it, or `null` |
| `node_budget_per_item` | what one item of a fan-out is bounded by, or `null`. A fan-out declaring only one of the two is constructed with a warning, and these two are where a reader sees which was left open |
| `fan_out` | `over`, `keep` and `max_failures` on a node that fans out |
| `planned` | whether the node is a `NotBuilt` placeholder, declared before its code exists. FT-40 counts every one at every stage and fails from stage `ship`; it reads them from `agent.py`, and from this field where the code declares no pipeline it can find |
| `touches` | the resources the node declares it reads or writes directly, beside the ones its tools declare (`docs/view.md` §4) |
| `model` | the client this node declared, and `null` where it takes the one the run was given (§2.2) |
| `allow_unknown` | whether the node accepts an `unknown` branch of its output schema |
| `allow_unfinished` | on an `agent` node alone: whether a loop that spends its budget without acting is expected here, which is what FT-35 reads |
| `context_builder` | `name` and `config` (§2.4) |
| `stream` | whether this node's calls may be streamed |

A `deterministic` node carries none of them, and carries one the others do not:

| Field | Holds |
|---|---|
| `fn` | a source version of the node's own function, in the shape §2.3 uses. `Deterministic(version=...)` declares one; left unset it is a hash of the source |

A `Deterministic` node's whole behaviour is that function, so nothing else on its entry moves when the body is edited. Declare a version where the function reads a corpus, a table or a store, since that data changes without the source changing.

**Two fields are on every kind, including `deterministic`.** `tools` holds the names this node
offered, sorted: a `Deterministic` node can take `tools=` and call them through `ctx.call_tool`,
and a pipeline-wide list cannot say a tool was removed from one node while another still
declares it. `consultation_route` holds what a route built by `on_reply` maps, and `null` for
any other route: a route factory returns a closure whose source is identical whatever mapping it
closed over, so the version alone says a change happened and this says what changed. It carries
`exhaustive`, the waiver of the unmatched and declined branches (`docs/tools.md` §4.6.1).

`accepts` is the one field on this list that every kind carries. It is a digest of the type the node's function declares for its first parameter, and `null` where the function declares none. A node whose successor stopped agreeing with it produced what it always produced, so the change is on the reading side and no other field records it. It is outside `graph_fingerprint`: a resumed run rebuilds each value in flight from the schema of the node that produced it, so what a node reads leaves the stored state as valid as it was. `docs/pipeline.md` §3.1 covers what the declaration does.

### 2.7 `schemas`

The tool declarations and output schemas the run's model calls offered, each stored once:

```json
"schemas": {
  "sha256:0a1b2c3d4e5f6789": [{"name": "document_search", "description": "...", "input_schema": {...}}],
  "sha256:9f8e7d6c5b4a3210": {"type": "object", "properties": {"answer": {...}}}
}
```

A `model_call` record carries `params.tools_ref` and `params.output_schema_ref` rather than the blocks (`docs/trajectory-format.md` §4.1.5). The set offered is the same on every call a node makes, and a manifest holds one copy of each distinct block whatever the run's length.

**The reference is a digest of the block as it was sent.** Two calls that offered different tools carry different references, so which set was offered stays readable per call. A trajectory read without its manifest keeps the references and loses the descriptions.

### 2.10 `mcp`

One entry per MCP server this run declared tools from, and empty where it declared none.

```json
"mcp": [{"server": "tickets", "read": "live",
         "drift": [{"tool": "tickets_create", "difference": "schema"}],
         "undeclared": ["tickets_purge"]}]
```

`read` is `live` where the run reached the server, and `replayed` where it was served the
listing from the cassette. A replayed run reaches no server, so it records no drift and no
undeclared tools: it is being served the recording rather than compared against it.

`drift` is one entry per difference between what the server offers now and what a recording
already held, so it is filled only on a run that has both, which is a recording being updated.
`difference` is `added`, `withdrawn`, `description` or `schema`. FT-43 reads it.

`undeclared` names what the server offers that `effects=` did not, which cannot be called. It
is what a project reads to see what a server gained since the declaration was written.

What each tool declared, and what its server claimed about it, is on that tool's own entry under
`tools` rather than here (`docs/tools.md` §7.3).

### 2.8 `unfinished`

What this run paid for and got nothing out of, per node:

```json
"unfinished": {
  "look_closer": {"executions": 1, "items": 0, "without_tool_calls": 1,
                  "model_calls": 18, "model_calls_without_tool_calls": 18}
}
```

An `AgentNode` produces its output from a `finish` call, so an execution that stopped on a budget axis or on a `finish` its own check kept rejecting returns `None` to the node after it. The run completes and records no error, which is why nothing else reports it. `executions` counts those, `items` counts the fan-out items that ended the same way, and `model_calls` is what all of them spent, including the calls their tools made.

**`without_tool_calls` is the sharper figure.** It counts the executions and items that made no tool call, no consultation and no delegation, so the loop spent its whole allowance without once acting, and `model_calls_without_tool_calls` is what those spent. A cap that binds after real work is the cap doing its job; a loop that never acted is a prompt or a tool declaration the model could not use, and it is what FT-35 fails a project for.

**A node with nothing to report is absent**, so `{}` is a run in which every unit of work produced something.

**It is read off this run's own trajectory when the run ends**, so a reader aggregating many runs opens one small manifest each rather than every record they wrote. A run whose payloads were dropped by sampling has already lost them by then, so the manifest says what a reader of that trajectory can see and no more.

`node_metrics(run_dir)` reads the same figures out of the trajectories, with everything else a node did beside them (`docs/evaluation.md` §5). `simple-agents check` reads this block from every run one pipeline made, which is the one check that reads more than the newest run (`docs/conformance.md` §3.7).


### 2.9 `constants`

Every module-level number the project's own code defines, one entry each:

```json
"constants": [
  {"module": "catalogue.ranking", "name": "WEIGHT", "value": 0.0024},
  {"module": "catalogue.ranking", "name": "MIN_RATING", "value": 6.0},
  {"module": "agent", "name": "CANDIDATES_WANTED", "value": 8}
]
```

**A number written into the code changes what the agent does, and somebody chose it.** `constant` is one of the six decision kinds for that reason, and a `constant` decision names the numbers it settled under `produces`. `simple-agents check` reads this array against those names and prints the ones no decision covers (`docs/conformance.md` §4.4).

**How the modules are found.** The node callables are the way in: the prompt functions, the `Deterministic` bodies, the routes, the finish checks and the tool functions. The modules those are written in are read, and so are the project's own modules they import, transitively. An installed package stops the walk, so a dependency's numbers and Simple Agents' own are not recorded. `Pipeline.manifest_constants()` returns the same array without running anything.

**What counts as one.** A module-level assignment of a numeric literal to a name that does not begin with an underscore. `True` is not one. The name is read from the module's source, so a constant imported from elsewhere is recorded where it is written and not again beside every import of it; the value is what the module held when the run started, so a number rebound at import time is recorded as what the run used.

**It is outside `behaviour_fingerprint`.** A number in a module the pipeline imports is not something the pipeline declares, and a stamp that moved whenever any of them changed would make a stored result stale that was not. Editing a constant does not move the fingerprint, so a project that keeps results beyond the run and changes a number re-runs what it stores on its own judgement (§6 of `docs/shipping.md`).

---

## 3. The cassette

A cassette stores every model call and tool call a run makes, keyed by the content of the request. Replaying serves them from the file, so the run makes no network call and spends nothing. This is what lets an evaluation run in CI (FT-21), and what stops a tool that writes or spends from executing once per rollout (FT-20).

```python
Cassette.into_run()                     # live calls, recorded in the run's own directory. The default
Cassette.off()                          # live calls, nothing stored
Cassette.record("cassettes/qa.jsonl")   # live calls, appended to the file
Cassette.replay("cassettes/qa.jsonl")   # no live calls, served from the file
Cassette.update("cassettes/qa.jsonl")   # served where there is an entry, live where not
```

**Every run records.** The default writes `<run_dir>/<run_id>/cassette.jsonl`, beside the
manifest and the trajectory, so a run can be replayed or re-scored after the fact. The run's id
does not exist when the envelope is constructed, so the path is filled in as the run starts.
Which run turns out to be worth replaying is not knowable while it is running, and a recording
that was not made cannot be made afterwards.

**The recording goes with the trajectory's payloads.** A run whose payloads are sampled out has
its default recording deleted when it closes (§7), so a project keeping less than everything
does not keep the same content in a second file. A cassette the project named is its own file
and is left where the project put it. `Cassette.off()` is what states that a run records
nothing.

Recording appends and never overwrites. An edited prompt hashes to a different key and records as a new entry, so a collision means the identical request was made a second time. If it came back different, both responses are kept and the manifest counts the divergence (§5). Replay serves the first response recorded for a key, so a replay is reproducible and an earlier run stays replayable after a later one has been recorded into the same file. Deleting the file records from nothing.

**One path per recording**, which follows from serving the first response. A second recording into a file that already holds one is written and never read, so `Cassette.record` refuses a file that is not empty and names `Cassette.update` for filling in the calls a file does not have. Two evaluations recorded into one path would leave the second replaying the first's answers under the second's name.

One cassette is shared by every run made through an envelope, including runs on separate threads, and its file and its index are guarded by a lock.

**A cassette replays the run it recorded**; a later run asking for something that run did not ask for calls out for it. A `UrlCache` on the fetch and search tools is what stops a second run re-requesting a page an earlier one read (`docs/tools.md` §4.5). A run replaying from a cassette never reaches that store, and a *recording* run does, so the cassette then holds whatever the store served.

### 3.1 The key

A model call is keyed on the model identity, the messages, the sampling parameters, the tools offered, and the seed:

```
ck_ + sha256({backend, request_model, model_revision, messages, params})[:16]
```

`params` is the configuration as sent: the seed, the sampling parameters, the contents of `extra`, the tool declarations offered, and the output schema.

A tool call is keyed on `{node_id, tool_name, tool_version, arguments, occurrence}`, where `occurrence` counts how many times that same call has already been made in that node. The count belongs to the node so that one node's recorded calls survive an edit to another's. `docs/tools.md` §3.1 covers what that requires of a tool, and §3.2 which tools are not keyed at all.

Model identity and the seed are both in the key, so switching models or changing a seed is a miss rather than a replay of the old response.

**The seed a call is keyed on is derived from the run's**, so a replay has to run at the seed the recording ran at. Every entry records it, and a replay that is given no `seed=` takes it from the file:

```python
pipeline.run(inputs, envelope=RunEnvelope(cassette=Cassette.replay("cassettes/qa.jsonl")))
```

A `seed=` that is passed is used instead. `Cassette.replay(path).recorded_seed` is the seed the file names, and `None` where it names none or several.

**A file recorded by runs at several seeds is refused** when no `seed=` is passed, because no one of them is the run to replay. That is what one evaluation's cassette holds: a rollout per seed. Pass the seed of the run to replay, or replay the whole evaluation through `EvalSuite.run`, which passes each rollout its own.

A file recorded before entries carried a seed names none, and a run replaying it generates one as before, so `seed=` is how it is replayed.

### 3.2 A miss

Any change to a keyed field means there is no entry, and replay raises `CassetteMiss` naming what changed:

```
No recorded response for call 0 of node 'extract_inseam' in cassettes/qa.jsonl.

The nearest recorded request for this node differs in:
  messages[0].content (recorded 412 chars, now 468 chars)

A recorded response answers the request it was recorded against, so replaying it
here would report a result the current code does not produce. Re-record with
Cassette.record('cassettes/qa.jsonl'), or revert the change.
```

A miss means the recorded response answers a request the current code no longer makes. Re-record, or revert the change.

Where the difference is the seed, the message names the run seed the entry was recorded at, which is the value to pass rather than the derived one on the request:

```
The nearest recorded request for this node differs in:
  params.seed (recorded 1564526049, now 102003894)

That entry was recorded at run seed 1927391078. A call's seed derives from the
run's, so pass seed=1927391078, or pass no seed and it is taken from the cassette.
```

### 3.3 `replay`

Token counts, concurrency, finish reason, content and the rate-limit allowance come back as recorded, so a replayed run reports what the live run met. A field absent from an entry replays as `null`, so a cassette written before that field was recorded still replays.

**Where the chunks fell comes back as well**, on a call that streamed: the sink receives the pieces the recording delivered rather than one lump, with no delay between them and the recorded time to first token on the `model_call` record. An entry recorded without streaming replays as one piece and records `stream: null`. Streaming is no part of the key (§3.1), so a recording made while streaming replays into a run that does not, and the other way round.

**Device time comes back too**, on the `model_call` record's `recorded_duration_ms`, so a compute-basis cost derived from a replay is what the live call spent rather than what the replay took. A cassette recorded before that field existed carries no duration, and a compute-basis cost derived from it reports unknown (§4.2).

A tool that failed with a model-facing error replays as that failure. A tool that failed any other way is not stored, because that run was invalid. `docs/tools.md` §1.3 covers which is which, and §3 covers the tools that are re-run on replay rather than served from the file.

`finish` does not go through the cassette: it is schema validation inside the library, with nothing external to serve from a file. It is still recorded. The call writes a `tool_call` record with no cassette key, each rejected attempt writes one carrying its rejection, and the `node_execution` record's `termination` says whether the node ended on an accepted answer, on one payload refused three times, or on a budget.

### 3.4 `update`

`update` is for iterating on a pipeline. Editing one node's prompt leaves every earlier node's calls on file and re-runs only what changed, where re-recording pays for the whole run again. On a pipeline of four nodes a change to the last one costs one call instead of four, and an evaluation multiplies that by k×n.

**It never serves a recorded response for a request it was not recorded against.** An edited request hashes to a key with no entry, so it is a miss, and a miss under this mode is answered by a live call recorded under the new key. The old entry stays on file and is never served for the new request.

What it does risk is a run intended to be offline making live calls. Three things make that visible: the manifest records `cassette.mode` as `update`, it counts `hits` against `misses`, and every `model_call` and `tool_call` record carries `replayed`, which is what FT-21 reads. An evaluation refuses this mode, so a reported number comes from a run that was all live or all replayed rather than a mixture of the two. A variant comparison is the exception, because it decides before the run which calls the recording answers and records the split (`docs/evaluation.md` §10).

---

## 4. Cost

Cost is never stored on a record. It is derived from the record against the basis the manifest declares, so a trajectory read after a rate change re-prices correctly (`docs/trajectory-format.md` §6). A stored figure cannot be re-derived, cannot be audited, and goes stale silently (FT-27).

### 4.1 The three bases

```python
PriceBasis(currency="USD",
           input_uncached_per_mtok=3.00,
           input_cache_read_per_mtok=0.30,
           output_per_mtok=15.00,
           cache_write_per_mtok_by_ttl={"5m": 3.75, "1h": 6.00})

ComputeBasis(currency="USD", device="H100-80GB", device_count=1, hourly_rate=2.69)
```

Under `price`, each token class is charged at its own rate. Costing a single input figure at the uncached rate misprices any cached workload, and on a large cached prefix the error is most of the bill.

Under `compute`, a call is charged `duration × device_count ÷ concurrent_requests × hourly_rate ÷ 3600`. Omitting the division charges every concurrent request for the whole device, which overstates cost by the batch factor and makes a well-batched local model look expensive.

**Declare a `ComputeBasis` when the hour is billed to someone.** A device the project owns has no hourly rate to read off an invoice, and inventing one produces a figure nobody pays.

**`DeviceBasis` is for that case**, and reports what the run used rather than what it cost:

```python
DeviceBasis(device="RTX-3090", device_count=1)
```

A call is charged `duration × device_count ÷ concurrent_requests`, which is the compute arithmetic without the rate, and the figure comes back in `device_seconds`. That is a unit rather than a currency, so nothing adds it to a figure in money and it fixes no currency for the run. `max_cost` is refused against it and names `max_wall_clock_ms`, which is what bounds such a run.

**A run whose own calls overlap is measured, not estimated, where the backend reports concurrency.** `concurrent_requests` divides under both `compute` and `device`, so a fan-out at `concurrent_items=8` against a server that reports its batch is charged its share rather than eight whole devices. `docs/model-clients/vllm.md` §5 covers turning that reading on.

**A run whose nodes call different models declares one basis per model**, keyed by the identifier the client reports as `request_model`:

```python
env = RunEnvelope(run_dir="runs/", cost_basis={
    "mistral-large-2512": PriceBasis(currency="USD", input_uncached_per_mtok=2.0,
                                     output_per_mtok=6.0),
    "Qwen/Qwen3-1.7B": ComputeBasis(currency="USD", device="RTX3090",
                                    device_count=1, hourly_rate=0.22),
})
```

Each call is priced against the basis for the model that served it, and the run totals in one currency across both. The manifest records `kind` of `by_model` with the bases under `bases`. A call to a model the mapping does not name prices as `null` with a reason, and where `max_cost` is set the run is refused before it starts.

**Two runs are refused before the first call**, because one basis cannot price them:

| Refused | Why |
|---|---|
| One basis, and the run calls both a hosted and a self-hosted backend | A hosted call is priced on tokens and a self-hosted one on device time |
| One `PriceBasis`, and the run calls more than one model | Per-token rates belong to one model, so the others would be priced at its rates |

One `ComputeBasis` over several self-hosted models is not refused: a device rate is a property of the deployment, so two models served by the same devices are priced by the same figure.

### 4.2 When a figure cannot be produced

| Situation | Result |
|---|---|
| No basis declared | `value` is `null`, with a reason. |
| A token count reported as `unknown` | `value` is `null`. An unmeasured count is not zero. |
| A token count reported as `unknown` whose rate is declared `0.0` | `value` is the price of the classes that were counted. No value of that count changes the total. |
| Cache tokens written at a TTL with no declared rate | `value` is `null`. |
| A call with no `ended_at` under `compute` or `device` | `value` is `null`. |
| A call replayed from a cassette that stored no device time | `value` is `null` under `compute` and `device`. Re-record to price the run. |
| `concurrent_requests` is `null` under `compute` or `device` | `value` is the whole device, flagged `is_upper_bound`. |

An unknown call makes the run total unknown, and a bounded call makes the total a bound. A total that dropped the calls it could not price would report less than was spent.

**What the calls that did price came to is `measured`, beside the total that is `null`.** `priced_calls` and `unpriced_calls` say how much of the run it covers, so a run that met a rate limit part way through still reports what it spent:

```json
"cost": {
  "value": null, "currency": "USD", "basis": "price", "is_upper_bound": false,
  "reason": "tokens.input_uncached is unknown on this call. An unmeasured token count is not zero, so the call has no price",
  "measured": 5.5024, "priced_calls": 940, "unpriced_calls": 54
}
```

`measured` is a floor and `value` is the figure to report. A run with one unpriced call has no total, because an unmeasured token count is not zero, and reading the floor as the total would state a number the run cannot support. `simple-agents report` prints it as `at least 5.5024 USD` with the missing calls counted beside it, and an evaluation's results file carries the same three fields with `unpriced_nodes` naming the nodes those calls were in (`docs/evaluation.md` §8.1).

Both figures are always present, and `measured` is `null` where no call could be priced at all.

### 4.3 What a tool spent

Model cost is derived from token counts against the basis. A tool's spend is not derived: it is what the tool was charged, which nothing in the run observes, so the `tool_call` record carries it as `spent` and the manifest sums it (`docs/trajectory-format.md` §4.2).

```json
"totals": {
  "cost":         {"value": 0.0995, "currency": "USD", "basis": "price", "measured": 0.0995, ...},
  "tool_spend":   {"amount": 0.180, "currency": "USD", "calls": 36, "source": "measured"},
  "charged_cost": 0.2795
}
```

`cost` is model spend and nothing else. `tool_spend` is what the tools cost, over the calls that bought something. `charged_cost` is the two together, which is what `max_cost` bounds.

**A tool reports what it was charged by taking a `SpendMeter`** (`docs/tools.md` §1.5). Where it does not, its `declared_cost.per_call` is used and `source` says `declared`. A price is what a tool charges; a call served from a cassette, one that failed, and one a cache answered all reach it and buy nothing.

**A run uses one currency.** Two would have to be added to make a total, so a tool whose `DeclaredCost` names a currency other than the cost basis' is refused before the run starts, and a `SpendMeter` reporting a second one is refused at the call that reports it. A tool whose vendor bills in something else converts inside the tool.

### 4.4 `max_cost`

`max_cost` bounds model spend and tool spend together.

**A paid call is refused before it is made**, against the most one call can cost: `max_per_call` where the tool declares one, otherwise `per_call`. The refusal is model-facing, so the agent is told to answer with what it has rather than the run being ended. A tool that declares no ceiling can take the run past the limit by whatever that one call cost beyond its declared price.

**A model call is charged after it returns**, so `max_cost` is checked between nodes like the other axes, and the `node_execution` record's `termination` says `max_cost`.

**`max_cost` is never enforced against a figure that is an upper bound.** Under a compute basis a call whose backend reported no concurrency is charged the whole device, which can be several times what it cost, and terminating on that ends runs that were inside their limit. The run ends on the first such call instead, naming `report_concurrency=True`. A run that sets no `max_cost` records the bound and continues. The call is recorded before the run ends: the manifest carries the model it ran on, its tokens and the bound, so a reader auditing what that run spent sees the call its trajectory holds.

**Setting `max_cost` without declaring a cost basis is refused before the run starts**, where the pipeline can make a model call. No cost could be derived for it, so the limit would bound only what its tools report (FT-27 with FT-18). A pipeline of `Deterministic` nodes whose only spend is a paid tool needs no basis.

### 4.5 Re-pricing a run from its record

The trajectory stores counts and the manifest stores the basis, so cost is derived on read rather than fixed at write. Three functions do the arithmetic outside a run:

```python
import json
from dataclasses import replace

from simple_agents import basis_from_manifest, runs, total_cost

run = runs("runs/")[0]
recorded = basis_from_manifest(run.manifest.get("cost_basis"))
records = [json.loads(line) for line in run.trajectory_path.read_text().splitlines()]

total_cost(records, recorded)     # what the run itself derived
total_cost(records, replace(recorded, input_uncached_per_mtok=0.15,
                            output_per_mtok=0.60))     # the same calls at other rates
```

**Start from the recorded basis and change the rates that moved.** A missing rate is not a rate of zero, and an unmeasured count under a nonzero rate has no price: either makes the total unknown rather than understated (§4.2). The recorded basis already carries the shape the backend's reporting requires, such as a cache-write rate of `0.0` on a backend that reports no cache-write count and bills storage separately.

- **`basis_from_manifest`** rebuilds the basis a run recorded, for a reader holding the runs and not the envelope that wrote them. A block whose kind this version does not read returns `None`, so an unrecognised basis reports unknown cost rather than a figure derived wrongly.
- **`cost_of(record, basis)`** prices one `model_call` record, and raises on a record of any other type. A `basis` of `None` returns an unknown cost.
- **`total_cost(records, basis)`** prices every `model_call` in `records` and skips the other record types. One unknown call makes the total unknown, and one upper bound makes the total an upper bound; a total that dropped the calls it could not price would report less than was spent. Under a per-model basis, each call is priced against the basis for the model that served it.

`node_metrics("runs/", cost_basis=...)` reports the same arithmetic per node (`docs/evaluation.md` §5.5), and `simple-agents report runs/` prints it per run.

---

## 5. Seeds

One seed governs a run. Each call gets its own, derived from it:

```
call_seed = int(sha256(f"{run_seed}:{node_id}:{call_index}")[:4 bytes]) & 0x7FFFFFFF
```

The mask keeps the result a non-negative 32-bit integer, which is the range backends accept.

The manifest records the run seed. Every call seed in the run reconstructs from it, so re-running at the same seed sends the same request, which is what makes a cassette recorded from one run replay against another.

**Sending the same request is not the same as getting the same response, and which one a backend gives depends on the backend.** A hosted API treats a seed as best-effort: requests are batched, and the arithmetic of a batch depends on what else was in it, so a token that was nearly tied can come out the other way. Measured against Mistral at `temperature=0` with a fixed seed, 23 of 376 distinct requests came back different on a later occasion. A self-hosted server under fixed configuration is closer to reproducible, and still not guaranteed under continuous batching.

**What this means for a run.** Exact reproduction comes from the cassette, not from the seed. The seed makes the request identical, records what sampling was asked for, and gives every call in a run its own value; replay is what returns the same answer. A run that needs to be repeatable offline records a cassette, and `cassette.diverged` in the manifest (§2.1) says whether the backend reproduced itself while recording.

**A run with no seed given generates one and records it.** Reproducibility does not depend on remembering to ask for it (FT-07). Passing `seed=` sets it explicitly, which is what an evaluation does per rollout.

**A run reading from a cassette takes the seed from the file** rather than generating one, so a run recorded without a seed replays without one (§3.1).

**A `Deterministic` node records `seed: null`.** It does not sample, and an absent seed there is a fact rather than an omission.

---

## 6. Redaction

Redaction runs as each record is written, rather than as a pass over the file afterwards. A trajectory stores full inputs and outputs, so a tool call carrying an auth header writes that header to disk, and a run that stops partway would leave it there (FT-16). The same rules apply to the cassette, which a project keeps so its evaluation can run offline (FT-21).

```python
Redaction(secret_env=["MISTRAL_API_KEY"], patterns={"employee_id": r"EMP-\d{6}"})
Redaction.none()   # nothing redacted, and the manifest says so
```

Three rule kinds, applied in order:

1. **Values of named environment variables.** The names are declared; the values are read from the environment when the first record is written, and the manifest records the names. A variable that is unset, or holds fewer than eight characters, produces no rule and is listed in the manifest under `secret_env_unusable`.
2. **Sensitive key names.** A field named `authorization`, `api_key`, `password`, `cookie` and similar has its value replaced whatever it contains, at any depth. Matching is on the whole name after lowercasing, so a field named `secrets_path` does not match. The full set is `simple_agents.redaction.SENSITIVE_KEYS`.
3. **Patterns.** Built-in credential formats, then any the project declares. The built-in set matches `sk_prefixed_key`, `github_token`, `aws_access_key_id`, `huggingface_token`, `google_api_key`, `slack_token`, `bearer_token`, `jwt` and `private_key_block`, and the expressions are in `simple_agents.redaction.BUILTIN_PATTERNS`.

Each substitution appends the field's path to the record's `redactions` array:

```json
"redactions": ["inputs.messages[0].content", "inputs.headers.authorization"]
```

A tool carrying a credential takes it as a `SecretStr` for this reason; `docs/tools.md` §1.6 states the two limits.

**A value can also declare itself, by its type.** A value carrying a `get_secret_value` method is written as `[redacted:secret_type]` and its path is listed. `pydantic.SecretStr`, `SecretBytes` and `Secret[T]` all carry one:

```python
from pydantic import SecretStr

token = SecretStr(os.environ["SUPPLIER_TOKEN"])
```

This matches on the type rather than the content, so it covers a credential that no pattern recognizes and no declared environment variable holds. It applies whatever the field is named, and it applies under `Redaction.none()`.

**The type protects the value it wraps, not what is derived from it.** `f"Bearer {token.get_secret_value()}"` is an ordinary string, and only the pattern rules see it. That string is the shipped adapters' auth header, and two rules cover it: the field is named `authorization`, and the value matches `bearer_token`.

**A value that is not plain data is converted to plain data before the rules run.** A credential in a field of an object is scrubbed like one in a dict, and the record keeps the object's fields rather than a rendering of the object.

**These rules match known credential formats and declared values.** A secret in none of those categories is not detected. `secret_env` and a secret-carrying type are the two ways to declare one.

**A cassette key is computed before redaction and the stored entry after it**, so two requests that differ only in a credential are two entries rather than one, and the file carries no secret.

**A redacted value that goes back into a later request stops the replay there.** A tool result is stored redacted, so a replay serves the marker where the recording had the value. Every model call the agent makes afterwards in that conversation is keyed on different messages, and the miss names the redaction as the cause. A tool that takes its credential as a `SecretStr` and returns only what the model needs is replayable, because what the run used and what the file holds are then the same (`docs/tools.md` §1.6).

**A tool that cannot avoid returning the credential declares `redact_result=True`.** Its result is redacted before the model reads it, so the two sides match and the run replays. `Redaction.at_boundary` names the rules that apply there, and defaults to `("secret_env", "sensitive_keys")`: the two that match a declared value or a field name, rather than a shape that also matches ordinary text. `docs/tools.md` §1.6 has the whole of it. The manifest's `redaction` object records `at_boundary`, so what the model was shown of a tool result is on file with the rules that were in force.

**Every field on a record is scanned except the ones the library generates itself**: the format
version, the record type, the ids, the sequence number, the timestamps, and the `redactions`
array, which reports the scan rather than being subject to it. Everything else is walked,
including a field added in a later version of the format. That covers what a backend sent
alongside its response, what a tool returned, and the text of an error, all of which can carry
a credential and none of which the library wrote.

**The manifest records rule names and environment variable names, never values.**

---

## 7. Trajectory volume

Every run writes a trajectory. `trajectory=` on the envelope governs how much of each one is kept:

```python
env = RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))
```

`Trajectory.full()` is the default and keeps everything. `Trajectory.sampled(rate)` keeps the payload fields on that fraction of runs and replaces them on the rest, as `docs/trajectory-format.md` §5.4 defines. `Trajectory.sampled(0.0)` keeps none.

**The rate governs the payload fields alone.** Counts, timings, token figures, seeds, routes, terminations, the manifest and derived cost are complete on every run at every rate. A six-turn agent node over a 7,000-token corpus writes about 380KB per run, of which about 91% is payload, so the volume a project accumulates falls by about an order of magnitude at 1%.

**Which runs keep their payloads follows from the `run_id`**, so the answer does not change between two readings of one run directory, and `recording.payloads` in the manifest says which this run was.

**A run that errored or suspended keeps its payloads whatever the rate.** A failure is the run most worth reading, and a suspended run is not finished, so the resume that completes it decides. The payloads are written in full as the run proceeds and dropped when it closes, so a run that crashed keeps them too.

**The default cassette follows the same decision at the same moment.** A run that keeps its payloads keeps its recording; a run that drops them has the file deleted as it closes, and the manifest's `cassette.dropped` says why while `cassette.recorded` still says how many calls were made. So the runs holding what was said are the runs that can replay it, and `Trajectory.sampled(0.0)` keeps both off disk with one setting. A cassette the project named is not touched, since the project chose where it goes.

**An evaluation refuses a sampled envelope.** Per-node accuracy and `absent_outputs` are computed from what each rollout's trajectory holds, so sampling inside one moves the numbers rather than the volume. `envelope.with_trajectory(Trajectory.full())` produces the envelope an evaluation takes from the one a production run uses.

---

## 8. Reading a run back

`runs()` lists the run directories under a path, newest first, and reads what each one recorded. It opens files and executes nothing:

```python
from simple_agents import runs

for run in runs("runs/"):
    if run.finished and "report" in run.node_ids:
        print(run.run_id, run.outputs_of("report"))
```

| On a handle | |
|---|---|
| `run_id` | The run's id, which is also its directory name |
| `path`, `manifest_path`, `trajectory_path` | Where the run is, derived from the directory rather than from the recorded path, so a run directory that moved still resolves |
| `manifest` | The parsed manifest, `{}` where it could not be read |
| `unreadable` | Why the manifest could not be read, `None` where it was |
| `outcome` | `completed`, `stopped_early`, `suspended` or `error`, and `None` on a run with no recorded outcome, which `liveness` separates into three (§8.3) |
| `liveness` | `running`, `abandoned` or `unknown` on a run with no recorded outcome, and `None` on a run that has one (§8.3) |
| `last_activity_at` | When the run last wrote a trajectory record, and `None` where it wrote none |
| `finished` | Whether the run reached an end: `completed` or `stopped_early` |
| `role` | What the run was for (§2.1), `agent` on a run whose manifest does not say |
| `live` | Whether an end user was on the other end (§2.1), false on a run whose manifest does not say |
| `node_ids` | Every node that executed, in the order each first ran |
| `outputs_of(node_id)` | What that node produced, on its last execution |

**Newest is by the manifest's `started_at`**, so `runs("runs/")[0]` is the run that began last and `reversed(runs("runs/"))` reads oldest first.

**A directory holding a `manifest.json` is a run whatever that file contains.** A run whose manifest cannot be parsed is listed with `unreadable` saying why, because a project with one broken manifest has a run and returning nothing would say otherwise.

**An evaluation's rollouts are not listed beside the runs a project launched.** Each rollout is a run directory of its own under one for the evaluation, at `runs/eval/<eval_id>/<example>-<rollout>/`. Pass `nested=True` for every run at any depth, or read one evaluation's rollouts by pointing at its directory:

```python
rollouts = runs("runs/eval/eval_e5a1bbef5a22")
```

**`role=` reads back one kind of run.** A project that ran a labelling pass or a judge through
the envelope has those runs under `runs/` beside the agent's:

```python
agent_runs = runs("runs/", role="agent")
label_runs = runs("runs/", role="labelling")
```

**`live=` separates real use from the runs made building the project.** A project that has
shipped reads what people actually did through it (`docs/shipping.md` §2):

```python
real = runs("runs/", live=True)
development = runs("runs/", live=False)
```

**`since=` and `last=` narrow it to a period.** `since` keeps the runs that started at or after
an ISO timestamp, matched as text, and `last` keeps the newest that many of what the other
filters left:

```python
recent = runs("runs/", nested=True, since="2026-08-14", last=500)
```

### 8.1 What a node's output comes back as

`outputs_of` returns the recorded output of that node's last execution, decoded. A recorded absence comes back as `Unknown` wherever it sits in the output, rather than as the tagged object the file holds:

```python
source = run.outputs_of("chase")["source"]
if isinstance(source, Unknown):
    ...
```

That is the same test as on a value a node has just returned, and it is what a node matcher receives during an evaluation (`docs/evaluation.md` §5.2). `read_trajectory` is the exception: it yields records as they are on disk, because a record is data rather than a value.

Three answers that are not the same:

- **`None`** means the node produced nothing.
- **`LookupError`** means the node did not run, and the message names the nodes that did. A run that stopped early reaches only part of the graph, so `node_id in run.node_ids` is the test to make before asking.
- **`{"type": "not_recorded", "reason": "sampling"}`** means the run kept no payloads (§7). The record holds that object and this returns it.

A node inside a bounded cycle answers for its last iteration, and a run that suspended and resumed answers for the execution that finished. `read_trajectory` is what reads every iteration.

### 8.3 Whether a run with no outcome is still going

The manifest is written when the run starts and rewritten when it ends. A process that died between the two leaves the start copy, and a killed process writes nothing, so `outcome` stays `null` on it forever. Reading that as a run still executing says something that will never become true.

`liveness` separates the two, and has three answers:

| | |
|---|---|
| `running` | The run could still be going |
| `abandoned` | It cannot be. Whatever it produced, nothing will say |
| `unknown` | Nothing on disk settles it |

It is derived rather than recorded, because nothing can be recorded by a process that is gone. What settles it, in order:

1. **The run's own `max_wall_clock_ms`.** A run past the bound it declared would have been stopped by the library, so it is not still executing. That axis is checked between steps rather than inside a call, so a run held inside one long call can pass its own bound while still going; the reading allows for that before calling a run abandoned.
2. **The last record in its trajectory.** A run writes a record for every model call, every tool call and every step, so silence is the evidence where the run bounded nothing. `last_activity_at` is that timestamp.
3. **Neither**, which is `unknown`.

```python
for run in runs("runs/"):
    if run.liveness == "abandoned":
        print(run.run_id, "stopped at", run.last_activity_at)
```

`simple-agents report` counts an abandoned run on its outcome line, and the conformance report counts one apart from a run that had not finished, because the two are different statements about what a project has to show. `Pipeline.rerun` runs again what such a run was given (`docs/pipeline.md` §1.13).

### 8.4 What every run did, without writing code

```
simple-agents report runs/
```

It reads the runs under a path and prints what each node did, over all of them. Nothing imports
the project, so it reads runs from another terminal or another machine:

```
simple-agents report: runs/

  3,261 of 3,293 run(s), 2026-08-11 to 2026-08-13, role agent
  21,391 model call(s), 12,582 tool call(s), 2.4354 USD, 26 run(s) whose cost could not be measured
  completed 3,230, error 31

  node         kind      execs   calls   tools   unfinished  its calls  cost
  look_closer  agent     3,063  15,610  11,313     257 (8%)      4,626  1.9102 USD
               produced nothing: 257 unit(s) of work, spending 4,626 of 15,610 model call(s)
               188 of those 257 made no tool call, consultation or delegation, spending 3,384 model call(s) (FT-35)
  hunt         agent       104   1,411     577     28 (27%)        772  0.2214 USD
               produced nothing: 28 unit(s) of work, spending 772 of 1,411 model call(s)
               1 of those 28 made no tool call, consultation or delegation, spending 23 model call(s) (FT-35)
               tools whose every call failed: consult 1

  tool                   registered in  called in
  what_they_thought_of           3,101      1,845
  explore_tag                       16         16
  consult                          104          1
  uncommon_books                     2          1
```

The figures above are one project's, read back over the runs it kept: `look_closer` spent 4,626
of its 15,610 model calls on executions that produced nothing, and 3,384 of them on executions
that never called anything. Its runs were written before manifests carried `unpriced_calls`, so
the spend line counts whole runs; a project whose manifests carry it reads `at least 5.5024 USD,
54 call(s) in 11 run(s) could not be priced`, and each node's own column carries its floor the
same way (§4.2).

**The tool block is registration against use.** A node's `tools` column counts the calls it
made and never says to what, so a tool a project built and then stopped reaching shows up as
the gap between two numbers. `uncommon_books` above is one: four candidate sources behind one
tool, registered in two of the directory's runs and called in one of them. A tool a pipeline no
longer offers keeps whatever the older runs recorded, so the number falls rather than
disappearing.

**The path can be a directory of runs, one run, an evaluation's directory of rollouts, or a
results file.** A results file prints the evaluation's own report instead
(`docs/evaluation.md` §8.1). A directory holding no run and no `runs/` exits 2.

`--json` prints the same as data, `--role`, `--live`, `--since` and `--last` narrow which runs
are read, and the first line names how many were read of how many are there: a figure over a
scoped set of runs says what it covered.

**Every role is read unless one is named**, so a project's labelling pass and its judge are in
the figures and the roles are counted on their own line. A run still executing is read from what
it has written so far, and the outcome line counts it as `still running`. Cost per node needs one basis: it
is derived against the one the runs recorded, and where the runs read were priced two ways each
node's cost reports unknown and the report says so.

**Nodes are keyed by `node_id`**, so a directory holding runs of two pipelines that share a node
id reports them as one node. Point at a directory per pipeline, or narrow with `--since`.

**A run made by `Pipeline.slice` is counted on its own line.** A rung runs under the same role
as the agent and keeps the node ids of the pipeline it came from, so the roles line cannot
separate it and its figures sit in the table beside the agent's. The node a rung starts at ran
on every one of its rollouts and on some share of the agent's, which makes `reach` and every
count over it a different figure with the same name (`docs/evaluation.md` §5.6).
