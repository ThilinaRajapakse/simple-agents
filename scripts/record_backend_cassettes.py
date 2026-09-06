"""Record the cassettes the adapter integration tests replay.

Run once per backend, with a key or a server present. The recorded cassettes are committed,
and `tests/test_adapter_integration.py` replays them with no key and no network.

    uv run python scripts/record_backend_cassettes.py mistral
    uv run python scripts/record_backend_cassettes.py vllm
    uv run python scripts/record_backend_cassettes.py gemini
    uv run python scripts/record_backend_cassettes.py agent-gemini
    uv run python scripts/record_backend_cassettes.py tools-gemini
    uv run python scripts/record_backend_cassettes.py eval-gemini
    uv run python scripts/record_backend_cassettes.py stream-gemini
    uv run python scripts/record_backend_cassettes.py {openai,openai-responses,anthropic}
    uv run python scripts/record_backend_cassettes.py {agent,stream}-{openai,openai-responses,anthropic}
    uv run python scripts/record_backend_cassettes.py tools
    uv run python scripts/record_backend_cassettes.py tools-vllm --base-url http://127.0.0.1:8001/v1
    uv run python scripts/record_backend_cassettes.py eval
    uv run python scripts/record_backend_cassettes.py graph
    uv run python scripts/record_backend_cassettes.py graph-vllm --base-url http://127.0.0.1:8001/v1
    uv run python scripts/record_backend_cassettes.py mixed --base-url http://127.0.0.1:8001/v1

The vLLM run needs a server started as `docs/model-clients/vllm.md` §2 describes. Re-recording
overwrites the cassette for that backend and leaves the other alone.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from schemas import Answer, Finding  # noqa: E402

from simple_agents import (  # noqa: E402
    AgentNode,
    AnthropicClient,
    OpenAIClient,
    OpenAIResponsesClient,
    Prompt,
    Section,
    AppendAll,
    Budget,
    Cassette,
    ComputeBasis,
    Deterministic,
    GeminiClient,
    Join,
    LLMNode,
    Loop,
    MistralClient,
    NodeFailure,
    PacedClient,
    Pipeline,
    PriceBasis,
    Redaction,
    RetryPolicy,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    Suspend,
    ToolRegistry,
    Unknown,
    VLLMClient,
    pipeline_factory,
    tool,
)
from simple_agents.evaluation import Example, EvalSuite, ExampleSet  # noqa: E402
from simple_agents.builtins import (  # noqa: E402
    DocumentIndex,
    consult,
    document_search,
    extract_to_schema,
    now,
    workspace_write,
)

CASSETTES = Path(__file__).resolve().parents[1] / "tests" / "cassettes"

MISTRAL_MODEL = "mistral-small-2603"
VLLM_MODEL = "Qwen/Qwen3-1.7B"
GEMINI_MODEL = "gemini-3.1-flash-lite"
# The build string the model list publishes for that identifier. Nothing in a response
# repeats it, so it is passed in and recorded rather than read back.
GEMINI_REVISION = "3.1-flash-lite-05-2026"

# Every value the cassette key covers is fixed here, so the replaying test reproduces the key
# exactly: the question, the prompt, the seed, the schema and the model identity.
QUESTION = "What is the capital of France? Answer in one word."
SEED = 41

MISTRAL_PRICES = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.15,
    input_cache_read_per_mtok=0.015,
    output_per_mtok=0.60,
)
VLLM_DEVICE = ComputeBasis(currency="USD", device="RTX-3090", device_count=1, hourly_rate=0.22)
# Published rates for gemini-3.1-flash-lite on 2026-08-12. The cache-write rate is 0.0
# because the provider bills no per-token cache-write class, and the count it reports for
# that class is `unknown`: `docs/model-clients/gemini.md` §3 has both.
GEMINI_PRICES = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.25,
    input_cache_read_per_mtok=0.025,
    input_cache_write_per_mtok=0.0,
    output_per_mtok=1.50,
)
OPENAI_MODEL = "gpt-5.6-luna"
ANTHROPIC_MODEL = "claude-sonnet-5"
# Published rates on 2026-09-06. GPT-5.6 bills a cache write at 1.25x the uncached rate and
# reports the count; Anthropic bills a write per TTL. `docs/model-clients/openai.md` §3 and
# `docs/model-clients/anthropic.md` §3.
OPENAI_PRICES = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.20,
    input_cache_read_per_mtok=0.02,
    input_cache_write_per_mtok=0.25,
    output_per_mtok=1.20,
)
ANTHROPIC_PRICES = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=2.00,
    input_cache_read_per_mtok=0.20,
    cache_write_per_mtok_by_ttl={"5m": 2.50, "1h": 4.00},
    output_per_mtok=10.00,
)

# The three backends `P3-69` added. Each refuses a temperature other than the default on the
# models these arms call, so their pipelines set none; the seed is dropped by two of them and
# the manifest says so. Chat Completions on GPT-5.6 refuses function tools unless reasoning
# is off, measured 2026-09-06, so the `openai` agent arm turns it off.
NEW_BACKENDS = ("openai", "openai-responses", "anthropic")


def _new_backend(backend: str) -> str | None:
    """Which of the three new backends an arm name ends in, or ``None``."""
    for name in NEW_BACKENDS:
        if backend == name or backend.endswith(f"-{name}"):
            return name
    return None


def _new_client(backend: str, *, tools: bool = False):
    """The client, basis and secret for one of the new backends' arms."""
    name = _new_backend(backend)
    if name == "openai":
        return (
            OpenAIClient(model=OPENAI_MODEL, reasoning=not tools),
            OPENAI_PRICES,
            ["OPENAI_API_KEY"],
        )
    if name == "openai-responses":
        return OpenAIResponsesClient(model=OPENAI_MODEL), OPENAI_PRICES, ["OPENAI_API_KEY"]
    return AnthropicClient(model=ANTHROPIC_MODEL), ANTHROPIC_PRICES, ["ANTHROPIC_API_KEY"]


