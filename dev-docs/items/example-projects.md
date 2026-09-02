# Agent shapes — analysis

Status: **open, and reframed on 2026-08-12.** The question in `random-thoughts-questions.md` item
5 asked about shipping a set of agent shapes. **What is being built instead is a set of example
projects**, on Thilina's ruling of that day; §19.9 is the decision and the evidence behind it.
What is here otherwise is the evidence gathered on 2026-08-09 and 2026-08-10, and the two things
that came out of it and did land: the `brainstorm` stage (`design/brainstorm-stage.md`) and the dogfood
#3 candidate in §17.

**Read §19 before §1 to §15.** A verification pass on 2026-08-12 re-checked every count,
benchmark, repository figure and price against its source, and the sections above did not survive
it intact: the demand evidence that produced §13's ranking was traced to a self-selected survey
of about twenty-one people, three of the four frameworks §5.3 describes have deprecated or deleted
what it names, and §12.5's central finding is contradicted by a table in its own paper. §18 is
what nine *later library items* changed; §19 is what checking the *sources* changed. Neither
rewrites the sections above.

Two wrong turns are kept rather than deleted, at §3 and §16.2, because both are repeatable: a
survey run on the wrong axis, and a set of candidates chosen for being defensible rather than for
anyone wanting them. §19 adds a third, at §19.1: a ranking built on a number nobody checked.

---

## 1. The question

From `random-thoughts-questions.md` item in Thilina's Corner:

> Deciding on a set of Agent shapes or types and shipping them (with customisation allowed).
> This mirrors Simple Transformers' approach of having a set of model shapes that can be used
> and customised, e.g. ClassificationModel, LanguageGenerationModel.

---

## 2. What is settled so far in the discussion

**Pipelines-as-nodes already ships** and is the enabling fact. `docs/pipeline.md` §1.6: a
`Pipeline` with a `node_id` is a node in another pipeline; internal nodes record under prefixed
ids (`research.hunt`) in the trajectory, the manifest and per-node metrics; two copies under
different ids do not collide; it carries its own budget under the run budget; `to_mermaid()`
renders the nested graph; `accepted_by`/`produced_by` type-check the seam.

Consequence: a shipped shape can be a sub-pipeline that is inspectable, ablatable, measurable
per node, individually budgeted, and replaceable one node at a time. This is a materially
better position than a class with a `.run()`, which would hide all of it.

**The "library ships no content" objection is weaker than it first looked.** The library already
ships nine tools whose `description` is prompt text the model reads. Shipping prompt content is
a line already crossed at item 7. A shipped sub-pipeline is to a graph roughly what a built-in
tool is to a node.

**The evidence bar from fan-out does not transfer.** That bar (two independent sessions meeting
the shape) exists because fan-out and branching change the core execution model: node API,
per-node denominators, format bumps. Wrong there is expensive and hard to undo. A shipped
sub-pipeline is additive — a module with a version, deletable, no format or API change. Wrong
costs a deprecation. Applying an irreversibility bar to a reversible thing was a category error.

**Thilina's method instead:** research what the field has converged on, ship a starting set,
expand on community signal. This is how Simple Transformers picked its task list — it followed
what the field had converged on, not what he had personally built.

**Known dependency:** any shape with an accumulating loop is DF2-D1, which is another session's.
Do not presuppose its answer. *(Closed 2026-08-09; §18.1.)*

---

## 3. The correction that reset the method

*2026-08-09, on Thilina's push-back mid-pass.*

The first research pass surveyed **techniques** — self-consistency, reflection/self-refine,
map-reduce, ReAct. Every source reached for (Anthropic's five workflow patterns, DSPy modules,
LangGraph prebuilts, "agentic design patterns" listicles) is on that axis.

**Simple Transformers shipped task shapes, not techniques.** `ClassificationModel` is "what is
the job". It is not `DropoutSchedule` or `LRWarmup`. The analogy being drawn is to the task
axis, and the first pass never went looking for a task taxonomy at all.

Two further faults in that pass, both worth recording because they are recurring:

- **Candidate list came from the dogfoods.** Retrieval-QA-with-abstention is dogfood #1;
  extraction-under-absence is dogfood #2. Designing the catalogue around the two tasks we happen
  to have is the same error as the evidence bar, in a different costume.
- **Ranked by narrative interest.** Reflection got disproportionate attention because it has a
  contested-literature story that is interesting to write about. That is not the same as being
  useful to ship.

**The two axes are probably not exclusive.** Likely shape: the shipping unit is task-shaped, and
techniques are how a task shape is customised (a QA shape run with k-sample aggregation, or
with a verify pass). But that is a hypothesis to test against the survey, not a conclusion to
search toward.

---

## 4. Method

### 4.1 Phase 1 — enumerate broadly, no filtering

Four independent source classes. Enumerate first, judge later. Anything named by a source goes
on the list even if it looks wrong, and the reason for dropping it is recorded rather than
silently applied.

| Source class | Why it counts as evidence | Status |
|---|---|---|
| **A. Task taxonomies** — what are people actually building agents *for* | Closest analogue to Simple Transformers' task list. Revealed demand. | **not started** |
| **B. What frameworks ship as first-class units** | Shipping something is a costly signal, so it is a revealed preference rather than an opinion | partial, technique axis only |
| **C. Technique taxonomies and surveys** | The customisation axis, and the literature that says what works | partial |
| **D. Benchmarks and evaluation suites** | A benchmark existing means the task is agreed enough to be scored, which is exactly the contract a shape needs | **not started** |

Source class A is the gap and is where the next work goes. Candidate probes: industry reports on
deployed agent use cases, vendor case-study catalogues, agent marketplace/directory listings,
job-to-be-done taxonomies in surveys, what the framework template galleries are named after
(as opposed to what the framework primitives are named after).

### 4.2 Phase 2 — one rubric, applied uniformly

So entries are comparable rather than each argued on its own terms.

| Field | Question |
|---|---|
| Contract | Input type → output type, stated precisely enough to be an `Example` |
| Axis | Task shape, technique, or both |
| Convergence | How many independent sources name it; do frameworks ship it or only write about it |
| Evidence | What is known, how well, and what is contested |
| Expressible | Does it fit three node kinds plus the graph? What is missing if not? |
| Ships content | Does it carry prompt text, or is it pure machinery? |
| Bounded | Is it small and terminating, per Thilina's "bounded, small tasks" criterion |
| Evaluable | Does the task type determine what an example and a matcher look like |

### 4.3 Stop rule

Enumeration stops when three consecutive sources in a class add no new entries. Recorded rather
than judged by feel, because the failure mode of this kind of pass is stopping when the story
is good enough.

---

## 5. Findings so far — source class C, partial

Every citation below was fetched and read, not recalled. Treat this section as one axis of a
two-axis survey, gathered before the method above existed.

### 5.1 Anthropic's five workflow patterns

<https://www.anthropic.com/engineering/building-effective-agents>

Prompt chaining, routing, parallelization (sectioning and voting), orchestrator-workers,
evaluator-optimizer. Plus autonomous agents as a separate thing. Stated guidance: "finding the
simplest solution possible, and only increasing complexity when needed", and "optimizing single
LLM calls with retrieval and in-context examples is usually enough".

Note the alignment with this library's own position: workflows for predictability, agents when
model-driven decisions are needed. That is FT-11 and the three node kinds, from a different
direction and independently arrived at.

**All five are techniques, not tasks.**

### 5.2 DSPy modules — the closest existing analogue to the proposal

Predict, ChainOfThought, ProgramOfThought, ReAct, MultiChainComparison, BestOfN, Refine, RLM.
Generalised over a signature, composable.

This is the strongest precedent for "ship a set of shapes, customisable". Worth a proper study
of what its module boundary is and what it refuses to make a module. The canonical docs URL
needs re-finding (`dspy.ai/learn/programming/modules/` redirects, the `7-changing-modules`
path 404s).

**Also techniques.** DSPy's task axis is the *signature*, and the module is orthogonal to it.
That split is itself a finding: DSPy separates "what is the job" (signature) from "how to
attempt it" (module). If that separation is right, this library's equivalent is roughly
output schema plus example contract on one axis, sub-pipeline on the other.

### 5.3 LangGraph prebuilts

`create_react_agent` as the core factory. Ships alongside: supervisor (multi-agent), swarm
(multi-agent), LangMem (memory), Trustcall (structured extraction), a reflection package
(main agent plus critique agent). Map-reduce is a documented pattern via the Send API rather
than a prebuilt.

Multi-agent and long-term memory are both out of scope for this library (`archive/plan-history.md`), so
two of the five prebuilts are not candidates regardless of merit.

*Corrected 2026-08-10.* **Long-term memory is in scope and is being built** as `archive/plan-history.md` §1.5;
§3.2's amendment of the same day is what moved it. So LangMem is one of the five that a
candidate could correspond to, and §9.2's K4 row is where that is tracked. Multi-agent is
unchanged. §7 below already says this list does not filter by scope, which is why the sentence
above is corrected in place rather than deleted.

### 5.4 Self-consistency — settled, and pure machinery

*Four of the five figures below belong to a different model than the sentence implies, the
baseline is not what a reader would assume, and "pure machinery" is wrong. §19.5.*

Wang et al., ICLR 2023, <https://arxiv.org/abs/2203.11171>. Sample k reasoning paths, marginalise,
take the most consistent answer. Reported gains: GSM8K +17.9, SVAMP +11.0, AQuA +12.2,
StrategyQA +6.4, ARC-challenge +3.9.

Relevant because it **ships no prompt content at all** and because the library already has
k-rollout machinery. Also because it is an aggregation over samples, which is a shape the three
node kinds can express without anything new.

### 5.5 Self-correction — contested, and this is the interesting one

*One claim below could not be sourced and another is misattributed to replication work. The
intrinsic/extrinsic split settles the question. §19.5.*

- Madaan et al., Self-Refine: generate, self-critique, refine, iterate.
- **Huang et al., "Large Language Models Cannot Self-Correct Reasoning Yet", ICLR 2024,
  <https://arxiv.org/abs/2310.01798>.** Intrinsic self-correction, meaning no external feedback:
  LLMs struggle to self-correct and performance sometimes *degrades*.
- Replication work reports Self-Refine's gains on constrained generation can come from outputs
  simply getting longer, and that the model's own iteration scores are not monotonic.

Why it matters here beyond the pattern itself: `simple-agents.md` §2.2 names draft-critique-revise
as the one shape that could not be expressed before the graph. It is now expressible as a
bounded cycle. So the library would be shipping a pattern whose literature says it often does
not work without external feedback — which makes it the sharpest test of whether "shape plus
caveat plus measurement" is really the product, or whether we just ship the popular thing.

### 5.6 Abstention and sufficient context — strongest task-adjacent finding so far

*The AbstentionBench figures verify; its six category names below are not the paper's. The
sufficient-context work is cited to the wrong authors and two of its figures are wrong. §19.5,
which also carries the argument this section was reaching for.*

- **AbstentionBench**, Kirichenko, Ibrahim, Chaudhuri, Bell (FAIR at Meta), 2025,
  <https://arxiv.org/html/2506.09038v1>. 35,000+ questions, 20 datasets, six categories of
  unanswerable: unknown answers, false premises, outdated information, subjective matters,
  underspecified context, unclear intent. Findings: **reasoning fine-tuning degrades abstention**
  (~24% drop for DeepSeek R1 and s1 against non-reasoning counterparts), instruction-tuning helps
  but verifiable-reward optimisation hurts, and **model size shows almost no correlation with
  abstention ability**.
- **Sufficient context**, Rashtchian and Juan (Google Research), ICLR 2025,
  <https://research.google/blog/deeper-insights-into-retrieval-augmented-generation-the-role-of-sufficient-context/>.
  Context is "sufficient" when it contains all information needed for a definitive answer. An
  LLM autorater classifies sufficiency at 93%+ accuracy. **Adding context increases confidence
  and paradoxically raises hallucination**: Gemma's incorrect-answer rate went from 10.2% with no
  context to 66.1% with insufficient context. Proposed method combines self-rated confidence
  with the sufficiency signal, improving selective accuracy by up to 10 points.

This is the closest thing yet to a shipped-shape justification, and it bears directly on
do-not-change #6 (`unknown` first-class) and FT-09/FT-10. The six-category taxonomy of
unanswerability is also a ready-made elicitation scaffold and a ready-made example-set
requirement.

**Caveat on all of the above:** these are the field's claims on benchmarks, not measurements we
made. If a shape ships, its own number has to come from our own run.

---

## 6. Open questions

1. ~~**Task axis or technique axis, or both?**~~ **Both.** Thilina, 2026-08-09. The survey covers
   both and the relationship between them is a finding rather than an assumption.
2. ~~**What is the shipping unit?**~~ **Any combination of sub-pipeline, task type in the brief,
   and template.** Thilina, 2026-08-09: *"settled on merit and scenario, not doctrine."* So the
   unit is decided per candidate, and a catalogue where different entries ship differently is a
   legitimate outcome rather than an inconsistency to iron out.
3. ~~**Are a shape's prompts overridable?**~~ **Yes, and not strictly.** Thilina, 2026-08-09:
   being strict *"would then make the shipped things examples rather than something that's plug
   and play."* This settles that a shipped unit carries real, working prompts and is usable
   without editing. Still open: how an override is recorded so a regression can be attributed to
   it (FT-15 is unversioned prompts, and a shipped unit ships prompts).
