# Failure taxonomy

The characteristic failures of coding agents building agents.

This document is the spec from which the conformance suite is derived. Every entry either maps to a conformance check or is marked as one that cannot be checked.

**Vocabulary is fixed.** *Builder*, *coding agent*, *project*, *agent*, *end user*, *elicitation*, *consultation*, and *the brief* each mean exactly one thing throughout these documents. Read this before `docs/trajectory-format.md`, which specifies the record shape several of these checks read, and `docs/run-envelope.md`, which specifies the manifest, the cassette, and the redaction rules the rest of them read.

---

## 1. How to read an entry

Each entry carries a stable ID (`FT-01`…). Conformance checks, failure messages, gates, and issue reports all cite the ID rather than restating the failure. An ID is permanent: a retired entry keeps its number and is marked retired, and a number is never reused, so a citation written today means the same failure after an upgrade.

```
### FT-nn: Short name
*Surface: … · Tier: …*

**What happens.**              What the coding agent does.
**Why it's wrong.**            What it costs the project.
**What the library provides.** What Simple Agents does about it, and what is left to the
                               project. Present where the library does part of the work.
**Check.**                     What the conformance check asserts.
**Failure message.**           The text emitted when it fires.
```

A failure message is emitted by the check runner and read by the coding agent. Each names what is missing and the next action, and where declaring a lower tier is the correct response, says so. A message citing another entry states the fact it is citing, so reading a second entry is never required to act on the first.

### 1.1 Detection surfaces

Each entry names the surface its check reads. The surface says what a check can see and what it costs to run.

| Surface | Means | Cost |
|---|---|---|
| **static** | Readable from the project's source without executing it: AST inspection, config reading, registry introspection at import time. | Cheap. Runs in a pre-commit hook. |
| **artifact** | Readable from files the project produces: the brief, the manifest, trajectory logs, eval results, the example set. | Cheap, but requires the project to have been *run* at least once. |
| **runtime** | Requires executing something: the envelope refusing to construct, the eval runner refusing a tool, a fuzz pass, a network-disabled CI run. | Expensive. Reserved for entries where nothing cheaper works. |
| **elicitation-only** | Not mechanically checkable. Enforced only by a required question in the brief. | Free to check *occurrence*, impossible to check *substance*. |

An `elicitation-only` entry still gets a gate, and the gate is an `artifact` check: the brief must carry an answer to the required question. It checks that the question was answered, not that the answer is right. Two checks go one step further and read an answer's text, and neither judges it: FT-25 reads whether the `consultation` answer opens on a negation, and FT-32 whether the `tool_effects` answer mentions each class of effect the run declares.

### 1.2 Tiers

Gates fire only when the project claims the tier or higher. Tiers are cumulative: `evaluated` includes every `prototype` gate.

- **`prototype`**: hygiene that costs nothing and whose absence makes the project undebuggable. Applies to everything, including throwaways.
- **`evaluated`**: the project makes a claim about how well it works. Everything about measurement lives here.
- **`trained`**: the project optimizes against a reward. RL-specific hazards only.

A check that fires on a project that never claimed its tier is a bug in the check. Report it rather than working around it.

---

## 2. Group A: Evaluation exists and is honest

### FT-01: No evaluation at all
*Surface: artifact · Tier: evaluated*

**What happens.** Success declared from a demo run, or from a handful of manual spot-checks the coding agent performed and eyeballed. No labeled set, no scoring function, no results file.

**Why it's wrong.** A demo is a sample of size one, drawn by someone who wants it to pass, on an input chosen after seeing what the agent does. It says almost nothing about behaviour on inputs nobody selected.

**What the library provides.** `simple_agents.evaluation` ships the example set, the runner, the metrics and the results file. The project has to supply the examples, their labels, and the comparison that decides whether an answer is right. No dataset ships with the library, because what counts as ground truth is task-specific.

**Check.** For a project claiming `evaluated` or higher: a labeled example set exists, a scoring function exists, and an evaluation results artifact exists that was produced by running the second over the first.

**Failure message.**
> No evaluation results found, but this project claims tier `evaluated`. A demo run is a single input chosen by someone who wanted it to pass, so it does not measure behaviour on inputs nobody chose. Create a labeled example set, define a scoring function over it, and run the evaluation. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-45: The number was measured over a pipeline the project does not declare

*Surface: artifact · Tier: evaluated*

**What happens.** The evaluation runs over a pipeline assembled inside the evaluation script: one node lifted out of the agent, or a graph that exists nowhere else. It scores, it produces a results file, and every other evaluation gate passes on it. The number then travels into the brief as the project's figure. One project measured retrieval recall this way and recorded it as its headline, until the builder said the figure was supposed to be about the final recommendation.

**Why it's wrong.** A figure is about something, and what it is about is the pipeline that produced it. A pipeline built inside the evaluation is not one the project runs, so the number describes a graph no end user ever meets. What the file records is a `graph_fingerprint`, a digest rather than a name, which matches no pipeline anybody can look up. Every check about how the number was measured passes, so the gap shows nowhere.

**What the library provides.** `@pipeline_factory("recommend")` names a pipeline, and the name travels onto the pipeline the factory builds, onto every run's manifest under `pipeline`, and into a results file's `config` (`docs/pipeline.md` §1.15). An evaluation over a rung of a registered pipeline, taken with `Pipeline.slice`, keeps the name of the pipeline it came from, so measuring one step at a time is not what this reports.

**Check.** The results file's `config.pipeline` names a pipeline. A file written before the field existed carries none and reports blocked, which is what re-running the evaluation clears.

**Failure message.**
> The number in `<results>` was measured over a pipeline this project registers nowhere. A pipeline is registered by `@pipeline_factory("<name>")` on the function that builds it, and the name then travels onto every run and into the results file. This file records none, so the graph it measured was built somewhere the project does not run: an evaluation script, or a node lifted out of the agent. Register the pipeline the figure is meant to be about and re-run the evaluation over it. Where the figure is about one step rather than the whole agent, take that step with `pipeline.slice(...)`, which keeps the name of the pipeline it came from.

### FT-02: No held-out split
*Surface: artifact · Tier: evaluated*

**What happens.** One pool of examples, used for development and for the reported number.

**Why it's wrong.** Every prompt edit made after looking at an example fits the agent to that example. A number reported over the same pool measures how well the agent does on examples it was tuned against, and says nothing about examples it has not seen.

**What the library provides.** Every example declares the split it belongs to, and one constructed without a split is refused. The set names which of its splits is the held-out one, as `ExampleSet(examples, held_out="held_out")`, and the results file records the name, so a project whose splits are called something else is read correctly. The project has to decide where the split falls and which side may be inspected.

**Check.** The example set declares at least two splits, one of which is the named held-out split, and that split is non-empty.

**Failure message.**
> The example set has no usable held-out split: `<reason>`. Every prompt or config change made after looking at an example fits the agent to that example, so a number reported over those same examples measures memorization, not performance. Partition the set into a dev split that may be inspected freely and a held-out split that may not, and report only the held-out number. The held-out split is named on the set, as `ExampleSet(examples, held_out="held_out")`. Partitioning alone does not prevent a leak: check also that no held-out example duplicates or paraphrases a dev example (FT-03). If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-03: Development examples leaked into the held-out set
*Surface: artifact · Tier: evaluated*

**What happens.** A split exists, but examples appear on both sides: copied, near-duplicated, or drawn from the same source document.

**Why it's wrong.** Contamination reintroduces the problem the split was created to solve, while the project still passes FT-02. The common cause is ordinary: examples generated in two batches, and the second overlapped the first.

**What the library provides.** Two examples cannot share an identifier, so the same example appearing in two splits is impossible rather than checked for. `ExampleSet.contamination(threshold=...)` covers what is left: the same content under two identifiers, and any pair sharing a `source`. The threshold has no default, because what counts as too similar depends on the task. `EvalSuite.run` runs the check before the first rollout and refuses a contaminated split, so the finding arrives before the rollouts are paid for rather than in the results file they produced.

**Check.** The contamination report in the results file holds no pair spanning two splits. The threshold is the one the project declared, and an evaluation that declared none ran no check, which the report says rather than failing.

**Failure message.**
> `<n>` held-out examples duplicate or closely match dev examples. Contamination undoes the split silently: the project passes the split check while still reporting memorization. Remove the overlapping examples from the held-out split, or regenerate the held-out split from a source the dev split never touched. The threshold applied was `<threshold>`, recorded in the brief. If it is wrong for this task, change it there. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-04: Happy path only, no absent-data cases
*Surface: artifact · Tier: evaluated*

**What happens.** Every eval example is one where the answer exists and is findable. Nothing tests what happens when the information is genuinely not there.

**Why it's wrong.** For extraction and retrieval agents, the absent case is where the dangerous failure lives, because it is where a model invents a plausible value. A set with no absent cases scores an agent that always guesses *higher* than one that reports absence, because abstaining costs it a rollout and there is no example on which abstaining is correct.

**Check.** The held-out split holds at least one example whose ground truth is `unknown`, or one whose answer key declares a condition whose right answer is absence (`Criterion(expects_absence=True)`, `docs/evaluation.md` §1.6). A pipeline that declares `allow_unknown=False` on every node producing the scored answer has stated that this output has no absent state, and the check does not fire.

**Which node that is** comes from the graph the results file records: the pipeline's last unit, and where that is a pipeline used as a node, its last unit in turn. Where the last unit calls no model, the model-calling nodes that feed it, since a `Deterministic` step assembling an answer carries no declaration of its own. A step on the way to the answer may have an absent state of its own, a lookup that finds no review or a match that does not resolve, and declares nothing.

Where the answer is a record, the absent case is usually one empty field rather than an empty answer, so the condition covering that field is what carries the declaration. An example set holding those cases and not declaring them reads to this check as a set with none.

**Failure message.**
> The held-out split contains no example where the correct answer is `unknown`. Without them an agent that always guesses scores higher than one that reports absence honestly, because there is no example on which reporting absence is correct. Add examples where the information is genuinely absent, labeled `unknown`, and read the false-confidence rate beside the abstention rate (FT-10). Where the absence is one field of a record rather than the whole answer, declare it on the condition that covers that field: `Criterion(id=..., text=..., expects_absence=True)`. If absence is impossible for this task, say so where it is enforced: `allow_unknown=False` on `<node>`, which is what produces the scored answer here; a step on the way to it may report absence of its own and declares nothing. What the builder said about this, in the brief's `absence_vs_error`: `<said>`. The evaluation records what each node declared under `config.nodes` in its results file and what each example declared under `examples`, which is what this check reads.

---

### FT-37: The reported number came from a pipeline the project no longer has

*Surface: artifact · Tier: evaluated · Stage: ship*

**What happens.** An evaluation runs, its file goes into the brief's `results` key, and the pipeline keeps moving underneath it. Prompts are edited, a node is added, the model is swapped. The file still holds a held-out split, seeds, intervals and absence cases, so what it says about the measurement stays true while what it describes stops being the code, and the project ships reporting a number for a pipeline it has replaced.

**Why it's wrong.** Tier `evaluated` is the claim that the project reports a number, and a number describes whatever produced it. Once the pipeline has moved, the figure describes something the project does not have, and nothing in the file says so. The results file records `graph_fingerprint`, which is the shape alone, so an edited prompt, a moved temperature or a swapped model leaves it identical, and the number can be several versions old with every gate green.

