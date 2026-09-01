# A conversation that outlives the run

One turn is one run. A chat's second message is a second run of the same pipeline, with its own trajectory, manifest and budget. A conversation is what carries the messages between them.

A value moving from one node to the next inside a run travels on an edge (`docs/pipeline.md` §1.3). What the agent remembers about a person lives in memory, which holds facts across runs and is reached through tool calls (`docs/memory.md`).

---

## 1. Declaring the store, and naming the conversation

The store is project configuration and is set once. Which conversation a run is a turn of changes per request, so it is an argument to the run:

```python
from simple_agents import ConversationStore, RunEnvelope

env = RunEnvelope(run_dir="runs/", conversations=ConversationStore("conversations/"))

def handle(question: str, chat_id: str):
    result = pipeline.run(
        {"question": question}, envelope=env.with_live(), model=client,
        conversation_id=f"chat-{chat_id}",
    )
    return result.output
```

`directory` is the project's to choose. A run naming a conversation through an envelope that declares no store is refused before it starts, the same as a memory tool with no store.

**A `conversation_id` names one conversation the project minted**: a chat, a ticket, a channel. It is recorded in the clear on the manifest of every run of that conversation, as it was given. A project that puts a person's identifier there has put that identifier in an artifact.

The file the conversation is kept in is named by a digest of the id, so an id holding a slash or five hundred characters does not decide a path. `store.conversation_ids()` lists what is held, read out of the files rather than from their names.

## 2. A node takes part by reading it

The prompt function splats the conversation where the history belongs:

```python
SYSTEM = "Answer as the bookshop's assistant."

def build_prompt(inputs, ctx):
    return [
        {"role": "system", "content": SYSTEM},
        *ctx.conversation,
        {"role": "user", "content": inputs["question"]},
    ]
```

**A node takes part by continuing the conversation**, which means putting its messages into what the prompt returns. The library then writes what that node produces back. A node that never reads it takes no part, and neither does one that reads it and renders it into something else: the step that summarises a conversation reads every message and turns them into one string, and its own prompt and answer are not a turn of the chat it just summarised (§5).

**A system message is never stored.** It is the node's standing instruction, the prompt supplies it every turn, and one carrying today's date or the reader's current plan has to be able to change. Storing it would put turn 1's copy at the head of turn 40.

**Splat the conversation rather than rebuilding its messages.** The library works out what a turn added by taking the conversation's own messages back out of what the prompt returned, and it matches them by identity first and by content second. A prompt that constructs new dicts with the same content still records one turn's worth; one that rewrites them records the rewritten copies as new.

**A run that names no conversation gets an empty one rather than nothing**, so the same prompt function serves a chat and a one-shot request without a branch around the splat. `ctx.conversation.id` is `None` there, which is what a node reads to tell them apart.

## 3. What a turn is

A turn is opened before the first model call and closed when the node finishes. What the node produces goes on as it is produced, not in one write at the end:

- A run killed mid-turn leaves the turn on the conversation. The next turn is not answering a person whose message the conversation never recorded.
- A run that errors closes its turn with `outcome: "error"` and whatever it had. A turn still open carries `None`, which is a run that has not finished.
- A run suspended for a consultation may resume days later, and the conversation does not stay empty for that whole gap. The resumed run continues its own turn, so what it eventually answers lands in the turn that asked and no turn is left open.

That is what the trajectory and the manifest already promise, applied to one more artifact.

**A fan-out reads the conversation and adds nothing to it.** A conversation is one sequence of turns and a fan-out is many items at once, so there is no order for its items to go on in. Each item is sent what was said before; what the items produce is on their own trajectory records. Where a fan-out's work belongs in the conversation, a node running once per run puts it there.

## 4. Reading a conversation back

```python
thread = ConversationStore("conversations/").thread("chat-8817")

thread.messages()                 # every message, oldest first
thread.compact()                  # said/answered pairs, without the agent's own working
thread.without_provider_state()   # every message, minus what one backend requires verbatim
thread.turns()                    # a Turn each: number, run_id, said, answered, outcome
thread.turn_count                 # how many turns; the next run is this plus one
thread.run_ids()                  # the run that produced each turn
thread.forget()                   # delete the conversation
```

`compact()` is the cheaper read: it carries what was said and what was answered and leaves out the tool calls and observations a turn made. A later turn that does not need the agent's working reads this instead.

`without_provider_state()` is what a conversation recorded against one backend and continued against another needs. A tool call recorded against Gemini carries a `thought_signature` that backend expects back on the next request, and an OpenAI-dialect adapter refuses to translate a call carrying it (`docs/model-clients/gemini.md`). This gives up the reasoning state rather than the conversation.

**Nothing here bounds a conversation.** A run is bounded by its budget and a conversation is not, so forty turns is forty budgets. `thread.turn_count` and the runs `thread.run_ids()` names are what a product reads to decide that a conversation has gone on long enough:

