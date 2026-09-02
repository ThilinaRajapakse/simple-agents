# The view

`simple-agents view` writes one file, `view.html`, showing the project as it stands. It opens
with the builder's stated purpose, who it is for, and what a useful result looks like. The map
then shows what is declared, what is built, what changed since the last run, the data and where
it flows, where money can leave, and where the agent can stop to ask a person. Every figure and
sentence on it is computed from the project's own code and records, so the page cannot drift
from the project the way prose does.

**A seventh page appears once the project has live runs.** "Operate" is not a stage: the ship
gate never closes, and a project with real traffic has a page about what that traffic is doing
(§6.8).

**The one file holds a page per stage, and it opens on the project's own.** A strip under the
header names the stages the project's tier has, marks where the project is, and switches
freely; the file opens on the stage `brief.toml` records, and `#stage/shape` at the end of the
page's address opens a named one. Each stage's page holds that stage's record: its questions
and the answers given to them, the decisions whose kind belongs to it, and the sections below
that are its subject. The drawing sits on the `shape`, `build` and `measure` pages, rendered
with what that page asks about (agreement at `shape`, change at `build`, the evaluation's
figures at `measure`); a page a tier does not have does not exist (a `prototype` project has
no `measure` page), a passed stage's page keeps its standing record with any drift marked, and
a page with nothing filed yet says so plainly. The header, the stage strip, what waits on
the builder and the writing panel are on every page.

The page is for the builder, and it speaks plainly: a step is a "fixed step", "model call" or
"decides for itself", a placeholder is "not built yet", and everything a step declares is on
its card. Served live, the header offers a project comment and the next open decision, and each
selected step offers its own comment. An open question takes an answer, an agreed thing takes an
amendment, and the coding agent answers in the same threads (§5). The picture is the shared
object: the builder points at it and writes on it, the coding agent acts on it.

The page title is the first heading in `idea.md` where that file has one; otherwise it is the
project directory's name. Its purpose card comes from answered brief entries, so it remains an
account from the builder rather than a summary the viewer invents.

**The page follows the reader's system, and offers five palettes** in the header: paper and
dawn are light, forest, slate and midnight are dark. A choice is kept in that browser and the
page keeps following the system until one is made. Every colour a reader meets was measured
before it shipped: text at 4.5:1 against what it sits on, and a line in a drawing at 3:1.

## 1. The command, and when it runs

```
simple-agents view                # writes <project>/view.html, a still picture
simple-agents view -o out.html   # somewhere else
simple-agents view --serve       # the live page, at http://127.0.0.1:7350/
simple-agents comments           # what the builder said through it, open first
```

`simple-agents check` rewrites the still page at every gate, so it cannot go stale between
looks. A failure to generate never changes a gate's verdict: the checks read files, the view
additionally imports the project's code, and a project whose code does not import still
deserves its report.

`view.html` carries its own styles and uses no network resource, so it opens the same way offline
or when shared from a project directory. `--serve` binds 127.0.0.1 only and follows the project as it changes: an edit to `agent.py`,
the brief, or the run directory reaches the open page within seconds, so the builder keeps
it open while the coding agent works. A run in progress is followed too: the page shows
which pipeline it is moving through, marks each step done as its record lands, and points
at the one it is on. The serving terminal prints one line per thing the builder sends.
During any design conversation, serve it; the still page is for records and for reading
away from the machine.

From code, the same page::

    from simple_agents.view import generate_view

    generate_view(".")

## 2. Registering the pipelines

The page draws the pipelines `agent.py` declares. Registering one is a decorator on the
function that builds it:

```python
from simple_agents import Budget, Deterministic, Pipeline, pipeline_factory


def load_rows(inputs, ctx):
    return inputs["rows"]


@pipeline_factory("ingest")
def ingest() -> Pipeline:
    return Pipeline([Deterministic(load_rows)], budget=Budget.unbounded())
```

The name is the pipeline's name everywhere a person sees it, so it should be the word the
builder uses. The factory takes no arguments and building the pipeline must be free of
effects: no model call, no network, no file the project keeps. Importing `agent.py` runs its
module-level code, so clients and pipelines are built inside functions, never at import. A
module-level `Pipeline` is picked up too, under the name it is bound to.

A project with runs and no registered pipeline still gets a page: the run record renders,
and the page says that registering the pipelines is what lights the rest.

## 3. A step declared before it is built

`NotBuilt` stands in a node's callable slot, so the shape can be written, drawn and agreed
before the code behind each step exists:

```python
from simple_agents import Budget, Deterministic, LLMNode, NotBuilt, Pipeline

pool = Deterministic(NotBuilt("filters the catalogue to eligible titles"), node_id="pool")
judge = LLMNode(NotBuilt("weighs each candidate"), output_schema=None, node_id="judge")
skeleton = Pipeline([pool, judge], budget=Budget(max_steps=6, max_tokens=40_000,
                                                 max_cost=None, max_wall_clock_ms=None))
```

