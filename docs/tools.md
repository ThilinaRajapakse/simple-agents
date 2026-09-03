# Tools

What a tool declares, how a registered tool is replayed, and the set that ships.

---

## 1. The contract

A tool needs to have the six items in the table below. The schema is derived from the function,
and the rest is declared by the author.

| | What | Supplied by | Where it comes from |
|---|---|---|---|
| 1 | The schema the model is shown | Derived | The parameter annotations (§1.1) |
| 2 | A description the model reads | The author | The docstring, or `description=` (§1.2) |
| 3 | How failures are signalled | The author | Which exception the function raises (§1.3) |
| 4 | A side-effect class | The author | `side_effect_class=`. Registration without one is refused (§1.4) |
| 5 | Cost and latency per call | The author | `declared_cost=`. Required on a `spends_money` tool (§1.5) |
| 6 | The resource it touches | The author | `touches=`, the same string wherever that resource is touched. `simple-agents view` computes what flows between pipelines from it (`docs/view.md` §4) |
| 7 | A contract test | The author | §6 |

```python
from simple_agents import SideEffectClass, ToolRegistry, tool

@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str) -> list[str]:
    """Search the product catalogue for items matching a description.

    Matching is on the words in the query. Returns the matching items, or an empty
    list when nothing matches. Do not call this for questions about delivery.
    """
    return catalogue.search(query)

registry = ToolRegistry([look_up])
```

**A tool is one function. Work that needs several steps is a pipeline**, handed to the model as
a `Delegation` on the node rather than written inside a tool body (`docs/pipeline.md` §2.5).
Reach for a tool where the agent needs one action with one result, and for a delegate where it
needs a graph: nodes that record separately, their own budget, and per-node metrics. A tool
whose body runs a `Pipeline` gets none of those, and is invisible to the check that decides what
an evaluation may execute (FT-20).

### 1.1 Signature

`query: str` with no default becomes a required string property. A parameter with a default
becomes optional.

Every parameter must be annotated. An unannotated one would be offered to the model with no
type, and the model would pass whatever it liked. `*args` and `**kwargs` have no JSON schema
equivalent and are refused.

Annotations are resolved against the module the function was defined in. A signature naming a
type declared inside another function cannot be resolved there and is refused.

Where the derivation cannot express a signature, pass `parameters=` with the schema written
out. Argument types are then the function's business, and the argument names are still checked
against it. A declared schema offering a property the function has no parameter for is refused
when the tool is built, because the model would be told it may pass something every call using
it is then refused for.

A description anywhere in that schema is prompt text: `Field(description=...)` on a parameter,
or the docstring of a model used as a parameter's type. The model reads it. Use it where the
argument's meaning is not obvious from its name and type:

```python
from typing import Annotated
from pydantic import Field

@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(
    query: str,
    top_k: Annotated[int, Field(description="How many to return. Above 10 crowds the turn.")] = 5,
) -> list[str]:
    """Search the product catalogue for items matching a description."""
```

Without one, `top_k` reaches the model as a bare integer with a default and nothing saying what
a good value is.

A call that does not satisfy the schema comes back to the model as a failure rather than
ending the run, so the model gets a turn to correct it. **This includes an argument the model
invented.** A key the tool does not take is refused by name, with the names it does take:

```
Call to 'find_book' passed ['year'], which it does not take. It takes ['author', 'title'].
```

A function taking `**kwargs` receives everything instead and is not checked, which is how a
tool absorbs an unexpected argument and tells the model it was ignored rather than refusing:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY, parameters=FIND_BOOK_SCHEMA)
def find_book(title: str, **extra) -> dict:
    """Identify one book by title. Returns what the catalogue holds."""
    found = catalogue.lookup(title)
    if not extra:
        return found
    return {**found, "ignored_arguments": sorted(extra),
            "note": f"This tool does not take {sorted(extra)}; the result is unfiltered by them."}
```

Reach for that where an ignored argument changes what the result means. A model that asked for
a filter it did not get should be told so, rather than reading the unfiltered result as
filtered.

### 1.2 Description

The model reads the description to decide when and how to call the tool. It is the function's
docstring, unless `description=` is passed to `@tool`, which replaces it. An empty description
is refused.

State what the tool does, what the arguments mean, what comes back, what a failure means, and
when not to reach for it.

A docstring that has drifted from the behaviour is worse than a missing one, because the
resulting failure looks like a reasoning failure and sends debugging to the prompt. The
contract test is what catches the drift (FT-23).

### 1.3 Failures

```python
raise ModelFacingError("No product matches that description. Try broader terms.")
raise CallerFacingError("The catalogue database is unreachable.")
```

A `ModelFacingError` is recorded on the tool call and handed to the model as an observation. A
`CallerFacingError` ends the run. Any other exception is treated as caller-facing, because an
infrastructure failure passed to a model produces an answer built on nothing (FT-22).

An empty result is usually not a failure. `document_search` returns an empty result list rather
than raising, because finding nothing is something the model acts on by searching for something
else, and raising would put a successful lookup in the record's error field.

**A source refusing because it is being asked too often is `Throttled`, and the library waits
and calls the tool again.** It is the one tool failure the library acts on rather than records.
A throttle handed to the model reads as the source having nothing, and an agent told that stops
looking: a run that met 736 rate limits reported them all as *no article*.

```python
from simple_agents import Throttled, retry_after_seconds

raise Throttled(
    "example.com is rate limiting this agent.",
    retry_after_s=retry_after_seconds(response.headers.get("Retry-After")),
)
```

`retry_after_s` is what the source asked for, where it said. Without one the wait doubles from a
second. Three attempts, then the failure reaches the model like any other, saying the source was
busy, so an agent can report that rather than absence. `http_fetch` and `read_page` raise it on
408, 429 and 503.

`ModelFacingError` takes a `retryable` flag. It is recorded on the tool call and read by nothing
else: it says what the tool's author thought, for whoever reads the trajectory afterwards. The
failure the library retries is `Throttled`.

### 1.4 The side-effect class

`read_only`, `writes`, `spends_money`, `irreversible`. Registration without one is refused
(FT-19). A tool whose class is unclear is not `read_only`; that has to be established.

An evaluation runs k rollouts over n examples, so anything a tool does happens k×n times.
`read_only` and a `writes` confined to the run's own workspace repeat harmlessly.
`spends_money` and `irreversible` reach outside the run, and an evaluation refuses to start
when it can reach one of those, unless it is replaying from a cassette (FT-20, and
`docs/evaluation.md` §7.2).

The class is recorded on every tool call, not only in the registry, so re-declaring a tool
later does not change what an old trajectory says happened.

### 1.5 Declared cost

```python
from simple_agents import DeclaredCost

DeclaredCost(currency="USD", per_call=0.005, latency_ms=800)
```

Required on a `spends_money` tool, where the figure is the point: it is what an evaluation
names when it refuses to run without a spend ceiling, and what `max_cost` is checked against
before a call is made. Optional elsewhere, because a local lookup's cost is zero and declaring
it says nothing. Recorded on every tool call and in the manifest, as declared rather than as
measured.

**It is not the arithmetic for what an evaluation will cost.** One rollout can call a paid tool
as often as the agent reaches for it, so `per_call` times the rollout count is a floor. What
bounds an evaluation is `max_cost` on the pipeline's budget, times the rollouts
(`docs/evaluation.md` §7.2).

**What a call cost is a separate field from what the tool charges.** The record carries
`declared_cost` on every call the tool made, and `spent` only on the ones that bought
something: a call served from a cassette, a call that failed, and a call a cache answered all
reach the price and pay nothing. Adding up `declared_cost` counts those; adding up `spent` does
not (`docs/trajectory-format.md` §4.2).

**A tool reports what it was actually charged by asking for a `SpendMeter`.** The library fills
the parameter and the model never sees it:

```python
@tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID)
def search(meter: SpendMeter, query: str) -> list[dict]:
    """Search the web. Costs money unless the answer is already stored."""
    stored = cache.get(query)
    if stored is not None:
        return stored
    results = provider(query)
    meter.spend(0.005)
    return results
