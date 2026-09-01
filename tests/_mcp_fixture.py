"""The reference MCP server on its HTTP transport, started and reaped for one test module.

Separate from `test_mcp.py` so the process handling is readable on its own. Two things here
are the point, and both were bugs first:

- **The port is claimed rather than the server's default.** Bound to 3001, the fixture connected
  to a server somebody else had left running and reported a pass for a transport it never
  reached.
- **The process group is what gets signalled.** `npx` execs through a chain, so terminating the
  process it returns leaves the node server holding the port after the run.
"""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
from typing import Iterator

import pytest

SERVER = ["npx", "-y", "@modelcontextprotocol/server-everything", "streamableHttp"]


def _free_port() -> int:
    with socket.socket() as claim:
        claim.bind(("127.0.0.1", 0))
        return int(claim.getsockname()[1])


def _listening(port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex(("127.0.0.1", port)) == 0


def reference_server_over_http() -> Iterator[str]:
    """Yield the URL of a reference server this fixture started, and reap it afterwards."""
    port = _free_port()
    process = subprocess.Popen(
        SERVER,
        env={**os.environ, "PORT": str(port)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    try:
        for _ in range(120):
            if process.poll() is not None:
                pytest.skip("the reference server exited before it listened")
            if _listening(port):
                break
            time.sleep(0.5)
        else:
            pytest.skip(f"the reference server did not listen on port {port}")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
        try:
            process.wait(30)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
