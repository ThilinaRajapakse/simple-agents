"""Does vLLM's `/metrics` report the concurrency the eval runner is issuing?

`concurrent_requests` on a `model_call` record is the divisor for compute-basis cost: a GPU
serving eight requests at once does not spend eight GPUs' worth of time on each. Neither shipped
adapter reports it, so it is null and the derived figure is flagged an upper bound.

vLLM publishes `vllm:num_requests_running` on `/metrics`. Before an adapter spends a request per
call to read it, this measures whether the number tracks what a caller actually has in flight.
If it does not, the flag does not ship and the field stays null.

    uv run python scripts/probe_vllm_concurrency.py --base-url http://127.0.0.1:8001

Start the server as `docs/model-clients/vllm.md` §2 describes. Nothing here is part of the library.
"""

from __future__ import annotations

import argparse
import re
import threading
import time

import httpx

RUNNING = re.compile(r"^vllm:num_requests_running(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$", re.M)
WAITING = re.compile(r"^vllm:num_requests_waiting(?:\{[^}]*\})?\s+([0-9.eE+-]+)\s*$", re.M)

PROMPT = (
    "Count slowly from one to forty, writing each number as an English word on its own line. "
    "Do not stop early."
)


def scrape(base_url: str) -> tuple[float | None, float | None]:
    """`(running, waiting)` as the server reports them, or `(None, None)`."""
    try:
        body = httpx.get(f"{base_url}/metrics", timeout=5.0).text
    except httpx.HTTPError:
        return None, None
    running = RUNNING.search(body)
    waiting = WAITING.search(body)
    return (
        float(running.group(1)) if running else None,
        float(waiting.group(1)) if waiting else None,
    )


def fire(base_url: str, model: str, issued: int) -> list[tuple[float, float | None, float | None]]:
    """Hold `issued` requests open at once and sample `/metrics` while they run."""
    samples: list[tuple[float, float | None, float | None]] = []
    stop = threading.Event()
    started = threading.Barrier(issued + 1)

    def call() -> None:
        started.wait()
        try:
            httpx.post(
                f"{base_url}/v1/chat/completions",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": PROMPT}],
                    "max_tokens": 400,
                    "temperature": 0.0,
                },
                timeout=180.0,
            )
        except httpx.HTTPError as exc:
            print(f"  a request failed: {exc}")

    def sample() -> None:
        started.wait()
        begun = time.monotonic()
        while not stop.is_set():
            running, waiting = scrape(base_url)
            samples.append((time.monotonic() - begun, running, waiting))
            time.sleep(0.25)

    threads = [threading.Thread(target=call) for _ in range(issued)]
    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    stop.set()
    sampler.join(timeout=2.0)
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--model", default="Qwen/Qwen3-1.7B")
    parser.add_argument("--levels", default="1,2,4,8")
    args = parser.parse_args()

    idle_running, idle_waiting = scrape(args.base_url)
    if idle_running is None:
        raise SystemExit(
            f"{args.base_url}/metrics does not publish vllm:num_requests_running. Either the "
            f"server is not up or this build does not export it."
        )
    print(f"idle: running={idle_running} waiting={idle_waiting}\n")

    print(f"{'issued':>7} {'peak running':>13} {'peak waiting':>13} {'samples':>8}")
    for level in [int(n) for n in args.levels.split(",")]:
        samples = fire(args.base_url, args.model, level)
        running = [r for _, r, _ in samples if r is not None]
        waiting = [w for _, _, w in samples if w is not None]
        peak_running = max(running) if running else float("nan")
        peak_waiting = max(waiting) if waiting else float("nan")
        print(f"{level:>7} {peak_running:>13.0f} {peak_waiting:>13.0f} {len(samples):>8}")
        time.sleep(1.0)

    print(
        "\nThe question this answers: does peak running track issued? If it does, an adapter "
        "reading /metrics per call fills concurrent_requests with a measurement. If it "
        "saturates below issued, the server is queueing and the number is what was in flight "
        "rather than what was asked for, which is still what the cost formula wants."
    )


if __name__ == "__main__":
    main()