```

A tool holding one is taken at its word: what it reports is what the call cost, and reporting
nothing means it cost nothing. That is the only way a cache hit inside a tool body reaches
`spent: null`, since nothing outside the tool can see it. The figure depletes `max_cost`.

`source` says where the figure came from, and defaults to `measured`, meaning the vendor
returned it. A tool that takes a meter so a cache hit can report nothing, while the figure
itself is the price the project declared, says so:

```python
meter.spend(declared_cost.per_call, source="declared")
```

The shipped `web_search` is such a tool, so its live calls record `source: "declared"`.

Unlike a `ModelHandle` or a `Workspace`, a meter does not stop the tool being served from the
cassette (§3.2). It reaches nothing outside the run, and a replayed call reports nothing.

**`max_cost` refuses a paid call it cannot afford, before the call is made.** The check is
against the most one call can cost: `max_per_call` where the tool declares one, otherwise
`per_call`. The refusal is model-facing, so the agent is told to answer with what it has and
the run continues:

```python
DeclaredCost(currency="USD", per_call=0.002, max_per_call=0.02)
```

Declare `max_per_call` where the price varies with the request, and the limit holds exactly.
Without it a run can pass the limit by whatever one call cost beyond `per_call`.

**A run uses one currency.** A tool whose `DeclaredCost` names a currency other than the cost
basis' is refused before the run starts, because the two cannot be added into a total. The same
holds for what a tool reports: `meter.spend(amount, currency=...)` naming a second currency is
refused at that call, since the figure is added to the run's totals and depletes `max_cost`.
Convert inside the tool where the vendor bills in something else.

A run whose only spend is a paid tool needs no cost basis (§4.4 of `docs/run-envelope.md`), so
its first reported figure has nothing to be checked against. That figure fixes the run's
currency, and every later one is checked against it, across tools and across a suspension. The
refusal names what fixed it.

### 1.6 Credentials

A credential goes in a `pydantic.SecretStr`, which is redacted by its type wherever the run
records it, whatever the field is named and whether or not any pattern would have matched it.

```python
from pydantic import SecretStr

http_fetch(headers={"Authorization": SecretStr(os.environ["SUPPLIER_TOKEN"])})
```

There are two limitations:

- **The type protects the value it wraps.** `f"Bearer {token.get_secret_value()}"` is an
  ordinary string and is covered only by the pattern rules. Pass the `SecretStr` itself as the
  field's value and let the library render it at the boundary.
- **A cassette key hashes a secret as its mask.** Two calls differing only in a typed secret
  produce the same key, and the second replays the first's response.

**A tool whose result carries a credential declares `redact_result=True`.** Its result is
redacted once, where the call is made, so the model, the node and the cassette are given one
string:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY, redact_result=True)
def fetch_supplier_page(url: str) -> dict:
    """Fetch one page from the supplier portal. Returns its body and headers."""
    return {"headers": dict(response.headers), "body": response.text}
```

Without it the model reads the credential and the file holds a marker, so every model call after
that tool call is keyed on content the recording does not have, and a replay of the run misses.
The miss names redaction as the cause.

`Redaction.at_boundary` is the set of rules applied there, and defaults to
`("secret_env", "sensitive_keys", "builtin")`. A project's own patterns are outside that
default. Pass `at_boundary=("secret_env",)` to apply only the exact-match rule, or `()` to
apply none.

```python
Redaction(
    secret_env=["SUPPLIER_TOKEN"],
    patterns={"employee_id": r"EMP-\d{6}", "internal": r"itk_[a-z0-9]{24}"},
    at_boundary=("secret_env", "sensitive_keys", "builtin", "internal"),
)
```

The kinds are `secret_env`, `sensitive_keys`, `builtin` and `patterns`, and a rule can be named
on its own, as `internal` is above. A name that is neither is refused at construction. A value
typed `SecretStr` is redacted at the boundary whatever this says.

**What `at_boundary` decides, for a tool that declares `redact_result`:**

| | The model reads it | The trajectory holds it | The cassette holds it |
|---|---|---|---|
| A rule in `at_boundary` | no | no | no |
| A rule outside it | yes | no | **yes** |

The cassette holds what the model was given, because a recording that holds anything else serves
a different string back and the call after it misses. So `employee_id` above keeps an employee id
out of the trajectory, lets the agent that has to act on one read it, and leaves it in the
cassette for `fetch_supplier_page` alone. Name the rule in `at_boundary` where that is not
wanted; the model then reads a marker instead.

The manifest records `at_boundary` under `redaction`, so what a run showed its model is
recoverable from the run.

---

## 2. The registry

```python
from simple_agents import ToolRegistry
from simple_agents.builtins import DocumentIndex, document_search, now

registry = ToolRegistry([document_search(DocumentIndex.from_directory("corpus/")), now()])
registry.add(look_up)

node = AgentNode(build_prompt, tools=registry, output_schema=Answer, budget=budget)
```

A registry is an object the project constructs and holds. There is no global one, so two
projects in one process do not share a namespace and a test does not depend on import order.

It refuses a tool that is not a `Tool`, a duplicate name, and the reserved name `finish`. An
`AgentNode` and a `Deterministic` node each take a registry or a plain list.

The registry is what lets a project enumerate every tool it declared, including any no node uses
yet. Pass it to the pipeline as well, and the manifest records those too, each with `offered`
saying whether any node was given it:

```python
pipeline = Pipeline([node], budget=budget, tools=registry)
```

### 2.1 A tool called at a fixed point

A tool the model chooses to call belongs to an `AgentNode`. A tool the work requires at a known
step is declared on a `Deterministic` node and called by name:

```python
def fetch_the_page(inputs: dict, ctx: NodeContext) -> str:
    return ctx.call_tool("http_fetch", url=inputs["url"])

node = Deterministic(fetch_the_page, tools=[http_fetch()])
```

The call is recorded, keyed and served from the cassette exactly as an `AgentNode`'s is.
Calling the tool's function directly instead, as `http_fetch().fn(url=...)`, runs it and
records nothing: no `tool_call`, no cassette entry, no manifest row, and nothing for an
evaluation to price or refuse.

No model is choosing this call, so there is nobody to hand a failure to: a tool raising
`ModelFacingError` raises out of `ctx.call_tool`. Catch it where the node can do something
else, or let it end the run. It is the failure the tool raised, so a node that treats one
kind differently catches that kind, and a replayed call raises the same kind the recording
made:

```python
try:
    page = ctx.call_tool("read_page", url=inputs["url"])
except Throttled:
    return {"source": "busy"}
```

A tool taking a `ModelHandle` is refused on this node kind, which makes no model call.

`finish` is never registered. The library builds it for each `AgentNode` from that node's
output schema, so termination is an explicit schema-checked call rather than a heuristic over
the model's prose.

---

## 3. How a tool is replayed

A recorded run replays with no network, which is what lets an evaluation run in CI (FT-21).
Replay works by looking a call up in the cassette, so the key has to identify the answer.

### 3.1 What a tool call is keyed on

A tool call's key is the node it was made in, its name, its version, its arguments, and how many
times that same call has already been made in that node.

The count belongs to the node so that one node's recorded calls survive an edit to another's.
Counted across the run, adding a `search("trousers")` to one node renumbers the identical call
in another and every entry recorded for it stops resolving.

The occurrence count is what lets a tool answer differently at different moments. Without it a
clock read twice would replay its first reading twice, silently, and the trajectory would
describe a run that did not happen:

```
now() -> "09:00"    live: two readings
now() -> "09:10"
                    replayed without the count: "09:00", "09:00"
                    replayed with it:           "09:00", "09:10"
```

Model calls already carry the same distinction, since the seed is derived from the index of the
call within the node and the seed is in the key.

**Calls that overlap take their numbers from their positions**, before any of them is made, so
two identical calls in one turn record two entries and each replays its own whichever finished
first (`docs/pipeline.md` §1.12).

A tool's description is not in this key. Editing it does not change what the tool returns for
the same arguments. It is in the key of every model call that offered the tool, because there
it changes what the model was shown.

### 3.1.1 The version, and when to change it

The version is what says a tool now answers differently. Change the body without changing it
and a replay serves the recorded answer: the trajectory reports the old value, marked
`replayed: true`, and nothing says the code moved. Change the version and the same replay
raises `CassetteMiss` naming the re-record command.