def build_prompt(inputs, ctx):
    return Prompt.user(
        "{question}\n\nReport the answer, or `unknown` if it is not known.",
        question=inputs["question"],
    )


def pipeline(temperature: float | None = 0.0) -> Pipeline:
    return Pipeline(
        [LLMNode(build_prompt, output_schema=Answer, node_id="answer", temperature=temperature)],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=120_000),
    )


# The agent recording covers the multi-turn path: a question needing more lookups than can be
# planned, so the loop runs until the model calls finish. Nothing else exercises the
# conversation the loop builds, which no backend accepts in the library's own shape.
CATALOGUE = {
    "trousers-ashford": "The Ashford trouser is cut from cotton twill. Sold by Northgate.",
    "trousers-belmont": "The Belmont trouser has a 34 inch inseam. Sold by Kirkwall.",
    "retailer-kirkwall": "Kirkwall ships from Leeds and offers free returns within 30 days.",
    "retailer-northgate": "Northgate ships from Bristol. Returns cost 4.95 GBP.",
}

AGENT_QUESTION = (
    "Which retailer sells the trouser with a 34 inch inseam, and what is its returns policy?"
)


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def search(query: str) -> str:
    """Search the product catalogue. Returns matching entries, or a note that none matched.

    Pass a few words, such as a garment name or a retailer name.
    """
    hits = [
        f"{k}: {v}"
        for k, v in CATALOGUE.items()
        if any(w.lower() in (k + " " + v).lower() for w in query.split())
    ]
    return "\n".join(hits) if hits else "No entries matched that query."


def hunt(inputs, ctx):
    return Prompt.user(
        "{question}\n\nSearch the catalogue as many times as needed, then call finish. Report "
        "`unknown` for anything the catalogue does not say.",
        question=inputs["question"],
    )


def agent_pipeline(temperature: float | None = 0.0) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                hunt,
                tools=[search],
                output_schema=Finding,
                budget=Budget(
                    max_steps=6, max_tokens=40_000, max_cost=None, max_wall_clock_ms=120_000
                ),
                node_id="hunt",
                temperature=temperature,
            )
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=180_000),
    )


# The context recording fans out over three documents, so the context builder runs three times
# in one run. Items 1 and 2 are where the pre-flight check has a real measurement to work
# from, which is the path no fake client exercises: the ratio comes from what the backend
# reported for the item before.
CONTEXT_DOCUMENTS = [
    "The Ashford trouser is cut from cotton twill and sold by Northgate.",
    "The Belmont trouser has a 34 inch inseam and is sold by Kirkwall.",
    "Kirkwall ships from Leeds and offers free returns within 30 days.",
]


def load_documents(inputs, ctx):
    return {"documents": list(inputs["documents"])}


def describe(inputs, ctx):
    return Prompt.user(
        "{documents}\n\nReport the retailer named in that line, or `unknown` if none is named.",
        documents=inputs["documents"],
    )


def context_pipeline() -> Pipeline:
    return Pipeline(
        [
            Deterministic(load_documents, node_id="load"),
            LLMNode(
                describe,
                output_schema=Answer,
                over="documents",
                node_id="describe",
                temperature=0.0,
                # A reasoning model generates until the context runs out without this, and a
                # budget is checked between steps rather than inside a call. 4000 is what a
                # short reading prompt was measured to need on 2026-08-18: 1200 returned
                # `finish_reason=length` with empty content, the whole ceiling spent on the
                # chain of thought.
                max_output_tokens=4000,
                context=AppendAll(max_input_tokens=100_000),
            ),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=180_000),
    )