**What the library provides.** `EvalSuite` writes `config.behaviour_fingerprint` into every results file: the shape, every prompt's version, every `Deterministic` node's function version, the sampling parameters, every tool's version and declared cost, the model, `allow_unknown` and the budgets, for the leaves and for every pipeline used as a node. Each run's manifest carries the same value, so the two compare without opening any code.

**Check.** From stage `ship`: the results file's `config.behaviour_fingerprint` equals the one in the newest run of the pipeline that results file measured, over the same nodes (`docs/conformance.md` §3.8). Before `ship` the report carries the same comparison as a note. A pipeline moves several times an hour while it is being built, and what clears this is another evaluation. A results file written before the field existed is `blocked` and says so. It compares two digests, so it says that the pipeline moved and never which part of it moved.

**Failure message.**
> The number this project reports was produced by a pipeline it no longer has. The results file `<results>` records `behaviour_fingerprint` `<measured>`, and the newest run of that same pipeline records `<current>`. A prompt, a node's version, a sampling parameter, a tool, the model or a budget has moved since that file was written, and tier `evaluated` is the claim that the project reports a number for the code it runs. Re-run the evaluation against the current pipeline and point the brief's `results` key at the new file. Where the figure is meant to describe an earlier version of the pipeline, say so in the brief beside the key, since nothing else on disk records that intent.

## 3. Group B: Statistical discipline

### FT-05: Single rollout per example
*Surface: artifact · Tier: evaluated*

**What happens.** Each example run once. Agents are stochastic; the result is one sample from a distribution reported as if it were the distribution.

**Why it's wrong.** Run-to-run variance on agent tasks is routinely larger than the difference between the two agent versions being compared. At k=1 an improvement cannot be told from a coin flip.

**What the library provides.** The runner takes `k`, runs that many rollouts per example at derived seeds, and records `k` in the results file beside every metric. The project has to choose the value.

**Check.** The results artifact records k rollouts per example with k at or above the threshold declared in the brief, and the threshold is not 1.

**Failure message.**
> Evaluation ran `<k>` rollouts per example, below the `<threshold>` declared in the brief. Agents are stochastic, and run-to-run variance is routinely larger than the effect being measured, so a single rollout cannot distinguish a real improvement from noise. Set k in the brief. Start at 5 and raise it if the interval is too wide to act on, and re-run. Pair this with FT-07 so the rollouts are reproducible. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-06: Point estimate with no interval
*Surface: artifact · Tier: evaluated*

**What happens.** "87% accuracy." No confidence interval, no variance, no n.

**Why it's wrong.** 87% over 15 examples and 87% over 1,500 are different claims, and a bare percentage does not distinguish them. Comparing two versions on point estimates alone supports conclusions the data does not.

**What the library provides.** Every metric the library reports carries a confidence interval and the n it was computed over, and names the calculation that produced it. The interval resamples examples rather than rollouts, so k rollouts of one example do not read as k independent observations. Where every example scored the same, resampling has no variation to read and the metric is a proportion, so the interval is Wilson's: 30 of 30 correct reports a range rather than certainty. A metric whose denominator is empty reports no value and says why, rather than reporting zero. A figure that is one total over another takes its interval by resampling examples and summing both totals inside each resample (`docs/evaluation.md` §11.7).

**Check.** Every reported metric carries a confidence interval and the n it was computed over, or a declared reason for having none. Two figures have one. A metric that reports no value at all states why instead: recall over a split where every answer is absent has no denominator, so there is nothing for an interval to be computed over. And a figure the project declared a count over this run rather than an estimate of a rate reports its totals and its reason (`docs/evaluation.md` §11.8). A figure that reports a value and declares neither fails, whatever text it carries.

**Failure message.**
> Metric `<name>` reported without a confidence interval. A bare percentage does not carry the sample size it was computed over, so two versions cannot be compared and a difference cannot be told from noise. Report the interval and n alongside every metric. A wide interval is a finding: widen the eval set rather than dropping the interval. A figure that is a count over this run rather than an estimate of a rate declares that, and reports the totals behind it. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-07: Seeds uncontrolled
*Surface: artifact · Tier: evaluated*

**What happens.** No seed recorded per rollout, so a result cannot be reproduced and a surprising trajectory cannot be re-run.

**Why it's wrong.** This is distinct from FT-05: a project can run k=20 and still be unable to reproduce any individual rollout. Without seeds an interesting failure found in the results is gone, and the difference between two eval runs cannot be attributed to a change rather than to sampling.

**What the library provides.** The envelope generates a run seed when none is given, and derives each call's seed from the run seed, the node id, and the index of the call within the node. One run seed therefore reconstructs every call seed in the run, and two calls from the same node do not sample identically.

A recorded seed makes the request identical and says what sampling was asked for. It does not make a hosted backend return the same response: a seed there is best-effort, and batching makes identical requests diverge. Reproducing a rollout means replaying its cassette rather than re-running it live at the same seed. The manifest's `cassette.diverged` counts how often a backend answered a repeated request differently, which is the measurement of how much this applies to a given provider.

**Check.** Every `node_execution` record of a node that samples carries a seed, every `model_call` record carries the seed that was sent to the backend, and every rollout in the results artifact records the seed it ran at. A `deterministic` node records `null` and passes, since it does not sample, and so does a node the run routed around, whose `termination` is `skipped`. A `tool_call` and a `consultation` carry no seed field at all (`docs/trajectory-format.md` §2).

**Failure message.**
> Rollouts recorded no seed, so no individual run can be reproduced. A surprising failure in the results cannot be re-run, and two eval runs that differ cannot be attributed to a change rather than to sampling. Record the seed on every rollout as part of the trajectory record. Combined with the cassette, which serves each call from a recording rather than from the backend (FT-21), this makes a recorded run replay identically. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-08: End-to-end metrics only
*Surface: artifact · Tier: evaluated*

**What happens.** One number for the whole pipeline. No per-node breakdown.

**Why it's wrong.** A single end-to-end score reports that the agent got worse and nothing about where. Localizing the regression then means bisecting by hand through prompt edits.

**What the library provides.** Per-node metrics are read out of the trajectories every run already writes, so they need no labels and no extra instrumentation. Each node reports executions, errors, model calls including the ones its tools made, tool calls, consultations, replayed calls, wall clock, tokens, cost, how it terminated, and how often its output reported an absence. It also reports `reach`, the rate of rollouts that ran the node at all, with an interval: in a graph a node does not run on every rollout, and every other figure on that node is over the rollouts that reached it.

**Scoring a node for accuracy needs a label for that node, and the project supplies it.** `Example.expected_by_node` carries it and `EvalSuite(node_matches=...)` says how it is compared. Given those, the library supplies the denominator, which is the rollouts that reached the node and carry a label, and the interval over it. A node no example labels reports no accuracy, and nothing is refused for want of one: ground truth about a node's own output is a fact about the task, and most projects have it for one node or for none.

**A step can also be evaluated on its own.** Per-node accuracy scores a step on the inputs it actually received, which is the thing under suspicion when the end-to-end number is low and every step looks fine. `Pipeline.slice` returns part of the graph as a pipeline, so the last step runs alone on ideal inputs, then the last two, and the rung where the number falls is the step that lost it (`docs/evaluation.md` §5.6).

**Check.** The results artifact contains per-node metrics for every node in the pipeline, not only a terminal score.

**Note.** `simple-agents check` reports, at tier `evaluated`, a project where no node carries a figure of its own: no example labels a node, `node_metrics` declares nothing, and no run was made by a slice of the pipeline as it now stands. It reports and never fails, because the per-node section is computed out of the trajectories with no project effort, so its presence says nothing about whether the project localised anything. A labelled node, a per-node figure or a slice evaluation clears it, and a slice clears it while it was taken of the pipeline the project has.

**Failure message.**
> Only an end-to-end metric was reported. When the number drops it identifies no node as the cause, leaving hand bisection through prompt edits as the only way to localize the regression. Record per-node metrics: the run envelope already captures the per-node data needed, so this is a reporting change rather than an instrumentation one. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

### FT-09: Output schema admits no `unknown`
*Surface: static · Tier: prototype*

**What happens.** The typed output schema has no representation for "the information is not there." The agent's only options are a value or an error.

**Why it's wrong.** An agent that structurally cannot say "I don't know" says something else, and that something else is a guess presented with the same confidence as a real answer. Adding the variant later means revisiting every consumer of the output.

**What the library provides.** `Unknown` is a distinct value in the schema, carrying an optional reason. `null` and `""` are never read as absence when a trajectory or a results file is read back (`docs/trajectory-format.md` §5.1), so neither can stand in for it.

**Check.** **Enforced at construction**: for every node whose brief entry marks its output as possibly-absent, an output schema that does not admit `unknown` is refused.

**Failure message.**
> The output schema for node `<node>` has no `unknown` variant, but the brief marks this value as sometimes absent. An agent that cannot report absence will report a guess instead, indistinguishable from a real answer. Add `unknown` as a first-class value in the schema. Do not model it as an empty string or a null: neither is read as absence, so both compare as asserted answers.

### FT-10: False confidence conflated with recall
*Surface: artifact · Tier: evaluated*

**What happens.** One accuracy number that mixes together "found the wrong value" and "failed to find a value."

**Why it's wrong.** Returning `unknown` when the value is not there is recoverable. Returning a confident wrong value is not, because whatever consumes it acts on it. One number covering both hides the second failure behind the first, and optimizing against that number trades the first away for the second. An answer that is partly right is a third result, and rounding it into either bucket is the same averaging one level down.

**What the library provides.** `simple_agents.evaluation` computes eight rates on every evaluation, each over its own denominator and with its own interval: accuracy, graded accuracy, false-confidence rate, partially-correct rate, recall, abstention rate, failure rate, and precision when asserting. The project has to supply the comparison between two asserted answers. Absence on either side is read by the library, so how a rollout is sorted is not a project decision. This check fails only for a project that reports its own numbers.

The same separation applies inside an answer, in both halves. An answer key that is a list of conditions (`docs/evaluation.md` §1.6) sorts an answer meeting some of them into `partially_correct`, which is its own outcome with its own rate, so "met two of three" and "met none" are not one number. And a condition's check reports a wrong value apart from a value the answer never gave: an answer that met none of its key by saying nothing is `missed` rather than `false_confidence`, so a field left empty is not measured as a field invented. A condition the key declares `required` decides that the answer is not partly right; which of the two failures it was is still read off what the answer asserted.

**Check.** The results artifact reports false-confidence rate (asserted a value, value was wrong) separately from recall (did not assert a value, one existed), each with its own interval.

**Failure message.**
> Results report a single accuracy number covering both wrong answers and missing answers. These have different costs: returning `unknown` is recoverable, returning a confident wrong value is not, because whatever consumes it will act on it. Report false-confidence rate and recall as separate metrics with separate intervals. Both rates need examples whose correct answer is absent to be worth reading: without them no rollout can show the agent asserting a value where nothing existed (FT-04). If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

---

## 4. Group C: Agency and shape

### FT-11: Everything made agentic
*Surface: static + artifact · Tier: prototype*

**What happens.** Every step is an `AgentNode`, which requires no decision about control flow.

**Why it's wrong.** Agency costs tokens, latency, variance and debuggability. A pipeline of all `AgentNode`s has no fixed points to evaluate and nothing to ablate, and its variance profile makes FT-05 and FT-06 more expensive to satisfy. Most of what feels agentic is an `LLMNode` inside deterministic control flow.

**Check.** Static analysis enumerates every `AgentNode` in the pipeline. For each, the brief must contain an answered justification entry stating what decision the model makes that fixed control flow could not. Whether the justification is *good* is elicitation-only.

