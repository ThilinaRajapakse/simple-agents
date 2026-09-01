"""Capture what Gemini answers, in the shape the wire fixtures use.

`tests/test_adapters.py` replays these through an `httpx.MockTransport`, which tests the part
a model cassette cannot: a cassette stores a decoded `ModelResponse`, so replaying one never
re-enters the adapter and says nothing about how the wire format was read. Run this again
whenever the backend's shapes might have moved.

    uv run python scripts/probe_gemini_wire.py

It needs `GEMINI_API_KEY` and writes to `tests/fixtures/wire/gemini/`. Every exchange is one
file holding the status, the request that produced it and the body that came back, verbatim.

Two of them are the reasons this adapter does not sit on `_openai_wire`, and both are
refusals: the OpenAI-compatible endpoint rejects the seed every run is keyed by, and either
endpoint rejects the turn after a tool call whose thought signature was dropped.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "wire" / "gemini"
NATIVE = "https://generativelanguage.googleapis.com/v1beta"
OPENAI = "https://generativelanguage.googleapis.com/v1beta/openai"
MODEL = "gemini-3.1-flash-lite"

# Long enough that the provider caches the prefix, so a second call reports a read against it.
CACHE_PREFIX = (
    "Catalogue entry. The Ashford trouser is cut from cotton twill and sold by Northgate. "
    "The Belmont trouser has a 34 inch inseam and is sold by Kirkwall. "
    "Kirkwall ships from Leeds and offers free returns within 30 days. "
) * 120

SEARCH = {
    "name": "search",
    "description": "Search the product catalogue.",
    "parametersJsonSchema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "A few words"}},
        "required": ["query"],
    },
}

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}, "confident": {"type": "boolean"}},
    "required": ["answer", "confident"],
}

QUESTION = "Which retailer sells the trouser with a 34 inch inseam? Search the catalogue."


def write(name: str, status: int, request: dict[str, Any], response: Any) -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.json"
    path.write_text(
        json.dumps({"status": status, "request": request, "response": response}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote {path.name}  ({status})")


def main() -> None:
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise SystemExit("Set GEMINI_API_KEY. It is in .env, which nothing reads for you.")
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    client = httpx.Client(timeout=300.0)

    def native(payload: dict[str, Any], model: str = MODEL, method: str = "generateContent"):
        return client.post(f"{NATIVE}/models/{model}:{method}", headers=headers, json=payload)

    print("A plain call, and the same request against a cached prefix")
    body = {
        "contents": [{"role": "user", "parts": [{"text": "Reply with the word OK."}]}],
        "generationConfig": {"temperature": 0.0, "seed": 41},
    }
    write("minimal", native(body).status_code, body, native(body).json())

    cached_body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": CACHE_PREFIX + "\nWhich retailer ships from Leeds?"}],
            }
        ],
        "generationConfig": {"temperature": 0.0, "seed": 41},
    }
    native(cached_body)  # the call that populates the cache
    response = native(cached_body)
    write("cached", response.status_code, cached_body, response.json())

    print("A tool call, with the signature the next turn is refused without")
    tool_body = {
        "contents": [{"role": "user", "parts": [{"text": QUESTION}]}],
        "tools": [{"functionDeclarations": [SEARCH]}],
        "generationConfig": {"temperature": 0.0, "seed": 41},
    }
    response = native(tool_body)
    write("tool_call", response.status_code, tool_body, response.json())
    part = response.json()["candidates"][0]["content"]["parts"][0]

    print("The turn after it, with the signature returned and with it dropped")

    def second_turn(with_signature: bool) -> dict[str, Any]:
        model_part = dict(part) if with_signature else {"functionCall": part["functionCall"]}
        return {
            "contents": [
                {"role": "user", "parts": [{"text": QUESTION}]},
                {"role": "model", "parts": [model_part]},
                {
                    "role": "user",
                    "parts": [
                        {
                            "functionResponse": {
                                "id": part["functionCall"].get("id"),
                                "name": "search",
                                "response": {
                                    "result": "belmont: 34 inch inseam. Sold by Kirkwall."
                                },
                            }
                        }
                    ],
                },
            ],
            "tools": [{"functionDeclarations": [SEARCH]}],
            "generationConfig": {"temperature": 0.0, "seed": 41},
        }

    kept = second_turn(True)
    response = native(kept)
    write("tool_result", response.status_code, kept, response.json())

    dropped = second_turn(False)
    response = native(dropped)
    write("error_missing_signature", response.status_code, dropped, response.json())

    print("Schema-constrained output, and a call that thinks")
    schema_body = {
        "contents": [{"role": "user", "parts": [{"text": "What is the capital of France?"}]}],
        "generationConfig": {
            "temperature": 0.0,
            "seed": 41,
            "responseMimeType": "application/json",
            "responseJsonSchema": ANSWER_SCHEMA,
        },
    }
    response = native(schema_body)
    write("json_schema", response.status_code, schema_body, response.json())

    thinking_body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": "A farmer has 17 sheep, all but 9 run away. How many are left? "
                        "Explain your reasoning."
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "seed": 41,
            "thinkingConfig": {"includeThoughts": True},
        },
    }
    # A model that thinks by default, so the fixture carries a thought part and a thought count.
    response = native(thinking_body, model="gemini-3-flash-preview")
    write("thinking", response.status_code, thinking_body, response.json())

    print("The refusals")
    overflow_body = {
        "contents": [{"role": "user", "parts": [{"text": "word " * 1_200_000}]}],
        "generationConfig": {"temperature": 0.0},
    }
    response = native(overflow_body)
    write(
        "error_context_overflow",
        response.status_code,
        {"contents": "1,200,000 words, elided", "generationConfig": {"temperature": 0.0}},
        response.json(),
    )

    small = {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
    response = native(small, model="gemini-does-not-exist")
    write("error_bad_model", response.status_code, small, response.json())

    response = client.post(
        f"{NATIVE}/models/{MODEL}:generateContent",
        headers={"x-goog-api-key": "not-a-key", "Content-Type": "application/json"},
        json=small,
    )
    write("error_bad_key", response.status_code, small, response.json())

    print("What the OpenAI-compatible endpoint does with the seed every run is keyed by")
    openai_body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with the word OK."}],
        "temperature": 0.0,
        "seed": 41,
    }
    response = client.post(
        f"{OPENAI}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json=openai_body,
    )
    write("openai_seed_refused", response.status_code, openai_body, response.json())

    print("A streamed call")
    with client.stream(
        "POST",
        f"{NATIVE}/models/{MODEL}:streamGenerateContent",
        params={"alt": "sse"},
        headers=headers,
        json={
            "contents": [
                {"role": "user", "parts": [{"text": "Name three UK cities, one per line."}]}
            ],
            "generationConfig": {"temperature": 0.0, "seed": 41},
        },
    ) as response:
        sse = "".join(f"{line}\n\n" for line in response.iter_lines() if line.strip())
        path = FIXTURES / "stream_minimal.json"
        path.write_text(
            json.dumps({"status": response.status_code, "sse": sse}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"  wrote {path.name}  ({response.status_code})")


if __name__ == "__main__":
    main()