# The tools recording is the one that tests item 7 against something that reads the request.
# It covers all three replay arrangements in a single run: `document_search` and `now` are
# filed under their arguments, `workspace_write` and `extract_facts` are re-run because their
# signatures ask for a handle, and `extract_facts` makes a model call inside a tool. A fake
# client returns a scripted response without reading what was sent, so it cannot show that a
# backend accepts a tool whose schema hides a handle parameter, nor that a nested call travels
# the same wire path as any other.
TOOL_CORPUS = {
    "ashford.txt": "The Ashford trouser is cut from cotton twill. Sold by Northgate.",
    "belmont.txt": "The Belmont trouser has a 34 inch inseam and is made of linen. "
    "Sold by Kirkwall.",
    "kirkwall.txt": "Kirkwall ships from Leeds and offers free returns within 30 days.",
}

TOOLS_QUESTION = (
    "Find the trouser with a 34 inch inseam. Report its fabric and which retailer sells it."
)


def outfit(inputs, ctx):
    return Prompt.user(
        "{question}\n\nSearch the documents, then use the extraction tool on the passage you "
        "found to pull out the fabric. Save what you found with the workspace tool, then "
        "call finish. Report `unknown` for anything the documents do not state.",
        question=inputs["question"],
    )


def tools_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            document_search(DocumentIndex.from_texts(TOOL_CORPUS)),
            extract_to_schema(Finding, name="extract_facts"),
            workspace_write(),
            now(),
        ]
    )


def tools_pipeline() -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                outfit,
                tools=tools_registry(),
                output_schema=Finding,
                budget=Budget(
                    max_steps=10, max_tokens=60_000, max_cost=None, max_wall_clock_ms=180_000
                ),
                node_id="outfit",
                temperature=0.0,
            )
        ],
        budget=Budget(max_steps=None, max_tokens=120_000, max_cost=None, max_wall_clock_ms=240_000),
    )


# The eval recording is the one that tests item 8 against something that reads the request. It
# runs a two-node pipeline over three labeled examples at k=3: nine runs, each with its own
# derived seed and so its own cassette key. Two nodes rather than one, because per-node metrics
# over a single node prove nothing about the grouping. A FakeModelClient returns a scripted
# response without reading what was sent, so it cannot show that k rollouts at derived seeds
# produce k distinct keys through the real wire path, nor that a two-node pipeline's records
# separate by node when a real backend produced them.
EVAL_CORPUS = {
    "kirkwall": "Kirkwall ships from Leeds and offers free returns within 30 days.",
    "northgate": "Northgate ships from Bristol. Returns cost 4.95 GBP.",
    "ashford": "The Ashford trouser is cut from cotton twill. Sold by Northgate.",
}

EVAL_EXAMPLES = [
    ("e1", "Which retailer ships from Leeds?", "Kirkwall"),
    ("e2", "Who sells the Ashford trouser?", "Northgate"),
    ("e3", "What is Kirkwall's annual revenue?", None),
]

EVAL_SEED = 41
EVAL_K = 3


@tool(side_effect_class=SideEffectClass.READ_ONLY)
def catalogue_search(query: str) -> str:
    """Search the retailer notes. Returns the matching entries, or a note that none matched.

    Pass a few words, such as a retailer name or a garment name.
    """
    hits = [
        f"{name}: {text}"
        for name, text in EVAL_CORPUS.items()
        if any(word.lower() in (name + " " + text).lower() for word in query.split())
    ]
    return "\n".join(hits) if hits else "No entries matched that query."


def eval_hunt(inputs, ctx):
    return Prompt.user(
        "{question}\n\nSearch the retailer notes as many times as needed, then call finish. "
        "Report `unknown` for anything the notes do not state.",
        question=inputs["question"],
    )


def eval_verify(inputs, ctx):
    # The notes come from the prompt function rather than from the previous node's output: a
    # node receives what the node before it returned, and `hunt` returns an answer.
    notes = "\n".join(f"{name}: {text}" for name, text in EVAL_CORPUS.items())
    return Prompt.user(
        "An earlier step answered a question with: {inputs}\n\nRetailer notes:\n{notes}\n\nRepeat "
        "that answer if the notes support it, or report `unknown` if they do not.",
        inputs=inputs,
        notes=notes,
    )


@pipeline_factory("answer")
def eval_pipeline() -> Pipeline:
    """The pipeline the evaluation cassette records and the project fixtures replay.

    Registered, so those manifests and their results file record which pipeline they are, and
    the fixtures pass FT-45 the way a project that registers its own pipelines does.
    """
    return Pipeline(
        [
            AgentNode(
                eval_hunt,
                tools=ToolRegistry([catalogue_search]),
                output_schema=Answer,
                budget=Budget(
                    max_steps=6, max_tokens=30_000, max_cost=None, max_wall_clock_ms=120_000
                ),
                node_id="hunt",
                temperature=0.0,
            ),
            LLMNode(eval_verify, output_schema=Answer, node_id="verify", temperature=0.0),
        ],
        budget=Budget(max_steps=None, max_tokens=200_000, max_cost=None, max_wall_clock_ms=600_000),
    )


def eval_examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id=example_id,
                inputs={"question": question},
                expected=expected
                if expected is not None
                else Unknown(reason="the notes give no figure"),
                split="held_out",
            )
            for example_id, question, expected in EVAL_EXAMPLES
        ]
    )


