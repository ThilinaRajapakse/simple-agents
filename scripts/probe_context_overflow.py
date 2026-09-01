"""Measure what each backend does with a request longer than its context window.

The library classifies an over-length refusal into `ContextOverflow`, and the matcher that
does it is written against what this script captured rather than against an assumption. Run
it again whenever a backend's error shape might have moved.

    uv run python scripts/probe_context_overflow.py vllm --base-url http://localhost:8001
    uv run python scripts/probe_context_overflow.py mistral

It reports four things and writes the refusal to `tests/fixtures/wire/<backend>/` in the
shape the other wire fixtures use:

1. the window the backend publishes on `GET /v1/models`,
2. the status and body of an over-length refusal,
3. whether that response carries a `usage` block,
4. for Mistral, whether the published token allowance moved across the refusal, which is the
   only evidence available here about whether a rejected request consumes anything.

The over-length request is built from the published window, so it stays proportionate to
whatever model is being probed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "wire"

MISTRAL_MODEL = "mistral-small-2603"
VLLM_MODEL = "Qwen/Qwen3-1.7B"

# The filler is one ordinary English word repeated, which every BPE tokenizer in use here
# encodes as a single token, so the repetition count is the token count closely enough to
# overshoot a window deliberately. Nothing in the library uses this; the payload only has to
# be too long.
FILLER_WORD = "context "
OVERSHOOT = 1.2

RATE_LIMIT_HEADERS = (
    "x-ratelimit-remaining-req-minute",
    "x-ratelimit-remaining-tokens-minute",
)


def probe(backend: str, base_url: str | None) -> int:
    if backend == "mistral":
        key = os.environ.get("MISTRAL_API_KEY")
        if not key:
            print("MISTRAL_API_KEY is not set. Export it from .env and run again.")
            return 1
        url = base_url or "https://api.mistral.ai/v1"
        headers = {"Authorization": f"Bearer {key}"}
        model = MISTRAL_MODEL
        window_field = "max_context_length"
    else:
        url = base_url or "http://localhost:8001/v1"
        headers = {}
        model = VLLM_MODEL
        window_field = "max_model_len"

    with httpx.Client(base_url=url, headers=headers, timeout=180.0) as client:
        window = _window(client, model, window_field)
        if window is None:
            return 1

        before = _small_call(client, model) if backend == "mistral" else {}
        status, body, response_headers = _overlong_call(client, model, window)

        print(f"\n=== {backend}: over-length refusal")
        print(f"status : {status}")
        print(f"body   : {json.dumps(body)[:800]}")
        print(f"usage present: {'usage' in body}")

        if backend == "mistral":
            print("\n=== rate-limit headers")
            for header in RATE_LIMIT_HEADERS:
                print(f"  {header}: {before.get(header)} -> {response_headers.get(header)}")

        _write_fixture(backend, model, window, status, body)
    return 0


def _window(client: httpx.Client, model: str, field: str) -> int | None:
    """The context window the backend publishes for this model, or a refusal to guess one."""
    response = client.get("/models")
    if response.status_code >= 300:
        print(f"GET /models returned {response.status_code}: {response.text[:300]}")
        return None
    entries = response.json().get("data", [])
    for entry in entries:
        if entry.get("id") == model:
            window = entry.get(field)
            print(f"=== {model}: {field} = {window}")
            if window is None:
                print(f"  the model list carries no {field}, so the window is unmeasured here")
            return window
    print(f"{model} is not in the model list. Present: {[e.get('id') for e in entries][:10]}")
    return None


def _small_call(client: httpx.Client, model: str) -> dict[str, str]:
    """One tiny call, so the allowance headers have a reading to compare against."""
    response = client.post(
        "/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Reply OK."}],
            "max_tokens": 4,
        },
    )
    return {h: response.headers.get(h, "") for h in RATE_LIMIT_HEADERS}


def _overlong_call(
    client: httpx.Client, model: str, window: int
) -> tuple[int, dict[str, Any], httpx.Headers]:
    filler = FILLER_WORD * int(window * OVERSHOOT)
    print(f"sending {len(filler)} characters, aiming at about {int(window * OVERSHOOT)} tokens")
    response = client.post(
        "/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": filler}], "max_tokens": 16},
    )
    try:
        body = response.json()
    except ValueError:
        body = {"_not_json": response.text[:600]}
    return response.status_code, body, response.headers


def _write_fixture(
    backend: str, model: str, window: int, status: int, body: dict[str, Any]
) -> None:
    """Store the refusal where the other wire fixtures live, with the payload described.

    The request that produced it is megabytes of filler, so the fixture records its size
    rather than its content. What the matcher reads is the response.
    """
    path = FIXTURES / backend / "error_context_overflow.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": status,
                "request": {
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"<filler, {window} token window overshot {OVERSHOOT}x>",
                        }
                    ],
                    "max_tokens": 16,
                },
                "response": body,
            },
            indent=2,
        )
        + "\n"
    )
    print(f"\nwrote {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=["mistral", "vllm"])
    parser.add_argument("--base-url", default=None, help="where the backend is listening")
    args = parser.parse_args()
    sys.exit(probe(args.backend, args.base_url))