**Failure message.**
> `<n>` of `<m>` nodes are `AgentNode`s, and `<k>` have no justification in the brief. Agency costs tokens, latency, variance and debuggability, and most steps that feel agentic are an `LLMNode` inside a fixed loop. For each `AgentNode`, record in the brief what decision the model makes that deterministic control flow could not, or change the node kind. A node for which that question has no answer should not be an `AgentNode`.

### FT-12: Agency asserted but never ablated
*Surface: artifact · Tier: evaluated*

**What happens.** The pipeline contains `AgentNode`s, the project claims to be evaluated, and no version of the pipeline without that agency was ever measured against it.

**Why it's wrong.** FT-11 records a reason for each `AgentNode` in the brief, and a reason is a belief about the task. Until a cheaper version of the node has been run over the same examples, the project is paying an agent loop's tokens, latency and variance on every rollout with no measurement of what that buys.

**What the library provides.** `compare_variants()` runs the pipeline and a variant of it against the same backend in one session and reports the difference on every metric, with an interval, alongside the cost and tokens each arm spent (`docs/evaluation.md` §10). `ablate()` generates the standard downgrades, one per `AgentNode` and one per removable node. `plan_variant()` says which of a variant's calls the baseline recording already answers before any are made, so a variant that changes no downstream request costs nothing to run.

**Which variants are worth trying is the project's.** `ablate()` produces a starting set, not the set that matters: an `LLMNode` can be the node worth removing, a tool can be the thing worth dropping, and neither is a downgrade the generated set proposes.

**A node with no arm in that set is named in `Ablations.skipped`, with why.** Removing it would feed a node a different declared shape, or leave a graph the pipeline refuses. The reason is what a variant written by hand has to answer, and every `AgentNode` gets its downgrade arm whatever else is skipped.

**A verdict needs 20 examples.** Below that the comparison reports the delta and the interval and names the metric in `undecided`, because a percentile bootstrap over examples that all move the same way returns an interval of zero width. A sweep over a small held-out split measures the arms and concludes nothing about them.

**Read reach alongside the result.** A node that runs on a third of rollouts is compared over that third, so the result covers the runs that reached it and says nothing about the rest. The per-node `reach` reported beside every other figure is what says which third.

**Check.** For a project claiming `evaluated` with at least one `AgentNode`: a written variant comparison exists in which that node is the one that differs, whose baseline records the `graph_fingerprint` the current pipeline has.

**Failure message.**
> `<node>` is an `AgentNode` and no variant comparison covers it. The reason recorded for it in the brief is a belief about the task, and every rollout pays an agent loop's tokens, latency and variance on the strength of it. Run `compare_variants()` over a variant with `<node>` downgraded, which `ablate()` generates, and read the metric deltas beside the cost each arm spent. Comparing a fresh run against an older results file measures the provider instead, so both arms have to run together. If this project is a throwaway, declare tier `prototype` in the brief and this gate will not fire.

---

### FT-35: Steps spent without a tool call
*Surface: artifact · Tier: prototype*

**What happens.** An `AgentNode` spends its whole budget and calls nothing on the way: no tool, no consultation, no delegation, and no `finish`. The node returns `None` to the node after it, the run completes, and no error is recorded anywhere.

**Why it's wrong.** The loop paid for every step and nothing it did survives it. On the wire a tool call, a consultation and a delegation are one namespace shared with `finish`, so a model that chose none of them at any step was shown declarations it could not use: a malformed tool block the server would not parse, a description written for a person, or a prompt that never asks for an action. One project spent 15% of a run's model calls this way, in one node, on a `<tool_call>` block one closing brace short, and every figure it reported said the run was fine.

**What the library provides.** Each run's manifest records what each node produced nothing with, so the check reads every run one pipeline made rather than the newest (`docs/run-envelope.md` §2.8). `node_metrics("runs/")` and `simple-agents report runs/` print the same figures beside what the node spent, and `results.report()` prints them per node for an evaluation.

**What is not this.** An execution that called a tool and then ran out of budget is reported and never failed here: a cap that binds after real work is the cap doing its job, and whether the remedy is the cap or the task is the project's to judge.

**Check.** Over every run made by the pipeline as it now stands, no node has a unit of work that ended on a budget axis or on `finish_rejected` having made no tool call, no consultation and no delegation. A unit is one execution, or one item of a fan-out. `allow_unfinished=True` on the node waives it.

**Failure message.**
> `<node>` produced no output in `<units>` unit(s) of work and never acted in any of them: no tool call, no consultation, no delegation, over `<runs>`. Those spent `<calls>` model call(s) on nothing. A tool call, a consultation and a delegation reach the model as declarations in one namespace shared with `finish`, so a loop that chose none of them at any step was shown declarations it could not use: read what `ctx.describe_tools()` renders into the prompt, and read the tool descriptions themselves, which are prompt text (FT-23). `simple-agents report runs/` prints what each node spent beside what it produced. Where a loop that spends its budget without acting is what this node is for, declare `AgentNode(..., allow_unfinished=True)` and this gate will not fire for it.

---

### FT-28: What a node accepts is undeclared
*Surface: static + runtime (enforced) · Tier: prototype*

**What happens.** A node declares what it produces and nothing declares what it reads. The node before it is changed, inserted or removed, and the node after it is handed a value of a shape its function was not written for.

**Why it's wrong.** It does not reliably fail. A prompt function that interpolates whatever arrived produces a different prompt and a run that completes, so the agent answers a question that was never asked and the trajectory records a successful run. There is no exception to locate and no failed node to read, so the change is invisible in every artifact the project keeps. Where it does fail, it fails inside the node on a line that names neither the edge nor the value.

**What the library provides.** A node's first parameter is what it accepts, and annotating it is the declaration: `def verify(inputs: Notes, ctx: NodeContext) -> str`. A pipeline is refused at construction where a node reads a type nothing reaching it can be, and a run is refused where the value handed over is not that type. The comparison is one-directional: both sides have to be declared and no value able to satisfy both, so a pipeline that annotates nothing is refused nothing. An exception raised inside a node carries a note naming the node and what it was reading. `docs/pipeline.md` §3.1 covers what is compared.

**Check.** **Enforced, not checked**: a pipeline whose declarations disagree does not construct, and a value that disagrees does not reach the node. The declaration itself is never required, so a project buys coverage per edge by annotating one.

**Failure message.**
> Node `<node>` reads its input as `<declared>`, and what reaches it from `<source>` is `<arriving>`. Every run would call this node with a value it does not describe, and a node that interpolates what it was given will produce a prompt rather than an error. Annotate the first parameter with what arrives, or change what the node before it produces. A node receives what the node before it returned, and a node that needs a value produced further back is sent it on its own edge: `docs/pipeline.md` §1.3.

---

### FT-40: A step that was declared and never built

*Surface: artifact · Tier: prototype*

**What happens.** A step was written as `NotBuilt("what it will do")` so the shape could be drawn and agreed before the code existed. The build moved on, the run record grew, and the placeholder is still in the pipeline at `ship`.

**Why it's wrong.** A `NotBuilt` step refuses to execute, so every run of the pipeline either routes around it or stops at it. Shipping one means shipping a system whose declared shape includes a step that cannot run, under a design the builder agreed to on the strength of that step existing.

**What the library provides.** `NotBuilt` stands in a node's callable slot and carries what the step will do; the manifest records the node with `planned: true`, and `simple-agents view` draws it dashed with those words on its card at every stage. Manifests carry `planned` from format `0.32`; a run written by an older version records nothing here.

**Check.** Every step standing in as `NotBuilt`, counted at every stage and a failure from `ship`. At `shape` a planned step is the shape working as intended and the count is reported as such; at `build` the count is what is still owed. This is the one check that reads the project's code: a step is declared in `agent.py`, and a project that has not run has no manifest to read one from, which is why reading only the manifest passed a project whose every step was a placeholder. Where the code cannot be imported the check falls back to the newest run's manifest and says so, and a project with no `agent.py` and no run has declared no step at all.

**Failure message.**
> `<count>` step(s) in this project's pipelines are still `NotBuilt`: `<list>`. Each was declared so the shape could be agreed before the code existed, and each still refuses to execute. Implement them, or take the design change to the builder and remove them; a pipeline shipped with one has a step that cannot run.

---

## 5. Group D: Recording and reproducibility

### FT-13: No trajectory logging
*Surface: artifact · Tier: prototype*

**What happens.** The agent runs and leaves nothing behind but its final output.

**Why it's wrong.** The omission is invisible until the data is needed, at which point it does not exist and cannot be recovered. Evaluation, ablation, regression detection, and later SFT and RL all read trajectories.

**What the library provides.** A run inside the envelope writes its trajectory, its manifest and its workspace to `run_dir/<run_id>/`. There is no switch that turns recording off. A run that crashed still leaves a manifest and the records written before the failure. `Trajectory.sampled(rate)` bounds what a project in production accumulates by keeping the payload fields on a fraction of runs; every run still writes a trajectory, and its counts, timings, tokens and seeds are complete whatever the rate (`docs/run-envelope.md` §7).

**Check.** The run directory holds a trajectory log conforming to the format in `docs/trajectory-format.md`: every line parses, every record carries the common fields and one of the seven record types, and at least one is a `node_execution`. A file that exists and holds something else fails the same check, because a trajectory nothing can read leaves as little behind as no trajectory. The check reads structure and not payloads, so a run whose payloads were sampled out passes; where any record carries an `omissions` entry the check reports the rate it read from the manifest. The run read is the newest whose `role` is `agent` (`docs/run-envelope.md` §2.1): a labelling pass or a judge goes through the same envelope and writes the same directory, and a project whose only runs declare another role fails with the reason naming what was found.

**Failure message.**
> No usable trajectory log was found for this run: `<reason>`. Nothing about the agent's behaviour is recoverable afterwards without one: no debugging a failure, no per-node evaluation, no ablation, and no later use of the runs as training data. A run inside the run envelope records by construction; the reason above says whether one was found and where.

### FT-14: Model version unpinned
*Surface: artifact · Tier: prototype*

**What happens.** A floating model alias in the config. The manifest records "the latest one."

**Why it's wrong.** When the score moves, the cause cannot be attributed to a local change rather than a provider-side one. An older eval stops being comparable to today's, and the loss becomes apparent only when the comparison matters.

**What the library provides.** The manifest records the model identity the client reported before the run, and the model that actually served each call. The two differ when a provider substitutes a model. Every `model_call` record carries the sampling parameters that call was made with, beside the identifier that served it (`docs/trajectory-format.md` §4.1). Pinning is the project's: pass a dated model string, or a repo ID with a revision SHA, to the client.

**Check.** The manifest records a fully-qualified model identifier, and the identifier is not an alias that resolves differently over time. What counts as fully-qualified depends on the backend: a dated model string for a hosted API, a repo ID plus a commit SHA for hub-hosted weights. A bare repo ID, or a branch name such as `main`, is an alias and fails.

**Every model that could serve a call is checked**, since a node may declare its own client (`docs/pipeline.md` §2.4). The check reads each node's model, falling back to the run's where the node declares none, and reports one failure per unpinned identifier naming the nodes it serves.

**On a hosted API the identifier is the only signal**, since a provider publishes its aliases and its dated names side by side and marks neither as canonical. The check fails an identifier carrying a floating marker, which is `latest`, `stable`, `preview`, `experimental` or `main`, and passes one it cannot classify. So a hosted name that floats without saying so passes this check, and the report names the identifier it read.

