"""The README's first agent, executed rather than read.

`test_readme.py` checks that every name the block imports is exported and that the counts
beside it are the counts that ship, and `prose_check.py` checks that it parses. Nothing ran
it, so the first thing a reader copies was the one shipped example with no execution behind
it. `docs/pipeline.md` §1.4's accumulator is what that costs: it parsed, it resolved, and it
was missing a node.

The block runs here unmodified. Two things around it are supplied rather than written into
the README: the policy documents it reads from `policies/`, and a scripted client in place
of the hosted one, which a test has no credential for. Both are built from the block's own
trailing comments, so nothing here restates a value the README states.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import simple_agents
from simple_agents import FakeModelClient, fake_response
from simple_agents.models import ToolCallRequest
from simple_agents.tools import FINISH_TOOL_NAME

REPO = Path(__file__).resolve().parents[1]

OTHER_DOCUMENT = """# Shipping

Standard delivery arrives within five working days.
"""


def _first_agent_block() -> str:
    """The fenced Python block under the README's `## A first agent`."""
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    section = readme.split("## A first agent", 1)
    assert len(section) == 2, "the README has no `## A first agent` heading"
    block = re.search(r"```python\n(.*?)```", section[1], re.DOTALL)
    assert block, "the README's first-agent section has no Python block"
    return block.group(1)


@pytest.fixture
def stated() -> dict[str, str]:
    """What the block says each expression evaluates to, from its trailing comments.

    `result.output.source     # 'returns.md'` reads as `{"result.output.source": "returns.md"}`.
    Everything the fixtures below put on disk or into the client comes from here, so a value
    edited in the README is the value this test runs against.
    """
    found = {}
    for line in _first_agent_block().splitlines():
        line_states = re.match(r"^(result\.[\w.]+)\s+#\s+'([^']*)'\s*$", line)
        if line_states:
            found[line_states.group(1)] = line_states.group(2)
    assert {"result.output.answer", "result.output.source"} <= set(found), (
        "the block no longer states an answer and a source in trailing comments, so the "
        "fixtures have nothing to build from"
    )
    return found


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stated) -> Path:
    """A working directory holding the `policies/` the block reads and nothing else.

    The document is named for the source the block states and holds the sentence it states
    as the answer, so the search has something to find and a second document to pass over.
    """
    corpus = tmp_path / "policies"
    corpus.mkdir()
    (corpus / stated["result.output.source"]).write_text(
        f"# Returns\n\n{stated['result.output.answer']}\n", encoding="utf-8"
    )
    (corpus / "shipping.md").write_text(OTHER_DOCUMENT, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch, stated) -> FakeModelClient:
    """A client in place of `MistralClient`: it searches once, then finishes.

    The block constructs `MistralClient(model=...)`, so the name it imported is what is
    replaced. A test has no credential, and what is under test is the plumbing rather than
    the model: that the tool is offered, the search runs, and the schema takes the result.
    """
    client = FakeModelClient(
        responses=[
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="c1",
                        name="document_search",
                        arguments={"query": "returning a damaged item"},
                    )
                ]
            ),
            # An `AgentNode` ends by calling `finish` with the answer. The library builds
            # that tool for the node from its output schema; `docs/tools.md` §5.
            fake_response(
                tool_calls=[
                    ToolCallRequest(
                        id="c2",
                        name=FINISH_TOOL_NAME,
                        arguments={
                            "answer": stated["result.output.answer"],
                            "source": stated["result.output.source"],
                        },
                    )
                ]
            ),
        ]
    )
    monkeypatch.setattr(simple_agents, "MistralClient", lambda **kwargs: client)
    return client


def _run_the_block() -> dict:
    namespace: dict = {}
    # `dont_inherit=True` or this file's `from __future__ import annotations` reaches the
    # block: `compile` takes the calling frame's future flags by default. Under PEP 563 the
    # block's `Maybe[str]` stays a `ForwardRef` that resolves against `builtins`, the node
    # is refused for admitting no `unknown`, and the README reads as broken when it is not.
    source = compile(_first_agent_block(), "README.md#a-first-agent", "exec", dont_inherit=True)
    exec(source, namespace)
    return namespace


class TestTheBlockRuns:
    def test_it_produces_the_answer_and_the_source_it_states(self, project, scripted, stated):
        result = _run_the_block()["result"]

        assert result.output.answer == stated["result.output.answer"]
        assert result.output.source == stated["result.output.source"]

    def test_the_manifest_is_where_the_block_says_it_is(self, project, scripted) -> None:
        """`result.paths.manifest  # runs/dev/<date>/<run_id>/manifest.json`, under the cwd."""
        result = _run_the_block()["result"]

        manifest = Path(result.paths.manifest)
        assert manifest.exists()
        assert manifest.name == "manifest.json"
        assert manifest.parents[3].name == "runs"
        assert manifest.parents[2].name == "dev"
        assert json.loads(manifest.read_text(encoding="utf-8"))["run_id"] == manifest.parent.name

    def test_the_agent_searched_before_it_answered(self, project, scripted, stated) -> None:
        """The README says the model decides when to search. The tool has to be offered for
        that to be true, and the search has to reach the documents on disk."""
        _run_the_block()

        offered = {tool["name"] for tool in scripted.requests[0].tools}
        assert "document_search" in offered

        served = scripted.requests[1].messages[-1]["content"]
        assert stated["result.output.answer"] in served, (
            f"the search did not return the document that answers the question: {served!r}"
        )
