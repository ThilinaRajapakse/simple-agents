# Memory

An agent that remembers something after the run ends reads and writes a memory store. The store
is declared on the envelope and whose memory a run reads is an argument to the run, and it is
reached through tool calls and nothing else.

**The store holds what the agent learns and writes.** What the end user tells the product is the
project's data model: written by the surface the person acted on, kept wherever the project keeps
its data, and reaching the run as inputs. A rating somebody clicked, a queue they built and a
form they filled in are the project's. A preference the agent was told in conversation and a fact
it worked out mid-run are the store's. Who writes it is the test.

A run started by an answer is on the agent's side of that test. A `remember` inside the pipeline
`Pipeline.answer_shelved` triggers is the agent writing down what it learned from a reply, and
that is the store's case (`docs/product.md` §4.3).

A value moving from one node to the next inside a run travels on an edge
(`docs/pipeline.md` §1.3); memory is for what outlives the run.

---

## 1. Declaring the store

```python
from simple_agents import MemoryStore, RunEnvelope

env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/"))

result = pipeline.run(question, envelope=env, model=client,
                      memory_scope=f"user-{user_id}")
```

`directory` is where the entries live and is the project's to choose. `memory_scope` separates
one end user's memory from another's: two runs over one directory under different scopes share
no entry. Every run that reaches memory names one, because one scope for every end user is one
memory for every end user.

**The two are declared apart because they have different lifetimes.** The directory is project
configuration, set once. The scope changes per request, so a request handler names it on the run
and one envelope serves everybody (`docs/product.md` §3).

The manifest records the directory, a digest of the scope, and how many entries the store held
when the run ended. The scope itself is not recorded, since it usually identifies a person.

### 1.1 A resumed run is given the scope again

The manifest holds the digest rather than the value, so `Pipeline.resume` cannot read the scope
back the way it reads a conversation's thread id. It is passed again, and one whose digest
differs from the scope the run started under is refused, so a reply filed against the wrong run
cannot reach another end user's memory:

```python
result = pipeline.resume(run_id, envelope=env, model=client, answer=reply,
                         memory_scope=f"user-{user_id}")
```

`Pipeline.answer_shelved` takes it too, for the answering pipeline that reaches a memory tool.

---

## 2. Reading and writing it

There are three built-in tools. Each is a factory, so the name is the project's to choose.

```python
from simple_agents import ToolRegistry
from simple_agents.builtins import memory_search, recall, remember

registry = ToolRegistry([remember(), recall(), memory_search()])
```

| Tool | Class | What it does |
|---|---|---|
| `remember` | `writes` | Stores one fact under a key. Returns the key and whether something was replaced |
| `recall` | `read_only` | Reads back one fact by its key. Returns `found: false` where nothing is stored |
| `memory_search` | `read_only` | Finds stored facts by the words in them. Returns the best matches and how many facts are stored |

**Search is lexical by default**, the same BM25 `document_search` uses, over the key and the
value together. A query sharing no words with a stored fact does not find it, so a fact stored
as "prefers books under 300 pages" is not found by a search for "length preference". §2.4 is
how to close that gap.

**A search that matches nothing over a store that holds something returns `keys`**, the first
50 in alphabetical order, so a miss on wording is recoverable with one `recall`. `stored` says
how many there are in total, so a store past 50 says so rather than appearing to be that size.

A write is a put rather than an append: storing under a key that already holds something
replaces it. §5 says why, and what follows for a fact with no natural key.

### 2.1 A node reads memory the way it reads anything else

An `AgentNode` calls these tools because it chose to. A `Deterministic` node calls one at a
fixed point, and what comes back travels on to the next node on an edge:

```python
from simple_agents import Deterministic, LLMNode, Pipeline

def load_what_is_known(inputs, ctx):
    stored = ctx.call_tool("memory_search", query=inputs["question"])
    return {"question": inputs["question"], "known": stored["results"]}

pipeline = Pipeline(
    [
        Deterministic(load_what_is_known, node_id="remember", tools=[memory_search()]),
        LLMNode(build_prompt, output_schema=Answer, node_id="answer"),
    ],
    budget=budget,
)
```