`version=` left unset is derived from the function's source, so an edited body changes it
without the author doing anything.

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY, version="2024-price-list")
def price_of(sku: str) -> str: ...
```

**The derived version covers what the function closed over as well as its source**, so two tools
one factory built over different configuration are two tools rather than one. The capture is read
when the tool is declared, so state the function accumulates while the run proceeds does not move
it.

**One case it does not cover**, and it needs `version=` set and changed by hand: **anything the
function reads from outside itself**, such as a file on disk or a table in a database. Only a
value captured at declaration is in the version.

### 3.2 A tool that takes a handle

**A handle is a parameter the library fills and the model never sees.** There are eight. Seven
name something the library owns and are written as the parameter's type; the eighth names the
node's own input and is written as annotation metadata, because the type of that value belongs
to the project.

```python
from typing import Annotated

from simple_agents import (Conversation, Memory, ModelHandle, NodeInput, Retrieval,
                            SpendMeter, Workspace)
from simple_agents.builtins import HostPolicy

def summarise(model: ModelHandle, text: str) -> str: ...
def save_note(workspace: Workspace, path: str, content: str) -> str: ...
def search(meter: SpendMeter, query: str) -> list[dict]: ...
def remember_size(memory: Memory, value: str) -> str: ...
def note_topic(conversation: Conversation, topic: str) -> str: ...
def find(retrieval: Retrieval, query: str) -> list[str]: ...
def follow(host: str, scope: HostPolicy) -> str: ...
def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[str]: ...
```

| Handle | What it is | Re-run on replay |
|---|---|---|
| `ModelHandle` | a model call from inside a tool | yes |
| `Workspace` | the run's own directory (`docs/pipeline.md` §3.1) | yes |
| `Memory` | the memory this run reaches (`docs/memory.md` §2.2) | yes |
| `Conversation` | the conversation the run is a turn of (`docs/conversation.md` §5) | yes |
| `Retrieval` | the recorded path for a search's embedding and rerank calls | yes |
| `NodeInput` | what the node was handed on its edges (§3.2.1) | yes |
| `SpendMeter` | what a call was actually charged (§1.5) | no |
| `HostPolicy` | the run's own copy of the fetch policy (§4.4) | no |

**Six of the eight stop the tool being stored in the cassette**, so the body runs again on a
replay. A `SpendMeter` does not: it reaches nothing outside the run, and a replayed call
reports no spend because none happened (§1.5). A `HostPolicy` does not either: a replayed
fetch is served, never made again, so it admits nothing and spends no request.

**`Retrieval`** is what a hand-written search tool asks for. `document_search` asks for one on
the project's behalf, and a project writing its own tool over its own store or its own client
asks for it directly:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def find(retrieval: Retrieval, query: str) -> list[str]:
    """Find the passages closest to a query."""
    vector = retrieval.embed(embedder, [query])[0]
    return [doc_id for doc_id, _ in store.search(vector, top_k=5)]
```

`retrieval.embed(client, texts)` returns one unit-length vector per text and
`retrieval.rerank(client, query, documents)` returns a score per document, most relevant first,
each carrying the `index` of the document it scored. Both are charged to the run's budget,
recorded as `model_call` records parented to this tool call, and served from the cassette on a
replay. A call made on the client directly, without the handle, is charged to no budget and is
made again on every replay and every rollout of an evaluation. `docs/retrieval.md` §6 covers
what those calls cost.

**`ModelHandle`** is how a tool makes a model call. That call goes through the cassette on its
own and is recorded against the tool's call in the trajectory. It charges a step, its tokens
reach the budget, and its cost derives like any other call.

Such a tool is re-run so that a replay writes the same records as the live run. A stored tool
returns its recorded value without running, so the model call inside it would not happen and
the replay would write one record where the live run wrote two.

**`Workspace`** is the run's own directory, `runs/<run_id>/workspace/`. Re-running means a
replayed run writes the same files into its own fresh directory, so a later step that reads
them finds them there. Paths are relative and one that escapes the workspace is refused.

**The rule such a tool has to satisfy: it may reach the outside world only through the handles
it was given.** A model call through the handle is served from the cassette and costs nothing
on a replay. A request written directly in the body is invisible to the library and is made
again on every replay and on every rollout of an evaluation. Python cannot detect the
difference, so this is a declaration in the same sense the side-effect class is.

Declaring `spends_money` or `irreversible` on a tool that is re-run is refused, since those are
the effects that must not repeat. A `SpendMeter` is exempt, because a tool holding one is
stored like any other and is not re-run. Register two tools instead. A tool that fetches a page
and extracts from it becomes `http_fetch` and an extraction tool: the agent calls `http_fetch`,
reads the page in the result, and calls the extraction tool with that text.

The trajectory records `re_executed` on every tool call. A re-run call reports `replayed: false`
inside a replayed run, because it did run; the two fields together say why no cassette entry
was served.

#### 3.2.1 `NodeInput`: the node's own input

A tool is declared once, where the pipeline is built. The value it needs is often what the node
receives on an edge, which is different on every run and on every rollout of an evaluation.
`NodeInput` is how the tool asks for it:

```python
from typing import Annotated

from simple_agents import AgentNode, NodeInput, SideEffectClass, tool

@tool(side_effect_class=SideEffectClass.READ_ONLY)
def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[str]:
    """Rank this node's shortlist against a query. Returns the titles that match."""
    return [row["title"] for row in pool if query.lower() in row["title"].lower()]

node = AgentNode(build_prompt, tools=[rank], output_schema=Shortlist, budget=budget)
```

The model is shown `query` and nothing else. `pool` is filled from the node's input each time
the tool runs, so a rollout searches what that rollout was handed.

`NodeInput("pool")` is the value under that key, and the node's input has to be a mapping
carrying it. `NodeInput` with no key is the whole input, whatever shape it has:

```python
def summarise(given: Annotated[dict, NodeInput]) -> str: ...
```

Under `over=`, the input is the item's: that key holds the one item this execution is running,
and every other key of the node's input is beside it unchanged (`docs/pipeline.md` §1.2). A
tool over a fanned-out node names the `over=` key.

**On a node with more than one edge into it the input is a `Join`**, so a key names the node
the value came from, and an edge that did not fire holds an `Unknown` (`docs/pipeline.md`
§1.3). A key that is not a declared in-edge is refused like any other. On a node reached by an
`on_error` edge that fired, the input is a `NodeFailure`, which has no keys, so a tool there
takes `NodeInput` with no key and reads the failure.

**Closing over the value instead does not work.** A closure is built when the pipeline is, and
`EvalSuite` builds one pipeline for every rollout, so a tool closing over a store or a list
reads the same thing k×n times while the trajectory records k×n different inputs. Nothing
raises.

A key the node's input does not carry, and a key on an input that is not a mapping, raise
`ConfigurationError` where the tool is called, naming the keys the node was handed. Where the
value is there on some runs and not others, take `NodeInput` with no key and read it in the
body.

### 3.3 What a tool may read

A tool may read anything that is in its key, anything a handle gives it, and the node's own
input through `NodeInput`. It may not read run state through any other route, because the
cassette would then serve one answer for two different situations. That is why a tool taking a
`NodeInput` is never stored: the input is not in the key, so there is no answer to serve.

Every value a `NodeInput` carries is one the node's `inputs` record already holds, so what the
tool read is readable from the trajectory. A value routed through a file or a closure is not
(`docs/pipeline.md` §3).

**The same holds for a node body, and nothing enforces it there.** A `Deterministic` body is
Python and the library executes it, so a call it makes to `urllib`, `requests` or a database
driver of its own succeeds. What that call loses is everything reaching the world through a tool
gets: the fetch policy does not see the host, no cassette holds the response so a replay makes
the call again and an evaluation makes it k×n times, the trajectory records the node's inputs
and outputs and not what it reached, and the side-effect class that would have declared it is
never written down. `ctx.record_access` puts a resource the body reached on the record
(`docs/pipeline.md` §3), and it records what the body says it did rather than what it did.

---

## 4. The built-in set

```python
from simple_agents.builtins import (
    DocumentIndex, HostPolicy, Reply, UrlCache, consult, document_search, extract_to_schema,
    http_fetch, memory_search, now, on_reply, read_page, recall, reduce_html, remember,
    web_search, workspace_list, workspace_read, workspace_write,
)
```

Each is a factory, because each needs something the project holds: the documents, the search
provider, the schema, the channel to the end user. The library ships no dataset and picks no
search vendor.

