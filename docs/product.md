# The product

The product is the surface the end user meets the agent through, together with any artifact the project keeps for them to read. The agent runs inside it. Every project has one, and where the builder runs a script and reads what it prints, that script is the product.

`used_through` records what it is at `brainstorm`, the product section of `design.md` pins how it works at `shape` (FT-34), stage 4 builds it beside the pipeline, and stage 6 agrees the surface an end user meets before more of it is built. This document is what those three rest on.

The library ships the machinery a product invokes: a run per request, a run that waits for a person, the record every run leaves, and the stamp an accumulating artifact carries. The server, the page and the scheduler are the project's.

---

## 1. Three shapes

Most real products mix them; the design section says which of the three each interaction belongs to.

- **Request-shaped.** The end user asks and a run answers: a chat, a form, a command. The product is a surface plus `pipeline.run` behind it.
- **Artifact-shaped.** Runs maintain something read between runs: a queue, a digest, an index. The product is the artifact, the surface showing it, and whatever refreshes it.
- **Effect-shaped.** Runs act inside another system: labels on tickets, drafts in an outbox. The product is those effects where the end user already works.

## 2. Every interaction is one of four kinds

The product section of `design.md` lists what the end user can do and classifies each interaction:

| Kind | What happens | What carries it |
|---|---|---|
| **Starts a run** | Their action becomes `pipeline.run(...)` | §3 |
| **Answers a waiting run** | Their reply resumes a suspended run | §4 |
| **Reads the artifact** | They read something a run wrote earlier | §5 |
| **Records a judgement** | What they say lands in `evals/labels.jsonl` | `docs/evaluation.md` §1.5 |

A surface with no interaction of the first two kinds never reaches the agent: it is a display over stored output, and writing the classification down is what puts that in front of the builder before it is built.

## 2.1 Declaring it

Nothing in a run reaches the surface: a web handler calls `pipeline.run`, so introspection
sees the pipeline and never what called it. `simple-agents view` draws the product from a
declaration, the way it draws a resource from `touches=`:

```python
from simple_agents import Product, Surface, product_factory


@product_factory
def product() -> Product:
    return Product(surfaces=[
        Surface("the support inbox", "starts_a_run", pipeline="triage",
                does="a script takes each new ticket and starts a run"),
        Surface("the rota", "answers_a_waiting_run", pipeline="triage", through="consult",
                does="the person on the rota answers when the agent asks"),
        Surface("the outbox", "reads_the_artifact", reads="outbox",
                does="the reply lands there as a draft for a person to send"),
    ])
```

`kind` is one of the four in §2. A surface that starts or answers a run names the `pipeline`
it reaches, by the name it is registered under; one that answers names the `through` channel,
by the consultation tool's own name, which is what joins it to who that channel says answers
(§4.4); one that shows stored output names what it `reads`, by the resource string the tools
use. A kind whose name is missing raises `ConfigurationError` saying which field to add.

**The view finds it the way it finds a pipeline**: by importing `agent.py`. A product
declared in another module is found when `agent.py` reaches that module, and the module
declaring it is the one whose numbers the page reads as the surface's own, so declaring it
beside the surface's own code puts both in front of the builder. A project declares one
product; registering a second is refused.

**FT-34 reads it against `design.md`.** The product section lists what the end user can do and
classifies each interaction, and a declared surface that section never names is an interaction
the builder was not shown. Before `ship` a project declaring no product is not read this way; from `ship` FT-34 fails one whose code was read and declares none.

## 3. A request is a run

Each request the surface accepts becomes one run, marked live, under the same envelope development used:

```python
from simple_agents import RunEnvelope

env = RunEnvelope(run_dir="runs/")

def handle(question: str, request_id: str):
    result = pipeline.run(
        question, envelope=env.with_live(), model=client, run_id=f"req-{request_id}"
    )
    return result.output
```

One `Pipeline` and one envelope serve overlapping calls: nothing per-run lives on either, and the library's own evaluation runner overlaps runs of one pipeline this way. What varies per request is an argument to the run. Four things stay the project's:

- **`run_id`.** A generated id separates runs starting inside one second; passing the request's own id, as above, makes a complaint traceable to its run.
- **Credentials.** The library reads no `.env` file. A model client takes its key from the process environment where none is passed, `GEMINI_API_KEY` or `MISTRAL_API_KEY`, so whatever puts the key there has to have run before the surface starts. A server started without it raises `GeminiClient has no API key` on every request that constructs one, and a project whose scripts load `.env` and whose web app does not meets that on the surface alone.
- **Memory scope.** Where the agent remembers something about the person it is serving, the run names whose memory it reads: `pipeline.run(question, envelope=env, model=client, memory_scope=f"user-{user_id}")`. That is for what the agent learns and writes. What the end user tells the product is the project's data model, and it reaches the run as inputs (`docs/memory.md`).
- **Pacing.** Each run paces its own calls, so N overlapping runs are N times the traffic. A shared client is bounded by constructing `PacedClient(min_remaining_requests=...)` sized for the runs in flight, whose floor a run does not override (`docs/model-clients.md` §5).

The runs a product makes are read back with `runs("runs/", live=True)`, which is what `watching_live` is implemented against, and what the next version is built from (`docs/shipping.md` §2, §7).

## 4. A question the agent cannot settle

The agent reaches something only the end user can decide. What happens next depends on whether anybody is waiting on the run, and that follows from what started it (§6).

### 4.1 A request somebody is waiting on: the run stops

A consultation mid-run raises `Suspend`, the run stops with its state on disk, and the surface shows the question. The answer does not have to arrive in the same process, or the same day:

