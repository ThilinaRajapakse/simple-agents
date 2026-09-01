"""The run this fixture is committed with, as a spec both modes drive.

`scripts/build_view_fixtures.py` regenerates the committed run by replaying
``cassettes/note.jsonl``, offline and free. Running this file directly makes it against the
live backend instead, which is how the cassette is recorded again:

    cd tests/fixtures/view_projects/one-pipeline
    GEMINI_API_KEY=... uv run python record.py

Run from the fixture's own directory either way, so the paths the record carries stay
relative to it.
"""

import os
import sys
from pathlib import Path
from typing import Callable

from simple_agents import Cassette, GeminiClient, PriceBasis, Redaction, RunEnvelope

sys.path.insert(0, str(Path(__file__).parent))
from agent import summarise  # noqa: E402

MODEL = "gemini-3.1-flash-lite"

# The by-model form, so the fixture set holds both shapes a manifest records.
BASIS = {
    MODEL: PriceBasis(
        currency="USD",
        input_uncached_per_mtok=0.10,
        input_cache_read_per_mtok=0.025,
        input_cache_write_per_mtok=0.0,
        output_per_mtok=0.40,
    ),
}

NOTE = (
    "Met the packaging vendor. They can do compostable trays at 12c a unit if we commit to "
    "50k units. Sarah wants a second quote before we sign. Follow up by Friday with the "
    "numbers comparison."
)

RUNS = (("note", {"note": NOTE}, 1450025368),)


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
    """Make the committed run, reading each call through the cassette given."""
    for label, inputs, seed in RUNS:
        result = summarise().run(inputs, envelope=envelope(cassette_for(label)),
                                 model=model, seed=seed)
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
