"""The runs this fixture is committed with, as a spec both modes drive.

`scripts/build_view_fixtures.py` regenerates the committed runs by replaying the cassettes,
offline and free. Running this file directly makes them against the live backend instead,
which is how the cassettes are recorded again:

    cd tests/fixtures/view_projects/prompted
    GEMINI_API_KEY=... uv run python record.py

Two runs, each given a different house style, so one step records two instructions and the
page has a step whose words arrive as data.
"""

import os
import sys
from pathlib import Path
from typing import Callable

from simple_agents import Cassette, GeminiClient, PriceBasis, Redaction, RunEnvelope

sys.path.insert(0, str(Path(__file__).parent))
from agent import trip  # noqa: E402

MODEL = "gemini-3.1-flash-lite"

BASIS = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=0.10,
    input_cache_read_per_mtok=0.025,
    input_cache_write_per_mtok=0.0,
    output_per_mtok=0.40,
)

NOTES = (
    "Prefers hotels near a metro stop. Vegetarian. Travelling with a partner who uses a "
    "wheelchair, so step-free access matters more than anything else on this list. Has been "
    "to Paris twice before and does not want the usual landmarks again. Likes markets in the "
    "morning and quiet museums in the afternoon."
)

THREAD = (
    {"role": "user", "content": "Is early May a good time for Paris?"},
    {"role": "assistant", "content": "It is. The markets are open and the queues are short."},
)

RUNS = (
    (
        "warm",
        {
            "message": "The trip is Paris then Lyon in early May, I have about 900 euros.",
            "notes": NOTES,
            "days": 4,
            "voice": "Talk to me like a local friend. Short sentences. Tell me the weather.",
            "thread": THREAD,
            "template": "Rewrite this reply so it opens with the first day.\n\n{reply}",
        },
        1450025368,
    ),
    (
        "brisk",
        {
            "message": "Two days in Lyon in June, travelling light.",
            "notes": NOTES,
            "days": 2,
            "voice": "Keep it brisk. Bullet points are fine.",
            "thread": THREAD,
            "template": "Cut this reply to three bullet points.\n\n{reply}",
        },
        1450025369,
    ),
)


def envelope(cassette: Cassette) -> RunEnvelope:
    return RunEnvelope(
        run_dir="runs",
        cost_basis=BASIS,
        redaction=Redaction(secret_env=["GEMINI_API_KEY"]),
        cassette=cassette,
    )


def client(api_key: str | None = None) -> GeminiClient:
    return GeminiClient(model=MODEL, **({"api_key": api_key} if api_key else {}))


def make(cassette_for: Callable[..., Cassette], model: GeminiClient,
         replaying: bool = False) -> None:
    """Make the committed runs, reading each call through the cassette given."""
    for label, inputs, seed in RUNS:
        result = trip().run(inputs, envelope=envelope(cassette_for(label)), model=model,
                            seed=seed)
        print(f"run: {result.paths.manifest}, cost {result.cost['value']}")


if __name__ == "__main__":
    import shutil

    if not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY is not set.")
    shutil.rmtree("runs", ignore_errors=True)
    shutil.rmtree("cassettes", ignore_errors=True)
    Path("cassettes").mkdir()
    make(lambda label, evaluation=False: Cassette.record(Path("cassettes") / f"{label}.jsonl"),
         client())
