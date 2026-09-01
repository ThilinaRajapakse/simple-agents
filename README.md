# Simple Agents

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

Simple Agents is a library for building an agent you can evaluate, debug, and improve. Training on your own runs is on the way.

You write the pipeline. Every run records what it did, replays with no network access, and can be scored against a labelled set of examples, with a confidence interval on every figure.

It is designed to be used by a builder and a coding agent working together. `simple-agents init` installs a staged build procedure where your coding agent will read it, and a conformance suite that checks the project against it.

> **Pre-alpha. Under construction.**

## Quick start

```
uv add simple-llm-agents      # or: pip install simple-llm-agents
simple-agents init            # or: simple-agents init --claude
```

Python 3.11 or newer. The import is `simple_agents` and the CLI is `simple-agents`. `init` registers the build procedure as a skill for your coding agent and points your project's `AGENTS.md` at it. From there:

1. The build runs in six staged gates, and the coding agent asks questions as needed to build your idea. [Building with a coding agent](#building-with-a-coding-agent) covers the stages and the two commands that drive them.
2. **[A first agent](#a-first-agent)** is what the code looks like. Every run it makes writes a manifest, a trajectory and a cassette, so it can be read back, re-priced and replayed for free.
3. **`simple-agents view`** shows the project as it stands, on one page: what is built, what is planned, what changed, and where everything flows.
4. An evaluation runs the pipeline over a held-out split and reports rates with confidence intervals. [Measuring the agent](#measuring-the-agent) is the short version, and the `measure` stage settles the rest.

## A first agent

An agent that answers questions from your own documents, and says so when the answer is not there.

```python
from pydantic import BaseModel
from simple_agents import AgentContext, AgentNode, Budget, Maybe, MistralClient, Pipeline
from simple_agents.builtins import DocumentIndex, document_search

class Answer(BaseModel):
    answer: Maybe[str]
    source: str | None = None

policies = DocumentIndex.from_directory("policies/", glob="*.md")

def ask(inputs: dict, ctx: AgentContext) -> str:
    return ("Answer the question from the policy documents, and name the document "
            f"the answer came from.\n\n{inputs['question']}")

pipeline = Pipeline(
    [AgentNode(ask, tools=[document_search(policies)], output_schema=Answer,
               budget=Budget(max_steps=8, max_tokens=50_000,
                             max_cost=None, max_wall_clock_ms=120_000))],
    budget=Budget(max_steps=None, max_tokens=200_000,
                  max_cost=None, max_wall_clock_ms=300_000),
)

result = pipeline.run(
    {"question": "How long do I have to return a damaged item?"},
    model=MistralClient(model="mistral-small-2603"),   # reads MISTRAL_API_KEY, or pass api_key=
)

result.output.answer     # 'You have thirty days from the date of delivery to return a damaged item.'
result.output.source     # 'returns.md'
result.paths.manifest    # runs/dev/<date>/<run_id>/manifest.json
```

The model decides when to search and when it has an answer. It cannot exceed the budget, and it cannot return a shape the schema does not describe.

And the run is written to disk:

```
runs/dev/<date>/<run_id>/
    manifest.json      what was configured: model, seed, budget, prompts, prices
    trajectory.jsonl   what happened: one record per step the run took
    cassette.jsonl     every call the run made, so it can be replayed
    workspace/         scoped file I/O for the run's tools
```

Runs are filed by what they are. This one was made while you were building, so it went under
`dev/`. A run an end user makes goes under `live/`, an evaluation's rollouts under `eval/`, and
a labelling pass or a judge under its own name. `runs("runs/")` reads them back and takes
`role=` and `live=` to narrow.

`docs/pipeline.md` covers the graph, `docs/run-envelope.md` the run directory.

## What the library provides

**Three kinds of nodes.** `Deterministic` runs plain code. `LLMNode` makes one model call at a fixed point in the graph. `AgentNode` hands control to the model, which chooses tools and decides when it is done. Nodes wire into a graph with branches, joins and bounded cycles. A run can suspend and resume later, and a whole pipeline can be one node inside another. See `docs/pipeline.md`.

**Runs held to a budget that you set.** Steps, tokens, wall clock and cost, on a node, on the pipeline, or on both. Any axis set to `None` is unbounded on that axis. A run that reaches a limit stops and names the axis it hit. See `docs/pipeline.md`.

**Tools that declare what they touch.** A tool is a Python function with a schema and one of `read_only`, `writes`, `spends_money` or `irreversible`. The class is recorded on every call, and an evaluation reads it before it starts. A paid tool runs under a spend ceiling you declare. One whose effects cannot be undone is refused until its calls have been recorded once and can be replayed. Built in: search over your own documents, lexically or by meaning; page fetch with a host policy and a cache; web search through a provider you supply; scoped file I/O; a clock; typed extraction; a question put to your end user mid-run; a memory the agent reads and writes across runs; and a conversation that carries from one run to the next. See `docs/tools.md`, `docs/retrieval.md` and `docs/memory.md`.

**An answer that can say it does not know.** Every node that calls the model declares a schema its output has to validate against, and a schema with no way to express absence is refused when the node is built. `Maybe[str]` is a string or `unknown`. It carries into the numbers: an evaluation reports what the agent got right, what it declined to answer, and what it asserted and got wrong as separate rates. See `docs/pipeline.md` and `docs/evaluation.md`.

**A complete record of every run.** Nothing has to be switched on. A manifest records what was configured; a trajectory records what happened, one entry per node execution, model call, tool call, consultation and delegation, with the four token classes on every model call. Cost is worked out from those counts against a price or compute basis you declare, so an old run can be re-priced from the record it already holds. Declared secrets and known credential formats are removed before anything reaches disk. See `docs/run-envelope.md` and `docs/trajectory-format.md`.

## Pointing a run at a model

```python
from simple_agents import GeminiClient, MistralClient, VLLMClient

MistralClient(model="mistral-small-2603")            # reads MISTRAL_API_KEY
GeminiClient(model="gemini-3.1-flash-lite")          # reads GEMINI_API_KEY
VLLMClient(model="Qwen/Qwen3-8B", model_revision="<sha>")

MistralClient(model="mistral-small-2603", api_key=secret)   # or pass it in yourself
```

A hosted backend reads its key from the environment variable named beside it, or takes one through `api_key=`. Either way it is held as a `SecretStr` and travels in a header, so it stays out of anything a refusal or a record quotes back. Each backend implements the same two-method interface. You can write custom adapters for any backend that the library does not ship (yet). A node can name its own model, so an expensive backend can be pointed at the steps, and only the steps, that need it. `docs/model-clients.md` covers which variable each backend reads, what each reports and how cost derives under each, with a page per adapter including the vLLM server flags that decide what a run can record.

## Cassettes and replays

Every run writes a cassette: every model call and tool call it made, keyed on the content of the request. Point a later run at that file and the calls are served from it, with no network, no credentials and nothing spent.

```python
from simple_agents import Cassette, RunEnvelope

env = RunEnvelope(cassette=Cassette.replay("cassettes/qa.jsonl"))
result = pipeline.run(inputs, envelope=env, model=client)
```

This is what lets an evaluation run in CI, and what keeps a tool that writes or spends from firing once per rollout. Change a prompt and the replay reports a miss naming the node and what changed. `Cassette.record` writes a file, and `Cassette.update` serves what is on file and calls out for the rest. See `docs/run-envelope.md`.

## Measuring the agent

An evaluation runs the pipeline k times over each example in a held-out split and reports rates with intervals.

```python
from simple_agents.evaluation import EvalSuite, ExampleSet

suite = EvalSuite(
    pipeline,
    ExampleSet.from_jsonl("evals/examples.jsonl"),
    answer="answer",
    matches=lambda s: s.answer.strip() == s.expected.strip(),
)
results = suite.run(envelope=env, model=client, split="held_out", k=5, seed=41)
results.write()

results.metrics["accuracy"].interval.point               # 0.71
results.metrics["false_confidence_rate"].interval.high   # 0.19
```

Eight rates are reported together, each over its own denominator and each with a confidence interval. You can declare metrics of your own alongside them. Per-node metrics say how often each node was reached and how often it was right, so a pipeline that loses the answer at one step shows where. `compare(before, after)` reads two results files and reports the paired difference, and `compare_variants` runs a change against the baseline in one session and pays only for the nodes the change can reach. See `docs/evaluation.md`.

## Building with a coding agent

`simple-agents init` installs the build procedure as a skill, at `.agents/skills/simple-agents/` or at `.claude/skills` with `--claude`, and points your project's `AGENTS.md` at it. The procedure runs in six stages, `brainstorm`, `research`, `shape`, `build`, `measure` and `ship`, and each one ends at a gate:

```
simple-agents questions --stage shape   # what your coding agent should be asking you
simple-agents check                     # the gate
```

The questions are the ones only you can answer: what the agent is for, what a right answer looks like, what it must never do. The answers go into a brief, and the gate refuses to advance while one that stage needs is missing. `simple-agents check` runs the conformance suite over the project and reports what is not yet true of it. Behind it is a catalogue of 43 characteristic failures of agent building, and the twenty-six checks that ship today read the project's own brief, runs and results. `docs/procedure.md` is the procedure itself, readable without installing anything.

## Full documentation

| File | What it covers |
|---|---|
| [`docs/procedure.md`](docs/procedure.md) | The six stages of a build, what to settle with the builder at each, the project layout, and the gate that ends each stage. Shipped as a skill, and what `simple-agents init` registers. |
| [`docs/pipeline.md`](docs/pipeline.md) | The pipeline as a graph, the three node kinds, branching, joining and bounded cycles, suspending a run and resuming it, streaming a node's output, handing a subtask to a pipeline the model chooses, what a node receives, the output schema and `unknown`, and budgets. |
| [`docs/tools.md`](docs/tools.md) | The tool contract, the registry, how a tool is replayed, the built-in set, which hosts a run may reach, caching what was fetched, and consulting the end user. |
| [`docs/retrieval.md`](docs/retrieval.md) | Searching by meaning as well as by words: which model embeds a corpus, how lexical and semantic results combine, reranking, where the vectors live, and what a search costs. |
| [`docs/memory.md`](docs/memory.md) | The memory store, the tools that reach it, what an evaluation does with it, and what redaction reaches. |
| [`docs/conversation.md`](docs/conversation.md) | A conversation that outlives the run: how a node takes part, what a turn is, reading one back, and compaction. |
| [`docs/context.md`](docs/context.md) | What the model is sent on each call, what overflow means, and how to replace the default. |
| [`docs/model-clients.md`](docs/model-clients.md) | The model seam, the comparison between the three shipped adapters, a model per node, retries and pacing, streaming, reasoning output, and writing another. Each adapter has its own page: [`mistral.md`](docs/model-clients/mistral.md), [`gemini.md`](docs/model-clients/gemini.md), [`vllm.md`](docs/model-clients/vllm.md). |
| [`docs/run-envelope.md`](docs/run-envelope.md) | The run directory, the manifest, cassette recording and replay, seeds, cost, redaction, and reading past runs back. |
| [`docs/trajectory-format.md`](docs/trajectory-format.md) | The record schema with seven record types, token accounting, and the encoding rules everything downstream reads. |
| [`docs/evaluation.md`](docs/evaluation.md) | Labelled example sets and their splits, k rollouts, the intervals over them, the eight rates, a figure per criterion, a metric the project declares itself, per-node metrics including reach and accuracy, comparing two versions, and comparing named variants of one pipeline. |
| [`docs/shipping.md`](docs/shipping.md) | What changes when somebody other than the builder uses the agent: a run that says it is live, who answers the agent once it has shipped, and what live runs are worth to the next version. |
| [`docs/view.md`](docs/view.md) | `simple-agents view`: one page showing the project as it stands, for the builder: what is built, what is planned, what changed, and where everything flows. |
| [`docs/product.md`](docs/product.md) | What the end user uses: the interactions a surface can offer, a run per request behind it, a run that waits for a person, and the artifact that accumulates. |
| [`docs/failure-taxonomy.md`](docs/failure-taxonomy.md) | The characteristic failures an agent project hits, each with a detection surface, tier, check, and failure message. The specification the conformance suite is derived from, and wider than the checks that ship. |
| [`docs/conformance.md`](docs/conformance.md) | Running `simple-agents check`: the brief, the tier and the stage a project declares, what each check reads, and what the report means. |
| [`docs/index.md`](docs/index.md) | The full list, with what each document covers and when to open it. |

The documentation installs with the package. `simple_agents.docs_path()` returns the directory holding it.

## License

Apache-2.0.