def eval_suite() -> EvalSuite:
    return EvalSuite(
        eval_pipeline(),
        eval_examples(),
        answer="answer",
        matches=lambda s: s.expected.lower() in str(s.answer).lower(),
        contamination_threshold=0.8,
    )


def record_eval(backend: str = "eval") -> None:
    """Record k rollouts of a two-node pipeline against a hosted backend."""
    path = CASSETTES / f"{backend}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    runs = Path(__file__).resolve().parents[1] / "runs" / f"record-{backend}"
    shutil.rmtree(runs, ignore_errors=True)

    if backend == "eval-gemini":
        basis, secret_env = GEMINI_PRICES, ["GEMINI_API_KEY"]
        # Nothing to pace against: this backend publishes no allowance on a response, so the
        # rollouts run at the concurrency asked for and a 429 is met by the retry.
        client = GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION)
    else:
        basis, secret_env = MISTRAL_PRICES, ["MISTRAL_API_KEY"]
        client = PacedClient(MistralClient(model=MISTRAL_MODEL))

    envelope = RunEnvelope(
        run_dir=runs,
        cost_basis=basis,
        redaction=Redaction(secret_env=secret_env),
        cassette=Cassette.record(path),
    )
    results = eval_suite().run(
        envelope=envelope,
        model=client,
        split="held_out",
        k=EVAL_K,
        seed=EVAL_SEED,
        concurrency=2,
    )

    print(f"recorded {path}")
    print(f"  rollouts : {len(results.rollouts)}")
    print(f"  accuracy : {results.metrics['accuracy'].value}")
    if isinstance(client, PacedClient):
        print(f"  paced    : {client.waits} wait(s)")
    for node_id, node in results.nodes.items():
        print(f"  {node_id:<9}: {node.model_calls} calls, {node.tool_calls} tool calls")


# The graph recording is the one that tests item 8c against something that reads the request.
# Two pipelines, because one covering all five shapes is not readable.
#
# `graph` branches on what the model answered: a question the notes answer goes to `hunt` and
# then to both arms of a parallel branch, and one they do not goes straight to `report`,
# skipping three nodes. `report` is a join of three edges, one of which is absent either way.
# Which arm runs is the model's decision, made by filling a schema field a route reads, so a
# fake client returning a scripted payload cannot exercise it.
GRAPH_CORPUS = {
    "kirkwall": "Kirkwall ships from Leeds and offers free returns within 30 days.",
    "northgate": "Northgate ships from Bristol. Returns cost 4.95 GBP.",
    "ashford": "The Ashford trouser is cut from cotton twill. Sold by Northgate.",
}

GRAPH_NOTES = "\n".join(f"{name}: {text}" for name, text in GRAPH_CORPUS.items())

# Two questions, recorded into one cassette. The notes answer the first, so `hunt` runs and
# both arms of the parallel branch run with it. The notes do not answer the second, so the
# route sends it straight to the report and three nodes are skipped.
GRAPH_QUESTIONS = [
    "Which retailer ships from Leeds?",
    "What is Kirkwall's annual revenue?",
]


def graph_classify(inputs, ctx):
    return Prompt.user(
        "Retailer notes:\n{GRAPH_NOTES}\n\nQuestion: {question}\n\nIf the notes state the answer, "
        "put it in `answer` as a short phrase. Report `unknown` only when nothing in the "
        "notes bears on the question.",
        GRAPH_NOTES=GRAPH_NOTES,
        question=inputs["question"],
    )


def graph_route(output, ctx):
    """Straight to the report where the model found nothing, so three nodes are skipped."""
    if isinstance(output.answer, Unknown):
        return "report"
    return "hunt"


def graph_hunt(inputs, ctx):
    return Prompt.user(
        "Retailer notes:\n{GRAPH_NOTES}\n\nAn earlier step answered: {answer}\n\nRepeat that "
        "answer if the notes support it, or report `unknown` if they do not.",
        GRAPH_NOTES=GRAPH_NOTES,
        answer=inputs.answer,
    )


def graph_summarise(inputs, ctx):
    return Prompt.user(
        "Summarise this answer in one short sentence: {answer}\n\nReport `unknown` if there is "
        "nothing to summarise.",
        answer=inputs.answer,
    )


def graph_cite(inputs, ctx):
    return Prompt.user(
        "Retailer notes:\n{GRAPH_NOTES}\n\nWhich note supports this answer: {answer}\n\nName the "
        "note, or report `unknown` if none does.",
        GRAPH_NOTES=GRAPH_NOTES,
        answer=inputs.answer,
    )


def graph_report(inputs: Join, ctx):
    """Three declared in-edges, and at least one of them is absent on either path."""
    return {
        "fired": list(inputs.fired),
        "absent": sorted(inputs.absent),
        "answer": next(
            (inputs[source].answer for source in inputs.fired if inputs[source] is not None),
            None,
        ),
    }