| Tool | Class | Replay | What it is |
|---|---|---|---|
| `document_search` | `read_only` | filed, or re-run | BM25 over a `DocumentIndex` the project builds, from texts or a directory (§4.1). Returns the ranked `results` and `documents_containing`, a count per query word. Lexical by default: a query sharing no words with a document does not find it. An index given an embedding client also searches by meaning, and the tool is then re-run on replay because it makes model calls (`docs/retrieval.md`) |
| `workspace_read` | `read_only` | re-run | Reads a file the run wrote. A missing path names the files that are present |
| `workspace_write` | `writes` | re-run | Writes into the run's own directory, creating parents |
| `workspace_list` | `read_only` | re-run | What the run has written so far |
| `now` | `read_only` | filed | The current time, ISO 8601 UTC. A replay serves the recorded instants in order |
| `read_page` | `read_only` | filed | One page, fetched and reduced to text: its tables, its structured data, its prose (§4.3). What an agent reads pages with. Takes a `HostPolicy` (§4.4) and a `UrlCache` (§4.5) |
| `http_fetch` | `read_only` | filed | One GET, returning the body as it came back. `robots.txt` honoured, an optional host allow-list, an optional interval between fetches, and `SecretStr` headers. Redirects are followed up to five hops with every destination checked the same way, and a URL naming a private or reserved address is refused unless `allow_private=True`. Takes a `HostPolicy` (§4.4) and a `UrlCache` (§4.5) |
| `web_search` | `spends_money` | filed | Search through a provider function the project supplies (§4.2). Requires a `DeclaredCost` |
| `extract_to_schema` | `read_only` | re-run | Typed fields out of a passage, one tool per schema. The schema is a pydantic model and must admit `unknown` |
| `consult` | `read_only` | filed | Asks the end user, through a channel the project supplies. Recorded as a `consultation` |
| `remember` | `writes` | re-run | Stores one fact under a key, for a later run to read. Replaces what that key held (`docs/memory.md` §2) |
| `recall` | `read_only` | re-run | Reads back one stored fact by its key. Reports `found: false` where nothing is stored |
| `memory_search` | `read_only` | re-run | Finds stored facts by the words in them. Lexical unless given an embedding client, and then by meaning as well. Returns `results` keyed on `key`, not on `doc_id` (`docs/memory.md` §2.5) |
| `compact_conversation` | `writes` | re-run | Replaces a conversation's older messages with a summary the caller supplies, keeping the newest (`docs/conversation.md` §5) |

Sandboxed code execution is deferred. It is the highest-power tool, with a real security
surface.

### 4.1 The document index

`document_search` searches a `DocumentIndex` the project builds, from texts in memory or from a
directory:

```python
index = DocumentIndex.from_texts({"a1": "Corveth raised a seed round.",
                                  "a2": "Corveth's seed round closed in March."})
index = DocumentIndex.from_directory("corpus/", glob="*.md")
```

The identifier is what a result names and what an answer cites. Matching is lexical, on the
words themselves, so a query sharing no words with a document does not find it.

**A title or heading is indexed by writing it into the text:**

```python
DocumentIndex.from_texts({d["doc_id"]: f"{d['title']} {d['text']}" for d in docs})
```

**`stopwords` are words to drop from a query before searching.** A list of English function
words and question words ships as `ENGLISH_STOPWORDS` and is the default. Without one, BM25
returns every document holding any query word, so a natural-language question reaches nearly
every document through words like `the` and `does`.

```python
index = DocumentIndex.from_texts(texts, stopwords={"part", "order", "the"})
index = DocumentIndex.from_texts(texts, stopwords=ENGLISH_STOPWORDS | {"depot"})
index = DocumentIndex.from_texts(texts, stopwords=())      # every word the query holds
```

Words are matched after lowercasing. They apply to the query and not to the documents, so a
word listed here is still findable in a passage, and negations are left out of the default for
that reason: dropping `not` from a query loses the difference between "is refused" and "is not
refused". A query of nothing but stopwords is searched as written.
`index.query_terms(query)` returns the words a query is searched on, and
`documents_containing` counts those same words.

**An index given an embedding client also searches by what a document means**, and must then
say how the two combine:

```python
index = DocumentIndex.from_texts(corpus, embeddings=SentenceTransformerEmbeddings(),
                                 ranking=Hybrid(fuse=RRF(k=5)))
```

`docs/retrieval.md` is that surface: which model embeds, how the lexical and semantic results
combine, reranking, where the vectors live, and what the model calls a search makes cost. The
tool is the same tool, with the same name and the same two arguments offered to the model.

**A corpus that changes is added to rather than rebuilt.** `index.add`, `index.replace` and
`index.remove` update the words and the vectors together, and `index.save` writes what the
index holds now:

```python
index.add({"a3": "The Ashford depot closes at 4pm on weekdays."})
index.save("corpus.index")
```

Only the documents given are embedded. An add made inside a running pipeline takes the
`Retrieval` handle, since embedding the new documents is a model call
(`docs/retrieval.md` §2.1).

### 4.2 The search provider

`web_search` searches through a function the project writes. The library owns the tool
declaration and the result shape; the provider owns the vendor, because a search API is a
choice with a key and a price attached:

```python
def brave(query: str, count: int) -> list[dict]:
    body = json.loads(fetch(f"https://api.example.com/search?q={quote(query)}"))
    return body["results"]

registry.add(web_search(brave, declared_cost=DeclaredCost(currency="USD", per_call=0.005)))
```

Results are normalised to `title`, `url` and `snippet`, read from the usual key names. A
result with no recognisable url is dropped.

**A provider that accepts `domains` lets the model restrict a search to named sites**, which
is how an agent checks a claim on the site that published it. `domains` is the library's name
for it, and the provider translates to whatever its API calls it:

```python
def brave(query: str, count: int, domains: list[str] | None = None) -> list[dict]:
    if domains:
        query = " ".join(f"site:{d}" for d in domains) + " " + query
    ...
```

A provider without the parameter keeps working. A search asking for domains against one is
refused, and the model is told the search cannot be scoped, rather than being given results
from the whole web under a request for one site.

**`provider_options` reaches every call uninterpreted**, for settings the builder fixes rather
than the model chooses:

```python
web_search(brave, declared_cost=..., provider_options={"country": "fi"})
```

### 4.3 Reading a page

`http_fetch` returns what the server sent, which for a web page is markup: navigation, script,
styling, and the content somewhere inside it. `read_page` returns the same page reduced to
text, and is what an agent reads pages with:

```python
registry.add(read_page(
    allow_hosts=["www.example.com"],
    min_interval_s=1.0,
    link_words=("size guide", "specifications"),
))
```

It takes every argument `http_fetch` takes and passes them on. What comes back is the page in
parts, under headings: its tables, the structured data it declared, then its prose.

**`order` decides which parts are rendered and in what sequence**, so what survives a limit is
the project's choice. The default is `("tables", "json_ld", "text")`; a project whose pages
carry prose rather than data passes `order=("text", "tables")`. `max_chars` bounds the result
and says where it cut.

**`link_words` says what a link to a further page looks like here.** Links on the page's own
host whose text or address contains one are listed at the end of the reply, which is how a
model reaches a detail that lives on a second page. Links to other hosts are dropped, so a page
cannot widen what an agent reaches by linking elsewhere.

**A page that fetches and reduces to almost nothing fails model-facing**, saying that the page
is rendered by JavaScript and that the rest of the site will behave the same way.

The reduction is also available on its own, for a project that fetches by other means:

```python
from simple_agents.builtins import reduce_html

reduced = reduce_html(body, base_url=url)
reduced.text                              # the prose, markup removed
reduced.tables[0]                         # [['Size', 'Chest'], ['M', '52cm']]
reduced.json_ld                           # the page's ld+json blocks, parsed
reduced.links_matching(("size guide",))   # same-host links, absolute
reduced.as_prompt(20_000)
```

Script, style, navigation and footers are dropped, tables keep their structure, a table of one
row is treated as layout, and image alt text is kept where it is long enough to be a
description. `ld+json` blocks are parsed and returned as they are: what a vocabulary means is
the project's to read. Reduction never raises, and a page that will not parse cleanly yields
what was read before the trouble.

There is no JavaScript rendering, and no extraction: pulling typed fields out of the reduced
text is `LLMNode(output_schema=...)` at a fixed step, or `extract_to_schema` mid-run (§4.7).

