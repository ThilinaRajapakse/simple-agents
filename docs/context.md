# The context builder

Every model call is assembled by a context builder: it decides which messages go on the wire
for that call. `AppendAll` is the default and sends everything it is given. A project that has
to send less than the whole conversation, or more, supplies its own.

---

## 1. When a context builder runs

Once for every model call, under every node kind.

| Where the call is made | What it is handed |
|---|---|
| `LLMNode` | the messages the prompt function built |
| `LLMNode(over=...)` | that item's prompt alone, once per item |
| `AgentNode(over=...)` | that item's own conversation, once per turn of it |
| `AgentNode` | the conversation so far, once per turn |
| A tool holding a `ModelHandle` | that call's own prompt (`docs/tools.md` §3.2) |

```python
from simple_agents import AppendAll, LLMNode

node = LLMNode(build_prompt, output_schema=Answer, context=AppendAll())
```

`context` defaults to `AppendAll()` and is set per node. There is no envelope-level or
pipeline-level default, so a node's context configuration has one source.

What comes back is what goes on the wire for that one call. Sending less is what §2 and §3 are
about. Sending more is how a node tells the model something that depends on where the run has
got to, and §4.1 has a worked example.

The conversation an `AgentNode` keeps is not changed by any of this. A message left out of one
call is still there on the next, and a message added to one call is not. What was sent is on
the `model_call` record, in `inputs.messages`.

---

## 2. Context overflow

A call goes through when the request fits the model's context window. Three quantities bear on
that, and one of them cannot be measured.

| Quantity | Where it comes from | Exact |
|---|---|---|
| The context window, in tokens | The backend's model list, `GET /v1/models` | Yes, before any call |
| The previous call's prompt, in tokens | `usage` on the response | Yes |
| What the next, unsent prompt will cost | Nothing reports it | No |

No backend counts a prompt that has not been sent, and no chat completion carries the window in
its response. A message list checked against a token limit before the call is therefore
converted from characters, which makes it an estimate. Overflow is answered in two layers: the
backend's refusal, which is always in force, and an optional pre-flight estimate.

### 2.1 The backend's refusal

In force under every configuration. A request longer than the window is refused by the backend
and the adapter raises `ContextOverflow`; the library adds the node and the call index before
it reaches the caller. `docs/model-clients.md` §7 covers what an adapter for a backend the
library does not ship has to raise. One that raises something else still surfaces the backend's
own message.

### 2.2 The optional pre-flight estimate

```python
AppendAll()                          # the backend decides what does not fit
AppendAll(max_input_tokens=200_000)  # stop before reaching the backend
```

Read `max_input_tokens` off the backend rather than picking a number, and leave headroom, since
the same window has to hold the output. Each adapter's page names the field that publishes it
(`docs/model-clients/mistral.md` §2, `docs/model-clients/vllm.md` §2).

**The ratio is measured.** The library holds the characters it sent on the previous call in
this node and the prompt tokens the backend reported for it, divides them, and extrapolates the
current list at the ratio that node exhibited.

**The check binds from the second call of a node onward.** The ratio comes from the previous
call in that node within the same run, so an `AgentNode` is checked from its second turn and a
fan-out from its second item. A node making one call per run is never checked, and §2.1 bounds
it.

**A backend that reports no prompt size produces no estimate**, and the ceiling does not bind
for that node. The run warns once for that node. A vLLM server started without
`--enable-prompt-tokens-details` is this case (`docs/model-clients/vllm.md` §2).

A `ContextOverflow` inside a fan-out is collected as that item's failure and the remaining items
still run. Anywhere else it stops the run.

---

## 3. What happens at `ContextOverflow`

`ContextOverflow` is caller-facing, so the run stops: the node record carries
`termination: "error"`, the manifest records `outcome: "error"`, and the trajectory keeps
everything written up to that point. A request the backend refused is on the trajectory as a
`model_call` record with `ended_at: null`. A request the pre-flight ceiling stopped was never
sent, so there is no `model_call` record and the node record carries the error.

`AppendAll` drops nothing, so a list that does not fit stops the run. Sending less is a
build-time decision with four answers: give the node less, fan out over the input with
`over=...`, raise the limit, or supply a context builder that drops what the task
can spare. The last one is declared in the brief and reports every drop on the record (FT-17).

---

## 4. Writing a context builder