A planned node declares `node_id=`, since there is no function to take a name from, and an
`LLMNode` or `AgentNode` may declare `output_schema=None` until the schema is settled; the
page shows the absence. The page draws the node dashed, with its own words on the card.

Executing a planned node raises `ConfigurationError`; the other nodes still run, so a
part-built pipeline is runnable down its built paths. The manifest records the node with
`planned: true`, and FT-40 counts every one at every stage and fails from stage `ship`.

## 4. What flows between pipelines

A tool names the resource it touches, and the same string wherever that resource is touched:

```python
from simple_agents.tools import SideEffectClass, tool


@tool(side_effect_class=SideEffectClass.WRITES, touches="catalogue")
def store_titles(rows: list) -> int:
    """Write fetched titles into the catalogue. Returns how many were written."""
    return len(rows)
```

Direction follows the side-effect class: a `READ_ONLY` tool reads the resource, a `WRITES`
or `IRREVERSIBLE` one writes it, and a `SPENDS_MONEY` call is shown without a direction,
since a paid call can be either. Every node kind declares the same for a resource it reaches
in its own code: `Deterministic(fn, touches="digest_store")`.

The system level of the page is computed from these: two pipelines that touch one resource
are connected through it, a resource written that nothing reads is a visible absence, and so
is one read that nothing fills. **A link's width is what that pipeline moves through that
store in one of its runs**, so the busiest path through the system draws itself, and a
pipeline that ran often does not draw a thick line for having run often. The totals it is
drawn from are on the store's card. **A bar inside each pipeline carries the same measure the
pipeline level's steps carry**, summed across its steps, under the same two controls: what
the drawing is over, and what the bar shows. A project with nothing recorded yet gets neither,
and its pipelines are drawn by their status and their step counts.

### 4.1 Recording what an access did

`touches=` names a resource. It says nothing about what a step asked for, what came back, or
which way the data went, and a step reaching the same resource through a tool records all
three. `ctx.record_access` closes that, so a store's history reads the same whichever way the
step was written:

```python
def publish(inputs, ctx):
    sent = mailer.send(inputs["body"])
    ctx.record_access("outbox", "write", inputs={"to": inputs["to"]},
                      outputs={"sent": sent})
    return {"sent": sent}
```

The direction is `"read"` or `"write"`, and a step that does both records one access each way.
`inputs` and `outputs` are payload fields like any other: the run's redaction applies and
sampling drops them (`docs/run-envelope.md` §6, §7). What they hold is the step's choice, so a
step that read 67,353 rows and kept 12 records the two counts rather than the rows:

```python
ctx.record_access("catalogue", "read", inputs={"eligible": True},
                  outputs={"rows": 67_353, "kept": 12})
```

The resource has to be one the node declared, and a name that is not raises
`ConfigurationError` saying what to add, so the declaration and the record always agree. Each
access is a `resource_access` record (`docs/trajectory-format.md` §4.5) and reaches the
per-step figures as `resource_reads` and `resource_writes` (`docs/evaluation.md` §5).

## 5. The conversation on the picture

Everything on the page is selectable and everything selectable can be spoken to: a step, an
edge, a pipeline, a resource, a question, a decision, or the project itself. On the served
page the builder writes in place; each submission becomes a thread in `comments.toml` beside
the brief, stamped with what the writer was looking at:

```toml
[[comment]]
id = "c3"
at = "recommend/judge_books"
said = "Why does the judge see the whole pool? I thought we agreed on unread only."
about = "judge_books, a model call in recommend"
stage = "build"
when = "2026-08-27T06:12:03.412Z"
status = "open"

[[comment.replies]]
by = "coding_agent"
said = "It should not. Capping the pool before ranking; the change lands today."
when = "2026-08-27T06:31:44.002Z"
```

`kind` says what the builder was doing: a plain `comment`; an `answer`, given inline on an
open question; or an `amendment`, given on an answer or a decision already recorded. The
page shows every thread on the element it is about and all of them together in one
conversation section on the `ship` page, the builder's words in one voice and the coding
agent's in another. The writing panel itself is on every page: on a page with a drawing it
speaks to the selected element, and on one without it speaks to the project.

**How the coding agent sees and answers.** `simple-agents comments` prints the open threads
with their whole exchange (`--json` for reading programmatically), the serving terminal
prints each arrival, and FT-39 reports open threads at every gate. The coding agent does
what a thread asks or takes it back to the builder, replies in the thread
(`append_reply(path, id, by="coding_agent", said=...)`), and closes it
(`set_status(path, id, "addressed", addressed_by=...)`) naming the decision or change that
answered it. The builder replies in the same threads on the page, and can take back a thread
of their own with **Take it back**. A thread taken back stays in `comments.toml` and stays on
the page under **Taken back**, where **Put it back** makes it open again.