### 4.4 Which hosts a run may read

`allow_hosts` fixes the reachable set when the tool is built. A `HostPolicy` is the same
containment with a way to grow, for a run that legitimately learns about a host while it is
working:

```python
policy = HostPolicy(["docs.example.com"], max_admitted=5, max_fetches=60)

registry.add(read_page(policy=policy))
pipeline = Pipeline(nodes, budget=budget, fetch_policy=policy)
```

`policy` and `allow_hosts` are two sources for one decision, and passing both is refused.

A subdomain of a host in scope is in scope, so `help.example.com` is reachable under
`example.com`, and a leading `www.` is ignored on both sides.

**The object built above is the declaration, and each run binds its own copy**, so two runs
served by one process count and admit separately. The run's copy is what the project's own
code touches. A route or a `Deterministic` function reads it at `ctx.fetch_policy`:

```python
def choose(output, ctx):
    ctx.fetch_policy.admit("brand.example", reason="named as the maker on the listing")
    return "read_the_site"
```

A tool the project wrote reaches it by annotating a parameter with `HostPolicy`; the run fills
that parameter with its copy, the model never sees it, and the tool stays served from the
cassette on replay:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def follow_the_maker(host: str, scope: HostPolicy) -> str:
    """Bring the maker's own site into scope so its pages can be read."""
    return scope.admit(host, reason="named as the maker on the listing").host
```

Calling `admit` or `spend_fetch` on the declaration itself raises, naming both routes, because
an admission made there reaches no run. Admission beyond `max_admitted` raises
`ConfigurationError` naming what was admitted already. A tool that admits catches it and
re-raises the sentence the model should read.

`max_fetches` is a ceiling on requests that reach the network for one run, whichever host
they go to. It counts requests. What a tool spends is not part of it.

**Passing the policy to the `Pipeline` records it in the manifest**, under `fetch_policy`: the
configured hosts, each admission with its reason, and how many requests the run made. Once a
run can add to its reachable set, the tool declarations no longer say what the agent could
touch, and this is where that is written down. A replayed run makes no requests, so it records
none.

`fetch_policy` is an array, one entry per pipeline that declared a policy, each naming the
pipeline it came from under `declared_by`. A pipeline used as a node may declare its own, which
bounds the fetches its own nodes make.

### 4.5 Reading the same page twice

The cassette replays one recorded run. It does not stop a *later* run re-requesting a page an
earlier one already read. A `UrlCache` does:

```python
cache = UrlCache("cache/pages", max_age_days=7)

registry.add(read_page(cache=cache, policy=policy))
registry.add(web_search(brave, declared_cost=..., cache=cache))
```

The directory is the project's to choose, and `max_age_days` is how long an entry is served
before the address is read again; how fast the pages move is a fact about them.

- A page served from the store says so and how old it is, so the model knows what it is reading.
- Nothing served from the store is charged against `max_fetches`, because nothing was requested.
- **The host checks still apply.** An address out of scope is refused whether or not it is
  stored.
- `read_page` stores the page as it came back and reduces on every read, so changing `order` or
  the reduction does not discard what is stored.
- A search is keyed on everything that identifies the request, `domains` included, so a scoped
  search is never served a whole-web result.

Entries expire on age and nothing else: no eviction, no size accounting, and one atomic write
per entry, so two processes writing one entry leave whichever finished last.

An evaluation replaying from a cassette never reaches the store. A *recording* evaluation does,
and the cassette then holds whatever the store served (`docs/run-envelope.md` §3).

### 4.6 `consult` is a designed interaction

```python
from simple_agents.builtins import ask_on_stdin, consult

registry.add(consult(ask_on_stdin, answered_by="builder",
                     description="Ask about fit preferences, not about stock."))
```

The builder anticipates that the agent will need a preference, a disambiguation, or an
authorisation it cannot derive, and registers this so it can ask rather than guess. It is not
an error path, an escalation or a fallback; an agent that treats asking as failure guesses
instead, and a guess is indistinguishable from an answer in a trajectory (FT-25).

The library never reads from a terminal itself, so the channel is a function the project
supplies. `ask_on_stdin` is the shipped one for a run someone is sitting in front of; a project
that reaches its end users some other way writes its own:

```python
def ask_in_chat(question, options, about):
    return chat.ask(question, buttons=options)

registry.add(consult(ask_in_chat, answered_by="end_user"))
```

The call is recorded as a `consultation` carrying what was asked, what came back, who answered,
and whether it was answered, unmatched, declined, unavailable or shelved. It is filed in the cassette, so
a replay of that run serves the recorded answer rather than asking the person again.

#### 4.6.1 The answer says which option it was

An answer comes back as a `Reply`. It is a string, so it reaches the model as the text the end
user typed and compares equal to it, and it carries `chose`: the option that answer was.

```python
reply = ctx.call_tool("consult", question="Ship it?", options=["yes", "no"])
reply.chose        # 'yes', or None where the answer was none of the options
reply.matched      # False where chose is None
```

**`options` decides how an answer is read and does not constrain what the end user may say.**
An answer matching none of them has `chose` set to `None` and is kept in full. That case is not
a failure: an end user who replies "make it 3 stars" to a yes-or-no question is amending rather
than answering, which is what an approval flow exists to catch. The trajectory records it as
`resolution: "unmatched"`, distinct from `declined`, where they said nothing at all. A channel
that can only return an option, such as one rendering buttons, constrains the answer by
construction and needs nothing here.

Matching folds case and punctuation, so `"Yes."` matches the option `yes`. Pass `match=` for a
rule of the project's own, taking the answer and the options and returning one of them or
`None`.

**A channel that writes prose needs one.** Whole-answer equality is right for a channel that
returns an option and nothing else, such as one rendering buttons. It reads no option at all out
of a sentence: measured on 2026-08-17 over 24 answers written by `SimulatedEndUser`, it matched
0, so every consultation routed to `unmatched` and the branches under `chose` were never taken.
`per_node.consultation_misreadings` is the figure that reports this (`docs/evaluation.md` §5.4).

**No rule over the text alone reads three kinds of answer.** Looking for an option's words
inside the answer matched 7 of those 24, and these survive it:

| The answer | Reading its words | What it means |
|---|---|---|
| `"Anything but The Witch of Whispervale."` | that title | the opposite |
| `"I have no strong feeling either way, go ahead."` | `no` | yes |
| `"Only if it is under 400 pages; otherwise, no."` | `no` | a condition, which is `unmatched` |

Matching on whole words rather than on substrings is what stops `"I don't know"` and `"Not now"`
reading as `no`. The three above survive that, and `unmatched` is the safe answer for all of
them: an end user who answers with a condition is amending the question.

**`read=` reads them with a model.** `ModelReader` is the shipped one. It takes its own client,
normally a cheaper model than the agent runs on:

```python
from simple_agents.builtins import ModelReader, consult

registry.add(consult(ask_in_chat, answered_by="end_user", read=ModelReader(model=cheap)))
```

It returns the option the answer meant, or `None` where it meant none, which is the third row
above and stays `unmatched`. `match=` and `read=` are two rules for one job, so a tool takes one
or the other.

One answer takes one call, or up to `attempts` of them. The reading runs wherever an answer
arrives: on the live run, in the process that resumes a run that stopped to ask, and on a
replay. Each call is recorded as a `model_call` whose parent is the `consultation`, charged to
the run's budget, and served from the cassette on a replay, so k rollouts of an evaluation pay
for one reading. A reader ships with the agent,
which is why the cost is the agent's: in production something has to read what a customer typed.
The stand-in that writes answers during an evaluation is the opposite, and its cost stays off
the node's figures (`docs/evaluation.md` §5.4).

**Editing the reader's prompt misses on the reading.** The reader is not part of the tool's
`version`, so an edit leaves every recorded answer where it is and misses on the reading's own
model call. What the run used is on the tool's manifest entry, as the model
and a digest of the prompt.

**`instructions` is the prompt, and `{options}` and `{answer}` in it are required:**

```python
ModelReader(model=cheap, instructions=(
    "A support agent offered these codes:\n{options}\n\n"
    "The engineer replied:\n{answer}\n\n"
    "Copy the code they meant, or null where they named none."))