```python
from simple_agents import runs

spent = sum(
    float((run.manifest.get("totals", {}).get("cost") or {}).get("value") or 0.0)
    for run in runs("runs/", nested=True)
    if run.run_id in set(thread.run_ids())
)
```

## 5. Compaction

Thirty turns does not fit. `compact_conversation` replaces the older messages with a summary of them and leaves the newest alone. It makes no model call of its own: the summary is an argument, so whichever node produced it did so on the record, under its own budget.

**On an `AgentNode`, the model calls it and writes the summary itself**, out of the conversation it is already holding:

```python
from simple_agents.builtins import compact_conversation

node = AgentNode(build_prompt, tools=[search, compact_conversation(keep_last=6)],
                 output_schema=Answer, budget=budget)
```

**Without an `AgentNode`, an `LLMNode` writes the summary and a `Deterministic` node files it.** That is two steps and one model call, and it is the shape to reach for when compaction should happen on a rule rather than on the model's judgement:

```python
from pydantic import BaseModel

from simple_agents import Deterministic, LLMNode, Pipeline
from simple_agents.builtins import compact_conversation

class Summary(BaseModel):
    summary: str

def summarise(inputs, ctx):
    older = ctx.conversation.messages()[:-6]
    return "Summarise this conversation for whoever continues it:\n" + str(older)

def file_it(summary, ctx):
    ctx.call_tool("compact_conversation", summary=summary.summary)
    return summary

pipeline = Pipeline(
    [
        LLMNode(summarise, output_schema=Summary, node_id="summarise",
                allow_unknown=False),
        Deterministic(file_it, node_id="compact", tools=[compact_conversation()]),
    ],
    budget=budget,
)
```

`allow_unknown=False` is right here: a conversation always has something to summarise, so the output has no absent state (`docs/pipeline.md` §2.2).

A `Deterministic` node cannot hold a tool that takes a `ModelHandle` (`docs/tools.md` §3.2), which is why the summary is written by a node rather than inside the tool.

**The messages a compaction replaced stay in the file and stop being read.** What was dropped is still there for anything reading the conversation's records. The summary goes at the head, where what it summarises was.

`keep_last` is how many of the newest messages are left alone, so the turn in progress and the ones around it are not summarised away.

A tool taking a `Conversation` is re-run during a replay rather than served from the cassette, the same as one taking a `Memory`, since the next turn reads what it wrote.

**A replay reproduces the conversation into whatever store it is given.** Replaying onto a conversation that has moved on since the recording is a `CassetteMiss`: the messages a node sends are part of the call's key, so drift is refused rather than answered from a recording made against different history.

## 6. What is recorded

Every run of a conversation carries a `conversation` object on its manifest (`docs/run-envelope.md` §2.1):

```json
"conversation": {"directory": "conversations/", "id": "chat-8817",
                 "turn": 4, "carried_in": 6, "node_id": "reply"}
```

`turn` is which turn this run was. `carried_in` is how many earlier messages the node was actually shown, and `node_id` is which node read them.

**`carried_in` of zero on a turn past the first is a conversation being written and not read**: the file fills up correctly, every run says which turn it is, and the agent starts from nothing every time. That is what the field is for.

The messages themselves are on each run's trajectory, in the first `model_call` record's `inputs.messages`, so what a turn was actually sent is on the record whatever the conversation now holds.

## 7. In an evaluation

`Example.conversation` is what the agent has already been told when the example starts, and `Example.turns` is a conversation the rollout runs through in order (`docs/evaluation.md` §11).

## 8. What redaction reaches, and what deletion does not

A message is redacted before it is stored, by the run's rules (`docs/run-envelope.md` §6), the same as a memory entry and a trajectory record. A message a rule changed carries `redactions` naming which of its fields. The three limits are memory's (`docs/memory.md` §4):

- The rules match known credential formats and values declared in `secret_env`. A secret in neither category is stored as written.
- A rule added later does not reach a message already stored.
- The conversation is a copy of run content that outlives every run and every trajectory. Deleting a run directory does not delete what that run said.

`thread.forget()` removes one conversation.

## 9. Two turns of one conversation at once

A conversation is a file each turn appends to. Appending needs no read, so two runs writing to one conversation cannot lose each other's messages or renumber them.

**What is not ordered is which of two simultaneous turns lands first.** Two workers answering one person's double-sent message write two turns, and which comes first is whichever reached the file first. A product that has to serialise them holds its own lock on the conversation before it starts the run, the same way it would around any other per-conversation work.

**A message longer than the operating system's atomic write can interleave with another process's**, which is the one way a line can be damaged. A single process writing many turns at once is safe: those are ordered by a lock the library holds. A reader skips a line it cannot parse, so a damaged line costs that message rather than the conversation.