4. ~~**Can a shape carry its own measured number?**~~ **Yes, in the repository and never in the
   wheel.** Thilina, 2026-08-12. Benchmark code and its results are a maintainer artifact:
   nothing force-included, nothing a builder inherits as a default, no data bundled. `simple-agents.md`
   §1.6 is untouched, because what makes a shipped dataset teach the wrong lesson is becoming the
   obvious thing to evaluate against, and a number the builder cannot adopt does not. §19.6 ran
   source class D and found the licences permit it where it matters, with one exception: **CRAG is
   CC BY-NC and unshippable**, and it is the benchmark whose scoring shape is right for abstention.
5. **Naming — a new name is needed.** Confirmed by Thilina, 2026-08-09. "Shape" is taken twice:
   `shapes.py` means what a node accepts and produces, and `simple-agents.md` §2.2 "Agent shape"
   means the three node kinds. Candidates to weigh once the catalogue exists, since what the
   things turn out to be should pick the word. **Moot for now, 2026-08-12**: what is being built
   is a set of example projects (§19.9), and an example project needs no new word.

---

## 7. Scope note that governs the survey

**`archive/plan-history.md`'s out-of-scope list is "for now", not forever.** Thilina, 2026-08-09, on
multi-agent and long-term memory specifically: *"That can, and might, change."*

So the enumeration does **not** filter candidates by current scope. A candidate that would need
multi-agent or memory is catalogued with its scope status recorded as a field, not dropped. The
survey's job is to describe the space; deciding what ships is downstream of it.

---

## 8. Survey results — three structural findings

These came out of the survey rather than being looked for, and each changes the design question
more than any individual candidate does.

### 8.1 Primitives are technique-named. Templates are task-named.

*The split holds and the reading of it below does not. Three frameworks do ship task-named
first-class objects, the n8n figure understates by six times, and the reason the split persists
is that importable task-named units keep dying while copyable ones live. §19.4.*

Every framework surveyed splits the same way, and none of them says so out loud.

| Framework | Its primitives (technique-named) | Its templates (task-named) |
|---|---|---|
| LangGraph | `create_react_agent`, supervisor, swarm, reflection | — |
| DSPy | Predict, ChainOfThought, ProgramOfThought, ReAct, MultiChainComparison, BestOfN, Refine, RLM | — |
| Pydantic AI | composable capabilities: thinking, web search, web fetch, image generation, MCP, tool search | — |
| OpenAI Agents SDK | manager pattern, handoffs | deep research clone |
| LlamaIndex | workflow steps | Document Q&A, Extraction Agent with Review UI, Invoice Extraction & Reconciliation, Document Parser, Human in the Loop, RAG, Web Scraping, Basic Workflow, Showcase |
| n8n | nodes | categories: Document Ops, AI Sales, IT Ops, Marketing, Support |

**So both axes exist in the field, and they are delivered by different mechanisms.** Techniques
ship as library objects; tasks ship as templates you copy. Nobody surveyed ships a task-shaped
unit as a first-class library object. That is either a gap or a warning, and the survey cannot
tell which.

Two details worth keeping. **LlamaIndex's template list is 5 of 11 on document extraction**, which
is the strongest single convergence signal in the whole survey. And **Llama Packs, the hub
positioned as "ready-made templates", drifted to vendor integrations** (Vanna, Arize Phoenix,
Zephyr, code-hierarchy) rather than task shapes. A community-expanded catalogue drifting toward
integrations is the failure mode of the "ship a starting set and let the community expand it"
plan, observed rather than hypothesised.

### 8.2 DSPy separates the job from the attempt, and that is the cleanest statement of the design

A DSPy **signature** says what the job is. A **module** says how to attempt it, and is generalised
across every signature. The two are orthogonal and compose.

Mapped onto this library: the job is the output schema plus the example contract plus the
matcher. The attempt is the sub-pipeline. If that separation is right, a catalogue entry is a
pairing rather than a single object, and the two halves are independently swappable.

### 8.3 The technique axis is nearly saturated by what already ships. The task axis is empty.

Anthropic's five workflow patterns, checked against the library:

| Anthropic pattern | This library |
|---|---|
| Prompt chaining | A `Pipeline`. Ships. |
| Routing | `route=` on a node. Ships. |
| Parallelization — sectioning | `LLMNode(over=...)` fan-out. Ships. |
| Parallelization — voting | **Does not ship.** |
| Evaluator-optimizer | A bounded cycle, `Loop(max_iterations=..., then=...)`. Ships as a primitive; nothing is pre-wired. |
| Orchestrator-workers | `AgentNode` plus a nested pipeline. Ships, partly. |
| Autonomous agent | `AgentNode`. Ships. |

**Six of seven are already primitives.** The technique axis has almost nothing left to add — the
identified holes are voting/self-consistency and DSPy-style `BestOfN` over a reward function.
Meanwhile nothing in the library is indexed by task at all.

This is a better argument for indexing the catalogue by task than the Simple Transformers
analogy was, because it comes from what the library has rather than from what another library
did.

---

## 9. Candidate catalogue

Convergence counts independent sources naming it. Scope is against `archive/plan-history.md`, read as
"for now" per §7 above.

### 9.1 Task axis

*Convergence counts below rest on §12's demand evidence, most of which did not survive §19.1.
"T7 is the anomaly" rests on consultation never having been used, which is false: §19.7.*

| # | Candidate | Convergence | Contract | Ships content | Expressible now | Scope |
|---|---|---|---|---|---|---|
| T1 | **Structured extraction from documents** | **6** — n8n's top task, 5 of 11 LlamaIndex templates, LangGraph Trustcall, a named commercial category (Box Extract, Sensible, LandingAI, Extend), enterprise Document Ops, this library's own `extract_to_schema` and dogfood #2 | document(s) → typed record, field-level absence | prompts | yes | in |
| T2 | **Retrieval QA over a corpus, with abstention** | **5** — LlamaIndex Document Q&A and RAG templates, n8n retrieval, the eval survey's planning/multi-step cluster, the abstention literature, dogfood #1 | question + corpus → answer or `unknown` | prompts | yes | in |
| T3 | **Classification / triage into a fixed set** | **4** — enterprise support triage, n8n sentiment and image classification, Anthropic's routing pattern, and Simple Transformers' own flagship | input → label from a declared set | prompts | yes | in |
| T4 | **Reduction over many documents** (summarise, aggregate) | **4** — n8n summarisation, Anthropic sectioning, LangGraph map-reduce, classic | many documents → one output | prompts | yes, `over=` plus a join | in |
| T5 | **Web research → report with citations** | **4** — GAIA / AssistantBench / WebVoyager, OpenAI's deep-research example, n8n scraping and enrichment, dogfood #2 | question → report + sources | prompts | ~~**blocked on DF2-D1**~~ *(unblocked, §18.1)* | in |
| T6 | **Conversational task completion under a policy** | **3** — τ-bench and τ²-bench, IntellAgent, enterprise's #1 deployed use case | multi-turn dialogue + policy → completed action | prompts | partly: consultation ships, multi-turn end-user loop does not | in |
| T7 | **Human-in-the-loop approval** | **3** — LlamaIndex template, enterprise compliance, finance reconciliation | proposed action → approved / rejected / amended | little | **yes, and the machinery already ships unused** (consultation, suspend/resume) | in |
| T8 | **Code review / software engineering** | **3** — SWE-bench family, Terminal-Bench, enterprise code review in production | repo + change → findings | prompts | yes | in, but far from the library's lane |
| T9 | **Data enrichment / lookup** | **2** — n8n lead enrichment, sales agents | partial record → completed record | prompts | yes | in |
| T10 | **Web / GUI navigation** | **4** — WebArena, Mind2Web, OSWorld, WorkArena | goal + browser → completed task | prompts | no | **out** (browser tooling, §3.2) |

**T7 is the anomaly worth staring at.** The library already ships consultation, suspension and
resume, `plan.md` §2.2 records a supervisor being considered, and dogfood #2 never used any of
it. A task-indexed catalogue would give that machinery its first reason to exist.

**T1 and T2 are the two that clear every column.** Both are in scope, both expressible today, both
have the highest convergence, and both are tasks where the output contract determines the
example and the matcher — which is the property §8.2 says a catalogue entry needs.

### 9.2 Technique axis

*K1's "ships no content: none" is wrong. Voting needs an answer-equivalence matcher, which is the
one thing the library refuses to supply. §19.5 and §19.7.*

| # | Candidate | Convergence | Ships content | Status |
|---|---|---|---|---|
| K1 | **Voting / self-consistency** | 3 — Anthropic parallelization-voting, Wang et al. ICLR 2023, DSPy MultiChainComparison | **none** | Does not ship. Pure machinery, settled evidence, and the k-rollout machinery already exists |
| K2 | **Best-of-N over a reward function** | 2 — DSPy `BestOfN`, DSPy `Refine` | none | Does not ship. Note the overlap with reward hacking, FT-26 |
| K3 | **Evaluator-optimizer / self-refine** | 4 — Anthropic, LangGraph reflection package, DSPy `Refine`, Madaan et al. | prompts | Expressible as a bounded cycle. **Evidence contested, see §5.5** |
| K4 | **Memory** | 4 — the eval survey makes it one of four capability dimensions (StreamBench, MemoryArena, MemBench, LongMemEval), LangMem | — | **In scope, and being built** as `archive/plan-history.md` §1.5. What ships is a store the library owns, reached through a recorded call. **Automatic memory formation is a candidate entry for this catalogue**, see below |
| K5 | **Multi-agent: supervisor / handoff / swarm** | 4 — LangGraph supervisor and swarm, OpenAI manager and handoffs, CrewAI, Anthropic orchestrator-workers | — | **Out for now, revisitable** |
| K6 | Prompt chaining, routing, sectioning, ReAct | universal | — | **Already primitives.** No catalogue entry needed |

**K4's row moved 2026-08-10**, at the memory design sitting, and memory has since been built (§18.4). `archive/plan-history.md`'s amendment took
long-term memory off the out-of-scope list and §1.5 is the build. What ships there is the store,
the scope and the recording rules, and it is deliberately not a shape.

**Automatic memory formation is where the shape would be, and it is noted here on Thilina's
instruction of 2026-08-10 rather than scheduled.** Mem0's product is the extraction step: hand it
a conversation, a model decides what in it is a durable fact, and reconciles that against what is
already stored as an add, an update or a delete. LangMem ships the same thing as a background
memory manager. Neither is a primitive. Both are **a small pipeline over primitives this library
already has**: a model node producing a typed set of candidate facts, a recall of what is stored,
a model node reconciling the two, and a write. That is why it belongs in this catalogue and not
in §1.5.

**What makes it a good first prebuilt, against §15.2's test** — a prebuilt earns its place by
what it brings to evaluation rather than by the wiring it saves. Extraction-and-reconciliation is
a step whose output is a typed record, so the example contract and the matcher fall out of the
output schema, which is the property §8.2 says a catalogue entry needs. It is also a step where
being wrong is expensive and invisible: a fact stored that was never true is read back by every
later run as though a person had said it, and nothing downstream distinguishes a remembered
falsehood from a remembered fact. A shape that ships with its own evaluation is the argument for
shipping shapes at all.

**What has to exist first:** memory (`archive/plan-history.md` §1.5) and semantic recall (§1.8). Reconciliation
against what is already stored is a recall, and a lexical one finds the stored fact only when the
new one is phrased in the same words, which is exactly the case a duplicate is not.

---

## 10. External validation the survey turned up by accident

"A Survey on Evaluation of LLM-based Agents", Yehudai et al., arXiv:2503.16416v2, 2026.
<https://arxiv.org/html/2503.16416v2>

Its five identified gaps in agent evaluation, against this library:

| The survey's gap | This library |
|---|---|
| "Coarse-grained, end-to-end success metrics" lack diagnostic power for intermediate failures | Per-node metrics, and FT-08 |
| "Current evaluations often prioritize performance while overlooking cost and efficiency measurements" | The cost bases, and the tool-spend work of 2026-08-09 |
| Static human-annotated data limits scaling | — |
| Benchmarks lack focus on safety, trustworthiness, policy compliance | The side-effect classes, partly |
| "Most benchmarks conflate backbone LLM capabilities with agent harness design, obscuring performance attribution" | Variant comparison, and model pinning in the manifest |

Three of five are things the library already built for its own reasons. This is independent
support for the design, arrived at by people evaluating agents rather than building them.

---

## 11. Naming — §6 item 5

The word has to name a task-indexed, ready-to-run, customisable unit. Thilina's plug-and-play
ruling (§6 item 3) rules out anything implying the thing must be edited before it runs.

| Candidate | For | Against |
|---|---|---|
| **Prebuilt** | Honest: these literally are `Pipeline` instances that were built ahead of time. No collision. Matches LangGraph's own usage, so a coding agent already knows the word | Bland. Reads as an adjective |
| **Blueprint** | Evocative, no collision, adaptation is normal for one | A blueprint does not run. Contradicts plug-and-play |
| **Recipe** | Familiar, customisation expected | Same objection: a recipe is instructions, not a working thing |
| **Pack** | Precedent | Taken by LlamaIndex, and drifted to integrations there (§8.1) |
| **Template** | Familiar | Commits to code generation, which is only one of the three delivery modes Thilina left open |

Leaning **prebuilt**, on the plug-and-play argument. Not decided.