```

`attempts` counts every call, so `attempts=1` is no retry and the default of 2 is one call plus
one more. A model naming something that is not an option is told what was wrong and given the
list again. A reader that has used its attempts ends the run, with the answer it could not read
in the message; the answer is on file, so a re-run against the cassette serves it without
asking the person again. The consultation is recorded either way, carrying the answer, a `chose`
of `null` and the failure, because a broken reader is not the end user having said something off
the list.

**A reader of the project's own takes a `Reading` and makes its call through it:**

```python
from simple_agents import Reading

def read_the_answer(reading: Reading, answer: str, options: list[str]) -> str | None:
    """Which offered option this answer meant, or None where it meant none."""
    response = reading.complete(client, f"Options: {options}\nAnswer: {answer}")
    return response.content.strip() or None

registry.add(consult(ask_in_chat, answered_by="end_user", read=read_the_answer))
```

A call made on the client directly, without the handle, is charged to no budget, recorded
nowhere, and made again on every replay and every rollout.

**A `Deterministic` node can carry this reading and nothing else that calls a model.** The
node's own function is handed no client and a tool it calls may take no `ModelHandle`. The
reading is the library's call, and the node's function still makes none. A node that asks a
person and branches on the answer is routed by how that answer is read whether or not a model
reads it.

**`on_reply` routes on the result**, one successor per option:

```python
Deterministic(
    ask_before_applying,
    tools=[consult(channel, answered_by="end_user")],
    successors=["apply", "amend", "stop", "proceed"],
    route=on_reply({"yes": "apply", "no": "stop"},
                   unmatched="amend", declined="stop", unavailable="proceed", shelved="proceed"),
)
```

**`unmatched`, `declined`, `unavailable` and `shelved` are all required.** An end user can
always say something that is not on the list, can always decline, can always turn out not to be
there, and can always be somebody the question was left with who has not answered yet, so a route
with nowhere for those to go is a run that stops on an answer it was given. Where the offered
options really are the only outcomes, waive all four with `exhaustive=True`; the waiver is
recorded in the run manifest, and an answer that arrives under it ends the run rather than
picking a branch.

**The three usually go to different nodes.** Somebody who declines has made a choice, and the
choice is information: the usual next step is to stop or to narrow. Nobody being there is the
absence of a choice, and nothing was learned about the question: the usual next step is to carry
on with what there is and report what is missing. A shelved question has reached somebody and the
answer is still coming, so the usual next step is to carry on and let a later run use the answer.
§4.6.3 covers all three.

Use `field=` where the node returns a model or a dict rather than the reply itself:
`on_reply({...}, field="answer", unmatched="amend", declined="stop", unavailable="proceed", shelved="proceed")`.

**When the run is unattended, the channel stops the run instead of blocking.** Raising
`Suspend` writes down where the run got to and ends the process; the answer arrives later and
`Pipeline.resume` continues from the same point, with the agent's conversation and its spend
intact.

```python
def ask_by_email(question, options, about):
    send_email(question, options)
    raise Suspend(waiting_for=question, options=options)

registry.add(consult(ask_by_email, answered_by="end_user",
                     description="Ask about fit preferences, not about stock."))
```

The question is recorded when it is asked, carrying `resolution: "pending"`, so a run that is
never continued still says what it was waiting for. The answer is a second `consultation`
record naming the first. `docs/pipeline.md` §1.8 covers resuming, and
`docs/trajectory-format.md` §4.3 covers the two records.

An answer delivered to a resumed run is filed in the cassette under the key the call would have
had, so the replay promise above holds for a run that stopped: replaying that run serves the
recorded answer and never suspends.

#### 4.6.2 A channel says who answers

```python
registry.add(consult(ask_in_chat, answered_by="end_user"))
```

Every consultation records `answered_by`, and it is the declaration made here rather than
anything the library observed. Without it a `consultation` says a question was answered and not
by whom, so an agent whose questions all went to a fixed string reports the same resolutions as
one measured against the people it is for.

| `answered_by` | Who that is | When to declare it |
|---|---|---|
| `end_user` | A person the agent is for | The channel a shipped project reaches its readers through |
| `builder` | The project's own author, standing in for that person | A terminal answered while the project is being built |
| `coding_agent` | The coding agent, answering as the end user | An unattended run, and only with `permission=` (below) |
| `simulated` | A model playing the end user | `SimulatedEndUser` declares this itself (`docs/evaluation.md` §5.4) |
| `canned` | Nobody: a fixed answer written into the channel | A stub, declared as one |
| `nobody` | Nobody, and nothing is answered | `unattended()` declares this itself |

`reaches` names which answerer, beside `answered_by` saying what kind, for a pipeline that
asks more than one person:

```python
registry.add(consult(ask_analyst, answered_by="end_user", reaches="requester",
                     name="ask_requester"))
registry.add(consult(ask_director, answered_by="end_user", reaches="approver",
                     name="ask_approver"))
```

Two tools reaching one person declare one name, and a pipeline that asks one person leaves it
unset. It is needed where a run supplies an answerer per name, through
`RunEnvelope(end_user={...})` or `EvalSuite.run(end_user={...})`: a tool that does not say which
of them it asks is refused rather than reaching whichever came first.

It is also recorded on the tool's manifest entry, so which tools reach a person is read off a
run rather than guessed from a name the project chose. **FT-31 reads it once the project has
shipped**, and fails a live project on `coding_agent`, `simulated`, `canned` and `builder`
(`docs/shipping.md` §4). Where the builder is the person the agent is for, the declaration is
`end_user`.

**A coding agent answering needs the builder's permission, recorded.** It is inventing what a
person would have said, and it knows what the pipeline it wrote needs to hear, so the agreement
is written down where the run records it:

```python
registry.add(consult(answer_from_the_session, answered_by="coding_agent",
                     permission="agreed 2026-08-15 that smoke runs may be answered without me"))
```

Never for a measurement. An evaluation answered this way measures the coding agent's idea of the
end user, and reports it as the agent's numbers.

**`RunEnvelope(end_user=...)` replaces the channel for one kind of run** without the pipeline
being rebuilt, and what actually answered is what each consultation records:

```python
smoke = env.with_end_user(unattended())
```

**A channel that calls a model returns `ModelAnswer`**, so the model, what it spent and what it
cost land on the consultation rather than on the node whose question it was:

```python
def ask_a_model(question, options, about) -> ModelAnswer:
    response = client.complete(ModelRequest(messages=build(question, options)))
    return ModelAnswer(reply_in(response), model=client.identity(), tokens=response.tokens)
```

`SimulatedEndUser` is the shipped one, for evaluating an agent that consults
(`docs/evaluation.md` §5.4).

#### 4.6.3 Three ways a consultation ends without an answer

A channel returns the answer, `None` where the end user declined, or one of three things where no answer is coming back now. Which one it returns decides what the record says and where `on_reply` sends the run.

| The channel | What it means | The run |
|---|---|---|
| raises `Suspend` | Somebody will answer, and this run waits for them | Stops, and `Pipeline.resume` continues it |
| returns `Shelved(reason=...)` | The question is on record and an answer may come later | Finishes now, and a later run uses the answer |
| returns `Unavailable(reason=...)` | There is nobody to ask | Finishes now, on what it has |

**Which one fits depends on what started the run.** A request somebody is waiting on can suspend, because there is a person at the other end of it. A run fired by cron, or by a store write, has no requester at the other end, so its channel shelves a question it cannot settle and the run finishes. `unattended()` is for a run with no one to ask: smoke runs, sweeps and fake runs (`docs/pipeline.md` §6).

```python
from simple_agents.builtins import Reply, Shelved, Unavailable, unattended

smoke = env.with_end_user(unattended())          # answers nothing, blocks nothing

def ask_the_site(question, options, about):
    answered = questions.answer_to(about)
    if answered is not None:
        return Reply(answered, chose=None, answered_at=questions.answered_at(about))
    questions.put(about, question, options)
    return Shelved(reason="the site is unattended; the question is on the questions page")

def ask_by_email(question, options, about):
    if not on_call():
        return Unavailable(reason="the desk is closed outside business hours")
    send_email(question, options)
    raise Suspend(waiting_for=question, options=options)