**An answer given on the page is not yet the brief.** The coding agent reads it, asks
whatever follow-up the question's scaffold needs, records the entry in `brief.toml`, and
addresses the thread; until then the page shows the answer as sent and with the coding
agent. The same holds for an amendment: it is the builder asking for a change, and the
record moves when the coding agent moves it. The asking and the recording stay the coding
agent's; the page is where the builder can speak without waiting to be asked.

A thread is `open` until what it asks for is done or decided, then `addressed`;
`withdrawn` is the builder taking it back, and nothing removes a thread. The gates report
open threads at every stage (FT-39), and `comments_block_gates = true` in the brief is the
builder's choice that an open thread refuses a gate rather than being reported beside it.

## 6. What the page computes

Each item below sits on one stage's page: the drawing on `shape`, `build` and `measure`, the
seams and the shared state on `shape` (§6.5), progress, the constants, the departures, the
last run, the change ledger and the data path on `build` (§6.6), the evaluation and its
examples on `measure`, the checks, the product, retention and the conversation on `ship`
(§6.7), and what the live runs are doing on `operate` (§6.8). `brainstorm` and `research` draw
the idea and the survey (§6.9). The header sentence, the findings and the stage strip are on
every page.

- **Where the project stands**, in one sentence at the top: the stage, what is built, what
  is still to build, and what waits on the builder, including any pipeline whose shape has
  never been agreed to.
- **An unconfirmed design says so.** A pipeline with no confirmation in the brief is drawn
  as proposed. At `shape` that is the page's first finding: the coding agent has shown a
  proposal, and it is waiting to be read. Once a confirmation exists the page marks any
  later change against it (§7).
