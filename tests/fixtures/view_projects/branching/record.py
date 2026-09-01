"""The runs and the evaluation this fixture is committed with, as a spec both modes drive.

`scripts/build_view_fixtures.py` regenerates the committed records by replaying the
cassettes under ``cassettes/``, offline and free. Running this file directly makes the
records against the live backend instead, which is how the cassettes are recorded again:

    cd tests/fixtures/view_projects/branching
    GEMINI_API_KEY=... uv run python record.py

Run from the fixture's own directory either way, so the paths the records carry stay
relative to it. One real run per ticket below and one real evaluation over the examples
beside it, so the view's run overlay and its measure section are tested against records a
backend wrote.
"""

import os
import sys
from pathlib import Path
from typing import Callable

from simple_agents import Cassette, GeminiClient, PriceBasis, Redaction, RunEnvelope, Unknown
from simple_agents.builtins.consult import unattended
from simple_agents.evaluation import EvalSuite, ExampleSet

sys.path.insert(0, str(Path(__file__).parent))
from agent import _triage, triage  # noqa: E402

# Read from the provider's price list on 2026-08-26, per million tokens.
BASIS = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.10,
    input_cache_read_per_mtok=0.025,
    input_cache_write_per_mtok=0.0,
    output_per_mtok=0.40,
)

MODEL = "gemini-3.1-flash-lite"

TICKET = "The export button greys out after I add a second filter. Is that expected?"

# A ticket with nothing to look up, so the run takes the branch that decides for itself and
# asks the rota. Two runs of one shape is also what the page reads to say what moved between
# them.
CHATTY = "Thanks, that sorted it. Anything else I should know before I close this?"

# One committed cassette per record made, named by what it holds.
RUNS = (
    ("ticket-export", {"ticket": TICKET}, 41),
    ("ticket-thanks", {"ticket": CHATTY}, 42),
)
EVALUATION = {"cassette": "evaluation", "split": "held_out", "k": 2, "seed": 41,
              "max_spend": 2.00}
# A rung: the pipeline from `classify` on, handed what `intake` would have produced. Its
# results file names the whole pipeline through `config.slice`, which is what makes the two
# a ladder on the page.
RUNG = {"cassette": "rung", "start": "classify", "seed": 44,
        "results": "evals/results/held-out-from-classify.json"}
# A variant: the same graph with the revision loop bounded at one pass. The comparison is
# written under `evals/variants/`, the variant's own results beside the others, and the arms'
# cassettes where `compare_variants` keeps them, under `runs/variant_cassettes/`.
VARIANT = {"name": "no revision", "seed": 43,
           "comparison": "evals/variants/no-revision.json",
           "results": "evals/results/held-out-no-revision.json"}


def envelope(cassette: Cassette) -> RunEnvelope:
    return RunEnvelope(
        run_dir="runs",
        cost_basis=BASIS,
        redaction=Redaction(secret_env=["GEMINI_API_KEY"]),
        cassette=cassette,
    )


def client(api_key: str | None = None) -> GeminiClient:
    return GeminiClient(model=MODEL, **({"api_key": api_key} if api_key else {}))


def reply_source(output: dict) -> object:
    """The answer an evaluation scores: which source produced the sent reply.

    An escalated ticket produced no reply at all, the rota has it, so the answer there is an
    absence rather than the branch's name. That is what lets an example whose right answer
    is absence be scored `correct_abstention` (`DF5-X20` is the defect this guards).
    """
    if output.get("from") == "escalate":
        return Unknown(reason="escalated to the rota, so no reply went out")
    return output.get("from")


def suite(pipeline=None, examples=None) -> EvalSuite:
    examples = examples if examples is not None else ExampleSet.from_jsonl("evals/examples.jsonl")
    return EvalSuite(
        pipeline if pipeline is not None else triage(),
        examples,
        answer=reply_source,
        matches=lambda s: s.answer == s.expected,
        node_matches={"classify": lambda s: bool(s.answer["needs_handbook"]) == bool(s.expected)},
        baseline=lambda example: "escalate",
    )


def make(cassette_for: Callable[..., Cassette], model: GeminiClient,
         replaying: bool = False) -> None:
    """Make every committed record, reading each call through the cassette given.

    ``cassette_for(label, evaluation=...)`` says which record the cassette is for. An
    evaluation's recording has to be one session (the runner refuses ``Cassette.update``),
    so a re-record is always a fresh file. ``replaying`` leaves the variant comparison out:
    ``compare_variants`` records its arms' cassettes itself under ``runs/variant_cassettes/``
    and always makes the baseline live, so it has no offline form.
    """
    for label, inputs, seed in RUNS:
        result = triage().run(inputs, envelope=envelope(cassette_for(label)),
                              model=model, seed=seed)
        print(f"run: {result.paths.manifest}, cost {result.cost['value']}")
    results = suite().run(
        envelope=envelope(cassette_for(EVALUATION["cassette"], evaluation=True)),
        model=model,
        split=EVALUATION["split"], k=EVALUATION["k"], seed=EVALUATION["seed"],
        max_spend=EVALUATION["max_spend"], end_user=unattended(),
    )
    results.write("evals/results/held-out.json", overwrite=True)
    print(results.report())

    rung = triage().slice(start=RUNG["start"])
    examples = ExampleSet.from_jsonl("evals/examples.jsonl")
    rung_results = suite(rung, examples.entering(rung)).run(
        envelope=envelope(cassette_for(RUNG["cassette"], evaluation=True)),
        model=model,
        split=EVALUATION["split"], k=EVALUATION["k"], seed=RUNG["seed"],
        max_spend=EVALUATION["max_spend"], end_user=unattended(),
    )
    rung_results.write(RUNG["results"], overwrite=True)
    print(rung_results.report())

    if replaying:
        return
    from simple_agents.evaluation import compare_variants

    comparison = compare_variants(
        suite(), {VARIANT["name"]: _triage(revisions=1)},
        envelope=envelope(Cassette.off()),
        model=model,
        split=EVALUATION["split"], k=EVALUATION["k"], seed=VARIANT["seed"],
        max_spend=EVALUATION["max_spend"], end_user=unattended(),
    )
    comparison.write(VARIANT["comparison"])
    comparison.variants[VARIANT["name"]].write(VARIANT["results"], overwrite=True)
    print(comparison.comparisons[VARIANT["name"]].report())


if __name__ == "__main__":
    import shutil

    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set.")
    shutil.rmtree("runs", ignore_errors=True)
    shutil.rmtree("cassettes", ignore_errors=True)
    Path("cassettes").mkdir()
    make(lambda label, evaluation=False: Cassette.record(Path("cassettes") / f"{label}.jsonl"),
         client())