```

Each is recorded as its own `resolution`, so a reader can tell asked-and-outstanding from nobody-to-ask. `docs/product.md` §4 covers what a surface does with a shelved question and how an answer arriving later reaches the work it should trigger.

**The model is told once about nobody being there, and the rest of the run is answered from that.** The first `Unavailable` reaches the model as an instruction to stop asking and to say in its answer what could not be settled. Every later question the model makes to that tool returns the same thing without reaching the channel again, and each one is recorded with `asked` set to `false`, so a run that kept asking is a count in `per_node.consultation_resolutions` rather than a hundred round trips. A resumed run starts over, since the process that continues it may have somebody the one that stopped did not.

**A question a node body asks always reaches the channel.** That rule is an instruction to stop asking, and a loop in a `Deterministic` or `LLMNode` body cannot read one, so `ctx.call_tool("consult", ...)` is never answered from it. A node walking a list and asking about each item asks about each item.

**`Shelved` never engages it, whichever asked.** A channel that shelves has reached somebody, and the next question is a different question.

**A channel that answers in the process that asked says so**, which is what lets an
`AgentNode` overlap two consultations in one turn:

```python
def ask_the_queue(question, options, about):
    return queue.answer(question, options)

ask_the_queue.may_suspend = False
```

A run stops on a turn boundary, so a call that can raise `Suspend` cannot overlap another, and
an undeclared channel is treated as one that can. `SimulatedEndUser` and `unattended()` declare
it themselves. Listing a consult tool in `concurrent_tools` whose channel does not declare it is
refused where the node is built; where a run then replaces the channel with one that can suspend
(`RunEnvelope(end_user=...)`), that run's consultations go one at a time.

#### 4.6.4 Naming what a question is about

A question is text, and text moves. `about=` is a short stable name for the thing the question concerns, the same name every time it comes up, and it is what an answer arriving later is matched on:

```python
ctx.call_tool("consult",
              question=f"{show} was last watched {gap.days} days ago. Keep it?",
              options=["keep", "drop"], about=f"show:{show_id}")
```

Without it there is nothing but the wording. A question embedding a day count is a different question tomorrow, so a shelf holds it twice and the end user is asked twice. `about` reaches the channel as its third argument, is recorded on the consultation, and is what `Pipeline.answer_shelved` files an answer against (`docs/product.md` §4).

It is part of the cassette key, along with the question and the options, so two calls asking the same words about different things replay as the two calls they were. What `about` does not do is stand in for the wording: a replay serves the answer recorded for the exact call that was made.

**A channel serving an answer it stored earlier says when it was given**, which is what separates a count of answers from a count of records:

```python
return Reply(stored.text, chose=None, answered_at=stored.at)
```

`answered_at` of `None`, which is every channel that asks and waits, means they answered during this call.

#### 4.6.5 Asking about each of many things

`route=` is one decision per node execution, so it fits a node that asks one question and branches on the answer. A node asking about each of a list of things handles each answer where it asks:

```python
def resolve_each(inputs, ctx):
    for entry in inputs["queue"]:
        reply = ctx.call_tool("consult", question=f"Keep {entry['show']}?",
                              options=["keep", "drop"], about=f"show:{entry['id']}")
        if getattr(reply, "chose", None) == "drop":
            entry["status"] = "abandoned"
    return inputs
```

Every call reaches the channel (§4.6.3), each is its own `consultation` record carrying its `about`, and `reply.chose` is what the tool's rule read. A reply that is `Unavailable` or `Shelved` has no `chose`, which is why the branch reads it rather than the text.

### 4.7 `extract_to_schema`: node or tool

Extraction is normally a node. `LLMNode(build_prompt, output_schema=ProductFacts)` is one model
call at a fixed point, with the `unknown` branch enforced at construction and its own per-node
metrics, and `LLMNode(..., over="documents")` runs it once per document.

`extract_to_schema` is for the case a node cannot cover: the agent decides during the run that
it needs typed facts out of something it has just read. The nodes are fixed before the run
starts, so that decision has nowhere else to go.

---

## 5. The finish check

`AgentNode(finish_check=...)` runs after the answer validates against the output schema. It
returns a string to refuse the answer, which reaches the model as a failed `finish`, or `None` to
accept it.

```python
def cited_what_it_read(answer: Answer, ctx: AgentContext) -> str | None:
    opened = {c.arguments["doc_id"] for c in ctx.tool_calls if c.name == "read" and c.ok}
    missing = sorted(set(answer.sources) - opened)
    if missing and not ctx.finish_attempts:
        return f"Sources {missing} were cited but never read. Read them, or cite what was."
    return None
```

### 5.1 What the check can see

`ctx.tool_calls` holds every call the node has made. Each carries `name`, `arguments`, `ok`, and
`result`, which is what the tool returned or the model-facing error it raised.

Tools run before `finish` whatever order the model asked in. A turn can carry several calls, so a
check testing what this run read sees the reads that arrived alongside the answer rather than
missing them by one turn.

`ctx.finish_attempts` holds the answers this check has already refused, each with its arguments
and the refusal that was sent.

### 5.2 Refusing the same answer twice

A refusal states what is wrong and what would fix it, in the words the model reads next. A
refusal the model believes it has already satisfied produces a loop: it re-sends the same payload,
the check refuses again, and the node spends its step budget without producing the answer it
refused.

Reading `ctx.finish_attempts` is what avoids it. A check that has refused an answer once and seen
no change has learned that the refusal is not actionable, and accepting the answer is usually
better than a run that ends with nothing.

One payload refused three times stops the node. The node record carries
`termination: "finish_rejected"`, the refusals are on the `finish` tool call records, and the node
produces no output. This bounds the cost of an unactionable refusal; it does not repair one.

### 5.3 Refusing an answer that cites what was never read

An agent that cites a page it did not open, or quotes text the source does not contain, has
asserted something it did not establish (FT-09, FT-10). Both are checkable from what the run
already records:

```python
from simple_agents import contains_normalised, url_was_read, urls_read

def cites_a_page_it_read(answer: Finding, ctx: AgentContext) -> str | None:
    if answer.source is None or url_was_read(ctx, answer.source):
        return None
    if ctx.finish_attempts:          # refused once and the answer did not move (§5.2)
        return None
    return (
        f"source must be a page read in this step. Read: {urls_read(ctx)}. Cite one of "
        f"those, or answer with no source."
    )
```

`url_was_read(ctx, url)` is true when that address was an argument to a tool call this node made
that succeeded. Any tool counts, and addresses are compared with `same_url`, so a trailing slash
or a `www.` does not make a page the agent read look like one it did not. `urls_read(ctx)` is
those addresses as the model wrote them, for naming in the refusal.

`contains_normalised(haystack, needle)` is the same check for a quote rather than an address, and
is what a `Deterministic` verifier node uses when the source is a passage rather than a page:

```python
if not contains_normalised(passage, answer.quote):
    return Answer(answer=Unknown(reason="the quote is not in the cited passage"))
```

It folds case, accents and punctuation, so `O₂` matches `O2` and a curly quote matches a straight
one. It does not join words across a separator: `therapist` does not match `the rapist`, and
equally `O₂` does not match `O 2`. A project whose sources write one word two ways compares on
its own rule.

What counts as grounded stays the project's decision. An exact span, the same host, a matching
quote and how many strikes to allow are facts about the task.

---

## 6. What a contract test asserts

Every tool the library ships has a contract test, and every tool a project writes needs one
(FT-23). A contract test checks the description against the behaviour, so a description that
has drifted from what the tool does fails it. It asserts four things:

- the result shape the description promises,
- the failure the description says can happen, and that it is the right kind,
- the boundary the description states, such as a path outside the workspace or a host outside
  the allow-list,
- the schema the model is offered, where a handle parameter must not appear.

Fix the fixture's content in the test, so the expected result is written down rather than read
back out of what the code produced.

**Quote the sentence under test.** A test whose name and docstring carry the words being checked
shows the reader which claim moved when it fails, and shows a description with no test behind it.

```python
def test_a_title_that_matches_nothing_comes_back_empty(lookup):
    """"Returns an empty list when no title matches." Finding nothing is a result rather
    than a failure: raising would put a successful lookup in the record's error field."""
    assert lookup.fn(title="Sir Nobody Whatsoever") == []