**Failure message.**
> The manifest records model alias `<alias>` on `<where>` rather than a pinned version. When results change, the cause cannot be attributed to a local edit rather than to a provider-side model update, and past evaluations stop being comparable to new ones. Pin the fully-qualified model identifier and record sampling parameters alongside it. For self-hosted weights that means the repo ID plus the exact revision SHA; a bare repo ID or a branch name resolves to different weights over time. Pin explicitly on upgrade, and treat the upgrade as a change to evaluate.

### FT-15: Prompts unversioned
*Surface: artifact · Tier: prototype*

**What happens.** Prompts inline as string literals, edited in place, with no version recorded in the manifest.

**Why it's wrong.** The same attribution failure as FT-14, from the other direction, and more common because prompt edits are casual. A regression traced to neither the model nor the code is traced to nothing.

**What the library provides.** Every prompt reaches the manifest with a version: the one declared as `prompt_version=`, or a hash of the prompt function's source and of what it closed over. The same holds for a route, a `Deterministic` node's function and a tool. A declared version also records the hash beside it, so an edit made without moving the declaration is readable (`docs/run-envelope.md` §2.3).

**Check.** Every prompt in the manifest records a version. A prompt whose source could not be read records `unavailable` and fails.

**Failure message.**
> The prompt for node `<where>` records no version: its source could not be read, so an edit to it leaves a score change with nothing to trace it to. Define the prompt as a function in an importable module rather than in a REPL or an `eval`, or declare `prompt_version=` on the node.

### FT-16: Secrets present in trajectory records
*Surface: artifact · Tier: prototype*

**What happens.** API keys, tokens, or personal data captured in recorded inputs and outputs.

**Why it's wrong.** A trajectory is written to disk and then used: attached to a bug report, copied into an eval set, later used as training data. Redaction after the fact is unreliable, because the record has usually already been copied by then.

**What the library provides.** Redaction runs on the record path, so a value is masked before it reaches the file, and every record lists the field paths that were altered. The built-in rules cover known credential formats and the environment variables the project declares. A `pydantic.SecretStr` is redacted by its type wherever it is recorded. Personal data in inputs and outputs is not detected, and declaring a pattern for it is the project's.

**Check.** Trajectory records are scanned against the project's declared secret patterns and a set of built-in high-confidence patterns. Any match fails. **Heuristic by construction**: a clean scan means no pattern matched.

**Failure message.**
> A value matching a secret pattern was found in trajectory record `<id>`, field `<field>`. Trajectories get committed, attached to bug reports, and reused as eval and training data, so a secret here may propagate. Add the pattern to the redaction config so it is stripped on the record path rather than cleaned up afterwards. This scan is heuristic. Passing it is not proof that no secrets are present.

### FT-17: Context silently truncated
*Surface: static + artifact · Tier: prototype*

**What happens.** The context builder drops the middle of the history on overflow and says nothing.

**Why it's wrong.** Silent truncation degrades the agent at the point where a task grows long enough to overflow. The change is invisible in the trajectory and presents as a model failure rather than a context failure, which sends debugging in the wrong direction.

**What the library provides.** The default `AppendAll` drops nothing, so overflow arrives as the backend's refusal rather than as quiet degradation. Every `model_call` record carries a `context` object with a `dropped` array. A context builder that removes a message returns a `Dropped` entry for it, which is what lands in that array. `DropOldestTurns` ships and does this.

**Check.** The manifest names a context builder for every node that can call a model, in `nodes[].context_builder`. For any builder other than the shipped `AppendAll`, the brief declares its policy, and every `model_call` record carries a `context` object whose `dropped` array lists each message the builder left out. A run whose messages shrank between one call and the next with an empty `dropped` fails: something was removed and nothing recorded it.

**Failure message.**
> The context builder truncates on overflow without recording it. An agent that silently loses the middle of its history degrades exactly when the task gets hard, and the trajectory will make it look like a model failure rather than a context failure. Either let overflow raise, which is what the default `AppendAll` does, or declare the truncation policy in the brief and return a `Dropped` entry for every message left out, which puts it in the `context.dropped` array of the record.

---

## 6. Group E: Budgets and control

### FT-18: No budget or termination condition
*Surface: runtime (enforced) + static · Tier: prototype*

**What happens.** A loop with no max steps, no token ceiling, no wall-clock limit, no cost limit, and termination inferred from the model's prose.

**Why it's wrong.** An agent loop with no bound can spend without limit while appearing to make progress. It is the most commonly omitted piece in hand-rolled agent code.

**What the library provides.** The four budget axes are max steps, max tokens, max wall clock and max cost, and `None` on an axis means unbounded there. An agent node terminates on an explicit `finish` call validated against the node's output schema; model output is never inspected for signs of completion. The node record says which axis stopped it. An agent node that fans out is every item's loop, so it is refused unless it declares `budget=`, `budget_per_item=` or both, and its item records say which axis stopped each item.

**A cycle in the pipeline graph is bounded separately, and there is no fifth axis.** `max_steps` counts model calls, so a cycle of `Deterministic` nodes makes none and would run forever under a budget that looks set. The bound is declared on the node that closes the cycle, as `Loop(max_iterations=..., then=...)`, and a cycle without one is refused at construction. `docs/pipeline.md` §1.4 covers it.

**Check.** Primarily **enforced, not checked**: a loop constructed without a budget refuses to run, and so does a pipeline containing an unbounded cycle. The static check exists to catch the failure at author time rather than first-run time, and to verify termination is an explicit schema-validated `finish` call rather than a heuristic over the model's output.

**Failure message.**
> This loop was constructed without a budget and will not run. Max steps, max tokens, max wall-clock, and max cost are all required, because an agent loop without them can spend without bound while appearing to make progress. Set the budget on the loop. Also confirm termination is an explicit `finish` tool call rather than a check on the model's prose. Prose heuristics make "why did it stop" unanswerable from the trajectory.

### FT-27: Cost recorded as a bare figure
*Surface: artifact · Tier: prototype*

**What happens.** A single cost number stored per call or per run, with no token breakdown beneath it and no record of the prices it was computed against.

**Why it's wrong.** The number cannot be recomputed, audited, or re-priced. Cached prompt tokens bill at a fraction of uncached ones and cache writes at a premium, so a figure derived without the breakdown misprices any cached workload, and prices change, so a stored figure goes stale while continuing to look authoritative. Self-hosted serving fails from the opposite direction: wall clock multiplied by a device rate charges every concurrent request for the whole device, so a well-batched server looks expensive by the batch factor. This compounds with FT-18, because `max_cost` is a budget axis and a budget enforced against an unauditable number is not enforced.

**What the library provides.** Records carry the token breakdown and the timings, the manifest carries the basis, and model cost is computed from those at read time. No record stores a model cost figure. A budget with `max_cost` set is refused where the pipeline can call a model and the envelope declares no basis, because there would be nothing to enforce it against, and `max_cost` is never enforced against a figure the library knows is an upper bound.

**A tool's spend is stored, in the `tool_call` record's `spent`**, because what a vendor charged is not a function of anything the run observed and there is no basis to re-derive it from. The rate is on the same record, and a tool that reports its own charge is where the figure comes from.

**Check.** The manifest declares a cost basis, and the records carry that basis's inputs: under `price`, the full token breakdown (uncached, cache-read, cache-write, cache TTL, output); under `compute`, the device type, count, hourly rate, and per-call `concurrent_requests`. A stored per-record cost field fails under either basis, because it is a derived value that can drift from its inputs with no way to tell which is authoritative. A compute-basis figure derived without concurrency fails unless it is labelled an upper bound.

**Failure message.**
> Cost is stored as a figure with no derivation behind it. It cannot be audited or recomputed. Under a hosted API, cached tokens bill at a fraction of uncached ones, so any cached workload is mispriced, and stored figures go stale silently when prices change. Under self-hosted serving, wall-clock times a device rate overcounts by the batch factor whenever more than one request is in flight. Record the token breakdown per call, or the device rate and per-call concurrency, and declare in the manifest which basis is in force. Derive cost from those at read time rather than freezing it into the record.

---

## 7. Group F: Tool discipline and eval safety

### FT-19: Tool registered without a declared side-effect class
*Surface: static (enforced at registration) · Tier: prototype*

**What happens.** A tool added to the registry with no declaration of whether it reads, writes, spends money, or does something irreversible.

**Why it's wrong.** The declaration is what an evaluation reads to decide whether a tool may execute during a rollout (FT-20). Without it, evaluation cannot tell a search from an order, so it cannot run safely at all.

**What the library provides.** The four classes are `read_only`, `writes`, `spends_money` and `irreversible`. The class is recorded on every tool call and in the manifest, so re-declaring a tool later does not change what an old trajectory says. There is no exemption, including for the built-in set.

**Check.** **Enforced at registration**: registering a tool without one of the four classes raises. The static check reports it at author time.

**Failure message.**
> Tool `<name>` was registered without a side-effect class. Registration is refused: evaluation uses this declaration to decide what may execute during rollouts, so an undeclared tool makes evaluation unsafe rather than merely unlabeled. Declare one of `read_only`, `writes`, `spends_money`, or `irreversible`. A tool whose class is unclear is not `read_only`; that class has to be established, not assumed.

### FT-20: Tools reaching outside the run executed inside eval rollouts
*Surface: runtime (enforced) · Tier: evaluated*

**What happens.** An eval runs k rollouts over n examples, and one of the tools in the loop sends email, writes to a live database, or places an order.

**Why it's wrong.** Every action repeats k×n times. An evaluation over 50 examples at k=5 sends 250 emails.

**Which classes are refused.** A class is refused where repeating the action k×n times acts on the world k×n times. `read_only` never does, with one exception the runner handles separately: `consult` asks a person, and an evaluation over a channel whose `answered_by` reaches one is refused before the first rollout unless `end_user=` says otherwise (`docs/evaluation.md` §5.4). The class describes the effect and that refusal bounds the rollouts. A `writes` confined to the run's own workspace does not either, because each rollout gets a fresh directory, and such a tool is re-run rather than replayed so that its files exist when a later step reads them (`docs/tools.md` §3.2). A `writes` into the run's memory store is the same case, because an evaluation gives each rollout its own store (`docs/memory.md` §3). `spends_money` and `irreversible` do.

**The two are refused differently, because a builder can do different things about them.** An `irreversible` tool is refused outright: an action that cannot be undone is not bounded by declaring how many of them are acceptable. A `spends_money` tool runs under `max_spend`, the most the whole evaluation may cost, which the builder declares and the runner checks before the first rollout (`docs/evaluation.md` §7.2). Money is the class where how much is a question with an answer.

**`examples × k` is a count of rollouts, not of calls.** One rollout calls a paid tool as often as the agent reaches for it, so nothing derived from `DeclaredCost` bounds an evaluation. What bounds one is `max_cost` on the pipeline's budget, which no rollout can pass, times the rollout count.

**What the library provides.** The refusal reads the class FT-19 requires, and covers the tools the pipeline can reach rather than everything in the registry. What a pipeline can reach includes the tools inside a pipeline a node may delegate to, since a rollout runs those too (`docs/pipeline.md` §2.5).

**And it ships the recording an evaluation replays.** `EvalSuite.record` runs each rollout live at the seed that rollout will use, into one cassette, and a call already on file is served rather than made again. The k rollouts of one example that make the same tool call therefore buy one answer between them, which is why recording costs no more than the same rollouts run live and usually less. A recording made any other way misses on rollouts it does not hold, and a replay against one is refused rather than reported (`docs/evaluation.md` §6.3, §7.7).

