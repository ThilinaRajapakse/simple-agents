# Prompts

A prompt is fixed text with named values dropped into it. The fixed text is the instruction the
project wrote; the values are the data that fills it on one run. The library keeps the two apart
so that a run records what the model was told as well as what it was sent, one step's
instruction can be read on its own across every example, and a truncated value says so.

---

## 1. Writing one

A prompt function returns a `Prompt`. A gap in the text is written `{name}` and is filled by the
keyword of that name:

```python
from pydantic import BaseModel
from simple_agents import LLMNode, Maybe, Prompt


class Itinerary(BaseModel):
    days: Maybe[list[str]]


def build_prompt(inputs: dict, ctx) -> Prompt:
    return Prompt.user(
        "Plan {days} days in {city} for a traveller who likes {tastes}.",
        days=inputs["days"],
        city=inputs["city"],
        tastes=inputs["tastes"],
    )


node = LLMNode(build_prompt, output_schema=Itinerary, node_id="plan")
```

A value can be anything; it reaches the model as `str(value)`.

**A literal brace is doubled.** `{{` and `}}` are one `{` and one `}` in the text, which is how a
JSON example is written into a prompt. Substitution is one pass and a value is inserted exactly
as it is, so a value that carries braces of its own needs no escaping.

```python
import json

Prompt.user(
    'Return JSON like {{"city": "Paris"}}.\n\n{schema}',
    schema=json.dumps(Itinerary.model_json_schema()),
)
```

**A string is refused.** Returning text from a prompt function raises `ConfigurationError`
naming the call that replaces it. Text the project has already assembled is passed as the fixed
text, `Prompt.user(text)`, which is what a template loaded from a file or chosen at run time
looks like.

**Text from outside the project goes in as a value**, not as the template: a persona a user
chose, an instruction an end user typed, a document. A brace in it would read as a gap and raise,
and the record should say it is data in any case.

```python
from simple_agents import Prompt, Value

Prompt.system("{voice}", voice=Value(traveller.voice, origin="the app's settings screen"))
```

---

## 2. Values

The keyword names the value. `Value` is for a value that carries more than its text.

```python
from simple_agents import Prompt, Value

Prompt.user(
    "Notes on this traveller:\n{notes}",
    notes=Value(traveller.notes, cap=2_000, origin="the traveller_files store"),
)
```

| Field | What it does |
|---|---|
| `text` | What fills the gap |
| `cap` | Cuts the text at that many characters, and records what was cut |
| `origin` | Where the text came from, in the project's own words, shown beside the value |

**`cap` is how a prompt is shortened.** A step that cuts a value with `text[:2000]` sends a
shorter prompt and records a whole one, so nothing downstream can tell that the model read half
a sentence. `cap` records `capped_from`, the length before the cut.

**`origin` matters most where the text is not the project's.** A persona a user chose, an
instruction an end user typed and a variant read from a store are all data, and a reader of the
record needs to know which.

---

## 3. Sections, and lists of them

A `Section` is a named piece of fixed text with its own values, used as a value inside another
piece. Naming a part is what lets a decision or a comment be about that part.

```python
from simple_agents import Prompt, Section

Prompt.user(
    "Answer the question.\n\n{context}\n\n{question}",
    context=Section("context", "Use only these notes:\n{notes}", notes=notes),
    question=question,
)
```

`Section.joined` builds a variable number of them:

```python
Prompt.user(
    "Answer using only the passages. Cite each claim as [n].\n\n{passages}\n\n{question}",
    passages=Section.joined(
        "passages",
        [
            Section("passage", "[{n}] {text}", n=i + 1, text=chunk.text)
            for i, chunk in enumerate(chunks)
        ],
    ),
    question=question,
)
```

`separator` joins the parts and defaults to a newline. Where every part carries the same text,
the record keeps that text once and counts the parts, so twelve passages record one template and
`parts: 12`.

**The seam is between instruction and data.** A tree rendered to whatever depth the data has can
be built from sections all the way down, and the record is then a tree of synthetic templates
that reads as machine output. Rendering it as one value is the better call.

---

## 4. More than one message