---

## 12. Second survey round — demand side and practitioner pain

*2026-08-09, on Thilina's instruction to gather real evidence from repositories and the problems
people hit, without narrowing to only that.*

**Most of this round did not survive verification. §19.1 and §19.3.** The GitHub counts in §12.2
reproduce exactly and their limits are now measured. §12.1's three-population finding rests on a
survey of about twenty-one self-selected people, §12.4's app count is short by 2.8×, and six of
the figures §12.6 reasons from are over-read, including the two that reordered the ranking.

Two source classes added to §4.1:

| Source class | Why it counts as evidence |
|---|---|
| **E. Practitioner pain** — what breaks, from issue trackers, surveys of people running agents | The library is a process library. What people fail at is more relevant to it than what they attempt |
| **F. Revealed build patterns** — what is actually in repositories and in funded companies | Demand side. §8.1's evidence was all supply side, which is what vendors chose to sell |

### 12.1 The finding that reorders §9: three populations disagree, and they disagree systematically

| Population | Top task | Source |
|---|---|---|
| **Frameworks and vendors** (supply) | Document extraction | §8.1 — 5 of 11 LlamaIndex templates, Trustcall, the commercial category |
| **Public repositories** (hobbyist and demo) | Research and RAG, by a wide margin | §12.2 counts |
| **Funded startups** (commercial) | Data extraction 62%, workflow automation 62% | §12.3 |

**Extraction wins two of three, and the population it loses to is the one least likely to ship
anything.** That is a better-grounded ranking than §9's convergence count, which counted sources
without asking what each population's incentives were.

### 12.2 GitHub repository counts

Public repositories with the phrase in name or description, GitHub search API, 2026-08-09.

| Phrase | Repos | | Phrase | Repos |
|---|---:|---|---|---:|
| voice agent | 15,942 | | email agent | 2,703 |
| research agent | 14,721 | | triage agent | 2,232 |
| rag agent | 9,899 | | browser agent | 2,106 |
| deep research | 8,027 | | code review agent | 1,988 |
| trading agent | 5,273 | | document extraction | 1,413 |
| sql agent | 3,382 | | data analysis agent | 1,005 |
| customer support agent | 3,049 | | scheduling agent | 724 |
| | | | devops agent | 1,787 |
| | | | social media agent | 646 |
| | | | summarization agent | 342 |
| | | | recruiting agent | 281 |
| | | | extraction agent | 263 |
| | | | translation agent | 251 |
| | | | personal assistant agent | 165 |
| | | | question answering agent | 130 |

The last six terms queried added nothing above the mid tier, so §4.3's stop rule fired here.

**Read these as ordinal at best, and only where the gap is large.** The phrase is matched in free
text, so "research agent" catches academic-research tooling and "voice agent" catches telephony
infrastructure; forks are not deduplicated; and a description is not a reliable statement of what
a repository does. They are a demand signal, not a measurement.

**Three categories the catalogue missed entirely**, which is why the term list deliberately
included phrases from outside it: **voice** (out of scope, real-time audio), **text-to-SQL /
database querying** at 3,382, and **trading** at 5,273 (a domain rather than a shape). Text-to-SQL
is the one that deserves a catalogue row: it is bounded, it has an unambiguous correct answer,
and it has established benchmarks.

Note also **"question answering agent" at 130 against "rag agent" at 9,899**. The task has a name
the field does not use. Anything shipped for T2 has to be called RAG or it will not be found.

### 12.3 What funded companies build

"The State of YC AI Agents (2026)", <https://voker.ai/blog/the-state-of-yc-ai-agents-2026>:
data extraction/processing 62%, workflow automation 62%, research and analysis 38%, content
generation 38%, search/retrieval 33%, customer support 29%. The write-up's own reading is that
founders gravitate to "structured work and operational tasks, where outcome success is more
clearly defined".

**Workflow automation at 62% has no row in §9 at all.** It is probably not one shape but the
absence of one: a fixed sequence with model judgement at named points, which is what a `Pipeline`
already is.

### 12.4 What people actually build, by function rather than by domain

`Shubhamsaboo/awesome-llm-apps`, 52 agent applications across four directories, classified by
what the agent *does* rather than what industry it is in:

| Functional shape | Count | Examples |
|---|---:|---|
| **Research → report** | ~12 | deep research (×3), multi-agent researcher, journalist, startup trend analysis, product launch intelligence, HN briefing, release radar |
| **Advisory: gather the user's situation → recommend** | ~11 | consultant, health/fitness, investment, personal finance, financial coach, life insurance advisor, mental wellbeing, meal planning, travel, home renovation, speech trainer |
| **Analyse one named source → findings** | ~6 | earnings call analyst, data analysis, data visualisation, AQI analysis, fraud investigation, medical imaging |
| **Generate content** | ~6 | email GTM (×2), movie production, meme, music, blog-to-podcast |
| **Infrastructure / meta** | ~7 | governance, trust layer, trust-gated team, self-evolving, agent teams, mixture of agents, system architect |
| **Computer / browser use** | 2 | windows-use, web scraping |

**Bias to state:** an awesome-list is showcase-biased. `starter_ai_agents` contains a meme
generator, a music generator and a breakup-recovery agent. Weight this below §12.3.

**The category the catalogue missed: advisory.** Elicit the end user's situation, apply domain
knowledge, recommend with reasons. It is the second-largest functional cluster here, and it is
**the shape of this library's own dogfood #2** — find t-shirts that fit *this person* — which §9
filed under "web research → report". Two things follow. Its distinguishing feature is that the
input is not fully supplied at the start, so it is the one shape whose contract *requires*
consultation, which is machinery this library ships and nothing has used. And a matcher for it is
genuinely hard: "was this a good recommendation" has no ground truth of the kind T1 and T2 have.

### 12.5 Practitioner pain

**"Measuring Agents in Production"**, Pan et al., ICML 2026, <https://arxiv.org/abs/2512.04123>.
20 case studies and 86 practitioners across 26 domains.

- **74% depend primarily on human evaluation.**
- **68% execute at most 10 steps before human intervention.**
- 70% prompt off-the-shelf models rather than tuning weights.
- **Reliability is the top development challenge, and practitioners address it through
  systems-level design** rather than through evaluation.

**LangChain, State of Agent Engineering 2026**, 1,300+ professionals,
<https://www.langchain.com/state-of-agent-engineering>.

- **48% do not run offline evaluations. 63% skip online monitoring.**
- Observability adoption ~89% against evals adoption 52%.
- 61% name hallucination as where agents fail them most; quality is the top production barrier at 32%.

**"What Challenges Do Developers Face in AI Agent Systems?"**, Asgari, Panichella, Derakhshanfar
and Olsthoorn, 2025, <https://arxiv.org/abs/2510.25423>. Stack Overflow topics and GitHub issue
topics across widely used agent frameworks. Five challenge families: environment and dependency
management; retrieval, embeddings and memory; orchestration and execution control; interaction
contracts between models and tools; runtime reliability. **Its central result is about
persistence rather than frequency: installation and prompting questions get resolved quickly,
while retrieval and orchestration problems are less visible, more complex, and persist as
ongoing maintenance burdens.**

### 12.6 What the pain data does to the argument

| Evidence | What it bears on |
|---|---|
| 48% run no offline evaluation; 74% rely primarily on human evaluation | FT-01 measured on real populations. The library's central premise is not a hypothesis |
| Observability 89% against evals 52% | People log and do not evaluate. The library's split between trajectory and evaluation is the real gap, and the trajectory half is the commoditised half |
| 61% name hallucination as the top failure | FT-09 and FT-10, and do-not-change #6 |
| **68% run at most 10 steps before human intervention** | The median production agent is **short and human-gated**. This is direct support for "bounded, small tasks", and it promotes **T7 human-in-the-loop** well above its 3-source convergence |
| Reliability addressed through **systems-level design** rather than evaluation | A prebuilt is systems-level design. This is the demand for the thing being proposed, stated by practitioners in the terms they used |
| Installation and prompting resolve fast; **retrieval and orchestration persist** | Where durable value is. Also a warning: a prebuilt that only saves wiring saves the cheap half |

---

## 13. Revised candidate ranking

**Superseded 2026-08-12.** The demand evidence that produced this order did not survive
verification (§19.1), T5's blocker is gone (§18.1), and the ranking that governs is §19.6's, by
how agreed the scorer is. The set actually being built is §19.9's, and it is example projects
rather than shapes. This section is kept as written because the three sections below cite it.

Integrating both rounds. Changes from §9 are marked.

| Rank | Candidate | Why |
|---|---|---|
| 1 | **T1 structured extraction** | Top in supply (§8.1) and in commercial demand (62%, §12.3). Contract determines example and matcher. Expressible today. Unchanged |
| 2 | **T2 retrieval QA with abstention** | Top in public repositories, 33% commercial. Best literature of any candidate (§5.6). **Must be named RAG**, per §12.2 |
| 3 | **T7 human-in-the-loop approval** | **Up from 7.** 68% of production agents are human-gated. The library ships consultation, suspension and resume, and nothing uses them |
| 4 | **T11 advisory / recommendation** | **New, missed in round 1.** Second-largest functional cluster, and dogfood #2's actual shape. The only candidate whose contract requires consultation. Weakness: no clean matcher |
| 5 | **T5 research → report** | Largest in public repositories, 38% commercial. **Still blocked on DF2-D1**, which this round makes more urgent rather than less |
| 6 | **T12 text-to-SQL / query a database** | **New, missed in round 1.** 3,382 repos, bounded, unambiguous answer, established benchmarks |
| 7 | **T4 reduction over many documents** | Unchanged |
| 8 | **T3 classification / triage** | 2,232 repos, and the Simple Transformers echo. Unchanged |
| — | **Workflow automation** | 62% commercial, but probably not a shape: it is what a `Pipeline` already is (§12.3) |

---

## 14. Open questions after round 2

**All three closed 2026-08-12.** Item 1 by measurement rather than by the paper it rested on: a
pipeline definition is 3 to 8 lines per node and 6 to 20% of its file, so a prebuilt saves 20 to
40 lines out of a thousand (§19.7), and the persistence finding it argued from is contradicted by
a table in its own paper (§19.3). Item 2: yes, advisory is evaluable where the recommendation
space is enumerable and typed, and τ-Rec does it with no model calls at all (§19.6). Item 3: the
search terms diverge by task, and the "agent" suffix is right for retrieval and wrong for
extraction and text-to-SQL (§19.2).

1. **Does a prebuilt that only saves wiring save the cheap half?** §12.5's persistence finding says
   installation and prompting are cheap to resolve and retrieval and orchestration are not. A
   prebuilt is worth most where it carries retrieval and orchestration decisions, which is also
   where it ships the most content.
2. **Can the advisory shape (T11) be evaluated at all?** It has no ground-truth matcher of the kind
   T1 and T2 have. If it cannot, it is a template rather than a measurable prebuilt, which is
   exactly the merit-and-scenario judgement §6 item 2 leaves open.
3. **Does the catalogue need a name people search for rather than a correct one?** "question
   answering agent" 130 against "rag agent" 9,899.

---

## 15. Verification pass, 2026-08-10

Claims rechecked against the code and the sources rather than against these notes.

### 15.1 Corrections — things above that were wrong

**§8.3 said six of Anthropic's seven patterns already ship. It is five, and one of the two
holes is bigger than the voting hole it did name.**

- **Orchestrator-workers does not ship.** *(Superseded 2026-08-10; §18.1.)* §8.3 recorded it as "`AgentNode` plus a nested pipeline.
  Ships, partly." An `AgentNode` delegates by calling *tools*, and
  `random-thoughts-questions.md:66`, in Thilina's Corner, states the constraint directly: *"A tool
  at a fixed point now works; exposing a pipeline to a model as a tool does not."* A model cannot
  hand work to a sub-pipeline, so the pattern has no expression. This also touches T5 and T11,
  whose usual implementations are orchestrator-shaped.
- **Parallelization ships in semantics only.** `LLMNode(over=...)` gives the fan-out, but
  `docs/pipeline.md:137` says *"Arms run one after another, in the order the nodes appear in the
  list. Nothing runs concurrently."* Anthropic's pattern is partly a latency pattern, and the
  latency half is `plan.md` §2.2's deferred concurrency item. Fan-out over 40 documents costs 40
  sequential calls.

**§8.1 overcounted LlamaIndex.** Extraction templates are **4 of 11**, not 5: Extraction Agent
with Review UI, Invoice Extraction & Reconciliation, Document Parser, Invoice Extraction.
Document Q&A is retrieval. The finding survives at 4 of 11; the number was wrong.

**§12.4's 52 apps is a floor and the classification is mine.** The
`autonomous_game_playing_agent_apps` directory was never enumerated, and the functional grouping
was done by eyeball over directory names rather than by reading the code. Treat the cluster sizes
as approximate, not counted.

**Verified and standing**, except the model-client claim, which is superseded (§18.2): voting and self-consistency genuinely do not ship — the only
`aggregate` in the source is `evaluation/metrics.py`, which aggregates rollout scores after the
fact and is not inference-time. One model client serves a whole run, confirmed at
`pipeline.py:337` where `model` is a `run()` argument. Consultation, suspension and resume all
ship. Nine built-in tools carry model-facing descriptions.

### 15.2 Gaps — things that were never considered