A context builder is an object with a `build` method. It is handed the message list and the
node's view of the run, and returns a `ContextResult` holding the messages to send and a
`Dropped` entry for each message left out. `to_manifest` is optional and reports the settings
the run was configured with.

This one ships, so `from simple_agents import DropOldestTurns` gets it without copying it:

```python
from dataclasses import dataclass

from simple_agents import ContextResult, Dropped, NodeContext


@dataclass(frozen=True, slots=True)
class DropOldestTurns:
    """Keeps the first message and the most recent turns."""

    keep_turns: int = 6

    def build(self, messages: list[dict], ctx: NodeContext) -> ContextResult:
        # A turn starts at the first message after the prompt that is not a tool result, so an
        # assistant message stays with the observations it asked for. A backend refuses a
        # request whose tool message does not follow the call that asked for it.
        starts = [i for i, m in enumerate(messages) if i > 0 and m.get("role") != "tool"]
        if len(starts) <= self.keep_turns:
            return ContextResult(messages=list(messages))
        cut = starts[-self.keep_turns]
        return ContextResult(
            messages=[messages[0], *messages[cut:]],
            dropped=tuple(
                Dropped(index=i, role=str(messages[i].get("role")), reason="older than keep_turns")
                for i in range(1, cut)
            ),
        )

    def to_manifest(self) -> dict:
        return {"keep_turns": self.keep_turns}
```

The frozen dataclass is what enforces the next rule on this one. Any object with `build` will
do.

`ctx` is the node's own view of the run, and `docs/pipeline.md` §3 lists its fields. Three of
them are filled only for a context builder: `last_input_tokens` and `last_input_chars`, what
the previous call in this node sent and what the backend charged for it, and `last_call_index`,
which call that was. All three are `None` until a call in that node completes, and
`last_input_tokens` is `unknown` when the backend reported no prompt size. A context builder
doing its own pre-flight check reports it as an `Estimate` on the result, which is what puts the
ratio on the record.

**A context builder must hold no state between calls.** One instance is shared across every
call, every fan-out item, every node given that instance, and every run of the pipeline, so a
value stored on it leaks into all four. Everything a decision needs arrives in the arguments.

**A context builder may read run state where a tool may not.** A tool is replayed from the
cassette under a key made from its arguments (`docs/tools.md` §3.1), so a tool that reads
mutable state can return two things for one key. The messages a context builder returns are
themselves in the key of the call, so one that varies with run state produces a `CassetteMiss`
rather than a response recorded against a different request.

### 4.1 A context builder that adds

The prompt function runs before the node's first call, so nothing a call measured is visible to
it. A context builder runs on every call, which is where a per-turn note goes.

```python
@dataclass(frozen=True, slots=True)
class RemainingTurns:
    """Adds a note once the node is close to its step ceiling."""

    warn_within: int = 4

    def build(self, messages: list[dict], ctx: NodeContext) -> ContextResult:
        ceiling = ctx.budget.max_steps
        if ceiling is None or ceiling - ctx.step >= self.warn_within or not messages:
            return ContextResult(messages=list(messages))
        note = f"This is turn {ctx.step} of {ceiling}. The last one has to be the finish call."
        return ContextResult(messages=[*messages, {"role": "user", "content": note}])

    def to_manifest(self) -> dict:
        return {"warn_within": self.warn_within}
```

The note goes on the call and not into the conversation, so turn 12's note is not still there at
turn 13 and each turn sees one note describing that turn. This one adds and never removes, so
`dropped` stays empty, which is what a record says when nothing was left out.

A tool holding a `ModelHandle` makes its call through the same context builder, over that call's
own prompt (§1), so a note like this one is appended there too.

---

## 5. What gets recorded

Every `model_call` record carries a `context` object (`docs/trajectory-format.md` §4.1.1):

```json
"context": {"context_builder": "AppendAll", "dropped": [], "estimate": null}
```

An empty `dropped` states that nothing was left out. `estimate` is `null` when no pre-flight
limit was configured, on the first call of a node, and when the backend reported no prompt size
for the previous call. When it is present it names the ratio it used and the call that ratio was
measured on, so a reader can tell an estimate from a count.

The manifest records which context builder each node ran with, under `nodes[].context_builder`
(`docs/run-envelope.md` §2.4), which is what a score change after a swap is traced to (FT-15).