**What it does not cover.** A pipeline started from inside a tool's body, by calling `Pipeline.run` there, is not a declared part of the pipeline. Nothing reads its tools, it writes its own separate run directory, and its spend depletes no budget of the calling run. Hand a subtask to a pipeline with `AgentNode(delegates=[...])`, which is declared and is read here.

**Neither does it cover a store the library does not own.** A tool declared `writes` that writes into a database, a file outside the run, or an object the project holds in memory is not refused, because `writes` means an effect confined to the run and nothing checks that it is. Such a store is also invisible: it is in no walk, and no record says a rollout read it. A memory store declared on the envelope is the case the library does own, and each rollout gets its own (`docs/memory.md` §3). A store reached any other way is a declaration the tool's author is making, on the same footing as the class itself.

**Check.** **Enforced**: the eval runner refuses to start when a tool the pipeline can reach is declared `irreversible`, or `spends_money` with no `max_spend`, unless the cassette is replaying, where the call is served from the file and the tool's body never runs.

**Failure message.**
> Evaluation refused to run: tool `<name>` declared `spends_money`, and this evaluation is `<rollouts>` rollout(s) (`<n>` examples × `<k>`), each of which may call it more than once. The acceptable spend is undeclared, so the run would spend an amount decided by how often the agent reaches for the tool. Say how much: `suite.run(..., max_spend=0.50)` is the most this evaluation may cost, model calls and paid calls together, and it is checked before the first rollout. The cheaper path is to buy each distinct call once: `suite.record(...)` makes the live runs and `suite.run(..., Cassette.replay(path))` replays them.

### FT-21: Evaluation cannot run offline
*Surface: runtime · Tier: evaluated*

**What happens.** The eval suite requires live network and live API spend, so it cannot run in CI, the automated job that runs a project's tests on every commit, and in practice stops being run at all.

**Why it's wrong.** An eval that costs money and needs credentials runs before the demo and then stops running. The regression it would have caught arrives later, with nothing to attribute it to.

**What the library provides.** A cassette keys every model and tool call on the content of the request, so a recorded run replays with no network and no credentials.

What replay exercises is everything around the model: the scoring function, the parsing of a response into the output schema, the pipeline wiring, a handle-taking tool's body, and a library or dependency upgrade. An edit that breaks any of those shows up as a moved number at no cost, and the delta is attributable to the edit alone because the responses did not change.

A prompt edit changes the request, so it misses and reports the diff rather than replaying the old response. Replay therefore measures the project's code, not its prompts, and it does not re-measure the model. Both of those need a live run.

**Check.** The full conformance suite runs to completion with network access disabled and no credentials present, replaying from cassettes.

**Failure message.**
> The conformance suite attempted a network call and cannot run offline. An eval that needs credentials and spend runs once before the demo and then never again, so a regression in the project's own code goes uncaught between live runs. Record cassettes for every external call and verify the suite passes with the network disabled.

### FT-22: Errors swallowed and fed to the model
*Surface: static (heuristic) · Tier: prototype*

**What happens.** A broad `except` around a tool body, returning the exception text to the model as a normal tool result.

**Why it's wrong.** It merges two categories that must stay separate. A model-facing error ("the search returned nothing, try different terms") is data the agent should act on. A caller-facing error (expired credentials, a 500, a full disk) means the run is invalid. Handed to the model, the second produces an agent that invents its way around broken infrastructure and returns a confident answer built on nothing, and a real outage reads as a quality problem.

**Check.** Lint for exception handlers that catch broadly and return the result as model-facing data without classification. **Heuristic**. It catches the common shape. An instance written differently is not reported.

**Failure message.**
> Tool `<name>` catches `<exception>` broadly and returns it to the model as data. Infrastructure failures handed to a model produce an agent that invents its way around them and returns a confident answer built on nothing, while a real outage looks like a quality problem. Classify each error path: model-facing errors return as data, caller-facing errors raise and invalidate the run. This check is heuristic. It finds the common shape, so a pass is not proof.

### FT-23: Tool description written for a human
*Surface: static (enforced at registration) · Tier: prototype*

**What happens.** A description explaining the implementation to a reader rather than the behaviour to a model.

**Why it's wrong.** The description is what the model reads to decide when and how to call the tool. A model that misunderstands a tool calls it wrongly, and the resulting failure appears as a reasoning failure, sending debugging to the prompt instead of the description. A description that has drifted from the behaviour misleads rather than omits.

**What the library provides.** A tool carries a `description`, which is the prompt text the model reads. The `@tool` decorator uses the function's docstring as the description unless one is passed explicitly, so the two are the same text by default and can be separated where the human reader and the model need different things. An empty description is refused at registration, as is an unannotated parameter, which would be offered to the model with no type at all. A run's manifest records each tool's description under `schemas`, so what the model was shown is readable afterwards.

**Check.** Enforced at registration rather than after the fact: a tool that registered has a non-empty description and a typed schema. Whether the description is *accurate* is what a contract test establishes, and every tool needs one; `docs/tools.md` §6 says what such a test asserts.

**What a contract test does not catch.** It compares the description against the code, so it catches the two drifting apart. It does not catch a description that matches the code and is wrong about the world. One shipped example: a search tool's description told the model that when the top hits are not what it wanted, "the collection does not cover that subject". The tool did exactly that, and its contract test passed. A lexical retriever finding nothing has established that those words did not reach a passage, not that the fact is absent, and a description saying otherwise teaches the model to conclude absence from a retrieval miss. Read the description as prompt text, and ask what a model would infer from it that the tool cannot support.

**Failure message.**
> Tool `<name>` has no description. The description is what the model reads to decide when and how to call this tool, so an empty one leads to misuse, and one written for a human reader describes the implementation rather than the behaviour. State what the tool does, what its arguments mean, what comes back, what a failure means, and when not to reach for it. Then write a contract test asserting what the description claims, which is what stops the two drifting apart.

---

## 8. Group G: Elicitation and consultation

### FT-24: Elicitation skipped
*Surface: artifact · Tier: prototype*

**What happens.** The coding agent decided alone what only the builder could decide: what ground truth means, what counts as failure, where the agency boundary sits, what the budget is, and proceeded on a plausible assumption.

**Why it's wrong.** This is the validity failure, and the rest of the suite cannot catch it. A project can pass every other check while measuring the wrong thing perfectly. The builder is also likely to have omitted crucial details from the initial prompt, because they did not know which details mattered. Identifying those is the coding agent's job, supported by the library.

**What the library provides.** The questions, the stage each becomes required at, and the gate. `simple-agents questions --stage shape` prints them, each with the scaffold that makes it answerable and the entry name that records the answer. A required question a builder cannot answer cold produces an invented answer, so every question ships with a way to answer it: a measurement to take first, or a set of concrete alternatives to choose between. The coding agent does the asking; the library never asks the builder anything itself. An entry also carries `source`, which says where the answer came from: `builder`, `research` for a finding out of `research.md` the builder agreed, `document` for something read out of a file they supplied, or `coding_agent` for one they have not seen.

**One question is put again at every stage.** `anything_else` is the builder's, where every other question is the library's, and its answer is what nothing was asked about. Its entry carries `asked_at`, the stage it was last put at, and the gate refuses while that names an earlier stage than the project is at. The answer accumulates under the stage it was given at, *nothing* is an answer, and a deferral is refused because there is no later stage to defer it to.

**Check.** For each question required at the project's current stage, the brief entry is `answered` from a source other than `coding_agent`, or `deferred` to a stage the project has not reached. `unanswered` fails, and so does a question with no entry at all, and so does one answered `source = "coding_agent"`. A deferral settles a question until the project arrives at the stage it names; at that stage the answer is due, so an entry deferred to the current stage or an earlier one fails alongside the blanks. A question put again at every stage is settled only where its `asked_at` names the current stage or a later one, and an entry for one carrying no `asked_at` at all fails with the blanks. The stage is what the brief declares or what its artifacts show, whichever is further on, and the requirement is cumulative, so declaring a later stage adds questions rather than skipping them. The gate establishes that the question was asked and answered, never that the answer is right. It cannot tell an answer that followed a re-asking from an `asked_at` moved on its own.

**Failure message.**
> Required brief entries have no answer at stage `<stage>`: `<list>`. An entry counts here when it is `unanswered`, when the brief carries none, when it is `deferred` to a stage this project has already reached, when it is answered `source = "coding_agent"`, which says the builder has not seen it, or when it is a question every stage puts again whose `asked_at` is missing or names an earlier stage. These are decisions only the builder can make: the coding agent guessing at them produces a project that passes every other check while measuring the wrong thing. Ask the builder each question and record the answer, or mark the entry `deferred` naming a later stage. A question every stage puts again takes no deferral: ask it here and write `asked_at` naming this stage. Do not fill these in on the builder's behalf; a plausible invented answer is worse than a blank.

### FT-25: Consultation treated as a fault path
*Surface: artifact · Tier: prototype*

**What happens.** The agent guesses at things the end user could have told it, because consultation was modelled as an error path, reached only when something breaks, rather than as designed behaviour.

**Why it's wrong.** Most consultation is planned: the builder anticipated the agent needing a preference, a disambiguation, or an authorization it cannot derive. An agent that treats asking as failure guesses instead, and the cost lands on the end user. The reverse failure is real too: an agent that consults constantly is unusable, and where the balance sits is a builder decision.

**Check.** Where the brief's `consultation` answer names something to ask, a consultation tool is registered on the newest run of one of the project's pipelines and at least one node was given it. Whether the agent can ask a person is a question about the project, so any pipeline answering it is enough (`docs/conformance.md` §3.8). Where the run it read asked nothing through that tool, the pass says so and does not fail: a run may legitimately have had nothing to ask. The same note reads the newest results file, and says where no rollout in it asked through the tool either. A tool can be registered, reachable from a node, and still never called, which is the state that note reports, and an evaluation is where a project is least likely to notice it: a rollout is refused over a channel that reaches a person, so every one of them answers with a stand-in. An answer opening on a negation, such as *"Nothing. Every input the agent needs is in the collection"*, says there is nothing to ask and passes. Reading further than the first word would mean reading prose, so an answer that opens on a negation and then names something passes too. Whether the consultation points are the *right* ones is not checkable: which nodes ought to be asking is a judgement no artifact carries, and neither is whether the answer still describes what the builder wants.

**What the library provides.** Three things, for three ways a designed interaction turns back into a fault path.

An answer that was none of the offered options is kept, recorded as `resolution: "unmatched"` rather than as a refusal, and a route built with `on_reply` must say where it goes. An end user correcting a question rather than answering it is the case that distinguishes designed consultation from a fault path, and it is the one a route with only the offered options would drop. `docs/tools.md` §4.6.1.

A consultation that ends without an answer records which of three things happened: `unavailable` where there was nobody to ask, `shelved` where the question went somewhere a person will see it later, and `pending` where the run stopped to wait. `on_reply` needs a branch for each of the first two. Nobody being there is not an end user declining, and neither is a question that has reached somebody and is waiting on them. `docs/tools.md` §4.6.3.

A channel declares who it reaches, and the declaration is on every consultation and on the tool's manifest entry. Without it a resolution of `answered` says a question was answered and not by whom, so an agent whose questions all went to a fixed string reports what one measured against its readers reports. `docs/tools.md` §4.6.2, and `docs/evaluation.md` §5.4 for the reader an evaluation supplies.

