"""The runs and the evaluations this fixture is committed with, as a spec both modes drive.

`scripts/build_view_fixtures.py` verifies the committed records by replaying the cassettes
under ``cassettes/``, offline and free. Running this file directly makes the records against
the live backend instead, which is how the cassettes are recorded again:

    cd tests/fixtures/view_projects/measured
    GEMINI_API_KEY=... uv run python record.py

Run from the fixture's own directory either way, so the paths the records carry stay
relative to it. What it makes, in order: two live runs; two evaluations of the decide prompt
as first written and one of the current prompt, which is the history the trend draws; the
reported evaluation; two rungs cut at ``extract`` and ``policy_check``; and one sweep of two
variants against the baseline, which is what the comparison draws.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from simple_agents import Cassette, GeminiClient, PriceBasis, Redaction, RunEnvelope, Unknown
from simple_agents.builtins.consult import unattended
from simple_agents.evaluation import EvalSuite, ExampleSet, Over, ProjectMetric, ProjectRatio

sys.path.insert(0, str(Path(__file__).parent))
from agent import build, canonical_vendor, claims  # noqa: E402

# Read from the provider's price list on 2026-08-26, per million tokens.
BASIS = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.10,
    input_cache_read_per_mtok=0.025,
    input_cache_write_per_mtok=0.0,
    output_per_mtok=0.40,
)

MODEL = "gemini-3.1-flash-lite"
SUBMITTED_ON = "2026-08-20"

RUNS = (
    ("claim-lunch", {"claim": "Client lunch at The Copper Kettle, 14 Aug 2026. Total £48.30 "
                              "incl. service. Receipt attached.", "submitted_on": SUBMITTED_ON}, 41),
    ("claim-dinner", {"claim": "Team dinner, Harbour Hotels restaurant, 7 Aug 2026, £212.00 for "
                               "six people, receipt attached.", "submitted_on": SUBMITTED_ON}, 42),
)

SPLIT = "held_out"
MAX_SPEND = 4.00
CONCURRENCY = 6

# Earlier evaluations, oldest first: two of the decide prompt as first written, then one of
# the current prompt, so the trend has a line, a break, and a line again.
HISTORY = (
    ("history-1", {"prompt_version": 1}, 11, "evals/results/held-out-1.json"),
    ("history-2", {"prompt_version": 1}, 12, "evals/results/held-out-2.json"),
    ("history-3", {}, 13, "evals/results/held-out-3.json"),
)
EVALUATION = {"cassette": "evaluation", "k": 2, "seed": 41, "results": "evals/results/held-out.json"}
RUNGS = (
    ("rung-extract", "extract", 44, "evals/results/held-out-from-extract.json"),
    ("rung-policy", "policy_check", 45, "evals/results/held-out-from-policy-check.json"),
)
VARIANTS = {
    "finance without the registry": {"registry": False},
    "audit cannot send back": {"revisions": 1},
}
SWEEP = {"seed": 43, "comparison": "evals/variants/sweep.json",
         "results": {"finance without the registry": "evals/results/held-out-no-registry.json",
                     "audit cannot send back": "evals/results/held-out-one-audit.json"}}


def envelope(cassette: Cassette) -> RunEnvelope:
    return RunEnvelope(
        run_dir="runs",
        cost_basis=BASIS,
        redaction=Redaction(secret_env=["GEMINI_API_KEY"]),
        cassette=cassette,
    )


def client(api_key: str | None = None) -> GeminiClient:
    return GeminiClient(model=MODEL, **({"api_key": api_key} if api_key else {}))


# -- scoring ---------------------------------------------------------------------------------


def _absent(value: Any) -> bool:
    return isinstance(value, Unknown) or (isinstance(value, dict) and value.get("type") == "unknown")


def answer(output: dict) -> Any:
    """The record the evaluation scores: a parked claim is an absence, the rest is the decision."""
    if output.get("decision") == "park":
        return Unknown(reason="parked for finance")
    return {k: output.get(k) for k in ("decision", "vendor", "total", "category", "po_number")}


def _truth(s) -> dict:
    return s.example.expected_by_node["extract"]


def check_decision(s):
    return s.answer["decision"] == s.example.expected_by_node["decide"] \
        if s.example.expected_by_node["decide"] != "escalate" else s.answer["decision"] == "approve"


def check_vendor(s):
    if _absent(s.answer["vendor"]):
        return Unknown()
    return canonical_vendor(s.answer["vendor"]) == canonical_vendor(_truth(s)["vendor"])


def check_total(s):
    if _absent(s.answer["total"]) or not isinstance(s.answer["total"], (int, float)):
        return Unknown()
    return abs(float(s.answer["total"]) - float(_truth(s)["total"])) < 0.01


def check_category(s):
    return s.answer["category"] == _truth(s)["category"]


def check_po(s):
    if _absent(s.answer["po_number"]):
        return Unknown()
    return str(s.answer["po_number"]).strip().upper() == str(_truth(s)["po_number"]).upper()


def extract_matches(s) -> bool:
    """Every field read as labelled; an absence on both sides is a match."""
    got, want = s.answer, s.expected
    for name in ("vendor", "po_number"):
        if _absent(got.get(name)) != _absent(want.get(name)):
            return False
        if not _absent(want.get(name)) and canonical_vendor(str(got.get(name))) != canonical_vendor(str(want.get(name))) \
                and str(got.get(name)).strip().upper() != str(want.get(name)).strip().upper():
            return False
    total = got.get("total")
    if not isinstance(total, (int, float)) or abs(float(total) - float(want["total"])) >= 0.01:
        return False
    return all(got.get(name) == want.get(name) for name in ("category", "receipt", "expense_date"))


def decide_matches(s) -> bool:
    return s.answer["decision"] == s.expected


def total_error(s) -> float:
    """How far the total read is from the total claimed, in pounds; a blank counts as the whole."""
    truth = float(_truth(s)["total"])
    got = s.answer["total"] if isinstance(s.answer, dict) else None
    if not isinstance(got, (int, float)):
        return truth
    return abs(float(got) - truth)


def money_approved(s) -> float:
    if not isinstance(s.answer, dict) or s.answer.get("decision") != "approve":
        return 0.0
    return float(_truth(s)["total"])


def money_claimed(s) -> float:
    return float(_truth(s)["total"])


def blank_fields(s) -> int:
    """Fields the claim stated that extract left blank; a blank where the claim stated nothing is right."""
    return sum(1 for name in ("vendor", "total", "category", "po_number", "expense_date")
               if _absent(s.answer.get(name)) and not _absent(s.expected.get(name)))


METRICS = [
    ProjectMetric(name="total_error_gbp", definition="pounds between the total read and the total claimed",
                  score=total_error, unit="GBP"),
    ProjectRatio(name="money_approved_share",
                 definition="pounds approved over pounds claimed",
                 numerator=money_approved, denominator=money_claimed, over=Over.ALL),
]
NODE_METRICS = {
    "extract": [ProjectRatio(name="fields_left_blank",
                             definition="fields the claim stated that extract left blank, over the five it reads",
                             numerator=blank_fields, denominator=lambda s: 5)],
}


def baseline(example) -> dict:
    """An agent that approves everything and reads nothing."""
    return {"decision": "approve", "vendor": Unknown(reason="did nothing"),
            "total": Unknown(reason="did nothing"), "category": Unknown(reason="did nothing"),
            "po_number": Unknown(reason="did nothing")}


def suite(pipeline=None, examples=None) -> EvalSuite:
    """The suite over a pipeline; a rung names only the labelled steps it still holds."""
    pipeline = pipeline if pipeline is not None else claims()
    examples = examples if examples is not None else ExampleSet.from_jsonl("evals/examples.jsonl")
    held = {node_id for node_id, _ in pipeline.declared_nodes()}
    node_matches = {"extract": extract_matches, "decide": decide_matches}
    return EvalSuite(
        pipeline,
        examples,
        answer=answer,
        matches=lambda s: s.answer == s.expected,
        criteria={"decision": check_decision, "vendor": check_vendor, "total": check_total,
                  "category": check_category, "po_number": check_po},
        node_matches={k: v for k, v in node_matches.items() if k in held},
        metrics=METRICS,
        node_metrics={k: v for k, v in NODE_METRICS.items() if k in held},
        baseline=baseline,
    )


def _run(built: EvalSuite, cassette: Cassette, model: GeminiClient, *, k: int, seed: int):
    return built.run(
        envelope=envelope(cassette), model=model, split=SPLIT, k=k, seed=seed,
        max_spend=MAX_SPEND, end_user=unattended(), concurrency=CONCURRENCY,
    )


def make(cassette_for: Callable[..., Cassette], model: GeminiClient,
         replaying: bool = False, sweep_only: bool = False) -> None:
    """Make every committed record, reading each call through the cassette given.

    ``cassette_for(label, evaluation=...)`` says which record the cassette is for. The
    reported evaluation is written last of the whole-pipeline evaluations so it is the
    newest on record. ``replaying`` leaves the sweep out: ``compare_variants`` records its
    arms itself and has no offline form. ``sweep_only`` makes the sweep alone, against the
    reported evaluation already on disk, which is the re-record after a change that moves
    only what a comparison writes.
    """
    if sweep_only:
        _clear_sweep()
        _sweep(model)
        return
    for label, inputs, seed in RUNS:
        result = claims().run(inputs, envelope=envelope(cassette_for(label)), model=model, seed=seed)
        print(f"run: {result.paths.manifest}, cost {result.cost['value']}")

    for label, knobs, seed, out in HISTORY:
        results = _run(suite(build(**knobs)), cassette_for(label, evaluation=True), model, k=1, seed=seed)
        results.write(out, overwrite=True)
        print(f"{out}: {results.metrics['accuracy'].interval.point:.3f}")

    results = _run(suite(), cassette_for(EVALUATION["cassette"], evaluation=True), model,
                   k=EVALUATION["k"], seed=EVALUATION["seed"])
    results.write(EVALUATION["results"], overwrite=True)
    print(results.report())

    examples = ExampleSet.from_jsonl("evals/examples.jsonl")
    for label, start, seed, out in RUNGS:
        rung = claims().slice(start=start)
        rung_results = _run(suite(rung, examples.entering(rung)), cassette_for(label, evaluation=True),
                            model, k=1, seed=seed)
        rung_results.write(out, overwrite=True)
        print(f"{out}: {rung_results.metrics['accuracy'].interval.point:.3f}")

    if replaying:
        return
    _sweep(model)


def _clear_sweep() -> None:
    """Drop the last sweep's arms, which `compare_variants` refuses to write over."""
    import json
    import shutil

    written = Path(SWEEP["comparison"])
    if written.exists():
        held = json.loads(written.read_text(encoding="utf-8"))
        ids = [(held.get("baseline") or {}).get("eval_id")] + [
            v.get("eval_id") for v in (held.get("variants") or {}).values()]
        for eval_id in filter(None, ids):
            shutil.rmtree(Path("runs/eval") / str(eval_id), ignore_errors=True)
    shutil.rmtree("runs/variant_cassettes", ignore_errors=True)