# Qwen3 emits a reasoning chain before its answer, and these prompts are open-ended enough for
# it to run to the context window on one call. `extra` is where a backend-specific option
# belongs, and this is the option that turns it off. Mistral is recorded without it.
NO_THINKING = {"chat_template_kwargs": {"enable_thinking": False}}


def graph_pipeline(extra: dict | None = None) -> Pipeline:
    return Pipeline(
        [
            LLMNode(
                graph_classify,
                output_schema=Answer,
                node_id="classify",
                temperature=0.0,
                extra=extra,
                successors=["hunt", "report"],
                route=graph_route,
            ),
            LLMNode(
                graph_hunt,
                output_schema=Answer,
                node_id="hunt",
                temperature=0.0,
                extra=extra,
                successors=["summarise", "cite"],
                route=lambda output, ctx: ["summarise", "cite"],
            ),
            LLMNode(
                graph_summarise,
                output_schema=Answer,
                node_id="summarise",
                temperature=0.0,
                extra=extra,
                successors=["report"],
            ),
            LLMNode(
                graph_cite,
                output_schema=Answer,
                node_id="cite",
                temperature=0.0,
                extra=extra,
                successors=["report"],
            ),
            Deterministic(graph_report, node_id="report", successors=[]),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=240_000),
    )


# `graph-loop` covers the two shapes the first pipeline does not: a cycle that runs out of
# iterations, and an error edge taken after a retry is exhausted. The model drafts and the
# critique is plain Python that always sends it back, so `max_iterations` is reached on every
# recording rather than depending on what the model says about its own work.
_FAILURES: list[int] = []


def loop_draft(inputs, ctx):
    # The entry node, and the node the cycle returns to, so it receives the run's inputs on
    # the first pass and the critique's output on the ones after.
    previous = f" Previous attempt: {inputs}." if isinstance(inputs, Answer) else ""
    return Prompt.user(
        "Write one sentence describing what Kirkwall offers, from this note: "
        "{kirkwall}.{previous} Report `unknown` if the note says nothing.",
        kirkwall=GRAPH_CORPUS["kirkwall"],
        previous=previous,
    )


def loop_critique(inputs, ctx):
    return inputs


def loop_again(output, ctx):
    """Always back to the draft, so the bound is what stops the cycle."""
    return "draft"


def loop_lookup(inputs, ctx):
    """Fails on every attempt, so the retry is exhausted and the error edge is taken."""
    _FAILURES.append(1)
    raise RuntimeError(f"the index is unreachable (attempt {len(_FAILURES)})")


def loop_fallback(inputs: NodeFailure, ctx):
    return {
        "failed": inputs.node_id,
        "attempts": inputs.attempts,
        "message": inputs.error["message"],
    }


def loop_report(inputs: Join, ctx):
    return {"fired": list(inputs.fired), "absent": sorted(inputs.absent)}


def graph_loop_pipeline(extra: dict | None = None) -> Pipeline:
    return Pipeline(
        [
            LLMNode(
                loop_draft,
                output_schema=Answer,
                node_id="draft",
                temperature=0.0,
                extra=extra,
                successors=["critique"],
            ),
            Deterministic(
                loop_critique,
                node_id="critique",
                successors=["draft", "lookup"],
                route=loop_again,
                loop=Loop(max_iterations=2, then="lookup"),
            ),
            Deterministic(
                loop_lookup,
                node_id="lookup",
                successors=["report"],
                on_error="fallback",
                retry=RetryPolicy(attempts=2),
            ),
            Deterministic(loop_fallback, node_id="fallback", successors=["report"]),
            Deterministic(loop_report, node_id="report", successors=[]),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=240_000),
    )