```python
from simple_agents import RunSuspended

try:
    result = pipeline.run(question, envelope=env, model=client)
except RunSuspended as stopped:
    surface.show(stopped.run_id, stopped.waiting_for)

# later, in whatever process handles the reply:
result = pipeline.resume(run_id, envelope=env, model=client, answer=reply_text)
```

`Pipeline.suspensions(run_dir)` lists the runs waiting and what each is waiting for, which is what a surface renders as an inbox. `docs/pipeline.md` §1.8 covers suspension itself.

### 4.2 A background run: the question is shelved

A run fired by cron or by something changing is unattended, and a queue refreshed on every store write cannot stop and wait. Its channel returns `Shelved` instead, the run finishes, and the question stays on record:

```python
from simple_agents.builtins import Reply, Shelved

def ask_the_site(question, options, about):
    answered = questions.answer_to(about)          # "coming back to it" / "gave up on it"
    if answered is not None:
        return Reply(answered, chose=None, answered_at=questions.answered_at(about))
    questions.put(about, question, options)
    return Shelved(reason="the site is unattended; the question is on the questions page")
```

`Pipeline.shelved(run_dir)` is that inbox, read from a file each run writes beside its manifest rather than from the trajectories, so a page listing open questions costs one read per run that shelved something:

```python
for question in Pipeline.shelved("runs/"):     # ShelvedQuestion, one per open question
    page.show(question.prompt, question.options, key=question.about)
```

`about` is what a shelved question is answered by, and `docs/tools.md` §4.6.4 covers naming it.

### 4.3 When the answer arrives

The run that asked has finished, so there is nothing to resume. Filing the answer starts a run of its own, and `pipeline=` is the work the answer triggers:

```python
from simple_agents import Pipeline

# in whatever handles the reply: a request handler, a worker, a button
Pipeline.answer_shelved("runs/", about="show:1421", answer="gave up on it",
                        pipeline=drop_from_up_next, envelope=env, model=client)
```

`answer` is what the person said, matched against the options that question offered, so `chose` is the option it was and `None` where it was none of them. The answering pipeline reads an `Answered`, which carries what was asked, what was said, and the run and record that asked it:

```python
from simple_agents import Answered

def drop_it(inputs: Answered, ctx) -> dict:
    if inputs.answer.chose == "gave up on it":
        queue.remove(inputs.about)
    return {"about": inputs.about}
```

Leave `pipeline=` unset where the next scheduled run is what acts on the answer. The answer is recorded either way, in a run of its own carrying a `consultation` that names the question and the run it was asked in, so a count of consultations and a count of answers are separable. Nothing already written is touched: the run that asked keeps saying `shelved`.

**The call returns an `AnsweredQuestion`**, so the caller reads what filing the answer did without opening the run directory: `run_id` names the run the answer was recorded in, which is not the run that asked; `question` is the `ShelvedQuestion` it answered; and `result` is the answering run's `RunResult`, carrying the output of `pipeline=` where one was passed:

```python
filed = Pipeline.answer_shelved("runs/", about="show:1421", answer="gave up on it",
                                pipeline=drop_from_up_next, envelope=env, model=client)
filed.run_id           # the answering run, for the record
filed.result.output    # what drop_from_up_next produced
```

**The answer reaches the next run through this call and the records it writes.** Where the agent has to carry what it learned from the reply further than that, the answering pipeline writes it to the memory store, with `memory_scope=` on this call naming whose memory (`docs/memory.md`).

**Nothing in the library watches for an answer.** The trigger is the project's, the same way a schedule is (§6). Two workers cannot answer one question twice: the shelf is claimed by an atomic rename, and the second finds the question already answered. Two people answering two different questions from one run reach for that same shelf, and the second waits rather than being refused.

### 4.4 Who the channel says it reaches

The channel declares who answers, and FT-31 fails a shipped project whose channel still names a stand-in (`docs/shipping.md` §4). An evaluation is refused over a channel that reaches a person, so rollouts never put the questions for real (`docs/evaluation.md` §5.4).

## 5. The artifact that accumulates

Where the product keeps results for the end user to read, the artifact outlives every pipeline that wrote it. Each stored result carries `behaviour_fingerprint`, and something re-runs what an older pipeline wrote: `docs/shipping.md` §6 is the whole of it, and `stored_output` in the brief records the answer.

**An evaluation must not write into it.** A rollout runs the real tools, so a pipeline ending in a store write would write seeded results into what the end user reads, examples × k times. During an evaluation the write goes to the run's own directory instead: a `Deterministic` body writes under `ctx.workspace`, and a tool writes through a `Workspace` handle (`docs/tools.md` §3.2). A step whose destination must stay the real store binds it where the tool is declared, and swapping that destination changes the tool's version and so its cassette key (`docs/evaluation.md` §6.7).

## 6. What makes a run happen

`used_through` names the trigger: a request, a schedule, something changing, or the builder by hand. The library owns no execution outside a call the caller made, so a schedule is the host's, calling a script that calls `run`:

```python
# refresh.py, run by cron or any scheduler the host already has
for old in store.produced_by_anything_other_than(stamp):
    store.write(pipeline.run(old.question, envelope=env, model=client), produced_by=stamp)
```

The same shape serves the waiting half: a loop over `Pipeline.suspensions(run_dir)` resumes the runs whose answers have arrived, and `Pipeline.shelved(run_dir)` lists the questions a background run left behind (§4).

## 7. Where the product runs

Deployment is the project's. Wherever the product runs, `runs/` has to land somewhere the project reads back, or the live runs stop feeding the next version and the checks read a project that apparently never ran. The run directory is the envelope's `run_dir`, and nothing else about the machine is assumed.