**Failure message.**
> The brief's `consultation` answer names what the agent must ask the end user, and `<reason>`, so the agent cannot ask and will guess instead. Consultation is designed behaviour, not an error path: the end user often holds information the agent has no way to derive. Register the consult tool and make it reachable from the nodes that need it, `registry.add(consult(ask, answered_by="end_user"))` and `tools=` on those nodes (`docs/tools.md` §4.6). Where there is nothing for the agent to ask, the answer opens on that: `none`, or `nothing`, or a sentence beginning with one of them. Whether these are the right consultation points is a judgement this check cannot make; that is a question for the builder.

### FT-41: A run stopped to ask, and nothing continued it

*Surface: artifact · Tier: prototype*

**What happens.** A consultation raises `Suspend`. The run writes its state to disk and ends, the surface shows the question, and the end user answers it. Nothing calls `Pipeline.resume`, so the run stays stopped and the answer reaches nothing.

**Why it's wrong.** Stopping and continuing are two halves of one design, and building the first produces a working demonstration: the question appears on the surface. The run then sits on disk waiting, which raises no error and writes no record anybody reads. The end user's answer changes nothing, and the surface told them it would.

**What the library provides.** `Pipeline.resume(run_id, envelope=, model=, answer=)` continues the run against the pipeline it started on, keeping its id, its trajectory and its manifest, so one run that stopped comes out as one run. `Pipeline.suspensions(run_dir)` lists what is waiting and what each is waiting for, which is what a surface renders as an inbox. The manifest records one `suspensions` entry per node that stopped, each gaining `resumed_at` when the run continues, from manifest format `0.6`. Where the run should finish without the answer instead, a channel returns `Shelved` or `Unavailable` and never stops it (`docs/product.md` §4).

**Check.** Every manifest under `runs/`, whatever role or pipeline each declares and whatever answered its model: how many carry a suspension, how many carry one that is still open, and how many record a `resumed_at`. A failure from `ship` where at least one suspension is open and no run has ever recorded a `resumed_at`. At every stage before that the three counts are reported and nothing fails. A project whose channels return `Shelved` or `Unavailable` never suspends and passes, and so does one whose open suspension sits beside a run that was resumed, since that is a run waiting rather than a project with no way to continue one. Whether a project intends to resume is not readable, and neither is whether the answer it resumed on was the right one.

**Failure message.**
> `<count>` run(s) under `runs/` stopped to ask something and are still waiting, and no run this project has made was ever continued. A run that raises `Suspend` writes its state to disk and ends; `Pipeline.resume(run_id, envelope=env, model=client, answer=reply)` is what picks it up, and until something calls it the end user's answer reaches nothing. `Pipeline.suspensions("runs/")` lists what is waiting and what each is waiting for, which is what the code that resumes reads. Where these runs should finish without an answer instead, the channel returns `Shelved` or `Unavailable` and the run never stops (`docs/product.md` §4). Whether resuming is the right design here is a builder decision; this check reads only that nothing does it.

### FT-29: The project has no current account of itself
*Surface: artifact · Tier: prototype*

**What happens.** What the project is for is written nowhere. The brief answers specific questions and the code says what the agent does; what the builder set out to make, and where it is heading, is in neither. Or the account exists, was written on the first day, and has not been read since.

**Why it's wrong.** What a project is for changes while it is built. The account written first is the one the next session reads first, and one that no longer matches sends the next reader at the problem the project used to have. The answer most likely to have moved is what the finished version looks like, which is what every remaining decision is aimed at.

**What the library provides.** `idea.md`, written at stage `brainstorm` and kept beside the brief. Five sections: what this is, who it is for, what it works on, where this is going and where it is not, and what is still open. The brief records `understanding_confirmed_at`, the stage at which that file was last confirmed to still describe the project, and advancing a stage means reading it again and writing the new stage there.

**Check.** `idea.md` exists at the project root, carries all five sections, and none of them is empty. The brief's `understanding_confirmed_at` names the stage the project is at. The check reads whether the sections are present and whether the confirmation is current. It cannot read whether what they say is true, and it cannot tell a confirmation that followed a reading from one that did not.

**Failure message.**
> The project has no current account of itself: `<reason>`. `idea.md` is what the next session reads first, and the brief's entries answer questions rather than saying what the project is. Write it with five sections: what this is, who it is for, what it works on, where this is going and where it is not, and what is still open. Then read it, and record `understanding_confirmed_at` in the brief naming stage `<stage>`, which is where this project is. Set it again at every stage after re-reading the file. This check reads whether the sections are present, never whether what they say is true.

---

### FT-30: Design decisions the builder never saw
*Surface: artifact · Tier: prototype*

**What happens.** The coding agent chooses which external service the project depends on, how many nodes it has and which are agentic, the numbers written into the code, the rules the prompts state, how a result is shown, and what the evaluation scores. It chooses well, and the builder learns about it by reading the code afterwards.

**Why it's wrong.** Every elicitation question asks the builder about their own world: their data, their end users, whether a wrong answer beats no answer. None asks the coding agent to put its own decision in front of them. The decisions that shape what the agent *is* go unreviewed until the builder reads the code, when changing one means rebuilding around it. A number chosen this way is a guess that became a requirement.

**What the library provides.** Six decision kinds, in `simple_agents.conformance.DECISION_KINDS`, each with the question to put to the builder: `dependency`, `shape`, `constant`, `prompt_rule`, `presentation` and `measurement`. The brief records one entry per decision under `[decisions]`, with what was chosen, what else was considered, why, and a status: `proposed` where the builder has not seen it, `agreed` where they have, `changed` where they wanted something else, and `not_applicable` for a kind this project has nothing of.

**Check.** Every one of the six kinds has at least one entry, and no entry is still `proposed`. A kind a project has nothing of is recorded `not_applicable` rather than left out, so nothing-to-decide and nobody-thought-about-it are different states. The check reads whether the decisions were recorded and settled. It cannot read whether the record is complete, because a decision the coding agent did not notice making is one it did not write down, and it cannot tell agreement from a rubber stamp.

**Failure message.**
> Design decisions the builder never saw: `<reason>`. Every elicitation question asks the builder about their own world, and none asks what the coding agent decided on its own, so these are the choices that reach a builder last and cost most to change. Record one entry per decision under `[decisions]` in the brief, naming its `kind`, what was chosen, what else was considered and why. Put each to the builder and record `status = "agreed"`, or `"changed"` with what they wanted instead. A kind this project has nothing of is `"not_applicable"`. This check reads whether decisions were recorded and settled, never whether the record is complete.

### FT-42: A decision names something the project never built

*Surface: artifact · Tier: prototype*

**What happens.** A decision was put to the builder and agreed, naming the tools the project would rest on, the steps it would take, the numbers it would use or the rules its prompts would state. What was built is not that. The brief still records the agreement, every run passes, and the difference between what the builder said yes to and what runs is in nobody's way.

**Why it's wrong.** The record of the agreement is prose, and prose is where the difference hides. One project's `agency_boundary` named two steps that decide for themselves; it shipped with none, and eleven checks passed over it on twenty-one runs. A decision naming a capability the project never built is an agreement about something that does not exist, and the builder has no way to learn that from the brief, which is the only place the agreement is written down.

**What the library provides.** `produces` on a decision, naming what it became: the tools of a `dependency`, the nodes of a `shape`, the numbers of a `constant`, the nodes whose prompts carry the rule of a `prompt_rule`. A `presentation` or `measurement` decision carries none, and one that names a `produces` is refused, because what a result looks like to a person and what an evaluation scores leave nothing in a run record to join a name against. The manifest records the node ids, the tool names and, from format `0.33`, every module-level number the project's own code defines (`docs/run-envelope.md` §2.9). A project whose runs all predate that format has its `constant` names left out rather than failed, and the pass says so.

**Check.** Every name under `produces`, against the node ids, tool names and constants of every run under `runs/`, whatever its role. A decision the builder agreed to can be about a pipeline the project runs for itself: one project's `dependency` decision named four nodes and six constants of a `role="corpus"` pipeline, and reading the agent's runs alone reported ten built names as never recorded. Read across all of them rather than the newest: a project with more than one pipeline runs whichever it was asked for, so the newest run describes one of them and a decision about any other would read as naming something that does not exist. Counted at every stage and a failure from `ship`, on FT-40's and FT-41's pattern, because a decision is agreed before the code exists and the gap between the two is what `build` is. The other direction is a report and never a failure: what the runs recorded that no decision names is printed under the checks, since which of a project's numbers are the builder's to decide is a judgement the library cannot make (`docs/conformance.md` §4.4).

**Failure message.**
> `<count>` name(s) under `produces` were never recorded by any run of this project: `<list>`. Each is a decision the builder agreed to, naming something the project does not have. Build what was agreed, or take the change back to the builder and record the decision `changed` with what it became. A decision about a pipeline that has not run yet is the same case: run it once, and the name is recorded.

### FT-43: The MCP server changed under the project

*Surface: artifact · Tier: prototype*

**What happens.** An agent is given tools from an MCP server somebody else runs. The builder was shown what each tool does, confirmed a side-effect class for each, and the project shipped. The server is then updated: a description is reworded, a schema gains a required field, a tool is withdrawn. The declarations in the project still name the tools, every run still passes, and what the model is being shown is no longer what the builder agreed to.

**Why it's wrong.** A tool's description is prompt text, and its schema is what the model is told it may pass. Both come from a server the project does not control, so both can move without anything in the project changing. A reworded description sends the model to a tool for work it no longer does, and the resulting failure looks like a reasoning failure and sends debugging to the prompt (`docs/tools.md` §1.2). A withdrawn tool fails at the moment the agent reaches for it. The side-effect class is the sharper case: it was confirmed against what one call did, and a server is free to change what that is.

**What the library provides.** A run reads each declared server once and records what it offered under `mcp` in the manifest: which tools, their descriptions, their schemas and their hints. A run that has both a recording and a reachable server records the `drift` between them, one entry per difference, naming the tool and whether the change was `added`, `withdrawn`, `description` or `schema`. Each tool's manifest entry carries the hints beside the class the project declared, so a claim and a declaration that disagree are readable from the run (`docs/run-envelope.md` §2.10). A replayed run reaches no server and records no drift, because it is being served the recording rather than compared against it.

**Check.** The `drift` array of every entry under the `mcp` of the run the checks read, which is the newest run of the pipeline the results file measured (`docs/conformance.md` §3.8). A project that declares no MCP server passes, and so does one whose run was replayed, since a replay has nothing to compare. It reads whether the server moved, never whether the move matters: a reworded description may be an improvement, and only the builder can say.

**Failure message.**
> The MCP server `<server>` no longer offers what this project declared: `<list>`. A description and a schema are what the model is shown, and a side-effect class was confirmed against what one call did, so a server that moved is a change the builder agreed to nothing about. Read what changed, take it to the builder, and update the `effects=` declaration and the brief's `tool_effects` answer to match.

### FT-44: A stamp the clock did not write

*Surface: artifact · Tier: prototype*

**What happens.** Every answered entry and every decision in the brief carries `recorded_at`, when what it says was written down. The coding agent writes the value itself, from what it takes the time to be, and what it takes the time to be is a guess: the first project built on the public package stamped twenty of thirty-three entries in local time with a UTC suffix, two hours ahead of every clock the run records.

**Why it's wrong.** The stamp is what puts an answer in order against a run, a comment and another answer. A composed one puts it in the wrong order, so a question of whether the code moved after an answer was given, or whether a comment arrived before an entry was amended, is answered from a number nobody read. The file looks the same either way: a stamp is a stamp, and nothing about `2026-09-02T02:25:00Z` says which clock it came from.

**What the library provides.** `simple-agents record answer` and `simple-agents record decision` write the entry and stamp it from the clock, in UTC (`docs/conformance.md` §2.3). `record_answer` and `record_decision` do the same from Python.

