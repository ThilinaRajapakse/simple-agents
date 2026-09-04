"""The comment loop, driven end to end: the page's script, the server, the file, and back.

`test_view_serve.py` exercises the server's API against `comments.toml`; what it cannot see
is the page's own side of the loop. This drives that side: the shipped script, run under the
harness DOM with its requests carried to a real `--serve` server, says something on the page,
and the words land in the project; the coding agent replies through the library's writer,
and a fresh load of the page shows the reply in the thread. The DOM is a stub, so how the
thread looks is still read by eye; what is held here is that the loop works.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from simple_agents.records.comments import append_reply, read_comments
from simple_agents.view.serve import build_server

HERE = Path(__file__).parent
DRIVER = HERE / "view_comments_e2e.mjs"
FIXTURES = HERE / "fixtures" / "view_projects"

SAID = "The reading list should hide anything I shelved this month. Can we add that?"


def node_or_skip() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("no node on PATH; install Node.js to run the view's own script")
    return found


@pytest.fixture()
def served(tmp_path):
    """A copy of the mid-build fixture, served the way `view --serve` serves it."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "mid-build", root, ignore=shutil.ignore_patterns("__pycache__"))
    server = build_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def drive(node: str, base: str, *words: str) -> dict:
    done = subprocess.run(
        [node, str(DRIVER), base, *words],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 0, f"the driver failed:\n{done.stderr}"
    return json.loads(done.stdout)


class TestTheCommentLoop:
    def test_a_comment_said_on_the_page_lands_in_the_project_and_renders(self, served):
        node = node_or_skip()
        root, base = served
        held = drive(node, base, "say", SAID)
        assert held["live"] is True

        # The words are in the project's own record, with the snapshot of what was looked at.
        mine = [c for c in read_comments(root / "comments.toml").all if c.said == SAID]
        assert len(mine) == 1, "the page's words did not land in comments.toml"
        assert mine[0].at == "project" and mine[0].status == "open"
        assert mine[0].stage, "the snapshot did not record the stage"

        # And the page the builder is looking at shows the thread after its own refresh.
        assert SAID in held["sections"]
        assert any(t["said"] == SAID for t in held["threads"])

    def test_the_coding_agents_reply_reaches_a_fresh_page(self, served):
        node = node_or_skip()
        root, base = served
        held = drive(node, base, "say", SAID)
        thread_id = next(t["id"] for t in held["threads"] if t["said"] == SAID)

        answer = "It should not. Capping the pool before ranking; the change lands today."
        append_reply(root / "comments.toml", thread_id, by="coding_agent", said=answer)

        again = drive(node, base, "read")
        mine = next(t for t in again["threads"] if t["id"] == thread_id)
        assert mine["replies"] == [{"by": "coding_agent", "said": answer}]
        assert answer in again["sections"]


@pytest.fixture()
def with_prompts(tmp_path):
    """The prompted fixture, served: five prompts, filled from two runs."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "prompted", root, ignore=shutil.ignore_patterns("__pycache__"))
    server = build_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


class TestWordsSelectedInAPrompt:
    """`P3-79`: a thread on words the builder dragged across keeps what it needs to survive.

    The address is a digest of the words, so selecting them again lands in the thread already
    open on them. Beside it the thread keeps the words verbatim, the run whose prompt they
    were read in, and the digest the fixed text had, which is what says the wording has moved
    since it was said.
    """

    WORDS = "Read the traveller's message"

    def test_a_selection_lands_with_the_words_the_run_and_the_instruction(self, with_prompts):
        node = node_or_skip()
        root, base = with_prompts
        held = drive(node, base, "select-words", self.WORDS)

        mine = read_comments(root / "comments.toml").all
        assert len(mine) == 1
        thread = mine[0]
        assert thread.at.startswith("prompt:trip/read_request#words-")
        assert thread.quoted == self.WORDS
        assert thread.run and thread.run.startswith("run_")
        assert thread.instruction and thread.instruction.startswith("sha256:")
        assert thread.about == "words in the prompt for read_request, a model call in trip"
        assert any(t["at"] == thread.at for t in held["threads"])

    def test_the_same_words_twice_are_one_address(self, with_prompts):
        node = node_or_skip()
        _root, base = with_prompts
        first = drive(node, base, "select-words", self.WORDS)
        second = drive(node, base, "select-words", self.WORDS)
        addresses = {t["at"] for t in second["threads"]}
        assert len(addresses) == 1, "the same words filed under two addresses"
        assert first["threads"][0]["at"] in addresses


@pytest.fixture()
def at_shape(tmp_path):
    """The skeleton, served: an unconfirmed design and one proposed decision."""
    root = tmp_path / "project"
    shutil.copytree(FIXTURES / "skeleton", root, ignore=shutil.ignore_patterns("__pycache__"))
    server = build_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield root, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


class TestAgreeingInOneClick:
    """`P3-61`: agreement is one act on the page, and a thread in the project.

    The page never writes the brief. What the click does is say so in `comments.toml`, at the
    address of the thing agreed to, and the coding agent records `shape_confirmed` or moves
    the decision from there.
    """

    def test_agreeing_to_the_design_lands_as_a_thread_on_the_project(self, at_shape):
        node = node_or_skip()
        root, base = at_shape
        held = drive(node, base, "agree")

        mine = read_comments(root / "comments.toml").all
        assert len(mine) == 1
        assert mine[0].at == "project" and mine[0].status == "open"
        assert mine[0].said == "I agree to the design as drawn: triage, reindex."
        assert mine[0].kind == "comment", "agreement is a comment, not a brief entry"
        assert any(t["said"] == mine[0].said for t in held["threads"])

    def test_agreeing_to_one_decision_lands_at_that_decision(self, at_shape):
        node = node_or_skip()
        root, base = at_shape
        drive(node, base, "agree-decision", "a_step_that_decides")

        mine = read_comments(root / "comments.toml").all
        assert len(mine) == 1
        assert mine[0].at == "decision:a_step_that_decides"
        assert mine[0].said == "I agree to this decision."
        # the snapshot says what was agreed to, so the thread reads after the wording moves
        assert "a_step_that_decides" in (mine[0].about or "")
