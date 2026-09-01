"""Measure whether Mistral reports cached prompt tokens without `prompt_cache_key`.

`docs/model-clients/mistral.md` §4 says caching is opt-in, and that without a key an identical prompt
sent twice reports `cached_tokens: 0`. Session 2 of the item 7 checkpoint recorded 95 model
calls with `input_cache_read > 0` and no key sent on any of them, which contradicts it.

This sends the wire request directly rather than through the adapter, because the adapter
decodes the usage block and the question is what the backend puts in it.

    uv run python scripts/probe_prompt_caching.py

Prints the raw `usage` for each call. Nothing is asserted; read the numbers.
"""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

MODEL = os.environ.get("PROBE_MODEL", "mistral-small-2603")
URL = "https://api.mistral.ai/v1/chat/completions"

# Long enough to exceed the 64-token block size by a wide margin, and stable across calls.
FILLER = (
    "The following is a reference note kept for archival purposes. "
    "It records nothing of consequence and exists to occupy a fixed number of tokens. "
) * int(os.environ.get("PROBE_REPEATS", "120"))


def call(client: httpx.Client, label: str, cache_key: str | None, question: str) -> dict:
    payload: dict = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": f"{FILLER}\n\nQuestion: {question}"},
        ],
        "temperature": 0.0,
        "max_tokens": 16,
    }
    if cache_key is not None:
        payload["prompt_cache_key"] = cache_key
    if os.environ.get("PROBE_TOOLS"):
        # An agent loop declares its tools on every call, so the declarations are a prefix
        # every request in a run shares. Session 2 of the item 7 checkpoint reported a
        # constant cached count with no key sent, and this is the candidate explanation.
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": "document_search",
                    "description": "Search the collection for entries matching a query. " * 40,
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]
    response = client.post(URL, json=payload, timeout=120.0)
    body = response.json()
    usage = body.get("usage", {})
    print(f"\n--- {label}")
    print(f"    status {response.status_code}")
    print(f"    usage  {json.dumps(usage)}")
    print(
        "    remaining tokens/min header: "
        f"{response.headers.get('x-ratelimit-remaining-tokens-minute')}"
    )
    return usage


def main() -> int:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        print("export MISTRAL_API_KEY first", file=sys.stderr)
        return 1
    print(f"model: {MODEL}\nfiller: ~{len(FILLER) // 4} tokens")

    with httpx.Client(headers={"Authorization": f"Bearer {key}"}) as client:
        call(client, "1. no cache key, first send", None, "Reply with the word ok.")
        time.sleep(2)
        call(client, "2. no cache key, identical prompt again", None, "Reply with the word ok.")
        time.sleep(2)
        call(client, "3. no cache key, third time", None, "Reply with the word ok.")
        time.sleep(2)
        call(client, "4. with cache key, same prefix", "probe-item7", "Reply with the word ok.")
        time.sleep(2)
        call(client, "5. with the same cache key again", "probe-item7", "Reply with the word ok.")

    print(
        "\nRead `prompt_tokens_details.cached_tokens` on calls 2 and 3. A non-zero value there "
        "means caching is not opt-in on this account, and `docs/model-clients/mistral.md` §4 is wrong."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