```python
Prompt.system("Work one day at a time. Never plan more than three stops in a day.") + Prompt.user(
    "Plan {days} days in {city}.", days=days, city=city
)
```

`Prompt.system`, `Prompt.user` and `Prompt.assistant` each build one message, and adding two
prompts together makes the longer one. An assistant message at the end is a reply begun for the
model to continue.

**`Prompt.turns` carries messages a run already recorded**, which is a conversation, a set of
few-shot examples held as turns, or a thread read back from a store:

```python
Prompt.system("{voice}", voice=persona) + Prompt.turns(thread.messages)
```

Nothing carried this way is text the project wrote, and the record marks it as carried.

**`Prompt.blocks` is content that is not text.** A `Section` in the list becomes a text block and
every other entry reaches the backend unchanged, so a block shape the library does not model
still goes through:

```python
Prompt.blocks(
    "user",
    [
        {"type": "image", "source": {"data": encoded}},
        Section("ask", "Read the total off this invoice."),
    ],
)
```

**`Prompt.marked` sets what a backend reads off a message** and the library does not model, such
as a cache marker:

```python
Prompt.system("{voice}", voice=persona).marked(cache_control={"type": "ephemeral"})
```

---

## 5. A model call from inside a tool

`ModelHandle.complete` takes a `Prompt` as a node's prompt function does, so every model call a
project makes is recorded the same way:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def summarise(model: ModelHandle, text: str) -> str:
    """Summarise a passage in two sentences."""
    reply = model.complete(Prompt.user("Summarise in two sentences:\n\n{text}", text=text))
    return reply.content or ""
```

---

## 6. What the run records

**On each model call.** `inputs.assembly` on the `model_call` record holds one entry per
message: the fixed text, the values that filled it with their lengths, and what any `cap` cut
(`docs/trajectory-format.md` §4.1.6).

`instruction` digests everything fixed about the prompt, so two calls differing only in their
data record the same one, and `templates` lists the distinct pieces it was built from. A message
carried in with `Prompt.turns` counts for neither, so a chat step keeps one instruction as its
conversation grows.

The whole of `assembly` is absent on a call built from a conversation rather than from a prompt,
which is every turn of an `AgentNode` loop after the first. It sits inside `inputs`, a payload
field, so a run's redaction applies to it and sampling drops it (`docs/run-envelope.md` §7).

**On the manifest.** Each entry in `prompts` carries `observed`, the distinct instructions that
step sent and how many calls used each, and `distinct`, how many there were. A step whose prompt
is written in the project's code records one, however many sections it is built from. A step
whose instruction arrives as data records as many as it saw, capped at twenty entries with
`distinct` carrying the true count.

**On the page.** `simple-agents view` has a prompts page built from all of this: every step's
text as written and as one run sent it, each value named with where it came from and what a
`cap` cut, and a comment on the whole prompt, on one value, or on words selected in it
(`docs/view.md` §6.10).

**In the version.** A prompt's recorded version covers the prompt function's source, what it
closed over, and the module-level strings it passes as fixed text:

```python
TONE = "Answer in two sentences."


def build_prompt(inputs, ctx):
    return Prompt.user(TONE + "\n\n{question}", question=inputs["question"])
```

Editing `TONE` moves the prompt's version and `Pipeline.behaviour_fingerprint`, so a result
stamped with the old one is reported as stale (FT-37). Only a name the function passes as fixed
text is read, and only where the module binds it to a string. Text fetched at run time exists
only once the run happens and is recorded as a value on the call.

---

## 7. Coming from a string

| Before | Now |
|---|---|
| `return f"Answer {q}"` | `return Prompt.user("Answer {q}", q=q)` |
| `return PREAMBLE + f"\n{q}"` | `return Prompt.user(PREAMBLE + "\n{q}", q=q)` |
| `return [{"role": "system", "content": s}, ...]` | `return Prompt.system(s) + ...` |
| `return text[:2000]` | `return Prompt.user("{doc}", doc=Value(text, cap=2000))` |
| history as message dicts | `Prompt.turns(messages)` |

**A prompt assembled with an f-string and passed as the fixed text goes through**, and records
one piece of text per example rather than one per step. A step whose text differs on every
example has no instruction that can be read, compared or agreed, which is what the record then
says about it.