**There is no `ctx.memory`.** A node reaches the store through a tool call, so what it read is
in a `tool_call` record parented to that node, and what it did with it is in the next node's
`inputs`. A value read from a store that no record names cannot be explained from the
trajectory, and the per-node numbers would be computed over inputs that are not the real inputs.

### 2.2 A project's own memory tool

A parameter annotated `Memory` is filled by the library and left out of the schema the model
sees, the same as `ModelHandle` and `Workspace` (`docs/tools.md` §3.2):

```python
from simple_agents import Memory, SideEffectClass, tool

@tool(side_effect_class=SideEffectClass.WRITES)
def remember_preference(memory: Memory, field: str, value: str) -> str:
    """Store one stated preference. Returns the key it was stored under."""
    memory.remember(f"preference.{field}", value)
    return f"preference.{field}"
```

A tool holding one cannot be declared `spends_money` or `irreversible`, on the rule that covers
every re-run tool (`docs/tools.md` §3.2).

### 2.3 A run that reaches no memory is refused

Two halves have to be present and either can be absent on its own. With no store on the
envelope:

```
Tool(s) 'recall', 'remember' take a Memory and this envelope declares no store, so the run
would stop at the first one having spent whatever the nodes before it spent. Memory outlives
the run, so the library will not invent a location for it.
Declare it: RunEnvelope(run_dir='runs/', memory=MemoryStore('memory/')), and name whose memory
the run reads: Pipeline.run(..., memory_scope=f'user-{user_id}').
```

With a store and no scope on the run:

```
Tool(s) 'recall', 'remember' take a Memory and this run names no memory scope, so the run
would stop at the first one having spent whatever the nodes before it spent. The store holds
one end user's memory per scope and the library will not decide whose memory this run reads.
Name it: Pipeline.run(..., memory_scope=f'user-{user_id}').
```

The library reads both off the tool declarations and refuses before the run starts.

### 2.4 Finding a fact phrased differently from the question

`memory_search` given an embedding client searches by meaning as well as by the words:

```python
from simple_agents.adapters import SentenceTransformerEmbeddings
from simple_agents.builtins import Hybrid, RRF

registry = ToolRegistry([
    remember(), recall(),
    memory_search(embeddings=SentenceTransformerEmbeddings(), ranking=Hybrid(fuse=RRF(k=5))),
])
```

**Each fact is embedded once and the vector is stored beside it**, in the same file as the
fact. A fact written before the store had embeddings, or written under a different embedding
model, is embedded the first time a search reads it and the vector is written back. A search
that finds every vector already in place embeds the query alone.

A store is therefore a mixture of embedding models, in the same way §4 makes it a mixture of
redaction rules. `entry.embedded_by` says which model made an entry's vector.

`ranking` takes the same values it takes on a `DocumentIndex`, and is required wherever
`embeddings` is given, for the reason `docs/retrieval.md` §4 states. `docs/retrieval.md` is the
whole surface: which models embed, how lexical and semantic results combine, reranking, and
what the model calls cost.

**The search becomes a model call, so it is charged and recorded.** Embedding the query is a
`model_call` record parented to the tool call, charged to the run's budget and keyed into the
cassette. The embedding model is a second identity in the run, and FT-14 reads it, so pin it.

### 2.5 What each tool returns

A node that hands one of these results to the next node reads these field names.
`document_search`'s are different: a memory result is keyed on `key`, not on `doc_id`.

```json
{"key": "preferred_length", "replaced": false, "stored_at": "2026-08-13T09:14:02.117Z"}

{"found": true, "key": "preferred_length", "value": "prefers books under 300 pages",
 "stored_at": "2026-08-13T09:14:02.117Z"}

{"results": [{"key": "preferred_length", "value": "prefers books under 300 pages",
              "stored_at": "2026-08-13T09:14:02.117Z", "score": 0.6633}],
 "stored": 4}
```