**Check.** Every `recorded_at` on an entry and on a decision, against the clock on the machine the suite runs on, with five minutes' tolerance for two machines disagreeing. A stamp ahead of that was composed. It cannot read a stamp behind the clock, which is what a composed stamp looks like once enough time has passed, so the writer is what closes this and the check is what catches a hand-written stamp at the gate that follows it.

**Failure message.**
> `<count>` stamp(s) in the brief are ahead of the clock, which read `<now>` when this ran: `<list>`. A stamp is when what the entry says was written down, and one in the future was composed rather than read, so nothing that puts this answer in order against a run or a comment can trust it. Write entries through `simple-agents record answer` and `simple-agents record decision`, which stamp from the clock in UTC, and correct the ones listed.

### FT-31: Shipped on a development channel
*Surface: artifact · Tier: prototype · Stage: ship*

**What happens.** The agent reaches an end user with the channel it was built against still in place: the coding agent answering its consultations, a model playing the reader, or a fixed string. Nothing in the build showed it, because every one of those answers.

**Why it's wrong.** A consultation is where the agent asks for what it cannot derive. An answer from a stand-in is what the coding agent, or a model, expected the person to say, and the agent proceeds on it while the person it was for never sees the question. The resolution reads `answered` either way, so a shipped agent whose questions reach nobody produces the same trajectory as one answered by its readers.

**What the library provides.** A channel declares who it reaches, at registration or for one kind of run (`docs/tools.md` §4.6.2), and the declaration is on every consultation and on the tool's manifest entry. `end_user` is a person the agent is for, and `builder` is the author standing in for that person while the project is built. `nobody` is `unattended()`, which answers `Unavailable` and is a design a project can ship, with the brief's `someone_there` answer saying so. `coding_agent`, `simulated` and `canned` belong to a build.

**Check.** The `answered_by` of every consultation tool on the run's manifest, and of the consultations of a live run where the project has one, since that is what a run did rather than what the pipeline declared. It fires on `coding_agent`, `simulated`, `canned` and `builder`. A project that registers no consultation tool passes, and so does one declaring `nobody`. Whether nobody being there is the right design is a builder decision, and this check does not read it.

**Failure message.**
> The agent has shipped and its consultations are answered by `<answerer>`, declared at `<where>`. That is a stand-in used while a project is built, so the questions the agent asks reach no end user and it proceeds on what the stand-in said. The resolution still reads `answered`, which is why nothing earlier reported it. Register the channel that reaches the people this agent is for, `consult(ask, answered_by="end_user")`, or replace it for live runs with `env.with_end_user(channel, answered_by="end_user")`. Where the builder is the person the agent is for, the declaration is `end_user` rather than `builder`. Where the run is meant to be unattended, `unattended()` declares that and this check passes.

### FT-32: The brief describes a pipeline that no longer exists

*Surface: artifact · Tier: prototype*

**What happens.** The `tool_effects` answer was true when the builder gave it. The pipeline then changed: tools were added, one moved to a side-effect class that reaches outside the run, and the entry still reads `answered` with the old answer in it.

**Why it's wrong.** `tool_effects` is where the builder agreed to what the agent may do outside the run: spend money, write somewhere permanent, take an action that cannot be undone. An answer that no longer describes the code records agreement to something else, and the builder has no way to see that from the brief. FT-24 reads whether the entry exists and FT-30 whether the decisions are settled. Neither reads whether either is still true, and an entry goes stale on a change rather than at a gate, so nothing is looking when it happens.

**What the library provides.** The manifest's `tools`, one entry per tool the pipeline registered, carrying the name, the declared `side_effect_class`, and `offered`, which is false for a tool no node was given (`docs/run-envelope.md` §2.1).

**Check.** Every side-effect class the run's manifest declares that reaches outside the run appears somewhere in the `tool_effects` answer, matched with underscores read as spaces and case ignored, so `spends_money` is satisfied by *"spends money"*. Three classes are read: `writes`, `spends_money` and `irreversible`. `read_only` is not, because the question asks what the agent may do that reaches outside the run and `read_only` is the answer *nothing*, which a builder writes as *"it only reads"*. Tool names are not read either: a builder describes a tool in their own words, and an answer naming a code identifier is not a better answer. It cannot read whether what the answer says about a class is right, or whether the answer covers every tool in that class.

**Failure message.**
> The brief's `tool_effects` answer does not describe what the run recorded: `<reason>`. That entry is where the builder agreed to what the agent may do outside the run, so an answer that has gone stale records agreement to something the code no longer does. Read the manifest's `tools` against the answer, take the difference to the builder, and record what they say. This reads whether each class of effect is mentioned at all, never whether what the answer says about it is right.

### FT-33: The build log stopped before the work did

*Surface: artifact · Tier: prototype*

**What happens.** The project keeps a `BUILD-LOG.md` and then stops writing to it. The runs continue, the design moves, and what the log describes is the project as it was some days ago.

**Why it's wrong.** The log records each exchange with the builder as it happens, which is the only account of why the project is shaped the way it is. Written afterwards it is a reconstruction, and what a reconstruction loses first is what was decided and then superseded. A log that stopped reads as current, so the next session works from an account of a project that has moved.

**What the library provides.** `docs/procedure.md` asks for the log beside the other artifacts, and this is the check that reads it.

**Check.** Where the project keeps a `BUILD-LOG.md`, it was last written no earlier than the run the checks read ended, which is the newest run of the pipeline the results file measured (`docs/conformance.md` §3.8). The end rather than the start, because an entry about a run can only be written once that run has finished, which gives the comparison a margin the length of the run. A run that crashed or is still going is dated by its start instead. A project that keeps none passes, since whether to keep one is the builder's decision. The check reads the file's modification time, so a project copied or checked out fresh has every file looking current and this finds nothing. It cannot read whether what the log says is true, or whether it records the exchanges rather than a summary of them.

**Failure message.**
> `BUILD-LOG.md` was last written `<log_written>` and the run this read finished `<run_started>`, so the log describes the project as it was before that run. It records each exchange with the builder as it happens, which is the only account of why the project is shaped the way it is; everything since that write has no such account. Write what has happened since into the log now, while it can still be recalled, and write each exchange as it happens rather than at the end. A project that keeps no build log passes this check.

### FT-34: The design the builder agreed to was never written down

*Surface: artifact · Tier: prototype · Stage: shape*

**What happens.** The coding agent settles how the agent will be built in conversation, writes the code, and the builder sees the design by reading what was built. The brief records a `shape` decision, which is one sentence naming what was chosen.

**Why it's wrong.** A sentence is not something a builder can react to. The decision that shapes a project is a sequence of steps, what each holds on to, and what it will not do, and a builder reading a plan says "that is not what I asked for" where a builder reading `chose = "a stateless run over a CSV"` says nothing. It also leaves no review record. The conversation is not stored as an artifact, so a design the builder accepted and a design the builder never saw look the same.

**What the library provides.** `design.md`, written at stage `shape` and kept beside the brief. Three sections: what it does step by step, what it holds on to between runs, and what the builder said about it. The brief records `design_confirmed_at`, the stage at which that file was last confirmed to still describe what is being built, and advancing a stage means reading it again and writing the new stage there. Where the pipeline moves under it, the report names it for re-reading (`docs/conformance.md` §4.4).

**Check.** From stage `shape`: `design.md` exists at the project root, carries all four sections, none of them is empty, and the fourth carries a quotation, which is a blockquote or text in quotation marks. Where the project declares a `Product` (`docs/product.md` §2.1), the product section names every surface it declares, matched on the surface's own name; a project declaring none is not read this way. The brief's `design_confirmed_at` names the stage the project is at. A quotation is a shape, not a fact: this reads whether something is quoted there, never whether the words are the builder's or whether they said them about this design. It cannot read whether any of the file is true, and it cannot tell a confirmation that followed a reading from one that did not.

**Failure message.**
> The design the builder agreed to is not written down: `<reason>`. A `shape` decision records one sentence, and a builder cannot react to a sentence; a plan they can read is what turns a design nobody objected to into a design they agreed to. Write `design.md` at the project root with four sections: what it does step by step, what it holds on to between runs, the product (every interaction the end user can take, classified as starting a run, answering a waiting run, reading the artifact, or recording a judgement; `docs/product.md`), and what the builder said about it. Where the code declares a `Product`, the product section names each of its surfaces. Put the first three to the builder before writing the code, record what comes back in their own words under the fourth, and iterate until they agree. Then record `design_confirmed_at` in the brief naming stage `<stage>`, and set it again at every stage after reading the file. This check reads whether the sections are there and whether something is quoted, never whether what they say is true.

---

### FT-36: The ground was never checked

*Surface: artifact · Tier: prototype · Stage: research*

**What happens.** The coding agent asks the builder what they want, then designs the agent out of what it already knows. Nothing goes and finds out how the task is done elsewhere, what data exists that would make it cheap, or what is known to go wrong. The options weighed in every later decision are the ones that were already in the room.

**Why it's wrong.** A project is bounded by the option set the coding agent brings to the first design, and a builder does not usually know what that set is missing. The cost is invisible in the artifacts: a `dependency` decision recording three alternatives looks the same whether the alternatives were found or recalled. It also lands late. A source that would have changed the shape of the pipeline arrives after the pipeline is built and measured, and the measurement is what has to be paid for again.

**What the library provides.** `research.md`, written at stage `research` and kept beside the brief. The parts the system needs, what was found against each, what the research says the project turns on, and what the builder said about it. The survey is a table with one row per candidate and an `Outcome` column, so a candidate nobody investigated says so rather than reading as covered. The brief records `research_confirmed_at`, the stage at which that file was last confirmed still to describe the project.

**Check.** From stage `research`: `research.md` exists at the project root, carries all four sections, none of them is empty, the survey section holds a table whose header names `Outcome`, that table has at least one candidate under the header, every row of it fills that column, and the last section carries a quotation. A row too short to reach the column counts as unfilled. A blank line ends a table, so a section holding two of them reads each against its own header. The brief's `research_confirmed_at` names the stage the project is at. An outcome is a cell, not a fact: this reads whether something was written there, never whether anyone looked. It cannot read whether the survey is complete, and a project that searched for nothing and wrote "not investigated" against every row passes.

**Failure message.**
> The ground this project rests on was never checked: `<reason>`. What gets weighed in every later decision is the option set gathered here, and a builder cannot supply what they do not know exists. Write `research.md` at the project root with four sections: the parts, and what each has to do; what was found against each part; what this turns on, having looked; and what the builder said about it. Break the system into parts first, then go and look against each one: what already does it, how it is built when it is built, what data and APIs it could draw on, and what is known to go wrong. Record the survey as a table with one row per candidate and an `Outcome` column, and fill every cell: a candidate nobody investigated is written as `not investigated, because ...` rather than left blank. Put it to the builder, record their words under the last section, then record `research_confirmed_at` in the brief naming stage `<stage>` and set it again at every stage after reading the file.

---

### FT-39: An unanswered comment

*Surface: artifact · Tier: prototype*

**What happens.** The builder points at a part of the system in the view and says something: a question, an objection, a change they want. The comment is recorded in `comments.toml` and stays `open` while the build moves on around it.

**Why it's wrong.** A comment is the builder writing into the record from the picture, and it is the one entry in the record that arrives unprompted. An open comment left behind is the builder's words going unanswered while the thing they commented on keeps changing, and nothing else reads that file.