```

### 6.1 What a contract test does not catch

It compares the description against the code, so it catches the two drifting apart. It does not
catch a description that matches the code and is wrong about the world.

A search tool's description once told the model that where the top hits are not what it wanted,
"the collection does not cover that subject". The tool did exactly that, and its contract test
passed. A lexical retriever finding nothing has established that those words did not reach a
passage, not that the fact is absent, so the description taught the model to conclude absence
from a retrieval miss.

Read the description as prompt text, and ask what a model would infer from it that the tool
cannot support.

---

## 7. Tools from an MCP server

An MCP server is one somebody else runs, offering tools over the Model Context Protocol: a
ticketing system, a warehouse, a document store. Its tools become tools of this project, with
one thing added that the protocol cannot supply.

Needs the optional extra:

```
pip install 'simple-agents[mcp]'
```

### 7.1 Declaring a server's tools

A server is an object the project constructs and holds. Constructing it connects nothing:

```python
from simple_agents import SideEffectClass, ToolRegistry
from simple_agents.mcp import MCPServer

tickets = MCPServer.http("https://mcp.internal/tickets")

registry = ToolRegistry()
registry.add_all(tickets.tools(effects={
    "tickets_search": SideEffectClass.READ_ONLY,
    "tickets_create": SideEffectClass.WRITES,
    "tickets_delete": SideEffectClass.IRREVERSIBLE,
}))
```

`MCPServer.stdio(command, args)` runs the server as a child process instead, which is how most
servers on a builder's own machine are started:

```python
files = MCPServer.stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "./corpus"])
```

That command runs on the machine the agent runs on, with whatever that account can reach. It is
the project's to trust, on the same terms as any dependency it installs.

**`effects` is the selection and the declaration at once.** A tool the server offers that it does
not name is not registered, so a server that gains a tool does not gain the agent one. A tool it
names that the server does not offer is refused when the run starts, naming what the server does
offer.

The connection opens on first use and is kept, so a product serving a run per request pays for it
once rather than per request. It closes when the process exits, and `with MCPServer.http(...) as
server:` closes it at a known point.

### 7.2 What the hints propose

An MCP tool carries four hints: `readOnlyHint`, `destructiveHint`, `idempotentHint` and
`openWorldHint`. **The specification says a client must treat them as untrusted unless the
server is**, and the MCP project's own account of why is that enforcing contracts across
untrusted servers is impractical. So a hint is what a server claims, and `side_effect_class` is
what a person declared. Both are kept.

Calling `tools()` with nothing declared reads the server and refuses, with one line per tool:

```
MCPServer('https://mcp.internal/tickets') offers 3 tool(s) and effects= declares none. A tool
cannot be registered without a side-effect class, because an evaluation reads it to decide
whether the tool may execute inside a rollout (FT-19). The server's hints propose:

    effects={
        'tickets_create': SideEffectClass.WRITES,  # destructiveHint: false
        'tickets_delete': SideEffectClass.IRREVERSIBLE,  # destructiveHint: true
        'tickets_search': SideEffectClass.READ_ONLY,  # readOnlyHint: true
    }

A hint is what the server claims, not what it guarantees. Confirm each against what one call
does, and declare only the tools this agent needs: a tool left out is not registered. That
confirmation is the brief's `tool_effects` answer.
```

That refusal is how the declaration is written the first time. What it proposes:

| Hints | Proposes |
|---|---|
| `readOnlyHint: true` | `read_only` |
| `readOnlyHint: false`, `destructiveHint: false` | `writes` |
| `readOnlyHint: false`, `destructiveHint: true` | `irreversible` |
| No annotations at all | nothing; the class has to be declared |

A tool carrying no annotations gets no proposal. The specification's defaults are
`destructiveHint: true` and `openWorldHint: true`, which read as `irreversible`, and an
evaluation refuses every tool in that class (§1.4). Servers publishing no annotations are common,
so a declaration proposed from their absence would have to be overridden tool by tool before
anything ran.

`idempotentHint` and `openWorldHint` are recorded and propose nothing: neither names an effect,
and the occurrence count in a cassette key already covers a call made twice (§3.1).
`spends_money` is never proposed, because MCP publishes no cost hint. A paid MCP tool declares
`declared_cost` the way any paid tool does:

```python
tickets.tools(
    effects={"tickets_enrich": SideEffectClass.SPENDS_MONEY},
    costs={"tickets_enrich": DeclaredCost(currency="USD", per_call=0.01)},
)
```

`touches=` is per tool on the same call, and takes what `@tool` takes (§1, item 6).

### 7.3 What a run records

Each tool's manifest entry carries an `mcp` object: the server, the four hints, the class the
hints proposed, the class the project declared, and whether the two agree.

```json
{"server": "tickets", "hints": {"read_only": false, "destructive": true,
                                "idempotent": false, "open_world": true},
 "proposed": "irreversible", "declared": "writes", "agrees": false}
```

A project that declared something milder than the server claims has said so in the manifest,
where a later reader can find it. `agrees` is true where the server proposed
nothing, since a claim that was never made cannot disagree.

The manifest also carries one `mcp` entry per server the run declared tools from, holding
whether the run read the server or was served a recording, what the server offers that the
project did not declare, and the `drift` between what it offers now and what a recording holds
(`docs/run-envelope.md` §2.10). FT-43 reads that drift: a description reworded, a schema
changed or a tool withdrawn is a change the builder agreed to nothing about, and it reaches them
as a check failure rather than as a production incident.

### 7.4 How an MCP tool is replayed

An MCP tool is an ordinary tool: stored in the cassette, served on a replay, taking no handle
(§3.2), and keyed on the node, its name, its version, its arguments and the occurrence (§3.1).

**Its version is a digest of the name, the description and the schema the server sent.** The
derived version cannot see any of those: it hashes the function and what it closed over, and the
function here closes over a connection, which is the same text for every tool one server offers
(§3.1.1). So a server that rewords a description or changes a schema invalidates the recording
rather than answering under the key of what it replaced.

**A server's tool listing is a call, so it is recorded and served like one.** A live run reads
the server once and records what it offered. A replayed run is served that listing and reaches no
server: no request, no child process, no network. This is what lets a recorded evaluation run in
CI, where the pipeline is built once per rollout and none of those builds can reach anything.

A replay whose recording holds no listing for a declared server raises `CassetteMiss` naming the
re-record, rather than reaching the server under a replay.

Two consequences worth stating:

- **A replayed run measures the project's code against what the server said then.** A server that
  has since changed is not what the replay exercises, which is the point of a replay and also its
  limit.
- **A description is prompt text**, so a reworded one moves the version, misses, and reports the
  difference. Re-recording is what takes the new wording, and reading it is what tells the builder
  whether the tool still does what they agreed to.

### 7.5 What this client does not offer

A server can ask the client for three things while a tool call is in flight. This library answers
none of them, and declares none of them at `initialize`:

| Request | What the server is asking for |
|---|---|
| `elicitation/create` | something from the end user |
| `sampling/createMessage` | a generation from the client's own model |
| `roots/list` | which directories the client exposes |

A server reading that declaration knows what it is connected to, and one that needs any of the
three is told so rather than left waiting.

**A server may offer fewer tools for that reason.** Some publish a tool only to a client
declaring the capability it needs. Measured against `@modelcontextprotocol/server-everything`: 13
tools to this library, and 16 to a client declaring all three. The three held back are absent from
the listing, so they are absent from the proposal `tools()` refuses with, and nothing in the
project says they exist. Where a server's documentation names a tool that never appears, this is
the first thing to check.

**A tool the server will only run as a task cannot be called.** Task execution is a protocol
revision that the specification has since removed, and a tool declaring
`execution.taskSupport: "required"` answers with an error:

```
MCP error -32601: Tool <name> requires task augmentation (taskSupport: 'required')
```

The server reports that inside the result, so it reaches the model as a failed call and the run
continues. Declaring such a tool in `effects=` is what makes the failure visible when it is called
rather than at declaration.

### 7.6 What a server does when it fails

A tool the server reports as failing raises `ModelFacingError`, so the model gets a turn to
correct the call. MCP reports a tool's own failure inside the result rather than as a protocol
error, which is the same distinction §1.3 draws.

An unreachable server raises `CallerFacingError` and ends the run, after the connection's own
attempt to reopen. An infrastructure failure handed to a model produces an answer built on
nothing (FT-22). A project that would rather carry on without the server routes around it
(`docs/pipeline.md` §1.3).