In order: `remember`, `recall`, and `memory_search`. A `recall` that found nothing returns
`{"found": false, "key": ...}` and no `value`. A `memory_search` given an embedding client adds
`retriever` to each result, naming `lexical` or `semantic`, and scores from the two are not
comparable. A search that matched nothing over a store that holds something adds `keys`.

---

## 3. Memory in an evaluation

**Each rollout gets its own store.** It holds what the example declares and what that rollout
writes into it, and it is discarded with the rollout.

```python
Example(
    id="q4",
    inputs={"question": "Find me something to read"},
    expected="The Left Hand of Darkness",
    split="held_out",
    memory={"preferred_length": "prefers books under 300 pages"},
)
```

Rollouts run concurrently over one pipeline. A store they shared would let one rollout answer
out of another rollout's write, and the same evaluation at the same seed would report a
different number each time depending on which rollout got there first. What an example's agent
already remembers is therefore part of the example, next to its inputs and its expected answer.

**This measures what the agent does with what it remembers**, over a memory the project
controls. A task whose answer depends on a conversation is a separate thing, and
`docs/evaluation.md` §13 is where it lives: an example carries what was already said, or the
turns the rollout goes through in order.

`memory` is written to the JSONL file with the example and read back with it. Every rollout
names the same scope, `rollout`, since each has a store to itself.

---

## 4. What is recorded, and what redaction reaches

Every read and every write is a `tool_call` record, parented to the node that made it, with the
arguments and the result in full. Nothing else in the run says the store exists except the
manifest's `memory` object.

**A value is redacted before it is stored.** The run's rules run over it on the way in, and the
entry records what they replaced and which rules were in force:

```json
{"key": "vendor_note", "value": "the key [redacted:sk_prefixed_key] was in the sample",
 "stored_at": "2026-08-10T09:14:02.117Z", "redactions": ["value"],
 "rules": {"enabled": true, "builtin": true, "declared_rules": [], "secret_env": []}}
```

**Redaction here has three limits.** Two of them follow from the store outliving the run that
wrote it.

- The rules match known credential formats and values declared in `secret_env`
  (`docs/run-envelope.md` §6). A secret in neither category is stored as written.
- A rule added later does not reach an entry already stored. The rules travel with the entry so
  a reader can tell what an entry was scanned against.
- The store is a copy of run content that outlives every run and every trajectory. Deleting a
  run directory does not delete what that run remembered.

A project that has to remove something removes it by key:

```python
MemoryStore("memory/").scoped(f"user-{user_id}").forget("vendor_note")
```

---

## 5. Replay, and why a write is a put

A tool taking a `Memory` is re-run during a replay rather than served from the cassette, the
same as one taking a `Workspace`. A replayed run makes the same writes and reads the store it
rebuilt, so it reaches the same answers as the run it is reproducing.

**This is what makes a write a put rather than an append.** Re-running has to leave the state
that running once left. Storing the same fact under the same key twice stores it once; appending
would store it twice, and a replay would report a store the live run never had.

A fact with no natural key goes under one derived from what it says, which keeps the write
idempotent:

```python
key = f"fact.{hashlib.sha256(fact.encode()).hexdigest()[:12]}"
memory.remember(key, fact)
```

---

## 6. Reading the store outside a run

```python
mine = MemoryStore("memory/").scoped(f"user-{user_id}")

len(mine)                     # how many facts are stored
mine.keys()                   # every key, sorted
mine.get("preferred_length")  # one entry, or None
for entry in mine.entries():  # oldest first
    print(entry.key, entry.value, entry.stored_at)
```

`scoped` is what a run reaches through a memory tool, and what a surface showing somebody their
own stored facts reads directly. It holds no file open and executes nothing. Two processes writing one entry leave
whichever finished last; each write is a single atomic rename, so a reader never sees half an
entry.