def _sweep(model: GeminiClient) -> None:
    from simple_agents.evaluation import compare_variants

    comparison = compare_variants(
        suite(), {name: build(**knobs) for name, knobs in VARIANTS.items()},
        envelope=envelope(Cassette.off()), model=model,
        split=SPLIT, k=1, seed=SWEEP["seed"], max_spend=MAX_SPEND, end_user=unattended(),
        concurrency=CONCURRENCY,
    )
    comparison.write(SWEEP["comparison"])
    for name, out in SWEEP["results"].items():
        comparison.variants[name].write(out, overwrite=True)
        print(comparison.comparisons[name].report())


def prune() -> None:
    """Keep the run directories the page reads, and drop the rest.

    The page walks the reported evaluation's rollouts and reads every other evaluation (the
    history, the rungs, the sweep's arms) from its results file alone, so their run
    directories are 24MB of trajectories nothing opens. Ruled by Thilina on 2026-08-29. The
    sweep's own cassettes go with them: nothing replays a sweep.
    """
    import json
    import shutil

    keep = json.loads(Path(EVALUATION["results"]).read_text(encoding="utf-8"))["eval_id"]
    for held in sorted(Path("runs/eval").glob("eval_*")):
        if held.name != keep:
            shutil.rmtree(held)
    shutil.rmtree("runs/variant_cassettes", ignore_errors=True)


if __name__ == "__main__":
    import shutil

    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set.")
    sweep_only = "--sweep-only" in sys.argv
    if not sweep_only:
        shutil.rmtree("runs", ignore_errors=True)
        shutil.rmtree("cassettes", ignore_errors=True)
        Path("cassettes").mkdir()
    make(lambda label, evaluation=False: Cassette.record(Path("cassettes") / f"{label}.jsonl"),
         client(), sweep_only=sweep_only)
    prune()