- **What waits on the builder**, under its own heading: only what they can act on. A comment
  the coding agent has answered, a question the stage needs (counted by the stage that asks
  it, since the gate's requirement is cumulative), an unconfirmed shape, an answer the code
  contradicts. Each carries the verb for it, and a project with none says so. A comment
  the builder spoke on last is with the coding agent and is not a task; it is listed as worth
  knowing. A one-click sentence already sent (Agree, This is right, The code is wrong)
  reads as sent, and as with the coding agent, in place of its button until the thread
  closes, so the act is visible and is not taken twice by accident. Everything else is worth knowing, kept
  under its own heading and shut: that a step decides for itself, or that money can leave at
  one of them, is a fact about the design rather than a task.
- **A step's card reads in three bands**: how it is wired, what it has done, and what has been
  said about it. Each band holds rows that open, and a shut row says on its right what it
  holds, so it can be skipped without being opened.
- **Design and discussion**: open questions, agreed choices, and the conversation with the
  coding agent. A question appears under its own name and not its brief key, with the
  words it was put in beneath: an entry recorded as `agency_boundary` reads "What the agent
  works out for itself". The key stays the address a comment is filed under, so what the
  builder writes still lands on the entry it is about.
- **Evidence from runs**: evaluation, examples, questions the agent asked, and run totals.
- **Run detail**: the data path, the newest run, its files, and changes since the run before.
- **Checks and notes**: only stated boundaries that the code contradicts, plus non-blocking
  notes. A matching brief answer is not repeated as a line-by-line code comparison.
- **What changed since the last run**: steps added, removed, changed in kind, or built
  where a placeholder was, computed by comparing the code against the newest run of each
  pipeline.
- **The system**: the pipelines, the resources between them, and the flows, drawn when the
  project has more than one pipeline.
- **The pipeline and its steps**: the graph with branches, loops and error paths, the data
  on each edge, and one card per step carrying everything the step declares, the decision
  recorded about it, and the comments on it. A step in the graph opens in place with
  **more +**, showing its facts without leaving the picture; the card beside it holds the
  schemas field by field, the recorded decisions and the conversation. A large graph can show
  the selected step and its direct links, then return to the whole pipeline.
- **What each step receives**: derived from the steps whose edges reach it. One edge in names
  the step it comes from and the schema it carries; several name a `Join` with a key per edge;
  an error edge names the `NodeFailure`; a step with no incoming edge receives what the run was
  given, or the input of its own pipeline where it opens a nested one.
- **How much data went through each step**, read from the newest run's own records: the
  keys that hold a count and how many they held, so a step reads `survey 2,000 · pool 40` on
  the way in and `items 40` on the way out. A record of scalars is named by its longest text
  (`ticket 74 characters`), and a `Join` counts the edges that fired and says how many did
  not. This is on the step in the graph, on its card, and in the data path.
- **The shape of what arrived and what left**: the keys, what each holds, and how much,
  three levels deep, with the keys holding a collection first. Beside it, a real value
  clipped to 220 characters a field, labelled with the run it came from. A step the run
  skipped says so rather than reporting an execution.
- **Where the data goes**, as one row per step in graph order: what enters the pipeline,
  what each step receives and produces, which resources it reads and writes, and what leaves at
  the end. The two columns make a narrowing visible without a sentence that enumerates what did
  not continue.
- **What has run**: each pipeline's run count, spend by unit, questions asked, and models,
  read from the manifests. Shapes that ran and are no longer in the code stay listed.
- **What is running**, on the served page: a run whose manifest is not yet closed shows as a
  banner on its pipeline, each step marked done as its record lands, the step it is on
  drawn moving, and the count of model calls still in flight. A rollout names the evaluation
  it belongs to, with how many of its rollouts the runner has scored out of the total it
  declared, the share right so far marked provisional with its n, what the rollouts so far
  cost, and the runner's own estimate of the time left. All of it is read from the
  `progress.json` the evaluation keeps current beside its rollouts
  (`docs/evaluation.md` §6.6), so the page invents no denominator; an evaluation written
  by an older library shows a count of finished rollouts and no total.
- **What the code says**, which is the part that is true before anything has run: each step's
  function and each tool's, with its signature, the fields of what it returns where the
  annotation names a model, its docstring, the file and line it lives at, and its body behind
  a click. None of it is written down twice, so none of it can drift. A tool that annotates
  no return type says so.
- **What the newest run wrote into its own directory**, which every run gets at
  `runs/<run_id>/workspace/` (`docs/run-envelope.md` §1).

### 6.1 How the drawing reads

**One frame and a glyph per kind.** Every step is the same box with a mark at its left:
braces for plain code, a small network for one model call, and the same network with a loop
around it for a step that decides its own next move. A pipeline used as a step is a stack, and
a store is a stack in a capsule. The three node glyphs are one mark developed three ways,
which is the order the kinds go in. They are drawn rather than written, so they print and
render the same on every machine.

**The outline carries status only:** solid is built, a short dash is a step declared and not
built yet, and a longer, warmer dash is a step that has changed since this pipeline last ran.

**An edge's width is how often it was taken.** The arm most runs take is the thick one and an
untraversed arm is a dotted hairline, so the spine of the system draws itself. **An arm the
record has not counted yet reads "not taken yet"**, which is a fact about the runs so far rather than
about the design. An edge whose source records no route at all is drawn without a count
instead: a nested pipeline's last step routes inside its own graph, and the container writes no
record.

**A bar inside each step carries one figure**, and the figure is written beside it. Two
controls above the drawing say what it is over and what it shows:

| Control | What it changes |
|---|---|
| **over** | the project's own runs, or the evaluation's rollouts. Never both: they answer different questions, and one population's figures added to the other's describe nothing |
| **bars show** | what it cost, how long it took, model calls, or items handled. Only the ones the record can fill are offered |

**Cost is never summed across two bases.** A project that ran against a hosted price and
against a device holds figures in dollars and in device-seconds; each is reported under its
own basis, and the cost bar is offered only where a shape's runs share one.

**The key includes only symbols present in the drawing**, so a project with no nested
pipeline has no nested-pipeline symbol.

**Stores sit in a column beside the graph** with a hairline to each step that touches them.
Selecting one opens §10, which carries how much each pipeline moves through it. A pipeline
reaching more stores than it has steps makes that column the taller of the two, and the frame
is drawn to hold it.

**On a system of many pipelines, both rows wrap** to the width the panel has, and the selected
pipeline's links are drawn at full strength while the rest are held back, so one pipeline's
stores can be followed through a drawing that holds every pipeline's.

**The drawing keeps the size its labels were written for.** It is scaled to fit only while
that costs less than a tenth, and scrolls sideways below that rather than shrinking its text.
The map shares the page's column with every other region. **The step's card and the story
sit beside the drawing on any screen 1280 pixels wide or wider**, in a column that grows
with the window and scrolls on its own. Where the drawing needs more width than that
leaves, the drawing decides: the rail moves under it and its two panels sit side by side, so
a laptop reads a wide pipeline at full size and a narrow one beside its card.

### 6.2 What every run cost, per step

Over every run under `runs/`, not the newest one: what each step's model calls cost in the
basis its runs declared, what its tools spent, how many model and tool calls it made, how
long it spent inside itself, how many fan-out items it handled with the cost of each, and how
many runs never reached it. A step's accesses to each store are counted here too.

**Cost per item is exact where the unit is declared.** A step with `over=` handles a countable
number of items and each call carries the item it was made for, so cost over items is
arithmetic. The page does not infer a denominator the project did not declare.

### 6.3 Walking one run

The page is about the system; this is the other question. On the `build` page (§6.6) the
newest run is one strip of the steps it took, in order. Selecting a step opens what it
received, what it produced, how long it took and where it went next, and under that every
model call, tool call, recorded access and question it asked. The steps the run never reached
are named under the strip, so the branches not taken are visible beside the ones that were.

The file carries the newest run of each shape and every rollout whose example came out wrong,
which are the ones a builder opens; the served page reads any other run on demand, and every
step in a served walk offers the full record behind it: the clipped values on the page
are a step's record cut to 220 characters a field, and the button returns the record itself,
raw, however large it is. `simple-agents report <run> --walk` prints the same walk in a
terminal.

### 6.4 An edge, selected

The line stays short: what it carries, and how often it was taken. Selecting it opens the
rest: the schema field by field, the key the value arrives under where the next step takes a
`Join`, what selects the edge (a route choosing an arm, a cycle returning, a failure path, or
nothing at all), how many runs went that way against how many there were, and what actually
travelled last time.

**What travelled is read from the receiving end.** A step with several edges into it records a
`Join` holding one entry per declared edge, carrying either the value that arrived or an
absence saying why it did not, so per-edge truth is on disk without anything new being
recorded.

### 6.5 The shape page, region by region

The shape page shows whether the design is what the builder asked for.

**What waits on the builder** carries the unconfirmed pipelines, with **Agree**
and **Something is wrong** on the design as a whole. Agreeing is one click: it lands as a thread
against the project, and the coding agent records the confirmation. Nothing on the page
writes the brief (§5).

**The drawing** reads as §6.1 describes it, with every step that is not built drawn dashed.

**The story** is the pipeline as a numbered rail beside the drawing: one row a step, in the
order the code declares them, carrying the step's name, what it is for in the words the
project already wrote, and the seams it holds. A step not built yet carries the sentence its
`NotBuilt` marker was given; a built one carries the first line of its function's docstring,
so neither is written down twice. Pointing at a row lights that step and every edge touching
it in the drawing, the arrow keys walk the rail, and selecting a row opens the step's card.
Where the drawing is too wide to share the width, the story and the card sit side by side
under it.

**A seam is where a step leaves the straight line**: it decides for itself, branches, loops
back with its bound, asks a person, spends money, makes a permanent change, or writes or
touches a resource. A read is not a seam, because it changes nothing outside the run.

**Seams** is the four answers the `shape` gate settles, project-wide, each beside the steps
the code actually has: `agency_boundary`, `consultation`, `tool_effects` and `used_through`.
Each row names the steps and the tool each one holds the seam through, and who answers where
a step asks. An answer naming a step the code says is something else is red here as well as in
the findings (§7); a step the code has that the answer never mentions is a quieter line; an
unanswered one names the question that settles it. The entry point carries the answer alone,
since no code declares what the end user opens.

**Shared state** is every resource with the steps that read it, write it, and touch it without
declaring a direction. Selecting one opens §10.

**Decisions** are the `shape` decisions, each with a mark for its status, what it chose, and
why. A proposed one carries **Agree**, the same one click; every one carries **Amend**.


### 6.6 The build page, region by region

The build page shows whether the agent is being built as agreed, and what changed.

**Progress** sits above the drawing, and is one chip a step, in pipeline order, in four
states: proven by a run, built and not yet reached by one, changed since its last run, and not
built yet. Each carries a mark as
well as a colour, and the counts under them are the sentence. Beside them, whether each
pipeline is still the shape the builder agreed to. Selecting a chip opens that step.

**The drawing** reads as §6.1 describes it: built solid, not built dashed, changed in the
longer, warmer dash.

**Constants** is every module-level number the project's own runs recorded, the steps that
reach it and the tools they reach it through, and the `constant` decision that settled it. A number no
decision names is **unconfirmed**, which is a number the coding agent chose alone, and one
click asks for it to be recorded. Where it is reached from is a text match over the source the
page already shows, so a number reached through a helper neither the step nor its tools name is
not found: it reports where a name is written and never that it is unused.

**Prompt rules** is the same for what the prompts tell the model. Each prompt the runs
recorded, with the `prompt_rule` decision that names its step, or **unconfirmed**. A step's
name opens the code that builds its prompt.

Both are gathered across the project's own runs, newest value first, rather than off the newest
one: a project with more than one pipeline runs whichever it was asked for, so the newest run
describes one of them. A number or a prompt added since the last run appears once something has
run, and a project with no run says so rather than showing an empty table.

**Build inconsistent with the design** is each place the brief and the code disagree (§7),
with the two ways out: the answer is wrong, or the code is wrong. Both are comments the coding
agent acts on; which one is right is the builder's to say. Where the code does something the
answer names other steps for, the one way out is to add it to the answer.

**The last run** is the newest run of the project's own agent as one strip: what it was given,
the steps it took in order, and the steps it never reached. Selecting a step opens its record
(§6.3). An evaluation's rollouts are not offered here; a rollout is opened from the grid on the
`measure` page (§11) and is shown here saying which it is.

### 6.7 The ship page, region by region

The ship page shows whether other people can use this, and what they will meet.

**Checks** is the conformance suite as a board, run over the project as the page is written.
One row a check, in the entry's own title, with a mark for passing, failing, waiting on
something that does not exist yet, or not applying at this stage or tier. **The count is out
of what ran**: a check waiting on an artifact the project has not produced is not a failure,
and the other two are counted beside it. A failing row carries what the check said to do about
it and **Show me** goes to where it shows on the page; a waiting one says what it waits on.
What passes is counted and kept shut.

**The product** is what the end user meets, drawn from the declaration
(`docs/product.md` §2.1) and joined to what the code has: the surfaces that start or answer a
run on the left, the pipelines they reach in the middle, and what is read on the right. Under
the drawing, one row a surface: what the end user does there, the channel an answer travels
through with who that channel says answers, the steps that write what an artifact surface
shows, and any name the declaration uses that the code does not have. A channel still
answered by a stand-in is marked, and so is a product no interaction of which reaches the
agent. **Parameters** are the numbers the declaring module defines, which no run reaches.

**Retention** is what a run of the shipped project keeps, in the builder's own answers.

**Brief against code** is each answer the code has an exact counterpart for (§7), as a tick
list. What to do about a disagreement is on the `build` page (§6.6), where the code is being
written; here the question is whether the record is true before other people are let in.

### 6.8 The operate page, region by region

The operate page shows what is stuck, failing or costing money, and what changed. Everything
on it is over the project's own live runs, the ones `runs(run_dir, live=True)` returns. A development run is not real traffic, and counting one
here would overstate what the agent did for real users. The page exists once there is at
least one live run.

**Now** is five counts: runs still going, runs stopped waiting on a person, runs that cannot
still be going, unanswered questions, and what today's runs cost. The three that need
somebody are marked.

**History** is one bar a day of how that day's live runs ended (finished, failed, stopped),
with what the day cost on its own scale under it, over the last 7, 30 or 90 days. A triangle
marks a day a tool call ended throttled; a dashed line marks a day the behaviour changed. **A
throttle the library waited out and then succeeded leaves no record**, so what is counted is a
call whose attempts were spent.

**Stuck** is every run that stopped: what it waits for, whether that is a person or a clock,
how long it has waited, and the options it offered. **Shelved** is every question a run asked
with no one waiting for the answer (`docs/product.md` §4.2), with why it was shelved. Continuing a run
is the project's own worker (`Pipeline.suspensions`, `Pipeline.answer_shelved`); what the page
owes an operator is knowing they are there.

**Conversations** is the conversations live runs are turns of, read from what each run
recorded. A conversation no node has read or written says so: its runs are turns of something
nothing carries forward.

**Changes** is every day one pipeline's behaviour moved, read within one graph, since two
pipelines have two behaviours and a switch between them is not a change. A confirmation records
the stage it was agreed at rather than a date, so nothing dates one and the marks are behaviour
alone.

**What has run** is every run the project has, split by what each was for: real traffic, made
while building, and an evaluation's rollouts. One figure over all three describes none of them.

### 6.9 The brainstorm and research pages, region by region

The two pages a project has before it has code.

**Brainstorm** shows what the project will be and which questions are still open.

**The idea** is five boxes: who uses it, the entry point, the agent, what it receives, and what
the end user gets. Each is filled from its answer, drawn dashed where it is unanswered, or
marked where the answer was put off to a later stage. The fifth box is a `shape` question.
Before that stage it reads *Asked at shape*, is drawn faint, and is not counted as
unanswered. On day zero the other four are dashed. Selecting a box opens its question; the
faint box waits for its stage. Under
the drawing: the tier, what finished looks like, and the first version.

**Questions** is what this stage asks, in four states, and they are not the brief's three: an
unanswered question this stage asks is **open**, one a later stage asks has **not been asked
yet**, and both read as unanswered in the record. An answered one offers **Amend**;
an open or deferred one offers **Answer**, and one answered on the served page reads *Answer
sent* with the words until the coding agent records them. Optional questions say so, and a
question put again at every stage says that too.

**Stages** is the six with answered-of-asked under each, so a deferral is distinguishable from
an omission and what is still ahead is visible. Selecting one opens its page.

**The idea file** is `idea.md`'s five sections read back, with **This is right**: one click that
records the confirmation the way any other does (§5). A section with nothing under it is marked,
and a confirmation naming an earlier stage than the project is at says so.

**Research** shows what was found and what the design rests on.

**The deciding factor** is the one sentence that stage produces, set large.

**Parts and candidates** is `research.md`'s survey, one column a part: each candidate with what
became of it and why, filled where it was adopted, outlined where it was rejected, and a ring
where it was not investigated. A candidate a `dependency` decision's own words reach names that
decision under it.

**Decisions resting on it** is each `dependency` decision with what it chose, why, and the
candidates it weighed. Matched on the words the decision uses, so a candidate described in
other words is not joined. **What the builder said about it** is that section quoted at the
foot.

## 7. What was said, against what the code does

An answer in the brief and the shape in `agent.py` are written at different times, and nothing
else compares them. The page reads six answers against their exact counterpart in the code:

| The answer | What the code's side is |
|---|---|
| `agency_boundary` | steps that are an `AgentNode` |
| `consultation` | steps holding a tool that asks a person |
| `what_goes_wrong` | steps declaring `on_error` or a retry |
| `budget` | steps with a `Budget` of their own |
| `tool_effects` | steps holding a `SPENDS_MONEY`, `WRITES` or `IRREVERSIBLE` tool |
| `judged_steps` | steps carrying a figure of their own in the reported evaluation |

**Matched on a step's name.** An answer naming a step the code says is something else is the
loudest thing the page reports: a brief naming two steps that decide for themselves, over a
pipeline holding none, passed 21 gate runs across 116 commits on one project. An answer that
names some steps and misses one the code has is reported more quietly, and an answer naming no
step at all says that rather than claiming a disagreement, since the join cannot read prose.

## 8. What a run did, and what it asked

**How each step ended** is on its card: a step that ran out of model calls, failed, or was
never reached ends differently, and a step with more than one execution in one run was
retried. A failure path that fired is reported by name, because a step reached only when
something before it failed is a step whose run went wrong.

**Runs that did not complete** are counted over the whole record in one sentence, by cause.

**Every question the newest run put to a person** is shown with what was offered, what came
back, which option the rule read it as, and who answered. An answer the channel said was one
option and the rule read as another is reported: the branch behind that question was never
taken (`docs/tools.md` §4.6.1).

**What moved since the run before** compares the last two runs of each pipeline step by step:
what each produced, how long it took, and whether it ran at all. The change ledger says what
moved in the code; this says what moved in the data.

## 9. Evaluation examples

`evals/examples.jsonl` is read for what a figure is over: how many examples, how they split,
how many in each split have absence as their right answer, how many distinct sources they came
from, which fields each carries, and which steps an example labels through `expected_by_node`.

**The worked example comes from an inspectable split.** `dev`, `train` and `development` are
inspectable. Held-out splits contribute counts but no displayed example, preserving their use
in evaluation (FT-02). A project with only held-out examples shows the split counts.

## 10. What a resource holds

A resource is a string a project chose. Its contents are unknown to the library.
Selecting one shows what can be known.

**Who touches it, and through what.** The steps that read it, write it, or touch it without
declaring a direction, and every tool that names it: its description, its side-effect class,
the steps that call it, its signature, and its own code. **A recorded access settles a
direction the declaration never carried**: `touches=` says a step reaches a store and an
access says which way it went, so a step that has recorded one is on that side and the card
says where the answer came from.

**What has gone in and out of it.** Every access the record holds, newest first, with what
was asked for and what came back. Two things count as an access and the card shows them
together: a tool call, where the tool declares the resource it touches, and what a step's own
code recorded with `ctx.record_access` (§4.1). The kind of thing a store is stays out of this
entirely, so a database, a directory of files, an inbox and a third-party API read the same way.

**What an evaluation's rollouts reached is counted apart** from what the agent's own runs
did. A rollout touches the real store, and counting it as work would overstate what the agent
does.

**Where it goes from there.** The steps that touch it and what each produces afterwards, so
the path is followed from where the data enters rather than from the first
step of the pipeline.

A resource that no tool names and no step has recorded reaching says so, and names the call
that would fill it in.

## 11. What the evaluation says, on the page

The page reads the results file the gates read: the one `results` names in the brief, or the
most recent under `evals/results/` where the brief names none (`docs/conformance.md` §3).

The measure page is a grid of regions, in the order of the three questions it answers: how
good is it, where does it lose it, and did the last change help. Every region is a drawing;
what opens and shuts is the numbers behind a figure and the record behind a rollout. Every mark carries its words on hover, and the same words are reachable without a
pointer: the numbers behind a figure, the legend beside a bar, the list under a chart.

**The headline strip.** The headline figure large, with one axis under it from 0% to 100%
carrying three things: this evaluation's plausible range with its point marked, what doing
nothing scored (the suite's `baseline=`, as counts over the same examples) as a hollow marker,
and the previous evaluation of the same figure as a diamond. Beside it, four tiles: the change
since last time in points, the do-nothing floor as counts, what measuring cost in total and
per example and per rollout, and how many built steps the evaluation reached. Under it, one
line of facts: rollouts right, examples and rollouts each, the split, the date, the model,
and whether the calls were live or replayed. Right means what `accuracy` counts: the right
value, or the right report of absence.

**How the rollouts ended** is one bar with a right side and a wrong side. The right arm
holds the rollouts that were right and those right by reporting absence; the wrong arm holds
partly right, missed and confidently wrong; a rollout that measured nothing (failed, or no
response) sits in a neutral centre. The legend under it carries every count and share, so the
bar's colour never carries a count alone. Under the bar, for an answer key with parts, one row
per condition: how often it was met, on the same axis, and how many examples fell short.

**Every example** is a grid: examples down, rollouts across, one square per rollout coloured
by how it ended, with what the example expects in words and how many of its rollouts came out
right. Examples that came out wrong sort first; the grid also sorts by name and by what is
expected, and finds an example by name. Selecting a square opens what that rollout answered
against what was expected, which conditions it met and fell short on, what was left out and
why, and a button that walks the rollout step by step. The grid is the hub: a segment of
the outcome bar, a condition's row, and a group's row in the figures table each light the
rollouts behind that number and dim the rest, and "Show all" clears it.

**All the figures** sit on one axis: name, plausible range with the point marked, value, the
range as text, and the rollouts it is over. A figure the project declared a count over the run
is drawn as a number with its reason and no range, because a census is not an estimate of a
rate (`docs/evaluation.md` §11.8); a figure in a unit other than a rate is a number too. A
figure opens to its numbers: the point, the range and how it was made, the totals behind a
ratio, what it is over, and the rollouts left out of it by cause with the figure that counts
them back in (FT-06). **Split by** a property of the example (split, source, any metadata
key) draws one row per group under each figure, on the same axis, each over its own examples
with its own range.

**Did the last change help?** Every comparison written under `evals/variants/` is drawn as
one before-and-after chart: per figure, a hollow dot before and a filled dot after on one
axis, the change beside it and the verdict in words (moved, held, or undecided). The figures
that moved sort first; a row that held is grey. What differed between the two arms comes
first, in words, as the candidate cause; an undecided row says why on the row (too few
examples, two populations), and what holds for every undecided row is said once under the
chart; the steps whose reach or accuracy moved and the
groups that moved on their own where the pooled figure did not open under it. The served page
compares any two results files on record with the same rule the library uses (`compare()`),
and refuses the pair the library refuses.

**The headline figure over time.** The evaluations on record, oldest to newest, each with its
plausible range as a whisker and the reported one ringed. A line joins only points that are
the same figure (the same name and definition) over the same behaviour; a dashed break marks
where `behaviour_fingerprint` moved, and a point measuring a different figure is a lone grey
mark. Rungs are left out, because a rung's denominator is its own examples, and so are a
sweep's arms and its own baseline, which are experiments against the project's behaviour
rather than that behaviour changing; the sentence under the chart counts them. With one
evaluation on record the region says so and draws nothing.

**Where it loses it, step by step.** Results files that are rungs of one pipeline
(`config.slice` names the pipeline they were cut from) are drawn as brackets under the steps:
the whole pipeline first, then each rung spanning the steps it ran, with its figure at the
bracket's end. A sentence per adjacent pair says where the figure falls and which steps
entered, as an observation and never as a paired difference. Selecting a rung shades the
drawing to its steps. The rungs as a table open under it.

**A project that has measured nothing yet** gets the same strip in words: how many examples
are on file and how they split, which steps the brief says are judged on their own, and the
call that produces the first number. Nothing else is drawn.

**Per-step figures land on the steps.** Reach, executions, model calls, tool calls and what
they spent, questions asked and who answered them, errors, how the executions ended, and the
step's own accuracy where an example set labels it (`docs/evaluation.md` §5).

**What it did not measure is said as plainly as what it did**: steps no rollout reached,
steps in the code the results file carries no figure for, pipelines the evaluation did not
measure at all, and figures whose population was empty.

**And what the figures describe.** The results file records the pipeline's shape, so a page
whose code has moved since says the evaluation measured a graph the project no longer has.
A brief naming an older results file than the newest on disk says that too, because that
older one is what every check reads.

## 12. What it does not do

It never writes the brief: answers and amendments travel as threads, and the coding agent
records them with `simple-agents record` (`docs/conformance.md` §2.3). The join between a step and the decision that produced it reads `produces` on a
`shape` or `prompt_rule` decision, which names the step exactly (`docs/conformance.md` §2.2). A
decision recording none is matched on the step's name in its wording instead, so a step agreed
to in other words shows as unagreed, and the card says which join it used.
A run is followed through the records it writes, so a step is marked done when its record
lands rather than the moment it finishes. What a step moved is counted from one run's records
and is that run's figure, not an average over the record.

**Every edge out of one step carries the same value.** A step resolves all of its out-edges
with the one output it produced, so what separates two arms of a route is which of them fired
rather than what each carried, and the edge card says so.

**A store's history is what was recorded.** A step that reaches a resource in its own code and
records nothing leaves the card with the declaration and no accesses, which the card reports
rather than filling in.
