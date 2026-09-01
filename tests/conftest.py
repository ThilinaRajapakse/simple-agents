"""Shared fixtures.

Note the framework split: pytest is how the library tests *itself*. The conformance checks
that run against a builder's project are a separate, bespoke runner (item 9), because their
failure messages are a prompt surface and pytest's assertion output would fight that design.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from simple_agents import RunEnvelope
from simple_agents.envelope import find_run

from schemas import Answer, Total

RUN_ID = "run_under_test"
"""A fixed run id, so a test knows where the run wrote before it runs."""


@pytest.fixture
def answer_schema() -> type[Answer]:
    return Answer


@pytest.fixture
def total_schema() -> type[Total]:
    return Total


@pytest.fixture
def envelope(tmp_path: Path) -> RunEnvelope:
    """A run envelope writing into the test's temporary directory."""
    return RunEnvelope(run_dir=tmp_path)


@pytest.fixture
def run_root(tmp_path: Path, envelope: RunEnvelope) -> Path:
    """Where a run made with the `envelope` fixture and `run_id=RUN_ID` writes.

    A run is filed by what it is, so this asks the envelope rather than assuming the run
    directory is one level down. A test whose envelope declares something else (live, a role,
    an evaluation) asks its own envelope the same way.
    """
    return tmp_path / envelope.placement() / RUN_ID


@pytest.fixture
def trajectory(run_root: Path) -> Path:
    """Where a run made with the `envelope` fixture and `run_id=RUN_ID` writes records."""
    return run_root / "trajectory.jsonl"


@pytest.fixture
def manifest_path(run_root: Path) -> Path:
    """Where a run made with the `envelope` fixture and `run_id=RUN_ID` writes its manifest."""
    return run_root / "manifest.json"


def run_path(run_dir: Path, run_id: str, *parts: str) -> Path:
    """Where a run wrote, found by its id rather than assumed to be one directory down.

    A run is filed by what it is, so a test that knows only the id asks for it the way
    anything else reading a run back does.
    """
    root = find_run(run_dir, run_id) or Path(run_dir) / run_id
    return root.joinpath(*parts)