**G1. The positioning tension, and it is the sharpest thing in this document.**
`simple-agents.md` §1.3 states that the *building* gap has closed and that what remains is the
improve-your-agent loop. **A prebuilt catalogue is a building convenience.** On its own it aims
at the gap the library's own positioning says is shut, which is also §1.2's "thin wrapper whose
only value is saved glue".

This composes with §12.5's persistence finding — installation and prompting resolve quickly,
retrieval and orchestration persist — into one test that is sharper than §3.4's:

> **A prebuilt earns its place by what it brings to evaluation, not by the wiring it saves.**

*(Amended 2026-08-12 on Thilina's ruling: the test has a second limb, and this one alone is too dogmatic. §18.6.)*

Under that test, a prebuilt ships as a pairing (§8.2): the sub-pipeline *and* the example
contract, the matcher, and the failure modes worth measuring. A prebuilt that ships only the
graph is the thing this library says it is not.

**G2. A shipped prompt has a model dependency, and plug-and-play hides it.**
Nothing above notices that prompts are tuned against a model. The library serves both Mistral and
a self-hosted Qwen3-1.7B, and item 8's recording showed a 1.7B model issuing four tool calls in
one turn and writing a tool's arguments before the search they depended on had returned. A
prebuilt that works on one and silently degrades on the other breaks the plug-and-play promise in
§6 item 3. At minimum a prebuilt has to declare what it was measured against.

**G3. A prebuilt that pre-answers elicitation is FT-24 wearing a friendly face.**
Picking a prebuilt plausibly settles several of the eighteen questions — `answer_form`,
`absence_vs_error`, `agency_boundary`. If it settles them *silently*, that is "the coding agent
decided alone what the builder should have decided", which is the failure FT-24 exists for. The
safe form is that a prebuilt **proposes** answers into the brief marked as its defaults, and the
gate still requires the builder to confirm them.

**G4. Nothing considered whether a prebuilt ships its own conformance checks.** It could: a
prebuilt knows failures specific to its task that the 28 generic entries do not name.

*(Answered 2026-08-12: **it could not.** There is no registration seam, no entry point and no
dynamic import in the conformance package, and a check cannot read a pipeline object because the
`Context` it is handed carries only artifacts, brief and taxonomy. Because a failure message must
be parsed out of `docs/failure-taxonomy.md` rather than written in Python, the taxonomy document
itself would have to become extensible. The entry count is 30, not 28. §19.7.)*

**G5. Concurrency is a cross-cutting constraint on the catalogue, not a detail.** T4 reduction
over many documents and T5 research are both latency-bound, and §15.1 establishes that nothing
runs concurrently. A prebuilt for either ships a known-slow implementation.

*(Closed as narrowed 2026-08-12. §16.0 already corrected the premise: a fan-out inside one run is
sequential, an evaluation overlaps rollouts at `concurrency=4`. So the constraint binds a run and
not an evaluation. Concurrency was scheduled the same day and is built, `archive/plan-history.md` §1.12, with the brief
at §1.12, so the constraint is being removed rather than designed around.)*

---

## 16. Dogfood candidates

Against Thilina's brief: a good demo and article, not a rehash, shows the library off, practical
and doable, and library additions are acceptable. Ordered by how strong the article is.

Where ground truth is marked **constructible**, it means labelled examples can be manufactured at
scale rather than hand-labelled, which is the expensive part of every dogfood so far.

### D1. Which step actually needs the expensive model?

Build any multi-node agent, then swap the model **per node** and measure which nodes actually
depend on a frontier model and which are as good on a local 1.7B or 8B.

- **The article.** "We ran the same agent twelve ways. One node needed the big model. The bill
  fell by most of it." Every team is paying frontier prices for every step on a hunch.
- **Exercises:** variant comparison, per-node metrics, both adapters at once, and **both cost
  bases** — the hosted arm prices in tokens, the local arm in device-seconds, which is the
  comparison the library is unusually equipped to make honestly.
- **Ground truth:** whatever the underlying task is. The measurement is the product.
- **Needs:** a per-node model client. That is `plan.md` §2.2's deferred item, named there and
  explicitly not foreclosed.
- **Not a rehash:** the advice "use a cheaper model for easy steps" is everywhere; a per-node
  ablation with intervals over which steps those are is not.

### D2. The disagreement finder

Given two artifacts that should agree, find every place they do not: a spec against its
implementation, API docs against an OpenAPI schema, a contract against the invoice billed under
it, a paper's abstract against its own results tables.

- **The article.** "We injected 200 contradictions and measured how many it found, and how many
  it invented." The invented ones are the headline, and inventing a discrepancy that is not there
  is exactly FT-10.
- **Exercises:** extraction (T1), fan-out, `unknown`, grounding helpers, and it makes false
  confidence the primary metric rather than a secondary one.
- **Ground truth: constructible.** Take a matched pair, inject n discrepancies, and the answer key
  is the injection list.
- **Needs:** nothing.
- **Not a rehash:** document comparison demos show the diff. None of them report the invention
  rate, because none of them have a held-out split.

### D3. Your policy does not cover that

Abstention-first question answering over real policy documents: insurance terms, employee
benefits, university regulations, tenancy law. The valuable answer is frequently absence.

- **The article.** "We built a retrieval agent that is scored on saying no." Motivated by the
  measured 10.2% → 66.1% wrong-answer jump when a model is given insufficient context rather than
  none (§5.6).
- **Exercises:** `unknown` as a first-class value, false confidence measured apart from recall,
  FT-04, intervals.
- **Ground truth:** the document either says it or it does not, so a human labels once. The
  unanswerable half is built directly from **AbstentionBench's six categories** — unknown answer,
  false premise, outdated, subjective, underspecified, unclear intent — which gives the held-out
  split a structure rather than a vibe.
- **Needs:** nothing.
- **Not a rehash:** every RAG demo optimises for answering.

### D4. The agent that waits

Watch a set of pages — regulations, pricing, dependency changelogs — over days, and report only
**material** changes. Suspends between checks and resumes in a different process.

- **The article.** "Our agent's lifespan is three weeks, not thirty seconds." Nobody demos an
  agent that stops and comes back.
- **Exercises:** suspend and resume, `UrlCache`, `HostPolicy`, `read_page`, budgets over a long
  horizon, and consultation to settle what "material" means for this builder.
- **Ground truth: constructible** from a page's real diff history, labelled material or cosmetic.
- **Needs:** nothing strictly. Something has to restart the process, which `simple-agents.md`
  §2.1 says is the project's job by design. Would exercise §3.2.1's supervisor question with a
  real case rather than a hypothetical.
- **Not a rehash:** every agent demo is one process running to completion.

### D5. Ask me three questions

Eligibility triage over a large rule set — grants, scholarships, benefits, visa categories. The
agent must elicit the user's situation to decide, and is **capped on how many questions it may
ask**.

- **The article.** "The agent is scored on how few questions it asks." Accuracy against questions
  asked is a Pareto curve, and it is a genuinely new-looking chart.
- **Exercises:** consultation as a designed interaction rather than a fault path, recorded in the
  trajectory; `unknown`; budgets; and it is the advisory shape (T11) that §12.4 found the
  catalogue had missed.
- **Ground truth:** eligibility is deterministic given a stated situation, so labelled examples
  are personas plus the rule set.
- **Needs:** nothing, though scoring question count as a project metric is exactly the count seam
  `plan.md` §2.1 says has no home.
- **Not a rehash:** chatbots ask endlessly. This one is penalised for it.

### D6. The agent that reads agent trajectories

An auditor over the library's own trajectory format: find where an agent cited a source it never
opened, asserted a value with no supporting tool call, or took an action its declared side-effect
class did not permit.

- **The article.** "We built an agent that audits agents." On-brand for automated red-teaming.
- **Exercises:** `grounding.py`, which currently ships plumbing with no showcase; the trajectory
  format as **input** rather than as exhaust; `runs()`.
- **Ground truth: constructible** by injecting violations into real trajectories, and this
  repository already holds hundreds of runs and 1,127+ manifests.
- **Needs:** nothing.
- **Risk:** self-referential. Reads as inward-looking unless the framing is about auditing *any*
  agent, which then needs the format to be worth adopting on its own.

### 16.0 Refinement to §15.1

`EvalSuite.run` takes `concurrency`, defaulting to 4, and runs rollouts in a thread pool
(`runner.py:246`). §15.1's "nothing runs concurrently" is correct about arms *within* one
pipeline and wrong if read as a statement about an evaluation. A fan-out of 200 items is 200
sequential calls inside one run; an evaluation of many runs overlaps them.

### 16.1 What these avoid

None is a chatbot, a customer-support demo, or a deep-research clone — the three most-built
things in §12.2 and the three most-written-about. D2, D4 and D6 have constructible ground truth,
which is the constraint that made dogfoods #1 and #2 expensive. D1 needs one library addition
that is already named and deferred rather than new.

### 16.2 Rejected by Thilina, 2026-08-10

All six above. *"Too technical, or too industry focused."* The test he set instead: something a
real person, not a startup CEO, says "oh that's cool, I could use that" about.

Recorded because the failure is repeatable. Every one of D1 to D6 was picked for being
*defensible* — clean ground truth, a metric that survives scrutiny. None was picked for anyone
wanting the thing. The consumer register was never searched for; §12 measured what people build
and §16 proposed for a different audience than the one that data describes.

---

## 17. Dogfood spec — the book recommender

Thilina's own candidate, worked up on his instruction, 2026-08-10. His stated blocker was that a
recommender needs user interactions that a single user cannot supply.

### 17.1 The blocker, and why it dissolves

Collaborative filtering needs a crowd. This is not collaborative filtering: the model already
knows about the books, so the work is content-based, and what one reader supplies is not
interaction data but **labels**.

**A Goodreads or StoryGraph export is a labelled dataset of a few hundred examples with real
negatives.** `My Rating` is 1 to 5, `Exclusive Shelf` separates read from to-read, `Date Read`
gives recency, and a did-not-finish shelf where one exists is the strongest negative signal a
reader produces. No other user is required.

### 17.2 The evaluation, and the trap in it

**The task is pairwise.** An example is two held-out books, one the reader rated high and one
low. The agent says which the reader preferred, or `unknown`. Binary, balanced by construction,
and immune to the fact that most people rate generously.

**The trap: a model can score well without modelling the reader at all**, by predicting general
acclaim. It has read a great deal about these books. An agent that always picks the
better-reviewed title would look like it understood someone's taste.

**The control, and it is the whole experiment.** Split the pairs by whether the reader agrees
with the crowd.

| Pair set | Definition | What it tests |
|---|---|---|
| `aligned` | reader's preference matches the direction of the crowd average rating | A popularity baseline scores 100% here by construction |
| `contrarian` | reader preferred the book with the *lower* crowd average | A popularity baseline scores **0%** by construction. Chance is 50% |

**The headline number is accuracy on `contrarian` pairs, against a 50% null.** Anything above it,
with an interval that clears 50%, is the agent modelling this reader rather than the consensus.
That is a claim worth making and it is falsifiable.

### 17.3 Splits, contamination, and the statistics

- **Pairs must be disjoint: each book appears in at most one pair.** Pairs that share a book are
  not independent, and `bootstrap_ci` resamples examples as if they were. This is the same class
  of error `simple-agents.md` §4.2 already records for rollouts, arriving through a different
  door. Disjoint pairing costs sample size and buys a valid interval. A cluster bootstrap over
  books would recover the n, and the library does not have one.
- **Expected n:** 300 rated books gives 150 disjoint pairs, of which the contrarian fraction is
  perhaps a third, so **40 to 50 examples**. The interval will be wide. That is honest, and it is
  precisely the situation FT-06 exists for.
- **Contamination (FT-03): assign whole authors to one side of the split.** Two books by one
  author are near-duplicates of each other as evidence about taste. `Example.source` is what
  `ExampleSet.contamination(threshold=...)` reads, so `source = author`, or the series where a
  book is in one.
- **Recency.** Ratings drift over a decade. Record `Date Read` in `Example.metadata` and report
  accuracy split by era, because a reader at 19 is a different reader.

### 17.4 The pipeline

**Two pipelines, because the profile is computed once per reader and the judgement runs per
example.**

`build_profile`, run once, output saved and passed as input to the second:

1. `read_shelf` — `Deterministic`. Parse the export, apply the split, keep the dev half only.
2. `summarise_batch` — `LLMNode(over="batches")`. Batches of about 30 books to a partial taste
   profile. The fan-out exists because a 150-book shelf plus review text will not fit one call,
   which is `AppendAll(max_input_tokens=...)` territory.
3. `merge` — `LLMNode`. Partial profiles to one `TasteProfile`: themes sought, themes refused,
   prose register, pacing tolerance, form preferences, hard nos.

`judge_pair`, run per example:

1. `gather` — `LLMNode(over="books")` over the two books, producing a `BookEvidence` each from
   descriptions and reviews. Retrieval is a `DocumentIndex` over a public book-metadata dump
   rather than live web search, so the evaluation is reproducible and free after recording.
2. `decide` — `LLMNode`. Profile plus two `BookEvidence` to `Preference(choice, confidence,
   reason)` where `choice` may be `Unknown`.

**There is no `AgentNode`, and that is a result rather than an omission.** Both steps have a path
known in advance. The honest place for agency is a `chase` node for a book whose information is
too thin to judge, which is dogfood #2's missing-measurement shape and hits **DF2-D1** the moment
it needs to accumulate across candidates. Build it second, if at all, and let the measurement say
whether it paid.

**The product pipeline** — the demo a reader actually uses — extends `judge_pair` with candidate
generation and a `select` node applying the obscurity preference, plus an optional `consult` for
what they are in the mood for.

### 17.5 What is measured

| Figure | How |
|---|---|
| **Contrarian accuracy** | The headline. Interval against a 50% null |
| Aligned accuracy | Sanity check. Near 100% means the popularity prior is intact |
| **False confidence** | Picked the wrong book while stating high confidence. The library's own split, applied |
| Abstention rate | How often `unknown`, and accuracy over answered separately from coverage |
| **Obscurity** | `ProjectMetric`, mean of `log10(ratings_count)` over recommended books. An agent that only names bestsellers is useless, and this is the number that says so |

Obscurity fits the existing `ProjectMetric` seam because it is a mean over examples. A *count* —
candidates dropped for having no description — does not, which is
`plan.md` §2.1, hit for a second time independently of dogfood #2.

### 17.6 What the library needs

**Nothing blocking. It can be built today.** What it would exercise or expose:

| | |
|---|---|
| **Per-node model client** (`plan.md` §2.2) | The merge step wants a strong model; `gather` runs over hundreds of books and wants a cheap one. D1's motivation arriving unprompted |
| **Within-pipeline concurrency** (§3.2.1) | `gather` over a large candidate pool is sequential (§16.0). It will be felt, which is better evidence than an argument |
| **A count metric** (random-thoughts item 2) | Second independent project reaching for one |
| **Cluster bootstrap** | Would recover the sample size that disjoint pairing spends. New, small, and the need is demonstrable rather than asserted |
| **DF2-D1** | Only if the `chase` node is built |

### 17.7 Risks to state before running

- **Training-data leakage.** If the reader's reviews are public, the model may have read them.
  Use a shelf that is not public, or check and report it. The contrarian control handles the
  popularity confound but not this.
- **Negative scarcity.** Generous raters produce few 1 and 2 star books. Use relative preference
  within a pair (5 against 3) rather than an absolute threshold, and treat did-not-finish as a
  negative.
- **One reader is one reader.** Every number is about this person. That is the correct scope for
  the claim being made, and it must not be written as though it generalises.

### 17.9 Refocused, 2026-08-10, on Thilina's correction

*"I am not trying to build a better recommender system. I am trying to demonstrate how to build
something that is cool and useful, using this library, and show that it's easy to do."*

**§17.2 to §17.7 optimised for the wrong objective.** The dogfood protocol measures the library,
not the agent: `archive/plan-history.md` §3.3's criterion is a *trivial* agent that passes at tier `evaluated`,
passing rather than good. A wide interval is not a problem to engineer around. Reporting
`71% (95% CI 54 to 84)` honestly is the library working, and it is one paragraph of the article.

**The author confound disappears once the task is "find a new author"**, because author identity
cannot be a shortcut when the author is what is being predicted. §17.3's contrarian machinery,
the disjoint pairing and the cluster bootstrap are all solving a problem this framing does not
have. Kept above as the record of a wrong turn.

**Measured against the real export** (`~/Downloads/goodreads_library_export.csv`, 2026-08-10):
346 rows, 303 rated, no `Average Rating` column, ratings 1★ 4 / 2★ 2 / 3★ 15 / 4★ 79 / 5★ 203,
74 distinct authors, only 4 authors spanning both 5★ and ≤3★, 0 reviews, 0 private notes, 2 DNF,
30 to-read, ISBN13 on 206.

**Candidate generation is free and keyless.** Open Library's search API, unauthenticated:
`?q=subject:epic+fantasy&sort=readinglog&fields=...` returns 3,039 works with
`readinglog_count` as a popularity figure. Sorted by popularity it returns Martin, Tolkien and
Jordan, so **the naive baseline is visibly the boring answer** and the demo gets its contrast for
free. Per-book coverage from a 30-book sample of the shelf: 25/30 matched, 19/30 carried both
rating fields, `ratings_count` median 44 (Open Library's own users, not a crowd),
`readinglog_count` median 249 and max 13,340 (usable as relative popularity).

### 17.10 The product

**Paste your Goodreads export, get authors you have never read, with reasons tied to the specific
books you loved, and an honest "I cannot tell" where it does not know.**

The pipeline, six nodes:

| Node | Kind | What it does |
|---|---|---|
| `read_shelf` | `Deterministic` | Parse the CSV, split loved from disliked, collect authors already read |
| `profile` | `LLMNode` | One call to a `TasteProfile`. 303 titles and authors fit in one prompt |
| `ask` | `Deterministic` + `consult` | Two questions: what are they in the mood for, how far from the usual |
| `find` | `Deterministic` + an Open Library tool | Subjects from the profile, excluding authors already read and the top popularity band |
| `assess` | `LLMNode(over="candidates")` | Per candidate author, a `Fit(verdict, reason, confidence)` or `Unknown` |
| `pick` | `Deterministic` | Rank, diversify, take five |

Plus `Loop(max_iterations=3, then="pick")` on `find` for when too few candidates come back
confident, which widens the subject set rather than lowering the bar.

**No `AgentNode`, and that is worth saying out loud in the article.** Every step's path is known
in advance. FT-11 in practice rather than in prose.

### 17.11 Why it is a good showcase

| Asset | What it buys the article |
|---|---|
| **Cassette** | A reader clones the repository and runs it **with no API key**, replaying the exact recorded run. Almost no agent demo can be run by its readers |
| `to_mermaid()` | The architecture diagram writes itself |
| **Consultation** | The agent asks the reader two questions and the trajectory records them. Most demos never ask anything |
| **`unknown`** | "I cannot tell whether you would like this" as a real answer rather than a hedge |
| Trajectory | "Here is exactly what it did, and why it picked this" |
| Budgets | The run costs pennies and the figure is on screen |
| Popularity baseline | Tolkien, Martin, Jordan. Free contrast, and it is what the agent has to beat to be worth anything |

### 17.12 The evaluation, right-sized

Split by author. Build the profile on the dev authors only, then ask `assess` about held-out
authors: roughly 20 the reader rated 5★ and 8 they rated ≤3★.

- One number, one interval, reported honestly and expected to be wide at n≈28.
- `Example.expected_by_node` labels `assess` directly, which is the per-node accuracy seam.
- Obscurity as a `ProjectMetric`: mean `log10(readinglog_count)` over what it recommends.
- Contamination is by author and `ExampleSet.contamination()` reads `source`.

**One hour of work, one paragraph of the article.**

### 17.13 What it needs

**Nothing from the library.** The project supplies an Open Library tool (a thin `http_fetch`
wrapper, `read_only`) and a `consult` channel that prompts on the terminal.

### 17.8 The article

*"You don't need a million users. You need one person's bookshelf."*

The turn is the contrarian split: **the score only counts the books where this reader disagreed
with everyone else.** Then two axes rather than one, since an agent recommending bestsellers has
told you nothing: right about this reader, and about books they had not heard of.

---

## 18. What later work changed, 2026-08-12

**This document was written 2026-08-09 and 2026-08-10 and nine items have landed since.** Every
claim below was true when it was made and is not now. The sections above are left as they were
written, with a pointer at the four that would otherwise mislead a reader who lands in the
middle of them.

### 18.1 Two blockers are gone, and both were load-bearing

**Orchestrator-workers ships.** §15.1's correction — "an `AgentNode` delegates by calling
*tools*, so a model cannot hand work to a sub-pipeline, and the pattern has no expression" — was
answered on 2026-08-10 by `AgentNode(delegates=[Delegation(pipeline, description=...)])`.
`build-logs/pipeline-as-tool-build-log.md` is the record and `docs/pipeline.md` §2.5 is what
shipped. That correction also said the hole touches **T5 and T11, whose usual implementations
are orchestrator-shaped**, which is the two largest candidates in §13 unblocked at once. The
`random-thoughts-questions.md` line it quotes has closed with it.

**T5's accumulator blocker is gone.** §9.1 marks T5 research → report "**blocked on DF2-D1**",
and §2 records the same dependency as another session's. DF2-D1 closed on 2026-08-09 at the
loop-accumulator sitting, and the finding was that **both shapes were expressible the whole
time**: a probe carried an accumulator round a cycle containing an `AgentNode` with nothing
changed. What shipped was `docs/pipeline.md` §1.3 and §1.4 saying how, plus `keep=`.
`build-logs/loop-accumulator-build-log.md` is the record. T5's row should read expressible.

### 18.2 One "verified and standing" claim no longer stands

§15.1 ends with "One model client serves a whole run, confirmed at `pipeline.py`". **A model is
declared per node** since 2026-08-10, resolving node-first then run, with a cost basis per model
behind it (`build-logs/per-node-model-build-log.md`). This matters to the catalogue rather than
being trivia: a prebuilt can now put a cheap model on its reduction step and a strong one on its
answer, and §16's D1 candidate is about exactly that choice.

### 18.3 G3's safe form is built, so the gap is closed rather than open

§15.2 G3 says a prebuilt that pre-answers elicitation is FT-24 wearing a friendly face, and that
**the safe form is that a prebuilt proposes answers into the brief marked as its defaults, with
the gate still requiring the builder to confirm them**. That mechanism shipped on 2026-08-11 as
the decision surface: six decision kinds recorded under `[decisions]`, each carrying `chose`,
`considered`, `because` and a status, and **FT-30 refuses a gate while any decision is
`proposed`** (`build-logs/decision-surface-build-log.md`). A prebuilt writes its defaults there
as proposals and the builder agrees to them one by one. G3 is a design constraint on a shipped
shape now, not an unanswered question.

Two counts in the same neighbourhood moved: G3's "eighteen questions" is **33**, and G4's "28
generic entries" is **30** (FT-29 at the `brainstorm` stage, FT-30 here).

### 18.4 Three capabilities a candidate depended on now exist

- **Memory ships** (2026-08-10), so §9.2 K4's "in scope, and being built" is built. **Semantic
  recall ships** (2026-08-11). Those are the two things §9.2 names as having to exist before
  automatic memory formation could be the first prebuilt, and both do.
- **Retrieval is materially stronger for T2.** A `DocumentIndex` given an embedding client
  searches by meaning, with the ranking, the fusion, the reranker and the vector store each
  settable (`docs/retrieval.md`). T2's contract is unchanged; what a shipped implementation of it
  would carry is not.
- **A third model client ships** (2026-08-12, Gemini). G2 says a prebuilt has a model dependency
  and must declare what it was measured against; the set it might be measured against is now
  three backends rather than two.

### 18.5 §16 and §17 are spent, and §1 to §15 are not

§17's book recommender **ran as dogfood #3** on 2026-08-10 and 11 and met the ship criterion at
10 of 10. `runs/dogfood-3/findings.md` is the record, and `DF3-D1` is what the pass is worth: the
evaluation's chance rate was about 0.5%. The dogfood half of this document is history. The
survey and the catalogue are live.

### 18.6 The test in G1 is amended, on Thilina's ruling of 2026-08-12

G1 states it as a single bar:

> A prebuilt earns its place by what it brings to evaluation, not by the wiring it saves.

**That is too dogmatic, and the dogfood record is what argues against it.** Thilina's wording:
*"The dogfoods tend to make stupid decisions, so providing right shape for the task is useful in
and of itself. It becomes more than wiring, it could be useful guidance."*

The evidence is on his side and it is already written down. `handoff.md` records that **the
recurring failure mode across all three dogfoods is routing rather than capability**, and
`runs/dogfood-3/findings.md` `DF3-D8` is six decisions the coding agent made alone, the pipeline among
them. A prebuilt that supplies the right decomposition is intervening at the point where every
run so far went wrong, and that is a benefit in its own right rather than saved typing.

**So the test has two limbs rather than one.** What a prebuilt brings to evaluation is one, and
what it settles that a coding agent otherwise settles badly is the other. G1's positioning
tension survives against a prebuilt that supplies **neither** — a graph with no example
contract, no matcher, and no decision it takes off the coding agent is the thin wrapper
`simple-agents.md` §1.2 rules out.

*(Both limbs were measured on 2026-08-12 and neither cleared. §19.7 is what the library can
actually hold, and §19.8 is what the dogfood record actually says, including an equivocation in
the paragraph above this one.)*

---

## 19. Verification pass and reframe, 2026-08-12

Eight parallel passes, run on Thilina's instruction that no figure in this document be trusted
and every one be re-checked against its source that day. `CLAUDE.md` is the standing rule they
were run under: a documented claim is not a measurement, check the thing rather than the tracker.
§15.1 is the precedent, and this pass found more than that one did.

**What survived is the method. What did not survive is most of the sourcing.** The two-axis
framing, the primitive/template split, and the decision to rank by revealed demand were all
sound. The numbers put into that framing were not checked when they were gathered, and six of
them carried the argument.

### 19.1 The third repeatable wrong turn: a ranking built on a number nobody checked

§13 ranks eight candidates, and §12.1 is what reordered §9 into it: *"three populations disagree,
and they disagree systematically"*, with extraction winning two of the three. **The commercial
population is one blog post, and its sample is about twenty-one people.**

`voker.ai/blog/the-state-of-yc-ai-agents-2026` exists, is a primary source, and carries the six
figures §12.3 quotes verbatim. What it does not carry anywhere is a sample size; the full report
is paywalled behind survey participation. **Every percentage on the page is an exact k/21** —
62% = 13/21, 38% = 8/21, 33% = 7/21, 29% = 6/21, 86% = 18/21 — and the one figure with a stated
different denominator confirms it, since "89% handle fewer than 10k conversations per month" is
given as among those in production and 16/18 = 88.9%. At n=21 the 95% interval on 62% is roughly
±21 points, so **"data extraction 62%" and "customer support 29%" are not separable**. The author
is the CEO of a company selling agent analytics, and the post's conclusion feeds that pitch.

**Checked against YC's own directory, the finding inverts.** The directory is a client-rendered
application and its search index refused an automated read, so this is one hop from primary: the
`yc-oss` mirror, rebuilt from the directory, read at `2026-08-12T01:07:53Z`, 6,151 launched
companies. Of the 1,230 companies in the 2025 and 2026 batches, 494 mention an agent in their
one-liner, long description or tags. Within those 494, by keyword over self-description:

| Theme | Share of 494 |
|---|---|
| coding and software engineering | 19.8% |
| research → report | 11.9% |
| sales, outbound, CRM | 11.7% |
| voice | 9.1% |
| browser and computer use | 7.1% |
| customer support | 4.9% |
| **structured extraction, document parsing** | **3.8%** |
| human-in-the-loop, approval, review | 3.8% |
| advisory and recommendation | 3.8% |
| text-to-SQL and analytics | 3.6% |
| retrieval, search, RAG, QA | 2.8% |
| classification and triage | 2.0% |
| summarisation | 0.0% |

**Extraction is 3.8% here against 62% there.** The two measure different things — voker asked
founders to multi-select internal capabilities, this reads outward-facing product copy — and the
keyword classification is ours, so treat the shares as approximate. What is not approximate is
that §12.3's figure cannot carry a ranking, and §13's rank 1 rested on it.

**§12.4's own count was also wrong, in the direction §15.1 predicted.** `awesome-llm-apps` holds
**144 leaf application directories across 12 top-level directories**, not 52 across four. Its
README lists 115 entries across 15 sections and **33 application directories are not linked from
it at all**, so even the README is a floor. 132,264 stars as of today. The one structural fact
worth keeping: **RAG is the largest single directory at 24 of 144**, and there is no directory
for extraction, classification or approval anywhere in the repository.

**Three better demand sources exist and round 2 missed all three.**

| Source | n | Fielded | Top use cases |
|---|---|---|---|
| Anthropic + Material, *The 2026 State of AI Agents* | 500+ technical leaders | late 2025 | data analysis and report generation 60%, internal process automation 48%; 56% plan research and reporting |
| LangChain, *State of Agent Engineering* | 1,340 | 18 Nov – 2 Dec 2025 | customer service 26.5%, research and data analysis 24.4%, internal workflow automation 18% |
| Menlo Ventures, *State of Generative AI in the Enterprise* | 495 enterprise decision-makers | 7–25 Nov 2025 | no agent use-case split |

**Menlo's headline is the one that bears hardest on this document, and it supports the library's
own position rather than the catalogue's**: *"Only 16% of enterprise and 27% of startup
deployments qualify as true agents — systems where an LLM plans and executes actions, observes
feedback, and adapts its behavior — while most are still built around fixed-sequence or
routing-based workflows wrapped around a single model call."* The median deployed thing is a
`Pipeline`. That is independent support for FT-11 and for the three node kinds, and it is an
argument against a catalogue of agentic shapes specifically.

One further figure, from the only large-sample classification of what people bring to a model at
all: Anthropic's Economic Index puts **Computer and Mathematical at 35% of Claude conversations**
in February 2026, and records the **top ten O\*NET tasks falling from 24% to 19%** of
conversations between November 2025 and February 2026. The distribution is flattening, which
argues against any small set covering much of the mass.

### 19.2 §12.2's GitHub counts reproduce, and their limits are now measured rather than asserted

All 22 phrases re-queried today through the same API, one call per phrase, query string
`"<phrase>" in:name,description`, spaced to stay under the unauthenticated cap, with
`incomplete_results` false on every one. **Every count reproduces within −0.4% to +2.5% over
three days, and the rank order is identical position for position.** So §12.2's numbers were
really measured, and the measurement is repeatable. That is worth recording because it is the
only part of §12 that held up.

**What the re-run adds is the limit.** Matching is token-normalised rather than literal, so
`"text to sql"` catches "Text-to-SQL"; substring matches inside longer descriptions inflate
counts, so `openai/openai-agents-js` is counted as a voice-agent repository because its
description ends "…and voice agents"; forks are not deduplicated; and collision rates differ
enormously by phrase. `"abstention"` at 548 is dominated by machine-learning calibration and
anomaly-segmentation research and is roughly 85% off-domain, while `"extraction agent"` at 265 was
clean on inspection. **The counts are ordinal within a family that shares a naming convention and
are not comparable across families.** Never read a gap under about 2× as meaningful, and never
compare an `X agent` phrase against a bare noun phrase.

**Twelve phrases were never queried, and two of them matter.** `text to sql` is **6,400**, nearly
double `sql agent` at 3,433, and §12.2 queried neither the higher one nor noticed the task.
`structured extraction` is **688** against `extraction agent` at 265, so keying the query on the
word "agent" understated extraction by 2.6× — which cuts the opposite way to §19.1 and is
recorded here rather than dropped. Also new: `recommendation agent` 887, `advisor agent` 707,
`summarizer agent` 612, `approval agent` 197, `classification agent` 128, `human in the loop
agent` 115, `report generation agent` 49.

### 19.3 §12.5's practitioner evidence is real and §12.6 over-read six of its figures

Every paper and report exists, and the five-family taxonomy, the sample sizes and the headline
sentences verify. What does not survive is the use each figure was put to.

- **"Measuring Agents in Production", Pan et al.** Real, arXiv:2512.04123, ICML 2026 oral by its
  own comments field. Two attribution problems. The ICML version is retitled
  *Characterizing Agents in Production*, so the title and the venue as cited belong to different
  versions. And **"86 practitioners" is not the survey**: *"We received 306 valid responses"*,
  filtered to *"86 responses that explicitly reported their systems as being in production or
  pilot phases"*. **"70% prompt off-the-shelf models" is 14 of 20 interview case studies**, a
  twenty-case denominator that cannot carry a population claim.
- **The 68% figure, which §12.6 uses to promote T7 from rank 7 to rank 3.** The sentence is real.
  The measurement is *"how many steps their deployed systems execute **within a subtask** before
  requiring human input"*, **N=60**, self-reported rather than instrumented. An agent chaining ten
  subtasks is consistent with it. It is not a bound on trajectory length and it does not say the
  median production agent is short.
- **"Reliability addressed through systems-level design rather than through evaluation."** The
  first half is the paper's. The contrast is not, and it inverts the paper: 74% rely on
  human-in-the-loop **evaluation**, so practitioners do evaluate, by hand.
- **LangChain's figures.** Observability 89% against offline evals 52.4% verifies, as does quality
  as top barrier at 32%. **"48% do not run offline evaluations" and "63% skip online monitoring"
  are arithmetic complements of options in a multi-select** — offline 52.4%, online 37.3% and
  not-evaluating 29.5% sum to 119.2% — so neither complement describes a population. The report's
  own non-evaluating figure is **29.5%**. The second is worse than imprecise: online *monitoring*
  is observability at 89%, so as worded it contradicts the report's headline. **"61% name
  hallucination" does not appear in the report at all**; hallucination appears once, as a write-in
  with no percentage.
- **The persistence finding, which §15.2 G1 composes with into its sharper test.** The abstract
  says what §12.5 quotes. **The measurement is cross-sectional** — share of questions without an
  accepted answer, median hours to an accepted answer, GitHub open-rate, median days to close,
  median age — with no time series, no cohort analysis and no reopen rate. Nothing measures
  maintenance effort. And the paper's own GitHub table contradicts the retrieval half:

  | Topic | Open % | Median days to close |
  |---|---:|---:|
  | Dependencies, installs, imports, environments | 6.5 | 6.0 |
  | **Embeddings and retrieval** | **6.2** | 35.4 |
  | Agent orchestration and invocation semantics | 16.3 | 15.0 |
  | Model–agent–tool interaction contracts | 7.7 | 50.4 |

  On the metric closest to persisting, **retrieval sits below installation**. What carries the
  finding is orchestration and interaction contracts. The claim that survives is "orchestration
  and tool-contract problems close slower than dependency problems", and it does not establish
  that wiring is the cheap half. §19.7 establishes that by measurement instead.
- **§10's Yehudai survey.** The five gaps verify one-to-one against that paper's own Future
  Directions section, and memory is one of
  its four capability dimensions. **Three of the four benchmarks §9.2 K4 attributes to it are not
  in it** — StreamBench, MemBench and LongMemEval appear nowhere in the paper including its
  bibliography. MemoryArena does.

**One 2026 source cuts against §12.6's direction of travel.** VentureBeat Research VB Pulse,
fielded June 2026, n=157 at organisations of 100+: *"66% of respondents already permit some
production deployment without human review, or are building systems intended to do so within the
next 12 months"*, with only 5% fully trusting the automated evaluations informing those decisions
and 23% running real-time quality checks on production answers. It is self-selected and says so,
*"directional, not precise"*. It measures a release-time gate where Pan et al. measures a runtime
one, so the two are not in direct contradiction — but nothing in §12 points the way this does.

### 19.4 §5.3 and §8.1 describe a world that ended, and the ending is the finding

**AG2 shipped the exact artifact this document proposes, and deleted it sixteen days before this
pass.** At v0.14.0, `autogen/agents/experimental/` exported `DocAgent`, `DeepResearchAgent`,
`WebSurferAgent`, `WikipediaAgent`, `ReasoningAgent`, `DoclingDocIngestAgent` and more, as
importable versioned tested classes named after the job. **v1.0.0, released 2026-07-27, removed
all of them**; the package now holds `tools/`, `middleware/`, `policies/`, `orchestration`,
`knowledge/` and `eval/`, and the v0.x line moved to a maintenance repository. **`ag2/eval/` was
built after the task-named agents were removed.** The pairing §8.2 proposes — the unit and its
evaluation together — has never coexisted anywhere.

**Llama Packs did not drift. They were deleted.** §8.1 records the hub "drifting to vendor
integrations" as the observed failure mode of a community-expanded catalogue. The docs now say
the concept is deprecated and the repository archived read-only, `llama-hub` was last pushed
2024-03-01, and the `llama-index-packs/` directory was **removed from the monorepo on
2026-04-03**. The failure mode is worse than drift.

**§5.3's LangGraph list is one major version out of date.** `create_react_agent` carries a
deprecation decorator in its own source, replaced by `langchain.agents.create_agent`. Of the five
things §5.3 names: supervisor is *"no longer actively maintained"* with a migration-away guide,
the reflection package was **archived 2025-03-18**, Trustcall is a third-party repository last
pushed 2025-07-17, and swarm and LangMem have **zero hits in the current 1,025-entry docs index**.
The prebuilt registry page returns 404. `langgraph.prebuilt.__all__` is now eight names, one of
which is an agent and the rest tool plumbing. Missed entirely: `deepagents`, LangChain's current
"batteries-included agent harness", actively developed with its own documentation section.

**§8.1's central claim is partially falsified, and the exceptions are informative.** *"Nobody
surveyed ships a task-shaped unit as a first-class library object"* fails against **txtai**, which
ships `txtai.pipeline.RAG`, `.Labels`, `.Summary`, `.Translation`, `.Entity` and `.Questions` as
importable task-named classes and is healthy at 12.9k stars. It also fails against Microsoft
AutoGen's `FileSurfer`, `MultimodalWebSurfer` and `VideoSurfer`, though that repository has been
stale since 2026-04-15 and Microsoft's active work moved to `agent-framework`, which ships
capabilities only. LlamaIndex core ships several task-shaped query engines. **The claim holds
against** LangGraph, DSPy, Pydantic AI, the OpenAI Agents SDK, CrewAI, smolagents, Google ADK,
Semantic Kernel, Microsoft Agent Framework, Haystack, Agno, Mastra, VoltAgent and PocketFlow. No
`ExtractionAgent`, `RAGAgent`, `ClassificationAgent` or `TriageAgent` exists in any of them.

**The sharper reading, which §8.1 could not reach and §19.9 acts on: every *importable*
task-named unit surveyed has died, and every *copyable* task-named project has lived.** AG2's
classes deleted, Llama Packs deleted, LangGraph's prebuilts archived, against LlamaIndex's 11
templates alive, Mastra's 22, the OpenAI Agents SDK's `examples/research_bot` and
`financial_research_agent`, and n8n's 7,887. The split §8.1 identified is not a gap in the market.
It is an equilibrium the field keeps re-deriving.

**And nobody ships the pairing.** Mastra's `template-chat-with-pdf` is thirteen files with zero
tests, zero evaluations and zero fixtures; `template-text-to-sql` the same. Every framework has an
evaluation kit — AG2's `ag2/eval/scorers/`, LangChain's `openevals` and `agentevals`, Agno's
`agno/eval/`, CrewAI's, VoltAgent's, Strands's, `dspy.Evaluate` — and **not one is bound to a task
unit**. txtai ships task-named pipelines and no evaluation for any of them.

**Three counts corrected in the other direction.** §8.1's LlamaIndex figure **verifies exactly at
4 of 11** (Extraction Agent with Review UI, Invoice Extraction & Reconciliation, Document Parser,
Invoice Extraction), and there are now two retrieval templates rather than one. §5.2's DSPy list
is **eight of fourteen**: `dspy/predict/__init__.py` exports `majority`, `BestOfN`,
`ChainOfThought`, `CodeAct`, `KNN`, `MultiChainComparison`, `Predict`, `ProgramOfThought`,
`ReAct`, `ReActV2`, `Refine`, `RLM`, `Tool` and `Parallel`; signature polymorphism verifies from
source; still no task-named module. And **§8.1 understated n8n by six times**: its templates API
returns **31 task-named categories**, not five, over 7,887 AI templates — AI Summarization,
Classification and Evaluation 3,038; AI Chatbot 1,255; **Document Extraction 969**; AI RAG 734;
Ticket triage 402; Invoice Processing 275. n8n bundling summarisation, classification and
evaluation into one category is the best evidence anywhere that T3 and T4 are one shape in
practitioners' heads rather than two.

**One usage measurement round 2 never found.** LangChain Hub publishes download counts over
10,025 public prompt repositories. Setting aside the generic agent scaffolds, the ranking of
task-specific prompts is `rlm/rag-prompt` at **32,743,125**, then the two text-to-SQL prompts at
5,568,782 and 4,244,184, then map-reduce summarisation at 416,515 and product extraction at
285,172. Retrieval outranks everything by two orders of magnitude.

### 19.5 The technique literature: the mechanisms hold, the numbers and one attribution do not

- **§5.4's five self-consistency gains are a per-task maximum across two models, not one model's
  results.** GSM8K +17.9 holds for both, but SVAMP is +7.6 on PaLM-540B against the +11.0 quoted,
  AQuA +12.5 against +12.2, StrategyQA +6.3 against +6.4 and ARC-challenge +3.5 against +3.9 —
  four of the five are GPT-3 code-davinci-002. **The baseline is few-shot chain-of-thought with
  greedy decoding**, not standard prompting, so these are the gain from sampling and voting rather
  than from adding chain-of-thought. Configuration: 40 samples, averaged over 10 runs, T=0.7.
- **The mechanism is not stale; the magnitudes and the sample count are.** Power-law scaling for
  self-consistency was re-derived in November 2025 and revised in June 2026, with dynamic
  allocation reaching the same quality at 4.8× fewer samples. The 2022 paper's own advice is that
  five to ten paths capture most of the gain. **And the belief that reasoning models obsoleted
  voting is itself false**: work on o1-like models finds longer chains do not reliably improve
  accuracy, that correct solutions are often shorter than incorrect ones on the same question, and
  that parallel sampling with a vote beats sequential self-revision.
- **§9.2 K1's "ships no content: **none**" is wrong.** Wang et al. states the scope limit itself:
  *"self-consistency can be applied only to problems where the final answer is from a fixed answer
  set, but in principle this approach can be extended to open-text generation problems if a good
  metric of consistency can be defined between multiple generations."* **A voting primitive needs
  an answer-equivalence matcher.** For a `Literal` label set that is free; for open text it is the
  whole difficulty, and it is the same seam §19.7 finds the library refuses to fill.
- **§5.5's self-correction split is settled by the paper §5.5 already cites.** Huang et al.'s
  intrinsic results degrade monotonically and not one cell of their tables improves: GPT-3.5 on
  GSM8K 75.9 → 75.1 → 74.7, on CommonSenseQA 75.8 → 38.1 → 41.8, Llama-2-70B-chat on GSM8K
  62.0 → 43.5 → 36.5. Its §6 endorses the extrinsic case explicitly, naming a code executor as
  *"the perfect verifier"*. **So a critique-and-revise unit is negative-value without external
  feedback and defensible with it**, and that distinction is the whole question for K3.
- **Two claims in §5.5 need correcting.** *"Self-Refine's gains on constrained generation can come
  from outputs simply getting longer"* **could not be sourced** in Self-Refine, in Huang et al. or
  in the Kamoi survey, and should not be repeated. The non-monotonicity half is **Madaan et al.'s
  own Appendix H**, not replication work, and their mitigation is to select the highest-scoring
  iteration rather than the last. The citable debunk is Huang et al. §5, and it is about prompt
  design rather than length: against Madaan's reported 44.0 → 67.0 on CommonGen-Hard they
  reproduce 53.0 → 61.1, then add one requirement to the *initial* prompt and get **81.8, falling
  to 75.1 after self-correction**. The survey to cite is Kamoi et al., TACL 2024.
- **Multi-agent debate should not ship beside voting.** Huang et al. Table 7, matched on response
  count: at nine responses, debate 83.0 against self-consistency 88.2.
- **§5.6's AbstentionBench figures verify**, including 35,000+ questions, 20 datasets, the ~24%
  abstention drop for reasoning fine-tuning, the RLVR degradation and the absence of any
  correlation with scale. **The six category names are not the paper's**: they are `Answer
  Unknown`, `False Premise`, `Stale`, `Subjective`, `Underspecified Context` and `Underspecified
  Intent`. The glosses in §5.6 are semantically right and should not be quoted as labels.
- **§5.6's sufficient-context citation names the wrong authors.** Rashtchian and Juan wrote the
  blog post; **the paper is Joren, Zhang, Ferng, Juan, Taly and Rashtchian, "Sufficient Context: A
  New Lens on Retrieval Augmented Generation Systems", arXiv:2411.06037, ICLR 2025.** The autorater
  figure is **93.0% accuracy on a gold set of 115**, not "93%+". *"Improves selective accuracy by
  up to 10 points"* is the paper's **"by up to 2–10%"**, and among answered items rather than
  overall. **The Gemma 10.2% → 66.1% figure is in the blog and not in the paper.** A finding §5.6
  omitted bears directly on any abstention design: *"SOTA LLMs output correct responses 35–62% of
  the time with insufficient context"*, so a hard sufficiency gate destroys a wide band of
  currently-correct answers.
- **§5.1's Anthropic page now carries a staleness banner** — *"Much of the tooling landscape
  described in this post has changed since December 2024."* The five patterns and the simplicity
  guidance verify verbatim; the page's own status has changed, and §5.1 and §8.3 both rest on it.

**The strongest argument for abstention in this document is one nobody wrote down.** Reasoning
fine-tuning degrades abstention by about 24%, verifiable-reward post-training degrades it further,
and scale does nothing for it, while models *"rarely over-abstain"* so recall carries nearly all
the signal. **Abstention is the capability that got worse while everything else got better.** That
is a better argument for do-not-change #6 and for FT-09 and FT-10 than any convergence count.

### 19.6 Source classes A and D, run for the first time

§4.1 marks both **not started**, and §4.1 names class A as "the gap and where the next work goes".

**Class A cannot validate the candidate list, because the category does not exist in the
literature.** Every taxonomy found with a stated methodology classifies by occupation (the
Anthropic Economic Index, O\*NET over 1M conversations and 1M API transcripts), business function
(McKinsey), audience served (Google Cloud's six agent types over 1,302 catalogued use cases:
customer, employee, creative, code, data, security), interface (the MIT AI Agent Index, n=30:
chat 12, browser 5, enterprise 13), or architecture. Five academic surveys were checked and none
proposes a task-shape taxonomy. Anthropic's own customer-stories page filters by Industry,
Product, Company size and Geography and **has no use-case facet at all**. Nobody publishes a
classification by output contract. That is a finding about the space rather than a failure of the
search, and it means §4.1's remaining gap closes as "no such evidence exists" rather than as data.

**Class D is where the answers are, and it settles two of §14's questions.** For each candidate,
what benchmarks exist and whether the scorer is mechanical:

| Rank | Candidate | Scorer | Contract alone gives the matcher? |
|---|---|---|---|
| 1 | **T12 text-to-SQL** | Execution-based. Run both queries, compare result sets. BIRD, Spider, Spider 2.0 | **Yes** |
| 2 | **T3 classification** | Accuracy and macro-F1 against a gold label. BTZSC, LegalBench, Banking77 | **Yes** |
| 3 | **T1 extraction** | Per-field, with the field's declared type choosing the rule and absence carried as `null`. ExtractBench, VAREX. ~~DocILE~~ | **Yes** |
| 4 | T2 RAG with abstention | The abstain decision is a boolean gold label and mechanical; the answer content needs a judge unless answers are spans. SQuAD 2.0, CRAG, AbstentionBench | Half |
| 5 | T7 approval | Mechanical against the action trace. **HiL-Bench** scores it with Ask-F1, rule-based, no judge; τ²-bench checks policy compliance programmatically; PhoneHarness labels `SAFE_COMPLETE` / `CONFIRM_FIRST` / `NEVER_AUTO` | Half — needs a gold blocker annotation the contract does not imply |
| 6 | T5 research → report | Splits in two. BrowseComp is mechanical exact-match; DeepResearch Bench is LLM-judged end to end on four dimensions plus citation accuracy | No |
| 7 | T11 advisory | **τ-Rec's scoring is deterministic, zero LLM calls**, typed catalogue predicates, pass^k — but its user simulator is a model, see the correction below. Only when the recommendation space is enumerable and typed; free prose falls back to expert rubrics, as in HealthBench's 48,562 physician-written criteria | Half |
| 8 | T4 reduction | **No agreed content scorer exists.** SummEval established ROUGE does not track human judgement; SummHay's coverage metric is a model call at r=0.71 against a 0.77 human ceiling | No |

**Two corrections to the table, 2026-08-16 at P3-5's survey, both from reading the full papers
and their implementations rather than their abstracts.**

- **DocILE does not belong in row 3.** Its primary metric never compares two values: both its
  tracks are scored as object detection, by average precision over bounding boxes under a
  character-centre containment rule borrowed from CLEval, with the paper stating that the
  challenge *"simplif[ies] the task ... by only requiring correct localization of the values"* and
  that the leaderboard does not depend on text read-out. Value-level scoring exists only in a
  separate secondary benchmark, and there is no per-field absence state anywhere in it: a missed
  field is a false negative in a detection count. **Row 3's verdict does not rest on it**, since
  ExtractBench and VAREX both score values per field, and ExtractBench is where the design
  actually is.
- **"Fully deterministic, zero LLM calls" is true of τ-Rec's scoring function and not of its
  evaluation.** The user is GPT-5 mini at temperature 1.0, and every constraint including the
  hidden ones sits in that model's system prompt with an instruction never to state them, so the
  reveal barrier is advisory and its leak rate is unmeasured. Reading the implementation also
  corrects the reward: the paper gives `constraint_score × policy_score`, "both in [0, 1]", and
  in `evaluator/constraint.py` and `evaluator/policy.py` each is 1.0 or 0.0, so the product is
  binary. The per-constraint and violation lists attribute a failure; they never soften it.

**§14 item 2 is closed: yes, advisory is evaluable, under one condition.** **§9.1's and §15.2's
suspicion about T7 is falsified outright** by three independent benchmarks. And **§8.2's premise
holds for three of eight candidates, not generally** — "the job is the output schema plus the
example contract plus the matcher" is true for T12, T3 and T1 and half-true or false for the rest.
Note the ranking's shape: **the three candidates whose contract determines their matcher are ranked
6th, 8th and 1st in §13.**

**τ-Rec carries a design worth more to this library than its scores.** Each constraint is tagged
`volunteer` (the user states it upfront), `on_ask` (revealed only if asked) or `hidden` (never
stated, but violations rejected). ~~Performance falls **84.6% → 58.6% → 20%** across the three.~~
That is a mechanically-scored instrument for exactly what consultation exists for, and it is the
first thing found anywhere that could put a number on FT-25.

**Corrected 2026-08-16 at P3-5's survey, against the paper's Table 3.** The struck sentence
misreads it three ways. The rows are **volunteer, mixed and hidden**, not the three tags, and the
strata are **presence-based**: a mixed task is one carrying at least one `on_ask` constraint and
no hidden one, so it still carries volunteer constraints. The task counts are 13, 32 and 15. And
the three figures are **one column of nine**, DeepSeek V4 Flash with no thinking, rather than a
result across models. The paper's own sentence is *"a 4× gap purely from how information is
revealed"*, and that gap is volunteer against hidden. **The finding survives and this framing of
it does not.** [`answer-shapes.md` S4.2](../design/answer-shapes.md#L449) is where the mechanism is read in
full, including the two things a design must not copy from it.

**Licences, which decide §6 item 4's mechanics.** Permissive and safe for code that downloads
rather than bundles: ExtractBench, VAREX, AbstentionBench, BTZSC, HiL-Bench and τ-Rec at CC BY
4.0; τ²-bench, BrowseComp-Plus, DocILE, SROIE and HealthBench at MIT; DeepResearch Bench at
Apache-2.0. Share-alike, which a downloader does not trigger: BIRD, Spider and SQuAD 2.0 at CC
BY-SA 4.0. **Unshippable: CRAG is CC BY-NC 4.0**, and it is the one benchmark whose scoring shape
is right for abstention, scoring a missing answer at 0 and a hallucination at −1. FUNSD is
non-commercial academic. Spider 2.0 costs money to query and BIRD-Interact's ground truth is
released only by email.

**Two shapes are absent from §9 and §13 and one of them is the largest agent task there is.**
**Code and software engineering** is 35% of Claude conversations, one of Google's six categories,
and has the strongest mechanical scorer of any agent task in existence, since SWE-bench Verified
runs the repository's own tests. §9.1 has it at T8 marked "far from the library's lane" and §13
dropped it. **Multi-step transactional workflow under a policy** is the most heavily benchmarked
agent shape that exists — the τ-bench family and WorkBench, scored by final database state plus
required actions plus pass^k, MIT licensed. §9.1 has it at T6 and §13 dropped it too; T7 covers
only its approval gate. Also absent, and worth a decision rather than an oversight: creative and
content generation, data analysis beyond SQL, security triage, scheduling, and translation.

### 19.7 What the library can actually hold, checked against `src/` rather than against these notes

**There is no matcher.** Not no default — no type, no protocol, no built-in, nothing importable.
`matches` is a bare callable with no default, and the refusal
([`runner.py` `EvalSuite.__init__`](../../src/simple_agents/evaluation/runner.py#L255)) is itself
the argument against shipping one: *"There is no default, because what counts as a correct answer
is a decision about the task: whether case matters, whether a longer span containing the answer
counts, whether a date may be written either way."* The names `exact_match` and `exact` appear
only inside docstrings and examples. **So three of the four things §8.2 says a catalogue entry
pairs have nowhere to live**, and two of them contradict positions the library states in its own
refusals: no example set may ship either
([examples.py:416](../../src/simple_agents/evaluation/examples.py#L416), `ExampleSet.from_jsonl`)
refuses a missing file with *"the library ships none: what counts as a correct answer is a decision
about the task"*, and the wheel force-includes only `docs/` and the skill, so there is no
package-data path for a JSONL or a cassette in any case.

**G4 is answered: no, a prebuilt cannot ship its own conformance check.** `CHECKS`
([checks.py:2128](../../src/simple_agents/conformance/checks.py#L2128)) is a frozen module-level tuple,
`run_checks` iterates it and nothing else, there are no entry points and no dynamic import
anywhere in the conformance package, and the check `Context` carries only artifacts, brief and
taxonomy — it cannot read a pipeline object. Adding one touches six places, and because a failure
message is required to be parsed out of `docs/failure-taxonomy.md` rather than written in Python,
**the taxonomy document itself would have to become extensible.**

**G3's mechanism is confirmed built and needs no change.** A decision carrying `chose`,
`considered`, `because`, `kind` and `status = "proposed"` is exactly the state FT-30 refuses to
advance past. The statuses are four, not three: `proposed`, `agreed`, `changed`,
`not_applicable`. **What the brief cannot do is record provenance** — `BriefEntry` has no field
distinguishing a supplied default from the builder's own answer, and FT-24 reads only whether the
status is `answered`, so anything writing defaults into `entries` passes with nobody asked.

**A prebuilt would pre-answer 8 of the 33 questions, propose 7 more, and cannot touch 18.** It
settles `agency_boundary`, `answer_form`, `presentation`, `tool_effects`, `unproven_answer`,
`consultation`, `unknown_literal` and `context_limit`. **The 18 it cannot touch include every
`brainstorm` question**, plus `ground_truth`, `absence_vs_error`, `who_labels` and `leakage` —
which is where the design failures actually happen.

**Saved wiring is measured, and §14 item 1 closes on it.** Across five real projects a pipeline
definition runs **3 to 8 lines per node and is 6 to 20% of the file it lives in**. dogfood-1's
entire retrieval-QA-with-abstention graph is 20 lines over 4 nodes; dogfood-4's `agent.py` is 1,008
lines of which about 55 is the pipeline. **A prebuilt saves 20 to 40 lines out of a thousand.**

**And the content ratio runs against `simple-agents.md` §1.6 hardest for the cheapest candidates.** T3 is
roughly 90% task content — the label set, each label's description, the prompt — and T1 roughly
80%, since a schema's field names and every `Field(description=...)` are sent to the model
verbatim. T12 has the highest ratio of project code to library machinery of the eight: the library
supplies the loop and the contract and none of the database.

**Four claims in §9.1, §15.1 and §15.2 are corrected.**

- **"Consultation ships and nothing has ever used it" is false**, and §9.1 calls T7 "the anomaly
  worth staring at" on that basis. **dogfood-3 and dogfood-4 both use `consult`**, registered on
  their agentic node, with real `consultation` records in their trajectories. dogfood-2 recorded
  having no consult tool as an *answered* brief entry rather than an oversight. **What is genuinely
  unused is suspension and resume** — no `Suspend`, `.resume(`, `suspend_before` or `suspensions(`
  anywhere in any dogfood project, and no `suspension.json` in any run directory. Both dogfood
  consult channels return `None` rather than raising `Suspend`, which is why.
- **`consult`'s answer is untyped and `options` is unenforced.** The channel is
  `Callable[[str, Sequence[str] | None], str | None]`
  ([consult.py:51](../../src/simple_agents/builtins/consult.py#L51), `ConsultChannel`), and the tool
  resolves only `None` to `declined`. A reply outside `options` is accepted. So an
  approve / reject / amend outcome is a string the project parses itself, which is the one
  candidate-adjacent gap with external precedent behind it (§19.6).
- **§15.1's "nothing runs concurrently" and §16.0's correction are both partly right and are now
  in one place.** `archive/plan-history.md` §1.12 carries it, and concurrency was scheduled on 2026-08-12 and
  built on 2026-08-13. §15.2 G5 is closed as narrowed: T4 and T5 ship a known-slow *run*, not a
  known-slow *evaluation*.
- **§15.2 G2 is reframed rather than closed.** A prebuilt would carry a model dependency, but the
  library **already ships thirteen tools whose descriptions are model-facing prompt text and has
  never declared what any of them was measured against.** That is an existing exposure rather than
  something a new artifact would introduce.

### 19.8 The two limbs of §18.6, measured

**Limb 2 rests on an equivocation, and it is in §18.6's own paragraph.** `handoff.md`'s sentence
— *"the recurring failure mode across all three dogfoods is routing rather than capability"* —
means **documentation routing**: the library had the capability and the coding agent did not reach
it. Every use of the word in all four findings records carries that sense, beginning with
`runs/dogfood-1/findings.md` D4, where `document_search` was reimplemented line for line and the fix is
called "the routing fix". **Not one instance refers to pipeline decomposition.** §18.6 cites it
for decomposition.

**Classified over all 52 numbered findings in the four completed records:**

| Category | Count |
|---|---:|
| Library defect or missing capability | 23 |
| Documentation gap, not routing | 14 |
| Documentation routing — shipped but not found | 7 |
| Bad number or library-supplied default | 3 |
| Evaluation or measurement design | 3 |
| Decision surface absent | 1 |
| **Wrong pipeline decomposition** | **1** |

One numbered finding in 52, or three in 54 counting two unnumbered incidents. **Three of the four
runs report nothing at all in the "things the builder wanted to volunteer and was never asked
for" category**, answered by Thilina directly at each sitting. `archive/dogfood-absorption.md`'s cold audit
of three projects produced nine items and **all nine are capability, none a decomposition**. And
`runs/dogfood-3/findings.md` §6 files the very pipeline `DF3-D8` names under *what did not go wrong*:
agency was justified per node, the builder chose it, and it was the third run in a row to land on
structured-data-first with the agentic node late.

**The two incidents that do support the limb are both wiring details inside a graph rather than a
graph's task identity.** Run 2 of dogfood #1 had a cycle reading its working set off an edge that
stays resolved at the value which entered it, losing 29 passages across 20 examples. And dogfood
#4's terminal node was named `argue`, with a schema carrying `argument`, `risk` and `fit` and **no
field meaning no**, so a book that should not be recommended could not be rejected. A prebuilt
carrying a fold node, or a verdict schema with a reject branch, prevents each precisely. Neither is
an argument for indexing by task.

**Dogfood #4 is still running and everything from it here is provisional.** Its build log, brief
and project files were read on 2026-08-12 as a mid-run snapshot. What does not depend on the run
finishing is Thilina's own note in `random-thoughts-questions.md`: *"The design stage is still
subpar. The coding agent made decisions that it didn't run by me and ended up with a hilariously
bad design."* **That is a fourth run failing on design after the decision surface shipped**, and
the run's own diagnosis places the failure at the `brainstorm` gate rather than at the pipeline —
a scope narrowing that was never a decision entry at all. **A task-shaped "book recommender"
prebuilt is a stateless discover-enrich-rank-present graph, which is the narrowing the builder
rejected.** It would have ratified the error rather than prevented it.

### 19.9 What was decided

**§6 item 4 — a measured number may be published, in the repository and never in the wheel.**
Thilina, 2026-08-12. Benchmark code and its results are a maintainer artifact: nothing
force-included, nothing a builder can inherit as a default, no data bundled. `simple-agents.md` §1.6 is
untouched, because the reason a shipped dataset teaches the wrong lesson is that it becomes the
obvious thing to evaluate against, and a number the builder cannot adopt does not.

**Item 1 is reframed from prebuilt shapes to example projects.** Thilina, 2026-08-12: *"maybe we
should also think about shipping example projects. So reframing prebuilts as examples of how to
build something for a particular task."* The evidence behind it is §19.4's sharper reading —
importable task-named units die, copyable task-named projects live — and the fact that an example
project sits on the **project** side of `simple-agents.md` §1.6, so the matcher, the example set and the
failure modes are content it may legitimately hold. That dissolves §19.7's three blockers at once,
and G4 stops mattering because an example simply passes the eleven generic checks.

**The purposes: all three, distributed across the set rather than crammed into each.** Thilina,
2026-08-12: *"it needs to be all three. But it doesn't need to be all three in one example or all
three in every example."* The three are proof that the loop works end to end, teaching how the
pieces fit, and a starting point to copy. This is the same ruling as §6 item 2's on shipping units,
applied to a different artifact: settled on merit and scenario, not doctrine.

**The material: written deliberately, not promoted from the dogfoods.** Thilina, 2026-08-12.

**Rot is a property of the task rather than of the example, and a cassette is the defence for
now.** dogfood #2 did not rot because it was written badly; its ground truth lived on retailers'
live pages, and its verdict was *"the agent works and the market does not have the data"*. Ground
truth in a bundled database, a committed corpus, a fixed label set or a held document set does not
rot; ground truth on the live web does. **Thilina's ruling is that a web-research example ships
anyway, with its cassette as an explicit "for now" defence**, which also means the example is
evaluable offline and replays for free — machinery no surveyed template gallery has.

**The set, as it stands on 2026-08-12.** Six, each declaring what it is for. Tasks were argued
from §19.6's scorer ranking and §19.1's corrected demand rather than from §13.

| Task | Purpose | Why it is in |
|---|---|---|
| **Text-to-SQL over a bundled database** | proof | The best scorer of the eight: execute both queries and compare result sets, no judge and no reference text. Cannot rot. Undermeasured until §19.2 |
| **Extraction, with enough nodes to show a graph** | proof | Thilina's addition: *"a bit more complicated than just 'read this doc and summarize' so we have a few nodes and a nice graph to show off."* Contract determines the matcher; clean licences |
| **Classification into a fixed label set** | teaching | The smallest of the eight at 8 to 15 lines. Exercises `allow_unknown=False` as a recorded waiver, which is documented and never shown |
| **Retrieval QA with abstention over a committed corpus** | starting point | The highest-usage artifact found anywhere, and the one candidate with a live literature argument rather than a popularity one (§19.5) |
| **Research → report** | starting point | Strongest demand signal in every population measured. **In on Thilina's ruling against the rot argument**, with the cassette as the stated defence |
| **An approval gate on an irreversible action** | proof | The library's largest never-exercised surface: `Suspend`, `resume` and `suspensions()` all ship and no project has used one (§19.7). Mechanically scorable (§19.6) |

**The set covers a judged criterion and a panel of judges.** Thilina, 2026-08-18, at the `P3-12`
sitting: *"some of the examples that we want to ship should include the judge, panel, etc. case so
that we would be covered on both fronts."* It is a property two of the six carry rather than a
seventh task, because a judge is a scoring technique and every task above already has a shape.
`P3-12` ships the seam and no default judge, so a project has to write the judging pass itself,
and an example is where a builder sees one written: what the pass is given, how a panel votes,
and how the judgements reach `evals/judgements.jsonl`. **Research → report is the natural home for
the judge**, since it is the one task whose answer is prose with no key, and **the panel belongs
where a single judge would be contestable**, which the build picks from the two. Neither changes
the task list or §19.6's scorer ranking.
[`archive/a-recorded-judgement.md`](../archive/a-recorded-judgement.md#L1) is the seam.

**One example project is product-shaped.** Decided 2026-08-20 at `P3-30`'s sitting: a real
surface invoking the agent, with a consultation surfacing in it, because an example is what
proves `docs/product.md`'s invocation story runs (a request as `run` under `with_live()`,
`Suspend` across the surface, `resume` on the answer). Like the judge above it is a property one
of the set carries rather than a seventh task, and the build picks which; the approval gate is
the natural candidate, since its `Suspend` and `resume` are the same seam.
[`build-logs/the-product-build-log.md`](../build-logs/the-product-build-log.md#L1) carries the sitting.

**What is still open.** How a maintained example set is kept honest over time — whether examples
run in continuous integration, how they are versioned, how one is deprecated — is not researched
and is the one design question a set of six raises that a set of zero did not. §6 item 5, the
name, is moot for as long as nothing ships as a catalogue.