def record(backend: str, base_url: str | None = None) -> None:
    path = CASSETTES / f"{backend}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    if backend in ("mistral", "agent", "context", "graph", "graph-loop"):
        client = MistralClient(model=MISTRAL_MODEL)
        basis = MISTRAL_PRICES
        secret_env = ["MISTRAL_API_KEY"]
    elif _new_backend(backend):
        client, basis, secret_env = _new_client(backend, tools=backend.startswith("agent-"))
    elif backend == "gemini" or backend.endswith("-gemini"):
        client = GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION)
        basis = GEMINI_PRICES
        secret_env = ["GEMINI_API_KEY"]
    else:
        client = VLLMClient(
            model=VLLM_MODEL,
            model_revision=_vllm_revision(),
            **({"base_url": base_url} if base_url else {}),
        )
        basis = VLLM_DEVICE
        secret_env = []

    runs = Path(__file__).resolve().parents[1] / "runs" / f"record-{backend}"
    shutil.rmtree(runs, ignore_errors=True)

    envelope = RunEnvelope(
        run_dir=runs,
        cost_basis=basis,
        redaction=Redaction(secret_env=secret_env),
        cassette=Cassette.record(path),
    )
    extra = NO_THINKING if backend.endswith("-vllm") else None
    if backend in ("graph", "graph-vllm", "graph-gemini"):
        for question in GRAPH_QUESTIONS:
            result = graph_pipeline(extra).run(
                {"question": question}, envelope=envelope, model=client, seed=SEED
            )
            print(f"  {question!r}")
            print(f"    fired  : {result.output['fired']}")
            print(f"    absent : {result.output['absent']}")
    elif backend in ("graph-loop", "graph-loop-vllm"):
        _FAILURES.clear()
        result = graph_loop_pipeline(extra).run({}, envelope=envelope, model=client, seed=SEED)
    elif backend in ("tools-vllm", "tools-gemini"):
        result = tools_pipeline().run(
            {"question": TOOLS_QUESTION}, envelope=envelope, model=client, seed=SEED
        )
    elif backend in ("agent", "agent-gemini"):
        result = agent_pipeline().run(
            {"question": AGENT_QUESTION}, envelope=envelope, model=client, seed=SEED
        )
    elif backend.startswith("agent-"):
        result = agent_pipeline(temperature=None).run(
            {"question": AGENT_QUESTION}, envelope=envelope, model=client, seed=SEED
        )
    elif _new_backend(backend):
        result = pipeline(temperature=None).run(
            {"question": QUESTION}, envelope=envelope, model=client, seed=SEED
        )
    elif backend in ("context", "context-vllm"):
        result = context_pipeline().run(
            {"documents": CONTEXT_DOCUMENTS}, envelope=envelope, model=client, seed=SEED
        )
    else:
        result = pipeline().run({"question": QUESTION}, envelope=envelope, model=client, seed=SEED)

    print(f"recorded {path}")
    print(f"  output   : {result.output}")
    print(f"  manifest : {result.paths.manifest}")


# The mixed recording is the one that tests per-node model selection against real backends. A
# fake client returns a scripted response without reading what was sent, so it cannot show two
# adapters coexisting in one run: that the cassette keys separate them, that the manifest records
# a different model per node, and that a cost basis per model prices a hosted call on tokens and
# a self-hosted one on device time inside one total.
MIXED_NOTES = (
    "The Aurora 3 laptop has a 14 inch display and weighs 1.2 kg. Its battery is rated at "
    "72 Wh. The Aurora 3 Pro has the same display and weighs 1.4 kg. Neither model states a "
    "warranty period."
)
MIXED_QUESTION = "How much does the Aurora 3 Pro weigh?"


def mixed_reduce(inputs, ctx):
    """The cheap step: pull the facts out, no judgement."""
    return Prompt.user(
        "List every fact stated about the Aurora 3 Pro, one per line. Report `unknown` if "
        "the notes state none.\n\nNotes:\n{notes}",
        notes=inputs["notes"],
    )


def mixed_answer(inputs, ctx):
    """The expensive step: answer from what the cheap one kept."""
    return Prompt.user(
        MIXED_QUESTION
        + "\n\nAnswer from these facts alone. Report `unknown` only when the facts do not "
        "contain the answer; where they do, give it.\n\n{answer}",
        answer=inputs.answer,
    )


def mixed_pipeline(local, hosted) -> Pipeline:
    """One node on each backend, which is what this recording exists to exercise."""
    return Pipeline(
        [
            LLMNode(
                mixed_reduce,
                output_schema=Answer,
                node_id="reduce",
                temperature=0.0,
                model=local,
                extra=NO_THINKING,
            ),
            LLMNode(
                mixed_answer,
                output_schema=Answer,
                node_id="answer",
                temperature=0.0,
                model=hosted,
            ),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=180_000),
    )


def record_mixed(base_url: str | None = None) -> None:
    path = CASSETTES / "mixed.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    local = VLLMClient(
        model=VLLM_MODEL,
        model_revision=_vllm_revision(),
        **({"base_url": base_url} if base_url else {}),
    )
    hosted = PacedClient(MistralClient(model=MISTRAL_MODEL))

    runs = Path(__file__).resolve().parents[1] / "runs" / "record-mixed"
    shutil.rmtree(runs, ignore_errors=True)

    envelope = RunEnvelope(
        run_dir=runs,
        # One basis per model, which is what a run spanning two backends needs.
        cost_basis={VLLM_MODEL: VLLM_DEVICE, MISTRAL_MODEL: MISTRAL_PRICES},
        redaction=Redaction(secret_env=["MISTRAL_API_KEY"]),
        cassette=Cassette.record(path),
    )
    result = mixed_pipeline(local, hosted).run(
        {"notes": MIXED_NOTES}, envelope=envelope, model=None, seed=SEED
    )

    manifest = json.loads(result.paths.manifest.read_text(encoding="utf-8"))
    print(f"recorded {path}")
    print(f"  output   : {result.output}")
    print(f"  configured: {manifest['models']['configured']}")
    for entry in manifest["nodes"]:
        print(f"  node {entry['node_id']:<7}: {entry['model']}")
    for entry in manifest["models"]["observed"]:
        print(f"  served   : {entry['request_model']} x{entry['calls']}")
    print(f"  cost     : {manifest['totals']['cost']}")
    print(f"  basis    : {manifest['cost_basis']['kind']}")


