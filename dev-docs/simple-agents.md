# Simple Agents — library specification

Status: pre-implementation. Nothing built. This document is the design of record.

Every decision below carries a **Why**. The rationale is the durable part; if the rationale is wrong, the decision should change. If you want to argue with a decision, argue with its Why.

---

## 1. Positioning

### 1.1 What this is

A library that makes AI coding agents produce **correct, evaluated, improvable** agent projects, by shipping an opinionated agent shape, a conformance suite that runs against the generated project, and a staged procedure with enforced gates.

**Nutshell:** the library holds the coding agent's hand so the coding agent can hold the builder's hand.

### 1.2 What this is explicitly not

| Not | Why not |
|---|---|
| An orchestration framework | Saturated. LangGraph, CrewAI, Microsoft Agent Framework, Pydantic AI, OpenAI Agents SDK, LlamaIndex Workflows, Agno, Atomic Agents, and vendor SDKs all live here. |
| "smolagents but simpler" | The *simple agent-building* seat is taken. smolagents is ~1,000 lines, model-agnostic, and explicitly minimal. A thinner wrapper would be it with less mindshare. |
| A training engine | verl, OpenRLHF, SkyRL, ART, and Tinker exist and are better at this than a new entrant will be. |
| A thin wrapper whose only value is saved glue | Glue is what coding agents write for free. Ease of use is a goal, not the disqualifier: the library should be easy *and* carry substance a session does not rebuild — the recording, the refusals, the eval process. |

### 1.3 Why the gap is real

The *building* gap closed — agent-building APIs are already friendly. The gap that remains looks like 2019-era Transformers: the **improve-your-agent loop**. Take an agent on your task, evaluate it rigorously, make it better. Today that means stitching an orchestration framework to a hand-written eval harness to ART/SkyRL/Tinker, with reward engineering in the middle. Each piece is documented for experts. Nothing owns the end-to-end experience.

Structural reason it persists: training libraries are built by RL people optimizing for throughput and research flexibility; orchestration libraries are built by app people who treat the model as fixed. Simple Transformers sat at exactly this kind of junction.

### 1.4 Prior art, and why it doesn't block us

Spec-driven development (GitHub Spec Kit, AWS Kiro) is the mature analogue: an executable specification as source of truth, code as a generated verifiable artifact, distributed as agent skills. This is **good news, not competition**:

- It validates the form factor. The "library as executable procedure for a coding agent" pattern works and has adoption.
- The distribution mechanism is standardized (skills directories, extension catalogs). Ride it; don't rebuild it.
- Libraries are not winner-take-all. Simple Transformers competed with HF Trainer, Lightning, and fastai and won a niche on opinionation and taste, not novelty.

**Differentiator is vertical, not structural:** generic SDD has no notion of evaluation under stochasticity, agency boundaries, trajectory capture, or an improvement ladder. Those are agent-building-specific and are the whole content of this library.

**Open question:** whether the procedure we encode differs from generic SDD enough to justify itself. Answered empirically by the dogfood runs, not by argument.

### 1.5 Audience

The **trust audience**, not the accessibility audience. People who *could* generate all of it and are better served not having to — the way a coding agent could implement PyTorch from scratch and should not.

This is a smaller top-of-funnel than Simple Transformers had, and that is accepted, not a problem to solve. The people who couldn't write the code at all now have coding agents. Do not design for them; designing for them produces a convenience wrapper (§1.2).

### 1.6 What the library ships and what the project holds

*Moved here from `simple-agents.md` §1.6 on 2026-08-15. It generalises §4.1, which states the same split for evaluation alone, and it is the line to check any proposed addition against.*

**The library ships machinery. The project holds content.**

| The library ships | The project holds |
|---|---|
| Split tracking, k-rollout execution, bootstrap intervals, contamination checks | The examples, their labels, and where the split falls |
| The tool contract, the registry, and the minimal built-in tools | Which tools this agent needs, and any tool the builder writes |
| The three node kinds and the run envelope | Which nodes exist, and what each one does |
| The elicitation questions and the gates | The answers, in the brief |

**No dataset ships with the library, and no dataset is built by us on a builder's behalf.** What counts as ground truth is task-specific and is a builder decision, elicited at build time. A shipped dataset would also teach the wrong lesson by being the obvious thing to evaluate against.

**The library's own tests use handcrafted fixtures, and that is a requirement rather than a shortcut.** Machinery can only be verified against data whose correct answer is already known, which is exactly what real data does not give. Do not reach for a public dataset to test library code; a public dataset belongs to a dogfood project, not to `tests/`.

---

## 2. Architecture

### 2.1 The run envelope (the containment decision)

```
┌─ Run envelope ─────────────────────────────────────────┐
│  manifest (models, prompts, tool versions, seeds,       │
│  budget) · trajectory log · cassette                    │
│                                                         │
│   ┌───────────────┐ ┌────────────┐ ┌───────────────┐   │
│   │Context builder│ │ Agent loop │ │ Model client  │   │
│   │what model sees│ │step/budget │ │pinned,versioned│  │
│   └───────────────┘ └────────────┘ └───────────────┘   │
│   ┌───────────────┐ ┌────────────┐ ┌───────────────┐   │
│   │ Tool registry │ │Output schema│ │ Consultation  │   │
│   │typed contracts│ │allows unknown│ │ asks end user │  │
│   └───────────────┘ └────────────┘ └───────────────┘   │
└─────────────────────────────────────────────────────────┘
                          │  reads trajectories
                          ▼
              ┌────────────────────────┐
              │ Eval and conformance   │
              └────────────────────────┘
```

**Decision:** every component runs inside a run envelope that records by construction.

**Expanded into `docs/run-envelope.md`, which is authoritative on detail** — the run directory, the manifest schema, cassette keying and replay, the cost bases, seed derivation, and the redaction rules. This section keeps the rationale only.

**Why:** the alternative is logging as a thing the agent author remembers to do. They don't, and the omission is invisible until you need to debug or evaluate — at which point the data doesn't exist. Containment makes recording structural rather than disciplinary.

**Decision:** the cassette is written by default, and is kept or dropped with the trajectory's payloads on one per-run decision. *(Added 2026-08-11, at the recording-default item. Two of the three artifacts the diagram names were written by construction and the cassette was not, so this completes the decision above rather than changing it. `build-logs/recording-default-build-log.md` is the record.)*

**Why:** a `model_call` record already carries the whole prompt and the whole response, so while the trajectory is full the cassette discloses nothing new and costs disk alone. Under a sampled trajectory it would be the only copy of the payloads, so a cassette defaulted on its own would defeat the single control the library offers over what is kept. One decision for both means the runs that keep payloads are the runs that can replay, and no others.

**Decision:** nothing runs that the builder did not ask for. Importing the library starts nothing, a call returns having left nothing running behind it, and no timer fires later. What the builder constructs is theirs, and may hold a thread or a process for as long as they hold the object: a connection to an MCP server holds both, opens on first use, and is reaped at process exit. *(Added 2026-08-04, at the item 8d sitting. It was previously carried, unstated, by the "no scheduler" half of §9 item 12.)*