**What the library provides.** `comments.toml` beside the brief, one `[[comment]]` thread per thing said, written by the served `simple-agents view` where the builder speaks in place and by the coding agent replying (`docs/view.md` §5). A thread carries the address, the words, a snapshot of what the writer was looking at, and its replies; `status` is `open` until the thing it asks for is done or decided, then `addressed` with `addressed_by` naming what answered it, and `withdrawn` is the builder taking it back. `simple-agents comments` prints the open threads. The brief key `comments_block_gates = true` is the builder's choice that an open thread refuses a gate rather than being reported beside it.

**Check.** Every comment in `comments.toml` is readable and none is `open`. Without `comments_block_gates = true` in the brief, open comments are reported under a passing check rather than failing it. A missing `comments.toml` passes: the builder has not commented on anything.

**Failure message.**
> `comments.toml` holds comments that block this gate: `<reason>`. Each is the builder pointing at a part of the system and asking for something. Do what each asks or take it back to the builder, then record the outcome: set the comment's `status = "addressed"` with `addressed_by` naming the decision or the change that answered it. The builder chose `comments_block_gates = true`, so the gate waits until none is open.

### FT-38: The brief was never read against the code again

*Surface: artifact · Tier: prototype · Stage: ship*

**What happens.** The entries describing the pipeline are answered at `shape`, the code is written, and the code keeps moving. The answers still read `answered` and still describe the pipeline as it was agreed, which is what they are read as long after they stopped describing the pipeline as it is.

**Why it's wrong.** Twelve of the brief's entries describe the pipeline rather than the builder's intent: what the answer looks like, which steps are judged, where the agency is, what the budget is, what the tools may do. The builder agreed to them once. Left unread they record agreement to something the code no longer does, and the builder has no way to see that from the brief. The brief presents an answer naming removed steps as current until its confirmation is updated. One of the twelve is read by another check, `tool_effects` against the manifest's tools (FT-32); the other eleven are prose and nothing else reads them at all.

**What the library provides.** `confirmed_against` in the brief holds `pipeline.behaviour_fingerprint(model=client)` from when those entries were last read against the code, and every run's manifest carries the same value. Where the two differ, the report names the entries that are due and prints the value to record.

**Check.** From stage `ship`: the brief records `confirmed_against`, and it equals the `behaviour_fingerprint` in the newest whole run of the pipeline the results file measured (`docs/conformance.md` §3.8). `simple-agents record read-against` writes that value. Before `ship` the report carries it as a note instead. A project with no answered entry describing the pipeline passes, since there is nothing there to go stale. It reads whether the value was recorded, never whether anyone read the entries, so a project that pastes the fingerprint without reading them passes.

**Failure message.**
> `confirmed_against` in the brief: `<confirmed>`. The newest run of the pipeline this project reports a number for was made by `<current>`. These entries describe the pipeline rather than what the builder wants, so each is now recorded agreement to something the code may no longer do: `<due>`. Read each against the code, take any difference to the builder, and record `<current>` in the brief as `confirmed_against`, which `simple-agents record read-against` writes. An entry goes stale when the pipeline changes rather than when a gate is reached, so this is the one check with nothing but a change behind it.

## 9. Group H: Training tier

### FT-26: Reward function trivially gameable
*Surface: runtime · Tier: trained*

**What happens.** A hand-written reward that scores highly for degenerate outputs: empty responses, repeated tokens, echoing the input, or padding to maximum length.

**Why it's wrong.** RL will find these. The optimizer searches for whatever the reward rewards, and a policy converges first on shortcuts a human reader would dismiss as trivial. The result is a good-looking training curve attached to an agent that does nothing useful, and a wasted training run.

**Check.** The reward function is fuzzed against a battery of degenerate candidates: empty, single repeated token, verbatim input echo, maximum-length padding, prior-example copy. Any candidate scoring above the declared floor fails.

**Failure message.**
> Reward function scored `<value>` on degenerate input `<kind>`, above the floor of `<floor>`. RL will find the shortcut before it finds the intended behaviour, producing a good training curve attached to a useless agent. Fix the reward so degenerate outputs score at the floor, then re-run the fuzz. Where hand-written rewards are not wanted, the judge-based default is the recommended path.

---

## 10. What is not checkable

These are things the suite does not check, and no additional entry would let it.

| Not checkable | Why not | What handles it instead |
|---|---|---|
| Whether the metric measures what the builder cares about | Requires knowing the builder's intent | Elicitation (FT-24) |
| Whether the eval examples are representative of real inputs | Requires knowing the real input distribution | Elicitation, plus revision after the agent meets reality |
| Whether the ground-truth labels are correct | The labels *are* the ground truth as far as the suite can see | Builder review; a second labeler where it matters |
| Whether an `AgentNode`'s justification is sound | It is prose stating a belief about the task | Ablation (FT-12) replaces the belief with data |
| Whether consultation points are the right ones | A product judgement about the end user's patience | Elicitation (FT-25), then contact with real end users |
| Whether `idea.md` describes the project truthfully, and whether it was read before being confirmed | Both are claims about prose and about what a person did | The builder, reading it at each gate (FT-29) |
| Whether the builder's words in `design.md` are the builder's | A quotation is a shape a check can read; whose words are inside it is not. The same holds for a brief entry | The builder, reading `design.md` (FT-34) |
| Whether a brief entry records the builder's answer or the coding agent's summary of it | Nothing in the artifact distinguishes them | The builder, reading the brief |
| Whether what the end user reads was produced by the pipeline that was measured | A results file and a run directory are what the suite opens. An artifact the project keeps, and the end user reads, is neither, and reading it would mean opening whatever storage the project chose | The builder, and the brief's `stored_output` answer, which records what the artifact is and what refreshes a result an older pipeline wrote (FT-24, `docs/shipping.md` §6) |
| Whether a node body reached the world without a tool | A `Deterministic` body is Python and the library executes it. A call it makes to `urllib` or a database driver of its own is indistinguishable from computation, so the fetch policy, the cassette and the record see none of it | The tools rule, stated at `docs/tools.md` §3.3, and `ctx.record_access` for a resource the body reached (`docs/pipeline.md` §3) |
| Whether the product's surface reaches the agent | The surface is the project's code in whatever form the project chose, and no check executes it. A `Product` declares which pipeline each surface reaches and FT-34 reads that against the design section, which is what the code says rather than what it does | The design section's classification, read by the builder (FT-34, `docs/product.md` §2), and the live runs a working surface leaves behind |
| Whether the agent is *good* | Not a conformance question | The builder, looking at the results |
| Whether the record of decisions is complete | A decision the coding agent did not notice making is one it did not write down | The builder, reading `[decisions]` against the code (FT-30) |
| Whether an `agreed` decision was read before it was agreed to | Nothing in the artifact distinguishes agreement from a rubber stamp | The builder, and the `involvement` answer that set how they are shown |

Every check above verifies that a process was followed. None verifies that the result is correct. A project at full conformance measured something carefully; the suite makes no claim about whether it measured the right thing.

---

## 11. Index

| ID | Failure | Surface | Tier |
|---|---|---|---|
| FT-01 | No evaluation at all | artifact | evaluated |
| FT-02 | No held-out split | artifact | evaluated |
| FT-03 | Dev examples leaked into held-out set | artifact | evaluated |
| FT-04 | Happy path only, no absent-data cases | artifact | evaluated |
| FT-05 | Single rollout per example | artifact | evaluated |
| FT-06 | Point estimate with no interval | artifact | evaluated |
| FT-07 | Seeds uncontrolled | artifact | evaluated |
| FT-08 | End-to-end metrics only | artifact | evaluated |
| FT-09 | Output schema admits no `unknown` | static | prototype |
| FT-10 | False confidence conflated with recall | artifact | evaluated |
| FT-11 | Everything made agentic | static + artifact | prototype |
| FT-12 | Agency asserted but never ablated | artifact | evaluated |
| FT-13 | No trajectory logging | artifact | prototype |
| FT-14 | Model version unpinned | artifact | prototype |
| FT-15 | Prompts unversioned | artifact | prototype |
| FT-16 | Secrets in trajectory records | artifact | prototype |
| FT-17 | Context silently truncated | static + artifact | prototype |
| FT-18 | No budget or termination condition | runtime + static | prototype |
| FT-19 | Tool without side-effect class | static | prototype |
| FT-20 | Tools reaching outside the run, in rollouts | runtime | evaluated |
| FT-21 | Evaluation cannot run offline | runtime | evaluated |
| FT-22 | Errors swallowed and fed to the model | static | prototype |
| FT-23 | Tool description written for a human | static (enforced) | prototype |
| FT-24 | Elicitation skipped | artifact | prototype |
| FT-25 | Consultation treated as a fault path | artifact | prototype |
| FT-26 | Reward function trivially gameable | runtime | trained |
| FT-27 | Cost recorded as a bare figure | artifact | prototype |
| FT-28 | What a node accepts is undeclared | static + runtime | prototype |
| FT-29 | The project has no current account of itself | artifact | prototype |
| FT-30 | Design decisions the builder never saw | artifact | prototype |
| FT-31 | Shipped on a development channel | artifact | prototype |
| FT-32 | The brief describes a pipeline that no longer exists | artifact | prototype |
| FT-33 | The build log stopped before the work did | artifact | prototype |
| FT-34 | The design the builder agreed to was never written down | artifact | prototype |
| FT-35 | Steps spent without a tool call | artifact | prototype |
| FT-36 | The ground was never checked | artifact | prototype |
| FT-37 | The reported number came from a pipeline the project no longer has | artifact | evaluated |
| FT-38 | The brief was never read against the code again | artifact | prototype |
| FT-39 | An unanswered comment | artifact | prototype |
| FT-40 | A step that was declared and never built | artifact | prototype |
| FT-41 | A run stopped to ask, and nothing continued it | artifact | prototype |
| FT-42 | A decision names something the project never built | artifact | prototype |
| FT-43 | The MCP server changed under the project | artifact | prototype |
| FT-44 | A stamp the clock did not write | artifact | prototype |
| FT-45 | The number was measured over a pipeline the project does not declare | artifact | evaluated |

**Counts.** 45 entries: 30 `prototype`, 14 `evaluated`, 1 `trained`. By surface: 34 artifact, 4 static, 2 static+artifact, 3 runtime, 2 runtime+static.

Five entries name a stage as well as a tier. FT-31, FT-37 and FT-38 fire once a project has reached `ship`, FT-34 once it has reached `shape` and FT-36 once it has reached `research`, and each reports `n/a` before that. FT-37 and FT-38 read a change rather than an arrival, and a stage a project has reached it stays at, so those two go on firing on every later run of the suite.

FT-40, FT-41 and FT-42 carry no stage field: they run at every stage and fail from `ship`, because what each counts is expected early and owed late.

**On ID ordering.** IDs are assigned in creation order and are permanent, so they are not always contiguous within a group. FT-27 sits in Group E next to the budget entry it compounds with, and FT-28 in Group C next to the entries about shape, rather than at the end of the document. Read the index for the full list; read the groups for context.

**Not every entry corresponds to a check that fires.** Some are *enforced by construction* rather than checked after the fact: FT-09's schema requirement, FT-18's budget requirement, FT-19's side-effect class, and FT-28's agreement between what one node produces and what the next reads. The library refuses to construct the offending object, so those failures surface as a construction error at author time rather than as a report at the end of a run. FT-20 is enforced the same way one level up, by the eval runner refusing to start.

The shipped conformance suite implements a subset of this document and grows toward it. An entry that no check yet enforces is still the specification of correct practice. `docs/conformance.md` covers the subset that runs today, what each of those checks reads, and how a project declares the tier that decides which of them apply.