# The suspend recording is the one that tests item 8d against a real backend. A fake client
# returns a scripted response without reading what was sent, so it cannot show that a backend
# accepts the conversation a resumed run rebuilds from a file. That conversation is assembled
# from `suspension.json` rather than held in memory, and the context sitting already found this
# backend family refusing a message order it disliked, so the rebuilt list is where such a
# refusal would surface.
SUSPEND_QUESTION = (
    "Find a trouser under 60 GBP. Ask the buyer which fit they want before you answer."
)


def _asks_and_stops(question: str, options, about=None):
    """A channel with nobody at the other end. The run stops and is continued later."""
    raise Suspend(waiting_for=question, options=options)


def suspend_registry(extra_answer: bool = False) -> ToolRegistry:
    return ToolRegistry(
        [
            document_search(DocumentIndex.from_texts(TOOL_CORPUS)),
            consult(
                _asks_and_stops,
                answered_by="end_user",
                description="Ask the buyer which fit they want.",
            ),
        ]
    )


def suspend_prompt(inputs, ctx):
    return Prompt.user(
        "{question}\n\nSearch the documents first. Then call `consult` once to ask the buyer "
        "which fit they want, and use their answer in your final response. Call finish when "
        "done. Report `unknown` for anything the documents do not state.",
        question=inputs["question"],
    )


def suspend_pipeline(extra=None) -> Pipeline:
    return Pipeline(
        [
            AgentNode(
                suspend_prompt,
                tools=suspend_registry(),
                output_schema=Finding,
                budget=Budget(
                    max_steps=10, max_tokens=60_000, max_cost=None, max_wall_clock_ms=240_000
                ),
                node_id="outfit",
                temperature=0.0,
                extra=extra,
            )
        ],
        budget=Budget(max_steps=None, max_tokens=120_000, max_cost=None, max_wall_clock_ms=300_000),
    )


def record_suspend(backend: str, base_url: str | None = None) -> None:
    """Run until the agent asks, then continue it as a second process would."""
    path = CASSETTES / f"{backend}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    if backend == "suspend-gemini":
        client = GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION)
        basis, secret_env, extra = GEMINI_PRICES, ["GEMINI_API_KEY"], None
    else:
        client = VLLMClient(
            model=VLLM_MODEL,
            model_revision=_vllm_revision(),
            **({"base_url": base_url} if base_url else {}),
        )
        basis, secret_env, extra = VLLM_DEVICE, [], NO_THINKING

    runs = Path(__file__).resolve().parents[1] / "runs" / f"record-{backend}"
    shutil.rmtree(runs, ignore_errors=True)
    envelope = RunEnvelope(
        run_dir=runs,
        cost_basis=basis,
        redaction=Redaction(secret_env=secret_env),
        cassette=Cassette.record(path),
    )

    run_id = "record-suspend"
    pipeline = suspend_pipeline(extra)
    try:
        pipeline.run(
            {"question": SUSPEND_QUESTION},
            envelope=envelope,
            model=client,
            seed=SEED,
            run_id=run_id,
        )
    except RunSuspended as stop:
        print(f"  suspended: {stop.waiting_for!r}")
        print(f"  state    : {stop.state_path}")
    else:
        raise SystemExit(
            "The agent never called `consult`, so nothing suspended and the recording proves "
            "nothing. Adjust the prompt and record again."
        )

    # The second process. Everything the first one held is read back from the file.
    result = suspend_pipeline(extra).resume(run_id, envelope=envelope, model=client, answer="slim")
    records = [
        json.loads(line)
        for line in result.paths.trajectory.read_text().splitlines()
        if line.strip()
    ]
    consultations = [r for r in records if r["record_type"] == "consultation"]
    print(f"recorded {path}")
    print(f"  output        : {result.output}")
    print(f"  consultations : {[r['resolution'] for r in consultations]}")
    print(f"  suspensions   : {result.manifest['suspensions']}")
    print(f"  manifest      : {result.paths.manifest}")


STREAM_QUESTION = (
    "Which retailer sells the trouser with a 34 inch inseam, and what is its returns policy?"
)


def stream_prompt(inputs, ctx):
    return Prompt.user(
        "{question}\n\nUse only this catalogue:\n{catalogue}"
        "\n\nReport the answer, or `unknown` if it is not in the catalogue.",
        question=inputs["question"],
        catalogue=Section.joined(
            "catalogue",
            [Section("entry", "- {k}: {v}", k=k, v=v) for k, v in CATALOGUE.items()],
        ),
    )