*Amended 2026-08-27, at `P3-38` sitting 1, on Thilina's call. The entry read "nothing runs outside one. The library owns no execution outside a call the caller made: no background thread, no daemon process, no timer that fires later", and that would have put an MCP connection's lifetime inside `Pipeline.run`. **Measured that day**: spawning a stdio server under `npx` costs about 400ms (351, 400 and 420 over three runs, warm cache) against a 5ms `tools/call`, and [`docs/product.md`](../docs/product.md#L7) opens on a product being a run per request, so a per-run lifetime charges 400ms to every request a shipped agent serves. Every other external resource in the library is already an object the builder constructs and holds: a `DocumentIndex`, a model client, a `UrlCache`, a `HostPolicy`. What this entry was protecting is that nothing runs the builder did not ask for, and an object written in the builder's own code is not that. **What it gives up:** whether something of the library's is running is now answered by reading the builder's code rather than by reading this rule. Thilina, on being asked to rule: "it might be a stupid rule to hold for a library that helps build agentic systems."*

**Why:** everything the envelope promises is scoped to a run the caller started and can watch. Something running in the background is activity no `RunResult` accounts for, spend no budget bound, and records written by nothing the caller called. The case that tested it is item 8d: a run suspended until a token quota resets could be built as a timer that wakes itself, and then a process that exits loses the run silently while a process that stays up spends money at a moment nobody is watching. It is built instead as a file and a refusal, and whatever restarts the process is the project's. It is also why a supervisor holding suspended runs stays out — it would have to be handed a factory for the caller's program to reconstruct a pipeline at all.

**What the amendment leaves standing.** A call made through a builder-held connection is recorded, budgeted and priced like any other call, so the activity this paragraph names as unaccounted for is still ruled out. The lifetime of the resource moved; what happens through it did not. The timer half is untouched, and item 8d's suspension is still a file and a refusal.

### 2.2 Agent shape

**Decision:** a pipeline of nodes. Each node is one of three kinds:

- `Deterministic` — plain code, no model call.
- `LLMNode` — model judgment at a fixed point in a fixed control flow. One call, one place, one output shape.
- `AgentNode` — the model decides what happens next (which tool, whether to loop, when to stop). **This is the agency escape hatch and it is deliberately the most expensive thing to reach for.**

**Why the three-way split:** the central design question of the whole library is *where does agency pay for itself*. Most of what feels agentic is an `LLMNode` in a fixed loop — `while insufficient and attempts < 3: queries = llm(...)` is deterministic control flow containing model judgment. Making the distinction type-level means:

- per-node evaluation is possible (an end-to-end agent gives one number and no way to localize a regression),
- per-node training data falls out for free,
- the ablation machinery (§4.3) has something to ablate.

**Decision:** no graph engine, no DSL, no scheduler in v0. A list of callables plus a run context.

**Why:** we do not yet know what the abstraction needs to be. Building it before the first dogfood is inventing rather than extracting, and extraction beats invention for API design (Rails from Basecamp, Django from a newsroom, Simple Transformers from Thilina's own notebooks). The constraint will reveal what is actually missing.

*Amended 2026-08-03, at the branching sitting.* **A pipeline is a directed graph over the same three node kinds, with edges declared on the node. A list is the case where every node has one successor, and every pipeline written against the decision above keeps its exact meaning.** Built as `build-logs/item8c-build-log.md` on 2026-08-04. The claim about existing pipelines was checked rather than asserted: the whole suite passed with the executor replaced by the graph walk, before any graph feature was added.

**The rationale above is not defeated. It was satisfied.** "Extraction beats invention" says do not design the abstraction before the constraint has shown what is missing, and the last line says the constraint will reveal it. Five build items and two cold-read checkpoints later, it has:

- **Fan-out set the evidence bar and this clears it.** `LLMNode(over=...)` was not planned. It was added at the item 5 checkpoint because two sessions met the shape and it turned out to be forced rather than invented. `build-logs/item8c-build-log.md` records the identical bar for branching.
- **Session 1 of the item 7 checkpoint went looking for "if `hunt` returned `unknown`, skip `verify`"**, found nothing, and paid for a verification call on all 31 of its `unknown` answers.
- **One shape cannot be expressed at all**: draft, critique, revise until accepted, at most three times. The control flow is fixed and only the judgment is the model's, which is this section's own definition of an `LLMNode`. `Deterministic` is never handed a model client, so the loop cannot go there, and the only kind that can hold it is `AgentNode`. **The shape forces the escape hatch this section exists to make expensive.**
- **The cost of waiting stopped being zero.** When this was written the pipeline shape was a constructor argument. It is now in three formats: `node_execution` records, per-node metrics whose numbers are read against a denominator of one execution per run, and the ablation unit.

**Routing is a property of a node, not a fourth node kind**, on the same argument that kept fan-out from being one. Do-not-change #8 is untouched.

**What the graph gives up.** Per-node numbers stop sharing a denominator: a node that runs on some examples and not others is counted over the runs that reached it, and its reach is reported as a rate with an interval beside every other number it carries. The list shape was also enforcing something it never claimed, which is that elaborate control flow was expensive to write; a graph makes it cheap, and the answer is that the instruments keep up rather than that the refusals hold the line. **What the graph does not give up is the property those numbers rest on**, which is that a node's input is a recorded value: every value a node receives arrives on a declared edge and is written to its record. Shared state is refused for exactly that reason. `docs/pipeline.md` §1.2 and `docs/evaluation.md` §5 own the detail.

*Amended 2026-08-09, at the DF2-D1 sitting.* **The refusal is settled and `plan.md` §2.2's shared-state entry is closed**, with item 8c's three reasons tested against the case that reopened them rather than restated. What the sitting found is that the property costs more to hold than anyone had written down. A node's output is the whole of what travels, and two kinds of node narrow it: one that calls the model produces what its `output_schema` describes, and one that fans out produces the outcomes. Dogfood #2 met both and used `ctx.workspace`; dogfood #1 run 2 met one, chose the graph over the workspace by name, and read the working set off the edge that entered its cycle, which stays resolved at what entered. Its retry therefore never accumulated, and 12 of the 20 runs that went round twice lost passages the first pass had retrieved. **Both shapes were expressible the whole time**, which a probe established before anything was designed. So the answer was `docs/pipeline.md` §1.3 and §1.4 saying how, and `keep=` for the one narrowing the library's own container was doing. `build-logs/loop-accumulator-build-log.md` is the record.

*Amended 2026-08-04, at the build.* **Per-node accuracy is no longer a permanent limitation and ships**, as `Example.expected_by_node` and `EvalSuite(node_matches=...)`, over the rollouts that reached the node and carry a label. The project supplies the label and the comparison; the library supplies the denominator and the interval. Nothing is refused for want of a label.

*Amended 2026-08-10, at the pipeline-as-a-tool item.* **A model can now choose which nodes run, by handing a subtask to a whole pipeline**, declared as `AgentNode(delegates=[Delegation(...)])`. Until this, a `Pipeline` with a `node_id` covered the case where the builder fixes the decomposition and nothing covered the case where the model chooses it, which is why orchestrator-workers had no expression in the library and why the two largest shapes in `items/example-projects.md` had none either. `build-logs/pipeline-as-tool-build-log.md` is the record and `docs/pipeline.md` §2.5 is what shipped.

**Do-not-change #8 is untouched, and this section's economics are the reason.** A `Delegation` is a declaration on an `AgentNode`, not a fourth kind: the escape hatch stays the one place agency is bought, and what the delegate holds is the same three kinds under prefixed ids, each with its own record, its own budget and its own per-node figures. The distinction this section exists to make is therefore preserved through a level of nesting rather than diluted by one — the model picks the subtask, and every step of answering it is still classified.

**Why it is not a `Tool`, which is the shape that suggests itself.** `Tool` requires a declared side-effect class (§8.2 item 6), and a pipeline has none to declare. That was the deciding argument for the record type (§6) and it decided the API too: forcing a pipeline into the dataclass would mean inventing a class, an `fn` and a `parameters` schema for it. **What the declaration buys is the whole pre-flight spine for free**, since `declared_nodes()` descends into a delegate: §4.4's refusal, the unserved-model and mixed-currency refusals, and the manifest's `nodes` all reach inside it without knowing delegation exists.

**And it closed a hole that was already open.** A builder could always write a tool whose body calls `Pipeline.run`, and measured at this item, that pipeline is outside every walk: a `spends_money` tool inside it is invisible to §4.4's refusal, so an evaluation would execute it k×n times with nothing having declared it. Python cannot detect that body, so the answer is the one §8.2 already uses for the handle rule — state the constraint, and make the declared path the cheap one.

### 2.3 Agent loop

**Decision:** in-house, not a wrapper around smolagents or Pydantic AI.

**Why:** the loop must enforce budgets, record to the envelope, respect tool side-effect classes during eval rollouts, and expose the node-kind distinction. Wrapping a framework means fighting it on all four. The loop is also the cheapest component to write — it is not where the value is, so owning it costs little.

**Tension to be honest about:** an earlier version of this design said "be a front-end, not an engine, ride the ecosystem." That advice still holds for *training* backends (§5), where the engineering is enormous and standards are consolidating. It does not hold for the loop, where the code is small and the required control is total.

**Requirements:**

- **Budget and termination are non-optional.** Max steps, max tokens, max wall-clock, max cost, explicit stop condition. A loop constructed without a budget **refuses to run** — not a warning.
  - *Why:* the most commonly omitted piece in hand-rolled agent code, with the worst failure mode (infinite loop burning money). Warnings get ignored by coding agents; refusal does not.
  - *Note on `max_cost`:* cost has two bases depending on the model backend — token prices for hosted APIs, device-seconds for self-hosted serving (`docs/run-envelope.md` §4). The budget axis is the same; what it is denominated in is not. Under self-hosting an unattributed figure overstates cost by the batch factor, and a budget enforced against that is not enforced (FT-27).
  - *Amended 2026-07-26, at item 4.* The agent shape shipped with `max_cost` unenforced and a comment saying it would stay that way, on the argument that terminating on a compute-basis figure that might be 8× high would end runs which were within budget. **That is now reversed: `max_cost` is enforced against the derived figure, including when the figure is an upper bound.** The argument it replaces is right about the arithmetic and wrong about which error to prefer. For a *limit*, an over-estimate stops a run early, which is recoverable and visible; the alternative is a budget axis that silently does nothing, which is the FT-18 failure the whole section exists to prevent, reached by a different route. The trajectory records `termination: max_cost` and the manifest records that the figure was a bound, so a reader can see why the run stopped and how good the number was. The residual risk — a well-batched self-hosted run stopping earlier than it needed to — is bounded by the batch factor and is fixed by the backend reporting concurrency, which is the same fix `docs/model-clients.md` §3 already asks for.
  - *Follows from the same amendment:* a pipeline that sets `max_cost` while the envelope declares no cost basis **refuses to run**. No figure can be derived, so the limit could never fire, and a budget nobody can compute is worse than an absent one because it looks set.
  - *Amended 2026-08-09, at the DF2-D2 sitting.* **`max_cost` is not enforced against a figure the library knows is a bound.** The 2026-07-26 amendment above is what was believed before this and is kept as the record. Three of its claims did not survive being measured.

    **It presented a choice between two options and there were three.** It weighed enforcing against a bound against "a budget axis that silently does nothing", and the bullet directly above already takes the third: a pipeline setting `max_cost` with no cost basis refuses to run, because a budget nobody can compute is worse than an absent one. A bounded figure is that case one degree weaker — computable, and not trustworthy to within the batch factor — and the refusal was never extended to it.

    **"Recoverable and visible" was priced at zero, and a re-run is not free.** The budget is per rollout. On a compute basis at eight requests in flight, a `max_cost` set with 2.7× headroom over the real per-rollout figure kills every rollout in an evaluation, and the report cannot distinguish an expensive agent from a ceiling computed against a number eight times the truth. The work already done is paid for and discarded, then paid for again.

    **The qualification never reached the decision.** `is_upper_bound` was discarded at the charge site and survived only into the manifest, so a run stopped on a number and what was known about that number was written down afterwards. And the fix the amendment relied on — the backend reporting concurrency — ships off by default for a stated reason, so "residual risk" described the default case rather than a residue.

    **Measured.** Across the three dogfoods, 1,127 manifests all declare a `price` basis, `is_upper_bound` is false on every one, and `max_cost` was set on 541 runs and fired zero times. This path had never executed, so nothing had contradicted the rule and nothing had confirmed it either.

    **What ships.** `report_concurrency` defaults on for `VLLMClient`, which removes the bound for the only self-hosted adapter the library has; the sample runs on a thread joined inside the call, so it costs one local request and no latency. A budget setting `max_cost` under a compute basis warns at run start, naming the flag. The first call producing a bounded figure ends the run, naming it again — one call rather than none, because the alternative is asking every client to declare a capability that arrives in its responses rather than in its signature, which refuses a hand-written adapter for something it was never asked to state. `max_cost` under a price basis is unchanged, and `max_cost` with no basis still refuses at construction.

    **What the compute basis is for.** An hourly rate on a device you own is a figure you invented, and `max_wall_clock` is the bound for that case. *(Amended 2026-08-13 at the concurrency item: `DeviceBasis` now reports what such a run used, in device-seconds and with no rate, so the alternative to inventing a figure is a measured one rather than a null. `archive/plan-history.md` §1.12 Decision 4.)* It fired 18 times across the dogfoods where `max_cost` fired none. The compute basis earns its place when the hour is billed to someone, which `docs/model-clients/vllm.md` §5 and `docs/run-envelope.md` §4 now say.
  - *Also amended 2026-08-09, at the same sitting.* **`max_cost` bounds what tools spend as well as what the model spends.** It was charged at one site, around the model call, so the axis named for cost bounded the model and nothing else — while on dogfood #2 tool spend was 1.9× model spend and 65% of the bill. A tool reports what it spent through an injected meter and that figure depletes the same axis. Keeping it a second ceiling was considered and rejected: a builder who sets `max_cost`, which is the axis FT-18 and every document points at, would otherwise leave the larger half unbounded by omission. `HostPolicy.max_fetches` stays as a count ceiling beside it, because a count and a sum bound different quantities. `build-logs/tool-spend-build-log.md` is the record.
- **Termination is an explicit tool call** (`finish`), schema-validated — not a heuristic on the model's prose.
  - *Why:* materially improves loop reliability and makes "why did it stop" answerable from the trajectory.

### 2.4 Context management

**Decision:** an explicit, pluggable component. v0 default is trivial (append everything; error on overflow rather than silently truncating).

**Why:** what goes into the prompt each step is the largest single determinant of agent quality. If it's buried in the loop body, builders who need to replace it will fork instead of extend. Trivial default is fine; implicit default is not.

**Built 2026-07-27, at item 6.** `docs/context.md` is authoritative on detail; this records the decisions and the rationale.

**One interface, one call site, called once per model call under every node kind.** `ContextBuilder.build(messages, ctx) -> ContextResult`, plugged into `_call_model`, which every kind already goes through. This is the second application of the rule the item 5 checkpoint established for `max_steps`: one step is one model call, everywhere. An `LLMNode` calling the builder once with a one-message list is the degenerate case rather than a special case, and two interfaces would mean implementing two things to change one behaviour. Set per node, with no envelope-level default, because two places to set one value is the ambiguity item 4 rejected when it split the envelope by lifetime.

**The builder is a view over the conversation, not a change to it.** An `AgentNode` keeps the full history whatever the builder returns, so a truncation on turn 5 does not compound into turn 6, and the full history stays reconstructible from the node's child records rather than being stored twice.

*Amended 2026-07-28, at the item 7 checkpoint.* **A builder decides what one call sends, and it can send more as well as less.** Everything written here and in `docs/context.md` framed the component around what gets left out, because overflow is what motivated it. Session 1 used it to add: a note before each turn saying how many turns of the budget remained, having found that an agent with no view of its own ceiling spends every turn searching and has none left to report what it found. It works, the record stays honest because `dropped` is genuinely empty, and it is the per-step hook item 5's session B asked for and could not have (`runs/checkpoint-item5/findings.md` §6). The session said plainly it did not know whether the use was intended, because the only place that answer existed was in `dev-docs/`. It is intended, `docs/context.md` §4.1 now shows it, and the view-not-a-change property is untouched: the note goes to the call, not into the conversation.

**Why this component may read run state where a tool keyed by its arguments may not**, which is the §6 rule in `runs/checkpoint-item5/findings.md` made exact by the code. A tool is keyed in the cassette by name, version and arguments, so a tool that reads mutable state can return two things under one key and replay serves whichever was recorded first: silent and wrong. The context builder's *product is the keyed material*, since `messages` is in the key. A builder that varies with run state produces a `CassetteMiss`, which is loud and correct. The line falls where it does for a reason, and this is the reason.

*Amended at item 7.* This was the second instance of a rule that now has three, and §8.2 states the general form. The wording above said "where a tool may not", which item 7 narrowed: a tool the cassette does not store is on the same side of the line as this component, for the same reason.

#### What overflow means, and why an estimate is unavoidable

The question is not what a call costs. It is whether the next request will go through. Three quantities decide that and they are not equally knowable. **Measured 2026-07-27 by `scripts/probe_context_overflow.py`, not assumed:**

| Quantity | Where it comes from | Exact |
|---|---|---|
| The context window, in tokens | `GET /v1/models`: `max_context_length` on Mistral (**262144** for `mistral-small-2603`), `max_model_len` on vLLM (`40960` for Qwen3-1.7B) | Yes, before any call |
| What the previous call's prompt cost, in tokens | `usage.prompt_tokens` on the response | Yes |
| What the next, unsent prompt will cost | Nothing reports it | **No** |

Neither backend reports a window on a chat completion, and nothing counts a prompt that has not been sent. Comparing a message list against a token window therefore means converting from characters. **There is no design that avoids the estimate**, and an earlier draft of this section that claimed otherwise was circular: checking the previous call's measured size against a limit only fires after that call already exceeded it, so it never predicts the next one. What remains is a choice between making an estimate and labelling it, or declining and letting the backend refuse. Both, layered:

- **The floor: the backend's refusal, classified.** In force under every configuration. Both backends answer **400** carrying the phrase `maximum context length`, and `_http` raises `ContextOverflow` on that. Only the phrase observed is matched; a backend phrasing it differently falls through to the general refusal carrying its own message. **Neither refusal carries a `usage` block and neither carries Mistral's rate-limit headers**, so whether a rejected request consumes anything is unmeasured, and nothing in the library claims it does not.
- **The optional guard: `AppendAll(max_input_tokens=N)`.** The number is exact and its source is the model list, so it lives in the project for the same reason `PriceBasis` does: a provider-published figure that changes over time. **The ratio is measured rather than assumed** — the library holds the characters it sent and the tokens the backend reported for the previous call in that node, divides them, and extrapolates at the ratio that node exhibited. No constant, no English-average default, nothing to configure. On the live recording the extrapolation landed within about 10% of what the backend then reported.

**Where the guard binds, stated because an axis that quietly fails to bind is worse than an absent one.** It needs a previous call in the same run, so an `AgentNode` is checked from turn 2 and a fan-out from item 2. **A node making one call per run is never checked.** That is acceptable where `max_steps` not binding was not: a single call has no earlier turns to waste, and it either fits or the backend refuses it. The alternative considered was refusing the combination at construction, on the `max_failures`-without-`over=` precedent; it was rejected because the check would require a node to introspect a separate object's configuration, and the cost of the no-op is zero. It is documented at the point a builder sets the limit and pinned by a test.

**What happens on overflow, and who decides.** `ContextOverflow` is caller-facing, so the run stops, except inside a fan-out where the item is collected into `failures` and the remaining items still run: one oversized document says nothing about the next one, which is the same reasoning that made fan-out failures collectable at all. Stopping is a default rather than a judgement about what a shipped agent should do. Overflow is foreseeable rather than broken infrastructure, so the response is a builder decision, and the mechanism for a builder decision is elicitation plus a seam. This is FT-17's wording already, and item 6 is what makes that sentence implementable.

**Nothing truncates.** No policy, no summarisation, no sliding window, no tokenizer. Deferred, and the seam exists so they can arrive later informed by a dogfood. A tokenizer dependency stays out of the core (§10), a message store is a tool rather than a context builder, and an envelope-level default is two sources for one value.

*Amended 2026-08-27, at `P3-39`. Two of the three clauses above move, and both moves are a boundary rather than a replacement prohibition.*

***"A message store is a tool rather than a context builder" is defeated.*** A conversation that outlives the run is read by the prompt function, through `ctx.conversation`, and neither a tool nor a context builder. **The argument is §2.4's own, one level out.** A tool is keyed in the cassette by name, version and arguments, so a tool reading a thread that has moved on since the recording replays whichever content was recorded first: silent and wrong, which is exactly why a tool reading mutable state is refused. A prompt function's product **is** the keyed material, since the messages it returns are in the call's key, so the same drift produces a `CassetteMiss`. The clause placed a message store on the side of the line its own reasoning excludes it from. **What still holds:** the context builder is a view over the conversation and never a change to it, so it drops from what a prompt function assembled and stores nothing between calls.

***"No summarisation" moves to a recorded tool, and the context-builder half stands.*** The reason to refuse summarisation was never that summarising is wrong: it is that a model call made inside a component the library calls on every request would be unrecorded, unbudgeted, unpriced, and outside any node. **A tool is none of those.** `compact_conversation` is a `tool_call` on the trajectory with its `model_call` parented to it, charged to the run's budget, and re-run on replay with the inner call served from the cassette, which is the rule a `Memory`-taking tool already follows. So the boundary is: **the context builder drops and never summarises; a tool may summarise because a tool is on the record.** The tokenizer clause and the envelope-default clause are untouched. Thilina, being asked to rule on the blanket form of these: *"I hate these stupid blanket rules you write down anyway."*

### 2.5 Model client

**Decision:** one interface, one adapter per backend. The builder always calls the model the same way; each adapter translates to its backend's wire format. `ModelClient` is a Protocol, so a builder can supply an adapter for a backend we do not ship without forking the library.

**Amended 2026-07-26, at item 4: the interface is two methods, `complete` and `identity`, not one.** An adapter reports `ModelIdentity(backend, request_model, model_revision)` from its own configuration, without making a call. This was forced by the cassette: the replay key must include which model was called, and it must be computable *before* the call, so it cannot come from the response. The alternatives were to declare the identity on the envelope or on each request, and both duplicate what the adapter already knows and can therefore disagree with it. The rule below survives intact — the library itself reads `identity`, in the cassette key and in the manifest's `models.configured`, which is the pin FT-14 checks. It is not there for the builder's convenience.

**Amended 2026-08-04, at item 8e: streaming is an optional second Protocol, and `ModelClient` is unchanged.** `StreamingModelClient(ModelClient)` adds `stream(request, on_chunk) -> ModelResponse`, which returns the same assembled response `complete` does, so nothing downstream of the seam reads a different shape. "Two methods" was the count that fell out of the item 4 amendment rather than the principle it settled, which was that `identity` must be computable before a call; streaming does not touch that. **The rule below is what decides it:** presence of the method is the capability declaration, so a client that cannot stream is refused by name rather than emulated, and a wrapper that does not delegate it is caught before the run rather than during it. A required third method was rejected because it breaks every hand-written adapter and wrapper on the day it ships, including the one `docs/model-clients.md` §4 shows a builder writing. A keyword on `complete` and a field on `ModelRequest` were both rejected for failing the same rule: neither lets the library ask whether a client can stream, so an adapter that ignores it quietly does not stream and nothing says so.

**Amended 2026-08-05, at item 8f: reasoning output is normalised, and the streaming method gained an optional keyword rather than a fourth method.** `ModelResponse.reasoning` is a `Reasoning(text, blocks)` where the backend reports a chain of thought separately from the answer, and `None` where it does not. It qualifies under the rule below on the reader test: the record needs it to explain a token count, since reasoning is charged as output tokens whether or not a backend returns it, and a call reporting 745 output tokens for 492 characters of content was otherwise unaccounted for. **`blocks` is the exception in this section**, and it is deliberate: no shipped adapter fills it, and it exists because Anthropic's thinking block carries a signature that has to be returned verbatim and OpenAI's reasoning item carries an id and encrypted content, none of which a string can hold. Thilina granted it on the argument that the alternative is a second format bump and a second re-recording when either adapter lands. It is to be measured against those providers rather than left on their published types.

`stream` gained a keyword-only `on_reasoning`, passed only to a `stream` whose signature accepts it. **That is the item 8e rule applied one level down**: presence of the parameter is the capability declaration, so an adapter written with two parameters keeps working and is refused by name only when a run asks for a channel it cannot serve. A fourth method was rejected for the reason a third one was, and a required parameter for the reason a required third method was.

**And the seam does not split a chain of thought out of `content`.** A backend that leaves the two joined reports `reasoning: None`; the library warns where it can tell, and never rewrites `content`. Splitting on `<think>` would be emulation under the "never emulated" clause below, the markers are model-specific rather than standard, and a wrong split corrupts the string an output schema is validated against.

**Decision (2026-07-26):** two adapters in v0 — a hosted API and self-hosted open weights served by vLLM (`archive/plan-history.md`, item 5). Neither sits on a third-party multi-provider layer.

**Both adapters are built, and the common surface survived contact unchanged (2026-07-26, item 5).** Nothing had to be added to `ModelResponse` and nothing had to be emulated, which is the first real evidence for the rule below rather than an argument for it. `docs/model-clients.md` is authoritative on what each backend fills in. Three things are worth carrying here:

- **Translation is real work, and it covers the conversation as well as the declarations.** The seam's `tools` are the library's own shape; both backends want OpenAI function declarations, and both send tool-call arguments back as a JSON string that has to be parsed. **So is the conversation an `AgentNode` builds**, which records a tool call as `{id, name, arguments}` and is rejected with a 422 until the adapter nests it under `function` and serializes the arguments. That was found by running the loop against a real model for the first time, at item 5, and it means an adapter for a backend we do not ship has to translate history too or it will work for an `LLMNode` and fail for an `AgentNode`. The pieces measured identical across the two live in one shared module; everything that differs stayed in its adapter. Authentication, the seed parameter's name (`random_seed` against `seed`), the usage block's fields, whether caching is opt-in, and the shape of an error body all differ, and all three error shapes encountered came from just two backends.
- **The token split forks on the backend, and that reached the format.** Mistral reports a cached count and no cache-write class; vLLM reports both, behind a server flag, or neither without it. The trajectory format went to `0.4` to say what a record means when only the total is available. This is the third time the two-backend decision has surfaced something a single-backend interface would have encoded silently, after cost basis and revision pinning.
- **Every failure inside an adapter is caller-facing.** A model call that did not happen invalidates the run, so it is raised rather than returned to the model as data (§2.7). The one case that tests this rule is a model returning tool-call arguments that are not JSON: it looks model-facing, but the library has no channel for correcting it, and recording an empty argument set would describe a call the model did not make. It raises, and constrained decoding is the fix.

**This does normalise.** The honest question is how wide the common surface is:

- **Normalised** — the call signature; the five-field token breakdown; backend, requested model, revision, serving model; finish reason; concurrency; content and tool calls. These are uniform because the library itself reads them: `docs/trajectory-format.md` §4.1 requires them, FT-14 and FT-27 check them.
- **Passed through, not translated** — backend-specific request parameters (thinking config, guided decoding, sampling knobs one backend has and another lacks). Fixed settings go in the adapter's constructor; per-call knobs travel in an opaque `extra` that reaches the backend untouched.
- **Never emulated** — a backend that cannot do something raises a caller-facing error naming the backend and the feature. The library does not fake a missing capability.

**The rule that keeps this a seam rather than a layer**, as amended 2026-07-28 at the item 7 checkpoint: **the library normalises what it reads or what a caller needs by name, passes through what it does not, and emulates nothing.** A provider layer is what you get when the last clause lapses — the common type accretes fields, then needs faking on backends that lack them, and now you are maintaining LiteLLM. Emulation is the hazard; a field with no library reader is not.

*What it replaces, and why.* The rule read "every field in the common response type must be one the library itself reads". Both item 7 sessions had to pace a batch against a per-minute quota, both wrote a pacer, and both estimated the remaining allowance from an average of previous calls — while the backend published the exact figure in a header on every response and the library read it for `Retry-After` and discarded the rest. Session 2's per-question spend ranged from 4,700 to 122,000 tokens, so its average predicted almost nothing, and it named this its largest avoidable guess. The old rule would have kept the field out, because nothing in the library paces. **Discarding what the library has no use for gets in the way of a builder who does have a use for it**, and the next builder meets the same wall in a different field. So the response now carries named fields for the allowance and a general passthrough for whatever else the backend sent, redacted like every other recorded value.

*(Amended from "thin seam over an existing provider abstraction. Do not write a provider layer." That sentence welded together two claims. "Over an existing provider abstraction" meant sit on LiteLLM or similar, and is dead — we go direct to two backends. "Do not write a provider layer" survives, and is what the rule above states precisely.)*

**Requirement:** backend, model id, revision, and sampling parameters are recorded — in the manifest for what was configured, on the record for what varied (`docs/trajectory-format.md` §4.1).

**Why:** eval results are meaningless if you can't say which model produced them. Attribution of a regression to a model change is impossible without pinning.

### 2.6 Structured output

**Decision:** typed schemas with validation, and `unknown` as a **first-class return value**, not an error and not an empty string.

**Why:** an extraction agent that hallucinates a value is strictly worse than one that admits it doesn't know. This makes *false confidence* a measurable quantity (§4.2) rather than a silent failure. Generalizes far beyond the motivating case.

### 2.7 Error and retry policy

**Decision:** two explicitly different paths.

- **Model-facing errors** — a tool failed, here is why, try something else. Returned as data into the trajectory and the context.
- **Caller-facing errors** — infrastructure is broken, the run is invalid. Raised.

**Why:** getting this backwards is why hand-rolled agents either mask real failures (everything swallowed and fed to the model, which cheerfully invents around it) or die on transient ones. The distinction must be made by the tool author at authoring time, not guessed by the loop.

Also, important to note: Any errors the library throws should be useful for both humans and coding agents. The error messages should be clear, actionable, and provide enough context to understand what went wrong and how to fix it whenever possible.

### 2.8 Elicitation

**Decision:** the library supplies the questions that must be asked of the builder, the stage at which each becomes required, and a gate that refuses to advance while a required answer is missing. The coding agent does the asking. The answers land in **the brief**.

**Why:** this is the validity mechanism. Conformance tests enforce process compliance; they cannot enforce that the eval measures the right thing (§3.2). The only mechanism for validity is asking the human at the right moment. Specifying *which* moments is the library's job — the coding agent will not identify them reliably on its own.

**Decision:** elicitation is **staged, not a single upfront questionnaire**. The general shape of the project is settled early with as much detail as is feasible; differentiating decisions may be deferred to a later stage.

**Why:** hammering everything down at the start is impractical for anything beyond a trivial project, and a coding agent that tries will either stall or invent answers. But the reverse failure — discovering at eval time that nobody ever established what ground truth means — is worse. Staging is what makes both avoidable.

**Decision:** every brief entry is `answered`, `deferred` (naming the stage it is deferred to), or `unanswered`. Gates fail only on `unanswered`, and only for questions required at the current stage.

**Why:** deferral is legitimate, so it must be expressible. If it is expressed as a blank, a postponed decision is indistinguishable from a forgotten one, and the gate can only choose between blocking legitimate work and letting omissions through. Recording deferral explicitly makes the distinction machine-checkable.

**What this buys the conformance suite:** because the brief is an artifact rather than a conversation, the *occurrence* of elicitation is checkable — a gate can assert that a required question was answered, and that `unknown` was not accepted where a human answer was required. The *validity* of the answers remains uncheckable. That is the §3.2 line, drawn precisely.

*Amended 2026-08-10, at the brainstorm sitting.* **There are four stages, not three, and the first one is `brainstorm`.** The eighteen questions shipped at item 10 all presuppose that the project exists as a specification: `ground_truth` asks what the correct answer is for one input, which assumes the shape of an input is known. Nothing carried a builder from an idea to something those questions could be asked about, and the session that found this is the evidence — a coding agent designed a research-grade evaluation for what was a demonstration, and rested it on a column the builder's real data does not contain, because nothing had asked what the project was for or whether one real input had been read.

**The brief gains a companion artifact, `idea.md`**, which is the project's own account of what it is, who it is for, where it is going and what is still open. It is the first thing a later session reads, and the library previously gave a project nothing of the kind. The brief stays authoritative on answers and `idea.md` on the narrative, which is the split `CLAUDE.md` already uses between `docs/` and `dev-docs/`.

**Two properties of this section survive intact and one is extended.** Staging is unchanged, and so is the three-way `answered` / `deferred` / `unanswered` status. What is extended is the ceiling: a gate can now also assert that the account exists and that it was confirmed current at the stage the project is at, and it still cannot assert that any of it is true or that the coding agent recorded the builder faithfully rather than its own summary. `design/brainstorm-stage.md` is the design of record, and `docs/conformance.md` is where that limit is stated to a builder.

### 2.9 The interaction model

Three parties, two channels. See the glossary in `CLAUDE.md` for the fixed terms; they are not optional vocabulary.

| Channel | Who asks | Who answers | When | Recorded in |
|---|---|---|---|---|
| **Elicitation** | Coding agent | Builder | Build time, in the coding-agent conversation | The brief |
| **Consultation** | The agent | End user | Run time, via tool call (§8.1) | The trajectory |

**The builder decides; the coding agent executes.** Every decision about what the system is, what it should do, and what counts as success belongs to the builder. The coding agent implements and — this is the part it will not do unprompted — extracts the decisions the builder did not think to state.

**Decision:** the library never asks the builder anything directly. It supplies questions and gates; the coding agent always mediates.

**Why:** it keeps elicitation a documentation problem rather than a UI problem. A library that prompts on stdin would have to own a terminal, a notebook, and an IDE surface, and would still be bypassed by the coding agent. Supplying the questions and failing the gate works through whatever interface the builder is already in.

**Decision:** consultation is a designed interaction, not a fault path.

**Why:** the naming matters because it sets the coding agent's default. A word implying exception — escalation, fallback, error — produces agents that consult only when something breaks. Most consultation is planned: the builder anticipated that the agent would need a preference, a disambiguation, or an authorization it cannot derive. Treating that as failure produces agents that guess instead of ask, which is failure mode #7 in §7 wearing a different hat.

---

## 3. The conformance suite (the spine)

### 3.1 The inversion

**Decision:** the test suite runs against **the builder's project**, not against the library. It is a conformance/compliance harness, closer to a linter than to a normal test suite.

**Why this is the differentiator:** a skill is open-ended and depends entirely on how faithfully the coding agent follows prose. Prose instructions produce drift. A **failing test produces feedback the agent acts on without a human in the loop** — tests are the only instruction format that is self-enforcing. This is what makes it a library and not a markdown file, and it is why the executable core matters more than the documentation.

Second-order benefit: it keeps working after the coding agent leaves. It lives in the builder's CI and catches the regression six months later.

### 3.2 The ceiling — state it plainly

Conformance tests enforce **process compliance**, not **validity**.

Checkable: a held-out split exists (FT-02); k ≥ threshold (FT-05); the reported metric carries an interval, or a declared reason for having none (FT-06, amended 2026-08-28 at `P3-48`); no dev example appears in the eval set (FT-03); trajectories are logged (FT-13); budgets are set (FT-18); tools declare side effects (FT-19); a reward function was fuzzed for trivial hacks (FT-26).

**Not checkable:** whether the metric measures the thing the builder cares about.

`docs/failure-taxonomy.md` §10 carries the full list of what is deliberately not checkable and what handles each instead. That table, not this paragraph, is the authoritative statement of the ceiling.

Validity is handled by mandatory elicitation (§2.8). Do not let the conformance suite imply a guarantee it cannot make — the library's credibility depends on being honest about this line.

### 3.3 Graded, not binary

**Decision:** tiers — `prototype` / `evaluated` / `trained`. Each tier's gates apply only when the project claims that tier.

**Why:** a project that doesn't need RL should not fail an RL-hygiene check. Binary conformance either sets the bar so low it's useless or so high that early projects fail and builders disable it.

### 3.4 Failure messages are a prompt surface

**Decision:** every conformance failure message states **what is missing, why it matters, and the specific next action**. Not a diagnostic — an instruction.

**Why:** the failure string is what a coding agent reads at the exact moment it is deciding what to do next. This is the highest-leverage prompt surface in the library. `AssertionError: no held-out split` is a bug in the docs, not a terse message.

This is a **hard convention**, enforced by a meta-test over the message catalogue.

---

## 4. Evaluation

### 4.1 The split that matters

**The content of an eval is irreducibly task-specific and cannot be pre-defined.** It depends on what the builder's agent is supposed to do.

**The machinery is general** — and it is exactly where non-experts get it wrong.

So: the library ships **machinery plus staged elicitation that helps the builder define the content** (§2.8). Evaluation is a load-bearing feature, not the point of the library.

### 4.2 Machinery (general, ships in v0)

**Built 2026-07-29** as `simple_agents.evaluation`, shipped as `docs/evaluation.md`. `archive/plan-history.md` item 8 records the decisions; this list is what was asked for.

- Labeled example sets with **split tracking** (dev / held-out) and contamination checks.
- k-rollout execution with **seed control**.
- Bootstrap confidence intervals. Nothing cleverer in v0.
- **Per-node metrics**, not just end-to-end.
- **False confidence measured separately from recall** — the rate at which the agent asserts a value that is wrong is a different number from the rate at which it fails to find one, and conflating them hides the dangerous failure.
- Regression detection between agent versions.

**Two things the build settled that this list did not anticipate.** The resampling unit is the *example*, not the rollout: k rollouts of one question move together, so resampling k×n rollouts as independent narrows the interval by roughly √k with nothing in the number saying so. And per-node *accuracy* is not available from a general example set, which carries one answer for the pipeline; what ships per node is behaviour — calls, tokens, cost, terminations, how often that node reported absence — and `docs/evaluation.md` §5 says so where a builder will meet it. FT-08 asks for localisation of a regression, and those localise one.

### 4.3 Ablation machinery

**Decision:** ship `oracle → ablate` as a first-class operation.

The workflow: build the fully agentic version first as an oracle (strong model, loose prompt, all tools), log every trajectory, then read the traces to find which decisions it makes non-trivially versus which it makes identically every time. The invariant ones get frozen into `LLMNode`s or `Deterministic` nodes. The residue is where agency actually pays.

**Why:** it answers the central question ("where does agency earn its cost") with data instead of priors, it produces the first labeled trajectory set for free, and nothing else in the accessible ecosystem does it. This is the most defensible feature in the library.

*Amended 2026-08-06, at the item 8a sitting, with Thilina's approval. The two paragraphs above are what was believed before it and are kept as the record.* **Two of the claims above did not survive the sitting, and what shipped is wider than either.**

**The trace-reading half is demoted from a verdict to a description.** "Read the traces to find which decisions it makes non-trivially versus which it makes identically every time" infers that a node does not need agency from the fact that it behaved simply on n examples. Thilina's objection is that the inference is not available: a node that took one search on three questions may take four on the fourth, and a builder may have chosen an `AgentNode` anticipating exactly that. The asymmetry is what makes it worse than an ordinary eval-set limitation, since accuracy reports a number and leaves the judgement to the builder while this recommends removing capacity. What survives is the measurement: build the variant, run it, compare. It carries the same eval-set limit as every other number the library reports and adds no new one. The library therefore never says "freeze this node".

**Ablation is one direction of a general operation, and the general one is what ships.** Downgrade and upgrade are the same comparison with the arms swapped, and so are adding or removing a tool at a node, swapping a model at a node, rewording a prompt and rewiring the graph. **A variant is another `Pipeline`**, which is what makes an arbitrary graph work and what stops a per-node model swap needing an amendment when it lands. `ablate()` is a convenience over it. `build-logs/item8a-build-log.md` §2 carries the whole design; `docs/evaluation.md` §10 is what shipped.

**The measurement that decided the shape of the comparison.** The library's own two-node recording, replayed, scores 0.556; the same pipeline at the same seed re-run live scores 0.778, and `compare()` calls that difference moved. A variant arm recorded today against an older results file therefore reports the provider rather than the change, so both arms run in one session. **And on that same recording the node worth removing is the `LLMNode`, not the `AgentNode`**: deleting it takes accuracy to 1.000 at no cost at all, because nothing upstream of a removed terminal node changes and the recording answers every remaining request.

*Amended 2026-07-29, at item 8.* **This section commits to shipping ablation in v0 and `archive/plan-history.md` §3.1 never gave it an item**, which was a gap in that plan rather than a decision. It now has one, **item 8a**, **scheduled 2026-07-30 between items 9 and 10**. Item 8 built the half it needs: `compare()` takes two results files and reports whether each metric moved, on an interval over the paired per-example difference. What is left is constructing the ablated pipeline and reading which decisions the oracle made identically every time. FT-12 is unbuildable until it lands and is not in the v0 seven, so nothing else is blocked. **Scheduling it was forced by the document review**: `docs/failure-taxonomy.md` FT-12 describes ablation in the present tense, and a builder-facing document may do that only for something that ships.

### 4.4 Eval safety — the tool contract's real job

**Decision:** the eval runner reads each tool's declared side-effect class and **refuses to execute anything non-replayable during rollouts**, forcing it through the cassette instead.

**Why:** you will run k rollouts per example. If a tool sends an email or places an order, k rollouts is a catastrophe. RL training libraries state "your agent must be runnable many times without affecting the real world" as a *precondition the user must satisfy*. Making it a property the type system enforces is exactly the thing a library can do and a skill cannot — and it is what ties the tool contract to the eval machinery.

**Built 2026-07-29, at item 8, and it is do-not-change #5 becoming true rather than aspirational.** Two clauses of the decision above were sharpened by building it. **It refuses to start rather than refusing to execute**: the check runs before the first rollout, so a k×n evaluation over an unsafe tool fails in a second instead of part-way through. And "non-replayable" resolved to *reaches outside the run*, which item 7 had already established: `read_only` and a `writes` confined to the run's own workspace repeat harmlessly, and `spends_money` and `irreversible` do not. The refusal covers the tools the pipeline can reach rather than every tool in a registry, since refusing a project for a tool this evaluation never touches is the over-refusal that gets suites disabled. `archive/plan-history.md` item 8 has the rest.

*Amended 2026-08-10, at the paid-evaluation item, with Thilina's approval.* **A `spends_money` tool may run in rollouts under a declared ceiling. `irreversible` may not, and has no ceiling and no override.**

**The rationale above is not defeated. It was satisfied.** What it protects is that no rollout performs an action nobody agreed to, and the catastrophe it names is an email and an order. Money is the class where a builder can say in advance how much, and `EvalSuite.run(max_spend=...)` is where they say it. Refusing it instead decides for them how their own money is spent.

**The ceiling is checked before the first rollout and never binds during one.** A rollout is bounded by the pipeline's `max_cost`, which depletes on what a tool meters and reaches inside a delegate, so `k × n × max_cost` bounds the evaluation. A declared `max_spend` below that figure is refused with both figures named. The `DeclaredCost.ceiling × k × n` arithmetic that suggests itself is not a bound: one rollout can call a paid tool any number of times, and 24 was measured against an arithmetic predicting one.

**What the ceiling does not cover**, and both are stated wherever it is documented: a rollout can exceed `max_cost` by one model call, whose cost is known only after it returns; and a tool that meters above its own `DeclaredCost` exceeds it by that call's excess, since a tool holding a meter is authoritative. `build-logs/paid-eval-build-log.md` is the record.

**The same item shipped the loop the refusal had been instructing without shipping.** `EvalSuite.record` runs the live runs an evaluation's rollouts will replay, at the seeds the runner derives, so the recording a replay needs is produced by the library rather than reconstructed from it. Before it, the documented instruction was unfollowable past the first example and the loop a builder wrote from it produced a completed evaluation reporting accuracy 0.0 over rollouts that had all failed.

---

## 5. The improvement ladder (v1+, specified now so v0 doesn't foreclose it)

Escalating, cheapest first. **RL is the last rung, not the product.**

1. **Prompt and config search** — no training.
2. **Rejection fine-tuning** — SFT on the project's own successful traces. Needs no reward engineering beyond a pass/fail check, runs on one GPU with LoRA, and is embarrassingly effective. The concrete budget-driven use case ("distill your expensive frontier-model agent into a cheap local one") lives here.
3. **RL** — GRPO with an automatic judge-based reward (RULER-style) as the default, so builders never hand-write reward functions unless they want to.

**Backend decision:** target the **Tinker API** as the training interface. SkyRL implements it, so a single script runs both hosted and on local GPUs. Adopt **OpenEnv**-compatible environments rather than inventing an environment spec.

**Why (and why this differs from §2.3):** here the engineering is enormous, standards are actively consolidating, and being a front-end is the right call. Riding a consolidating standard early is also how Simple Transformers benefited from HF's ecosystem instead of competing with it.

**v0 constraint:** none of this is built in v0. The only requirement v0 must satisfy is that the trajectory format (§6) is rich enough to serve as SFT/RL training data later.

**Checked at design time (2026-07-26), with the limits stated.** The format records full inputs and outputs on every record rather than making content optional, carries seeds wherever sampling occurs, and preserves an `AgentNode`'s inner loop as child records rather than collapsing it — which is what makes a trajectory replayable as a training example at all. What has *not* been verified is whether the encoding is convenient for a specific trainer's data loader, and that cannot be verified until something actually trains on it. Treat this as a design-time argument, not an empirical result.

---

## 6. Trajectory format

**Decision:** JSONL. Stable field names. Boring on purpose. **Written in full as `docs/trajectory-format.md`** — that document is the schema of record; this section is the summary.

**Decision:** six record types — `node_execution`, `model_call`, `tool_call`, `consultation`, `delegation`, `resource_access` — linked by parent id. A `Deterministic` or `LLMNode` node still resolves to one record plus at most one call; an `AgentNode` emits its inner loop as child records.

> **Record types are not node kinds.** There are still exactly **three node kinds** (§2.2, do-not-change #8) and **six record types**. They are not parallel lists: every node execution emits one `node_execution` record whichever kind it was, and `node_kind` is a *field* on that record. The other five record types are things a node *does* — call a model, call a tool, consult the end user, hand a subtask to a pipeline, reach a resource in its own code. Do not infer a fourth node kind from this section.
>
> **`delegation` is the entry most likely to be misread that way, and it is not a node kind either.** It records one subtask an `AgentNode`'s model sent to a pipeline declared on that node. The pipeline it names emits no record of its own, exactly as a pipeline used as a node does not; what emits records are the three kinds inside it.

*Amended 2026-08-10, at the pipeline-as-a-tool item.* The count was four through `0.18` and is five from `0.19`. **`delegation` is a fifth type rather than a `tool_call` because of one field.** A `tool_call` record carries a `side_effect_class`, which `docs/tools.md` §1.4 defines as declared by the author and never inferred, and which is what the eval runner reads to decide whether a rollout may execute the thing. A pipeline declares no such class: its effects are its tools', each separately declared and separately recorded. Writing `null` there, or deriving a class from the tools inside, would put a value the whole FT-19 spine treats as a declaration into a record where nobody declared one. The alternative was materially cheaper and was rejected on that single point; `build-logs/pipeline-as-tool-build-log.md` §2.2 has the full cost of the bump.

*Amended 2026-07-30, at the document review.* The record type was called `node` through `0.7` and is `node_execution` from `0.8`. Every other type names the event it records, and this one records an execution rather than the node. The reasoning, the rejected alternative and what the rename cost are in `design/trajectory-format-changelog.md`.

**Why not one record per node execution, as this section originally said:** an `AgentNode` is a loop of many model and tool calls, and those inner steps are exactly what ablation reads (§4.3). Collapsing them into a single record destroys the most defensible feature in the library. The one-record case survives unchanged for the node kinds where it was ever sufficient.

Every record carries at minimum: format version, record type, run id, record id, parent id, sequence index, inputs, outputs, timestamps, error (if any), and redactions. Type-specific fields add node kind and budget; backend, requested and serving model, model revision, params, token breakdown and serving concurrency; tool name and declared side-effect class; consultation prompt and resolution. Seeds are recorded wherever sampling occurs.

**Decision:** **cost is never stored** — it is derived from the record against the cost basis declared in the manifest. There are two bases, because there are two backends (§3.1 of `plan.md`): `price` for hosted APIs, `compute` for self-hosted serving.

**Why:** under `price`, cached prompt tokens bill at a fraction of uncached ones and cache writes at a premium, so a single stored figure misprices any cached workload. Under `compute`, wall-clock times a device rate charges every concurrent request for the whole device, overstating cost by the batch factor. Both bases also drift — prices are revised, hardware rates renegotiated — so a stored figure goes stale silently either way. The record's inputs are ground truth; cost is a computation over them (FT-27, and `docs/run-envelope.md` §4 for the formulas).

Three further reasons the shipped document carried until the 2026-07-30 review, kept here because they are the argument rather than the rule: a stored figure cannot be re-derived, since whatever multiplier produced it is not in the record, so the number can only be believed; the basis changes, so a figure stored six months ago and re-read today is wrong with nothing in the record saying so; and a stored figure and a derived figure will eventually disagree, with no way for a reader to adjudicate. *Where the formulas now live:* `docs/run-envelope.md` §4 owns the two bases, the arithmetic, and the five situations where a figure cannot be produced. `docs/trajectory-format.md` states only that no record carries a cost field, because cost is not a field. Before the review both documents stated the compute formula, which is two shipped documents that could drift apart about money.

**Why this is written second (right after the failure taxonomy):** everything downstream reads it — eval, ablation, conformance, and later SFT/RL. It is the most expensive thing in the library to change once projects exist. *That sentence was in the shipped document's opening and was cut on 2026-07-30: it is about our ordering, not about the format.*

**Resolved (was open question 2):** the native format is the source of truth. Where a field's semantics match an OpenTelemetry GenAI attribute exactly, we adopt that definition and record the mapping; where they do not, we use our own field and say so. An OTel exporter ships as an adapter after v0, not as the format.

**The four reasons not to align outright**, in order of weight. These were §1.3 of the shipped document until 2026-07-30, when they moved here: they argue against a design nobody proposed, and they were the largest concentration of maintainer voice in `docs/` (five of the six uses of "we" in the whole shipped tree were in this passage and its table).

1. **Telemetry versus record.** OTel is a span format built for dashboards, with sampling as a first-class concept. Ours is a complete record that doubles as training data. A sampled trajectory is worthless for SFT and fails FT-13 outright.
2. **No slot for what our checks read.** Node kind as a type-level distinction, declared side-effect class, seed, and split membership have no OTel equivalents. FT-07, FT-19 and FT-20 all read fields the conventions cannot express.
3. **Opposed content defaults.** OTel's message-content attributes are opt-in and discouraged for privacy reasons. Here, inputs and outputs are required on every record, which is what makes the trajectory training data.
4. **Maturity.** As of July 2026 the GenAI conventions are still in development with no stated stabilization timeline, and were recently split out of the main semantic-conventions repository into their own, which carries a heavy open issue and pull-request load. Freezing our most expensive artifact onto a spec in that state leaves neither stability nor interop.

**Why borrow names anyway:** it costs one naming decision and makes the exporter mechanical. Interoperability with existing tooling is worth keeping cheap, and forfeiting it entirely would be a real loss.

**What the shipped document keeps**, as `docs/trajectory-format.md` §7: that keys are flat `snake_case`, the four fields whose semantics match exactly, and the one that must never be mapped, `tokens.input_uncached` against `gen_ai.usage.input_tokens`, because an export that maps one onto the other silently undercounts every cached call. Thilina's replacement wording, "the library makes an effort to follow OTel's conventions, but cannot guarantee it", was argued down: it hedges where the actual rule is stricter and more useful, which is that a name is borrowed only on exact semantic match.

---

## 7. Failure taxonomy — seed list (historical)

**`docs/failure-taxonomy.md` is written and is authoritative.** It expands these 16 into 29 entries, each with a detection surface, tier, check, and drafted failure message, plus an explicit list of what cannot be checked at all.

This list is kept as the historical seed so drift between it and the expansion stays visible. The mapping lives here rather than in the taxonomy, which ships to builders and has no use for it. Do not add to this list; add to the taxonomy document.

**Seed → taxonomy entry.** All 16 seeds produced at least one entry, so nothing from this list was dropped in expansion.

| Seed | Expanded to | Seed | Expanded to |
|---|---|---|---|
| §7.1 | FT-01 | §7.9 | FT-18 |
| §7.2 | FT-02, FT-03 | §7.10 | FT-14 |
| §7.3 | FT-05 | §7.11 | FT-26 |
| §7.4 | FT-06 | §7.12 | FT-19, FT-20 |
| §7.5 | FT-11 | §7.13 | FT-22 |
| §7.6 | FT-04 | §7.14 | FT-15 |
| §7.7 | FT-09, FT-10 | §7.15 | FT-24 |
| §7.8 | FT-13 | §7.16 | FT-25 |

Four seeds each carried two distinct failures needing different fixes, which is why 16 became 19 seeded entries. The remaining nine were added during expansion and have no seed: **FT-07** (seeds uncontrolled), **FT-08** (end-to-end metrics only), **FT-12** (agency never ablated), **FT-16** (secrets in trajectories), **FT-17** (context silently truncated), **FT-21** (eval cannot run offline), **FT-23** (tool docstring written for a human), **FT-27** (cost recorded as a bare figure), **FT-28** (what a node accepts is undeclared, added at item 8g).

*(Amended 2026-07-26. The taxonomy previously carried a `Seed` field on every entry; it was removed because it cites section numbers in this document, which builders cannot resolve.)*

The characteristic failures of coding agents building agents. **Each entry must map to a conformance check, or be explicitly marked as one that cannot be checked.**

1. No eval at all — success declared from a demo run.
2. Eval examples reused from development (contamination).
3. Success declared on n=3, no repetition, no interval.
4. Point estimates reported with no variance.
5. Everything made agentic because it reads better in a plan.
6. Happy path only — no handling of the "data is absent" case.
7. Hallucinated values where `unknown` was correct.
8. No trajectory logging, so nothing is debuggable after the fact.
9. No budget or termination condition.
10. Model version unpinned, so regressions can't be attributed.
11. Reward function trivially gameable (when the project reaches the `trained` tier).
12. Tools that mutate the world executed inside eval rollouts.
13. Errors swallowed and fed to the model, masking infrastructure failure.
14. Prompts unversioned, so a regression can't be traced to a prompt edit.
15. Elicitation skipped — the coding agent decided alone what the builder should have decided.
16. Consultation treated as a fault path, so the agent guesses where it was designed to ask.

---

## 8. Tools

### 8.1 Minimal built-in set (v0)

**Built 2026-07-27, at item 7.** `docs/tools.md` §5 is authoritative on detail. Every row shipped, and the table below records what each became and what the row's original wording got wrong.

| Tool | Shipped as | Note |
|---|---|---|
| Document search | `document_search` over a `DocumentIndex` | BM25 in pure Python, so no dependency. The project supplies the documents; no dataset ships (§3.4 of `plan.md`). *Amended 2026-08-11: an index given an embedding client also searches by meaning. The core keeps its two dependencies — a local model is the optional `semantic` extra and an endpoint needs none — and the ranking, the fusion, the reranker and the vector store are all the builder's to set.* |
| Web search | `web_search(provider=...)` | The provider is a function the project writes. The library picks no vendor and holds no key, because a search API is a vendor choice with a price attached. The only shipped `spends_money` tool, so it is what exercises `declared_cost` and FT-20. |
| HTTP fetch | `http_fetch`, and `read_page` over it | robots.txt via stdlib, an optional host allow-list, an optional interval between fetches, `SecretStr` headers. **"With caching" was answered by the cassette rather than by a second cache**: a recorded run replays every page it read with no network, which is the caching an evaluation needs. *Amended 2026-08-09 at absorption item 7: that is right for replaying one run and wrong for the next one, which re-fetches what the last run read, so `UrlCache` ships in front of the network. Item 5 added `read_page`, which reduces a page to text, and item 6 `HostPolicy`, a reachable set that grows during a run.* |
| Extract-to-schema | `extract_to_schema(schema)` | **The row was nearly cut and should not have been.** Most extraction is `LLMNode(output_schema=...)`, or `over=` for many documents, and the first draft of this amendment proposed answering the row that way. That is right at build time and wrong at run time: an agent deciding mid-run that it needs typed facts cannot add a node. The tool exists, and §8.2 records what had to change to let a tool call a model at all. |
| Finish / answer | `FinishTool`, supplied by the library | Built at item 3. Item 7 added `AgentNode(finish_check=...)`, which is the half of session B's S5 that replay soundness permits (`runs/checkpoint-item5/findings.md` §6). |
| Consult | `consult(ask=...)` | The channel is a function the project supplies; the library owns no terminal (§2.9). The first thing to write a `consultation` record, which the format has carried since Phase 0 with nothing emitting it. |
| Workspace read/write | `workspace_read`, `workspace_write`, `workspace_list` | Scoped to the run directory, which is what forced the `Workspace` handle: a `Tool` is built before the run exists, so the path cannot be closed over. |
| Now / clock | `now` | Trivial to write and the sharpest case in the whole item. A clock is the tool that broke the old cassette key, and fixing it is what §8.2's replay clause came from. |

**Deferred to v0.5:** sandboxed code execution. Highest-power tool, real security surface, expensive to get wrong early.

### 8.2 The tool contract

Every tool ships with:

1. **Typed signature.** *Implemented 2026-07-26, at item 5.* The annotations produce the JSON schema the model is shown, so the declaration cannot drift from the implementation. Before that the schema defaulted to empty, which told the model the tool took no arguments and made an `AgentNode` unusable with any tool that took one.
2. **A docstring written for the model**, not for a human reader.
3. **A contract test** proving the tool does what the docstring claims.
4. **Declared cost and latency.** *Typed at item 7 as `DeclaredCost`, and required only on a `spends_money` tool.* Refusing every tool without one would block `now`, whose cost is zero and whose declaration says nothing, which is the over-refusal that gets suites disabled. On the class that spends, the figure is the point: k×n rollouts multiply it.
5. **Failures returned as data**, not raised (§2.7).
6. **Declared side-effect class**: `read_only` / `writes` / `spends_money` / `irreversible`.

Item 6 is what makes evaluation possible at all (§4.4).

**Amended 2026-07-27, at item 7: the ban on tools reading run state is replaced by the constraint it was standing in for, and the clause count stays at six.** `runs/checkpoint-item5/findings.md` §6 recorded the rule as "tools cannot see run state", on the grounds that a tool keyed by its arguments can return two answers under one key and replay serves whichever was recorded first. The rule is broader than its reason, and stating it as a ban blocked two things a builder legitimately wants: extraction decided mid-run, and a tool that writes into the run's own directory. The real constraint is that **the cassette key must identify the answer**, and there are two ways to satisfy it. Both are mechanisms rather than declarations, which was the deciding consideration: a mode a coding agent has to classify into is a mode it will sometimes classify wrongly.

- **A tool call's key gained an occurrence count** — how many times that same name, version and argument set has already been called in this run. Any intra-run impurity then replays correctly, because within a run any two calls are ordered and the ordinal captures whatever changed between them. This is not the ordinal *fallback* rejected at item 4 (`archive/plan-history.md` item 4): it is content hash **plus** ordinal, strictly more specific, so a changed argument still misses and still misses loudly. It also makes tool calls consistent with model calls, whose seed already derives from the call index and is in the key.
- **A tool whose signature asks for a `ModelHandle` or a `Workspace` is not keyed at all**, and its body runs again during a replay. The library reads this off the signature, the same way it already reads the JSON schema off the annotations, so nothing is declared and nothing is judged. The rule such a tool must satisfy is that **it may reach the outside world only through the handles it was given**, and declaring `spends_money` or `irreversible` alongside a handle is refused.

**Why no key expansion reaches the model-calling case, which is the part worth keeping.** A filed tool is not run on replay, because its answer is served. For a tool that calls a model, not running it means the nested `model_call` record is never written, so a replay writes fewer records than the live run it is reproducing and per-node token accounting disagrees between the two. That is a fault in record *shape*, not in key selection, so no lookup scheme fixes it: every lookup scheme ends in "found it, do not run the function".

**The generalised rule, which now has three instances rather than two:** anything replayed through the cassette must be a function of what its key covers; anything not replayed through the cassette may read the run, provided everything it does externally is itself replayed. A context builder is on the second side because its product *is* the keyed material (§2.4). A filed tool is on the first. A handle-taking tool is on the second, and is the instance that made the rule worth stating as a rule.

### 8.3 Third-party tool plug-in path

A registry with the same contract requirements. No exceptions for community tools: a tool without a declared side-effect class cannot be registered, because the eval runner cannot reason about it.

**Built 2026-07-27, at item 7, as an explicit `ToolRegistry` the project constructs.** No global default and no auto-registration from the decorator, for the reason item 4 split the envelope by lifetime: a global mutable is a second source for one value, it makes test order significant, and two projects in one process would share a namespace. The alternative of having no registry object at all was live, since `Tool.__post_init__` already refuses a missing side-effect class and `Pipeline` already writes every tool to the manifest. It was rejected because item 8's eval runner needs somewhere to enumerate *every declared tool*, including one no node uses yet, and a list held on a node is not that.

**Amended 2026-08-07, at item 13.** That reason named the FT-19 and FT-23 static checks as consumers and neither exists: FT-19 is enforced at registration instead, and FT-23's check was measured unbuildable and the entry narrowed (`build-logs/item13-build-log.md` §1.7, §1.8, §2.2). The capability was also unrealised in any artifact, which the same item measured: a project holding a registry produced a manifest byte-identical to one holding a plain list, because `Pipeline` walked `node.tools` and `ToolRegistry.to_manifest` had no caller (§1.5). **`Pipeline(nodes, budget=..., tools=registry)` now writes the whole declared set to the manifest**, each entry carrying `offered`. The registry's reason for existing is that manifest row and the `tool_effects` elicitation question that reads it, rather than two checks that were never built.

### 8.4 Tool-authoring guide

Write this **immediately after** the failure taxonomy and trajectory format. It is the surface a coding agent hits most often, and a bad convention here propagates into every downstream project.

---

## 9. DO NOT CHANGE

These are settled. Changing any of them means the project is no longer the thing that was designed. If one genuinely needs to change, the rationale in this document must be defeated explicitly and in writing, not worked around.

1. **The nutshell.** The library holds the coding agent's hand so the coding agent can hold the builder's hand. Every feature is justified against this or it doesn't ship.
2. **Conformance tests run against the builder's project**, not the library. This is the spine. Without it this is a skill, not a library.
3. **Budget and termination are non-optional.** Refuse to run, never warn.
4. **Tools declare a side-effect class.** No registration without it. No exceptions for built-ins or community tools.
5. **The eval runner refuses non-replayable tools in rollouts.** `irreversible` outright, with no ceiling and no override. `spends_money` unless the evaluation declares a spend ceiling the pipeline's budget can be shown to hold to. *(Amended 2026-08-10 at the paid-evaluation item; §4.4 carries the argument. The clause that moved is "refuses" becoming "refuses unless the builder has said how much", for the one class where a builder can say it in advance.)*
6. **`unknown` is a first-class return value.** Never coerced to an error, empty string, or guess.
7. **The record formats are versioned, and every record declares its version.** Breaking changes are permitted while the format is pre-adoption; each bumps the version and is recorded in the changelog. Once real projects depend on it, changes are additive by default and a breaking change requires the same explicit written argument as any other settled decision. *(Amended from "additive changes only after freeze" — declaring that before a line of code exists would freeze the decisions made with the least information anyone will ever have, and the first dogfood is designed to prove some of them wrong. The durable property is that a record is self-describing and a breaking change is visible and deliberate, not silent.)*

    *Amended 2026-08-20, at `P3-31`, and the trigger narrows from a date to what a break costs. The library writes five versioned formats and a break costs an adopter three different things, measured that day. A **trajectory** (`0.26`) or **manifest** (`0.31`) written by an older version is read, and the figure that cannot be derived from it degrades with a stated reason ([`per_node.py:684`](../src/simple_agents/evaluation/per_node.py#L684), `attributable`; [`spend.py:281`](../src/simple_agents/conformance/spend.py#L281), `_carries_counts`). A **results file** (`0.23`) is refused and the message says to re-run the evaluation ([`results.py:490`](../src/simple_agents/evaluation/results.py#L490), `EvalResults.read`), which costs k rollouts of real spend. A **suspension file** (`0.5`) is refused ([`suspension.py:108`](../src/simple_agents/records/suspension.py#L108), `SuspensionState.from_json`), and a run that stopped mid-flight cannot be resumed, so the work is gone. A **variant comparison** (`0.2`) is written and never read back.*

    *So from `0.1.0`: **the results file and the suspension file are additive by default**, on the same terms as the sentence above, because a break in either destroys work an adopter cannot cheaply recreate. **The trajectory and the manifest stay pre-adoption through 0.x**, because they degrade rather than refuse and four more dogfoods are meant to find what is wrong with them; their clock starts at `1.0.0`.*

    *What this leaves open: a suspension version mismatch is the worst outcome the library can produce for anyone holding a file, and the refusal is what makes it worst. If that format has to move, it gains a read-old path rather than a bump.*
8. **The three node kinds** (`Deterministic` / `LLMNode` / `AgentNode`) and the explicit agency boundary.

    *Amended 2026-08-18, at `P3-12` stage 2, and the boundary is narrowed rather than moved. What it protects is that the builder's code cannot reach a model except where the node kind says so: a `Deterministic` node's function is handed no client, its `ctx` exposes none, and a tool it calls may take no `ModelHandle`. All three still hold, and `tests/test_agency_boundary.py` still asserts them. What changed is that one library-owned call can be recorded under that node kind: the reader a consultation registers with `consult(read=...)`, which turns what an end user said into the option they meant. It is recorded on the consultation, charged to the run, and served from the cassette on replay.*

    *The argument is that the agency was already there and was being exercised badly. `on_reply` routes on `chose`, and `chose` was decided by whole-answer equality, which read an option out of 0 of 24 measured prose answers, so every one routed to `unmatched`. The choice was never "add a model to this node or not"; it was "route on a rule that cannot read the answer, or on one that can". FT-11 is untouched, since nothing here is the model choosing what to do, and FT-07 is untouched, since a `deterministic` node record still carries `seed: null` and the reading's `model_call` carries its own. The build is [`build-logs/consultation-reading-build-log.md`](build-logs/consultation-reading-build-log.md#L1).*
9. **Failure messages are instructions**, not diagnostics. Enforced by meta-test.
10. **Conformance is graded, not binary.**
11. **No training, RL, or backend integration in v0.** Specified in §5, built later.
12. **No DSL.** The graph is declared in Python on the node, as `successors=`, `route=`, `loop=`, `on_error=` and `retry=`. What is ruled out is a second syntax for the same thing: a YAML or JSON pipeline file, or a fluent builder such as `pipeline.node("hunt").then("verify")`. Declaring it in Python means a coding agent writes the graph with knowledge it already has, a type checker and an IDE see it, and there is nothing to document twice. A configuration format would change who the library is for, which is what makes this an entry here rather than a preference.

    *Amended 2026-08-03, at the branching sitting, with the argument in §2.2: a pipeline is a directed graph with declared edges, built in v0 as `build-logs/item8c-build-log.md`, and the DSL half of the rule is what that amendment was careful to keep. Do-not-change #8, the three node kinds, is untouched, because routing is a property of a node rather than a fourth kind.*

    *Amended 2026-08-04, at the item 8d sitting. The entry read "No DSL and no scheduler in v0", and the scheduler half is gone. Two things were tangled in it. "Nothing is concurrent or queued" contradicted `plan.md` §2.2, which commits to concurrency in principle, and a v0 scope decision belongs in `archive/plan-history.md` rather than in the list of things that define the project. And "scheduler" was the wrong word for what was meant: `_walk` has decided which node runs when since item 8c, so a first attempt at repairing the phrasing asserted the opposite and would have shipped false. What the clause was actually protecting is that the library owns no execution outside a call the caller made. That is real, was never stated here, and has moved to §2.1 beside the containment decision it completes. **§2.1 narrowed that wording on 2026-08-27 at `P3-38`**, to nothing running that the builder did not ask for, so a resource the builder constructs may hold a thread or a process; read §2.1 for what stands.*

    *Amended 2026-08-13, at the concurrency item, and only to record that the amendment above held. Work in a run overlaps where the pipeline and its nodes declare it may (`archive/plan-history.md` §1.12). Nothing about that runs outside a call the caller made: the threads exist for the duration of `Pipeline.run` and are joined before it returns, so §2.1's decision is untouched. The DSL half is untouched too, since every declaration is a keyword argument on the object it governs.*
13. **The dogfood order: trivial task first, shopping agent second.** (`runs/dogfood-protocol.md`. This is a methodological requirement, not a preference.)
14. **v0 ships when the ship criterion is met** (`archive/plan-history.md` §3.3) — not when it feels complete.
15. **Honesty about the conformance ceiling** (§3.2). Never let the suite imply it validates correctness of the metric.
16. **Elicitation and consultation are distinct** (§2.8, §2.9) — different actors, different channels, different records. The builder decides and the coding agent executes; the library never asks the builder directly; consultation is a designed interaction, not a fault path.

---

## 10. Constraints and requirements

- **Python.** Floor is **3.11** (decided 2026-07-26). `tomllib` is in the standard library from 3.11, and the brief is TOML/YAML that every gate has to read — a 3.10 floor would put a TOML dependency in the core for the sake of a version reaching EOL in October 2026.
- **Dependency minimalism.** Every dependency is a maintenance liability in a stack that churns monthly. The thin-front-end architecture exists so upstream churn is absorbed by adapters, not the core.
- **Runs offline.** After the cassette layer, the whole conformance suite must run in CI with no network and no spend. This is a hard requirement, not an optimization.
- **Deterministic replay.** A recorded run replays identically.
- **Scoring makes no model calls.** *Added 2026-08-18, at the P3-12 sitting.* Where a number depends on a model's judgement, the judgement is made by a run and written to a file, and the scoring code reads that file. Scoring runs again on every `rescore` and in CI, so a model call inside it would need credentials on a machine that has none, spend money every time a number is recomputed, and give a slightly different answer on each pass.

  *Why this is an addition and not an amendment.* P3-12 was scheduled expecting to defeat the offline requirement above, and measuring it showed there was nothing to defeat: that requirement names the conformance suite, and the conformance suite reads artifacts. `docs/conformance.md` §1 states it executes nothing, and nothing in `conformance/` imports `EvalSuite`, calls `matches` or reaches a model. What the offline requirement protects is FT-21, an evaluation that needs live network and live spend and so stops being run, and `docs/evaluation.md` §6.4's promise that `rescore` calls no model. A judge that records its judgements meets both, so the rule that lets the judge exist is stricter than the one it was expected to move. `items/a-recorded-judgement.md` carries what a judge callable from inside scoring would have cost.
- **No secrets in trajectories.** Redaction is part of the record path, not a post-processing step. *Amended 2026-07-26, at item 5:* the record path has two mechanisms, not one. Detection matches known credential formats, sensitive field names, and values declared in `secret_env`; declaration by type covers a value that no pattern recognizes, via `pydantic.SecretStr`. Both are needed, since the type only protects what the builder marked and a credential arriving as a plain string inside a response is not marked. The reasoning, and the two limits that must be stated wherever the type is documented, are in `archive/plan-history.md` item 7.

  *Amended 2026-07-28, at the item 7 checkpoint:* **the scan covers every field on a record except a named set that the library generates itself** — format version, record type, the ids, `sequence`, the timestamps, and the `redactions` array. It used to be the reverse: the redactor walked a list of six field names and wrote every other field out exactly as it arrived.

  That list lives in `redaction.py` and record fields are added in `trajectory.py`, so the two were never edited together. The guarantee that redaction happens by construction was therefore true only for fields somebody had remembered to enumerate, which is not what "by construction" means. Adding `provider` at this checkpoint wrote a `set-cookie` header into a trajectory with nothing raised and no test failing, and it was found only because a test happened to assert that exact thing. Inverting the list also brought `error` into the scan, so a credential inside an exception message no longer reaches disk in the record most likely to be pasted into a bug report.

  **The general form, worth applying beyond redaction: a mechanism that protects something must fail closed, so the thing enumerated is what gets skipped, not what gets covered.** Adding a field is routine; remembering a list in another module is not.
- **Docs are a prompt surface.** Ambiguity is a bug and gets filed as one.
- **Dual-audience documentation.** Every concept doc must serve both the human and the coding agent. Where the two conflict, the coding agent's needs win, because the human reads via the agent.

---

## 11. Open questions and assumptions

### Open questions

| # | Question | How it gets resolved |
|---|---|---|
| 1 | Does the encoded procedure differ from generic SDD enough to justify existing? | Dogfood runs. Compare against a Spec Kit-style baseline on the same task. |
| 2 | ~~Align the trajectory format with OpenTelemetry GenAI conventions, or stay standalone?~~ | **Resolved 2026-07-26.** Own the record shape; borrow attribute definitions only on exact semantic match; ship an exporter later. The four reasons are in §6 above, moved there from the shipped document on 2026-07-30; what ships is `docs/trajectory-format.md` §7. |
| 3 | Are `prototype` / `evaluated` / `trained` the right conformance tiers? | First two dogfood runs will show which gates fire spuriously. |
| 4 | ~~How are cassettes keyed, given non-deterministic model output?~~ | **Resolved 2026-07-26, at item 4.** A strict content hash over model identity, messages, sampling parameters, tools and seed. Prompt drift resolves as a *miss*, reported with the fields that differ, rather than as a fallback: replaying a response recorded against an edited prompt would report a number the current code never produced, offline and green. `docs/run-envelope.md` §3. |
| 5 | Does the procedure transfer across coding-agent models and generations? | Meta-eval across models (`items/meta-eval.md`). |
| 6 | Does agency pay off in the shopping agent's missing-measurement hunt? | Empirical, per-task. This is exactly what the ablation machinery is for. |
| 7 | ~~Naming, license, packaging, and skill-distribution mechanics.~~ | **Partially resolved 2026-07-26.** Distribution `simple-agents` (PyPI, verified available), import `simple_agents`, one CLI `simple-agents`, Python ≥ 3.11, Apache-2.0. **The documentation ships inside the wheel** (item 5): the library cites `docs/*.md` from its docstrings, so an install without them hands the reader references it cannot resolve, and `docs_path()` returns the installed directory. **Fully resolved 2026-08-06, at item 10.** The skill ships inside the wheel at `simple_agents/.agents/skills/simple-agents/SKILL.md`, force-included from `docs/procedure.md` so the shipped document and the skill are one file. **Three things were measured rather than assumed.** A wheel cannot run anything at install time: the installer unzips, and only the dead egg format had post-install scripts. No harness scans `site-packages`, which is why [Library Skills](https://library-skills.io/) exists at all, and its own documentation states that Claude Code does not read `.agents/`. And the convention is real rather than proposed: FastAPI and Typer both ship a skill at that path, and both are installed on this machine. So `simple-agents init` is the answer, run by the builder immediately after installing, linking the skill into `.agents/skills/` or `.claude/skills/` and naming it in `AGENTS.md`. The original answer — *decide before public release, not before v0* — was overtaken: these land in the first commit, so deferring them meant deciding them by accident. |
| 8 | Is the in-house loop (§2.3) the right call, or does it become a maintenance sink? | Revisit after the second dogfood. |

### Assumptions being made

- **Coding agents are the primary user.** If humans end up being the primary user, the documentation strategy is wrong and much of the design follows from a false premise.
- **Process compliance is most of the value.** Assumes the gap between "coding agent output" and "correct agent project" is mostly skipped process, not missing capability. Plausible, unverified.
- **Small specialized agents remain economically motivated.** If frontier models get cheap and good faster than task-specific training pays off, the improvement ladder (§5) loses its motivation and the library reduces to the eval and conformance core. That core is independently valuable, so this is a survivable outcome, not a fatal one — but it should be watched.
- **The trust audience is large enough to sustain a library.** Smaller than Simple Transformers' audience by construction (§1.5). Accepted.
- **Documentation tuned to current coding agents will transfer.** Mitigated by keeping the procedure thin and the executable core thick. Open question 5.
