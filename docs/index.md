# Simple Agents

Simple Agents is a library for building an agent that can be evaluated, debugged, and improved. Every run records what it did, replays with no network access, and can be scored against a labelled set of examples, with a confidence interval on every figure.

These nineteen documents are the reference for what the library does. They are written for a builder and for the coding agent working on their behalf.

**Start with `docs/procedure.md`.** It is the order to build in, and each stage points at the documents that stage needs. `simple-agents init` registers it as a skill, so a coding agent has it loaded rather than having to remember it.

The right column below is the other way in. A document no stage names is opened on a condition, and that column is the condition.

Read "What it covers" to determine if the library already ships a feature that is needed, before deciding to implement it.

---

## The documents

| Document | What it covers | When to open it |
|---|---|---|
| `docs/procedure.md` | The six stages, what to settle with the builder at each, the project layout, the gate that ends each stage, and the feature index naming every capability the library ships | First, and again at every gate |
| `docs/pipeline.md` | The pipeline as a graph, the three node kinds, branching, joining and bounded cycles, suspending a run and resuming it, streaming a node's output, naming a pipeline, which model a node calls, handing a subtask to a pipeline the model chooses, what a node receives, the output schema and `unknown`, budgets, watching a run in progress, and running the pipeline without a backend | First, and before any node is written |
| `docs/tools.md` | The tool contract, the registry, how a tool is replayed, the built-in set, reading pages, which hosts a run may reach, caching what was fetched, the finish check, what an end user's answer says about which option it was and how a model reads one that says it in prose, who a consultation channel says answers, the three ways a consultation ends without an answer, naming what a question is about, asking about each of many things, and giving the agent the tools an MCP server offers | Before writing anything the agent calls out to: searching a document collection, fetching a page, extracting to a schema, asking the end user, before routing on what they answered, and before connecting to an MCP server |
| `docs/retrieval.md` | Searching by meaning as well as by words: which model embeds a corpus, how lexical and semantic results combine, reranking, where the vectors live, how a corpus that changes is added to, and what the model calls a search makes cost | When a query phrased differently from the document has to find it, and before choosing an embedding model |
| `docs/context.md` | What the model is sent on each call, what overflow means, and how to replace the default | When a prompt outgrows what a backend accepts, or a node has to send less than the whole conversation |
| `docs/memory.md` | The memory store, the tools that reach it, what an evaluation does with it, what redaction reaches, and why a write is a put | When the agent has to remember something after the run ends |
| `docs/conversation.md` | A conversation that outlives the run: declaring the store, how a node takes part, what a turn is, reading a conversation back, compaction, and what each run records of it | When a second message has to know what the first one said: a chat, a ticket thread, anything multi-turn |
| `docs/model-clients.md` | The model seam, the comparison between the three shipped backends, a model per node, retries and pacing, streaming, reasoning output, and writing an adapter | When choosing a backend, or connecting one the library does not ship |
| `docs/model-clients/gemini.md` | `GeminiClient`: pinning a model, declaring prices, prompt caching, evaluating against a backend that publishes no allowance, and the thought signature a tool call is refused without | When the run is pointed at Gemini |
| `docs/model-clients/mistral.md` | `MistralClient`: declaring prices, prompt caching, the published rate-limit allowance, and what the backend does not report | When the run is pointed at Mistral |
| `docs/model-clients/vllm.md` | `VLLMClient`: the serve command and what each flag decides, pinning the revision, per-call settings, and serving concurrency | When the run is pointed at a self-hosted vLLM server |
| `docs/run-envelope.md` | The run directory, the manifest, what a run declares it is for, cassette recording and replay, seeds, cost, redaction, and reading past runs back | Before the first run that has to be reproducible, priced, or replayed, and when a project reads what its runs produced |
| `docs/trajectory-format.md` | The record schema: seven record types, token accounting, and the encoding rules everything downstream reads | When reading a run's records, or writing something that consumes them |
| `docs/evaluation.md` | Labeled example sets and their splits, running a labelling pass and keeping what it decided, k rollouts, the intervals over them, the eight rates, a figure per criterion, and a metric the project declares itself, per-node metrics including reach and accuracy, the end user an evaluation answers its consultations with, recording the runs a replayed evaluation is served from, what an evaluation does with a rollout the backend never answered, and what an evaluation refuses to run | Before drawing a split, before labelling anything, before evaluating an agent that spends money, and before reporting any number about how well the agent works |
| `docs/evaluation.md` §4.1, §4.2 and §8.2 | What a figure is read against: `rollout_noise`, how far it moves when the same examples are run again, which no interval covers; `EvalSuite(baseline=...)`, what an agent that did nothing would have scored on the examples that ran; and `results.grouped(key)`, every figure over each cell of a property of the example, which a pooled number hides | Before quoting any figure, before reading a difference between two runs as an improvement, and whenever a split holds more than one kind of example |
| `docs/evaluation.md` §9 and §10 | Comparing two versions of the agent, and comparing named variants of one pipeline: `compare` reports the paired difference between two results files, `compare_variants` runs the baseline and every named arm in one session and pays only for the nodes the change can reach, `ablate()` generates the standard downgrades, and `plan_variant` says what a sweep will cost before it runs | Before changing a node kind, a tool, a prompt, a temperature or a model, and whenever the question is whether a change moved anything |
| `docs/shipping.md` | What changes when somebody other than the builder uses the agent: a run that says it is live, reading live runs back, what one keeps, who answers the agent once it has shipped, what the end user reads once it outlives the run that wrote it, and what live runs are worth to the next version | Before anyone other than the builder uses it, and at the `ship` gate |
| `docs/view.md` | `simple-agents view`: the one page showing the project as it stands, registering pipelines so it can draw them, `NotBuilt` for a step declared before it is built, `touches=` and `ctx.record_access` for what flows between pipelines and what went in and out of each store, what each step is handed and hands on with how much moved and what every run cost it, how often each edge is taken, one run walked step by step, the example set it is measured on, what the reported evaluation measured and what it did not, and the builder's comment record | At the `shape` gate's design conversation, whenever the builder asks where things stand, after an evaluation, before proposing anything structural, and when a run went wrong |
| `docs/product.md` | What the end user uses: the three product shapes, the four kinds of interaction a surface can offer, a run per request behind a surface, a question the agent cannot settle and what happens when the answer arrives, the artifact that accumulates, what triggers runs, and where `runs/` has to land | At `used_through`, at the design stage's product section, and before the surface is built |
| `docs/failure-taxonomy.md` | The characteristic failures an agent project hits, what each check reads, and the ones no check enforces yet | When a check fails, and when deciding what the project still has to do |
| `docs/conformance.md` | Running the checks: what a tier, a stage and a gate are, the brief a project declares, what each check reads, what the report means, and the notes it prints under the checks | Before the first `simple-agents check`, and when a check reports something unexpected |

An installed copy carries these files beside the package. `simple_agents.docs_path()` returns the directory holding them.

---

## The vocabulary

These terms mean one thing each throughout the documents and the library's error messages.

| Term | Meaning |
|---|---|
| **Builder** | The person using Simple Agents to build their idea. Every decision about what the agent should do is theirs. |
| **Coding agent** | The AI coding assistant the builder works with. |
| **The project** | What the builder and the coding agent produce together: agent code, evaluations, the brief, trajectories, and the manifest. The conformance suite runs against this. |
| **The agent** | The runnable agent inside the project. One component of it. |
| **The product** | What the end user uses: the surface they meet the agent through, and any artifact the project keeps for them to read. The agent runs inside it. Where the builder runs a script and reads what it prints, that script is the product. |
| **End user** | A person using the agent the builder produced. May be the builder, or a customer of theirs. |
| **Elicitation** | The coding agent asking the builder, at build time. Recorded in the brief. |
| **Consultation** | The agent asking the end user during a run, through a tool call. Recorded in the trajectory. |
| **The brief** | The file recording elicited answers, one entry per question. |