def stream_pipeline(extra=None, temperature: float | None = 0.0) -> Pipeline:
    """One streaming node and one that does not stream, so a recording holds both shapes."""
    return Pipeline(
        [
            LLMNode(
                stream_prompt,
                output_schema=Finding,
                node_id="answer",
                temperature=temperature,
                stream=True,
                extra=extra,
            ),
            LLMNode(
                lambda inputs, ctx: Prompt.user(
                    "Restate this in one sentence: {inputs}. Report `unknown` for anything absent.",
                    inputs=inputs,
                ),
                output_schema=Finding,
                node_id="restate",
                temperature=temperature,
                extra=extra,
            ),
        ],
        budget=Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=180_000),
    )


def record_stream(backend: str, base_url: str | None = None) -> None:
    """Record a streamed call and a non-streamed one, and report what the backend delivered."""
    path = CASSETTES / f"{backend}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)

    if backend == "stream":
        client = MistralClient(model=MISTRAL_MODEL)
        basis, secret_env, extra = MISTRAL_PRICES, ["MISTRAL_API_KEY"], None
    elif backend == "stream-gemini":
        client = GeminiClient(model=GEMINI_MODEL, model_revision=GEMINI_REVISION)
        basis, secret_env, extra = GEMINI_PRICES, ["GEMINI_API_KEY"], None
    elif _new_backend(backend):
        client, basis, secret_env = _new_client(backend)
        extra = None
    else:
        client = VLLMClient(
            model=VLLM_MODEL,
            model_revision=_vllm_revision(),
            **({"base_url": base_url} if base_url else {}),
        )
        basis, secret_env, extra = VLLM_DEVICE, [], NO_THINKING

    runs = Path(__file__).resolve().parents[1] / "runs" / f"record-{backend}"
    shutil.rmtree(runs, ignore_errors=True)
    envelope = RunEnvelope(
        run_dir=runs,
        cost_basis=basis,
        redaction=Redaction(secret_env=secret_env),
        cassette=Cassette.record(path),
    )

    pieces: list[str] = []
    temperature = None if _new_backend(backend) else 0.0
    result = stream_pipeline(extra, temperature=temperature).run(
        {"question": STREAM_QUESTION},
        envelope=envelope,
        model=client,
        seed=SEED,
        run_id=f"record-{backend}",
        on_token=lambda event: pieces.append(event.text),
    )

    records = [
        json.loads(line)
        for line in result.paths.trajectory.read_text().splitlines()
        if line.strip()
    ]
    calls = [r for r in records if r["record_type"] == "model_call"]
    print(f"recorded {path}")
    print(f"  output          : {result.output}")
    print(f"  pieces delivered: {len(pieces)}")
    print(f"  rebuilt content : {''.join(pieces) == (calls[0]['outputs']['content'] or '')}")
    for call in calls:
        print(
            f"  call {call['params']['seed']}: stream={call['stream']} "
            f"finish={call['finish_reason']!r} tokens={call['tokens']} "
            f"rate_limit={call['rate_limit']}"
        )


def _vllm_revision() -> str:
    """The commit the local weights came from, which the server does not report.

    Follows the hub's own cache resolution: ``HF_HUB_CACHE``, then ``HF_HOME/hub``, then the
    default under the home directory.
    """
    import os

    if os.environ.get("HF_HUB_CACHE"):
        hub = Path(os.environ["HF_HUB_CACHE"])
    elif os.environ.get("HF_HOME"):
        hub = Path(os.environ["HF_HOME"]) / "hub"
    else:
        hub = Path.home() / ".cache" / "huggingface" / "hub"

    ref = hub / f"models--{VLLM_MODEL.replace('/', '--')}" / "refs" / "main"
    if not ref.exists():
        raise SystemExit(
            f"No local snapshot for {VLLM_MODEL} under {hub}. Pull the weights first, or "
            f"pass the revision explicitly."
        )
    return ref.read_text().strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "backend",
        choices=[
            "mistral",
            "vllm",
            "gemini",
            "agent",
            "agent-gemini",
            "context",
            "context-vllm",
            "tools-vllm",
            "tools-gemini",
            "eval",
            "eval-gemini",
            "graph",
            "graph-vllm",
            "graph-gemini",
            "graph-loop",
            "graph-loop-vllm",
            "suspend-gemini",
            "suspend-vllm",
            "stream",
            "stream-vllm",
            "stream-gemini",
            "mixed",
            "openai",
            "agent-openai",
            "stream-openai",
            "openai-responses",
            "agent-openai-responses",
            "stream-openai-responses",
            "anthropic",
            "agent-anthropic",
            "stream-anthropic",
        ],
    )
    parser.add_argument("--base-url", default=None, help="where the vLLM server is listening")
    args = parser.parse_args()
    if args.backend in ("eval", "eval-gemini"):
        record_eval(args.backend)
    elif args.backend == "mixed":
        record_mixed(args.base_url)
    elif args.backend.startswith("stream"):
        record_stream(args.backend, args.base_url)
    elif args.backend.startswith("suspend"):
        record_suspend(args.backend, args.base_url)
    else:
        record(args.backend, args.base_url)
