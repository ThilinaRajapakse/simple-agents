"""What an installed copy of the library carries.

The docstrings cite `docs/*.md` by path, and the conformance suite, the procedure and the
builder's coding agent all read those files. A package built without them leaves every one of
those references pointing at nothing, and the failure is invisible from a source checkout,
where the files are present for a different reason.
"""

from __future__ import annotations

import ast
import importlib
import re
import tomllib
from pathlib import Path

import pytest

import simple_agents
from simple_agents import docs_path

REPO = Path(__file__).resolve().parent.parent
SHIPPED_CODE = sorted((REPO / "src" / "simple_agents").rglob("*.py"))
CITATION = re.compile(r"docs/((?:[a-z0-9-]+/)*[a-z0-9-]+\.md)")


def _package_inits() -> list[Path]:
    """Every ``__init__.py`` under the library, which is where its surface is declared."""
    return sorted((Path(simple_agents.__file__).parent).rglob("__init__.py"))


def _declared_and_imported(init: Path) -> tuple[list[str], set[str]]:
    """What a package's ``__init__`` puts in ``__all__``, and what it imports from inside."""
    tree = ast.parse(init.read_text(encoding="utf-8"))
    declared: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", "") == "__all__" for target in node.targets
        ):
            declared = [entry.value for entry in node.value.elts if isinstance(entry, ast.Constant)]
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.level or 0) > 0
        for alias in node.names
    }
    return declared, imported


@pytest.mark.parametrize("init", _package_inits(), ids=lambda p: p.parent.name)
def test_every_name_a_package_imports_from_inside_the_library_is_exported(init) -> None:
    """A name pulled into an `__init__` and left out of `__all__` is invisible.

    It imports, so nothing fails and no test notices. What cannot find it is everything that
    reads the surface rather than guessing at it: `dir()`, a star import, an editor's
    completions, and a coding agent reading `__all__` to see what the library offers.

    `progress_of` sat in that state after the full-test pass ruled the evaluation surface up to
    the top level. Dogfood #4 went looking for exactly it, did not find it, and reimplemented it
    by globbing manifests, wrongly twice.
    """
    declared, imported = _declared_and_imported(init)

    assert sorted(imported - set(declared)) == []


@pytest.mark.parametrize("init", _package_inits(), ids=lambda p: p.parent.name)
def test_every_exported_name_is_there_and_named_once(init) -> None:
    """The other direction: `__all__` promises nothing it does not have.

    A name that was renamed or removed leaves a star import raising `AttributeError`, and a
    duplicate is a merge that went in twice.
    """
    module = importlib.import_module(
        str(init.parent.relative_to(Path(simple_agents.__file__).parent.parent)).replace("/", ".")
    )
    declared, _ = _declared_and_imported(init)

    assert [name for name in declared if not hasattr(module, name)] == []
    assert sorted({name for name in declared if declared.count(name) > 1}) == []


def test_docs_path_holds_the_documentation() -> None:
    assert docs_path().is_dir()
    assert (docs_path() / "trajectory-format.md").is_file()


def test_every_document_cited_by_the_library_is_installed_with_it() -> None:
    cited = {
        name
        for source in SHIPPED_CODE
        for name in CITATION.findall(source.read_text(encoding="utf-8"))
    }
    missing = sorted(name for name in cited if not (docs_path() / name).is_file())

    assert cited, "no docs are cited from the library, which means this test proves nothing"
    assert missing == [], (
        f"The library cites {missing} from its docstrings, and they are not in "
        f"{docs_path()}. An installed copy would carry a reference to a file its reader "
        f"cannot open."
    )


def test_the_wheel_is_configured_to_carry_the_docs() -> None:
    # docs_path() falls back to the source checkout, so the test above passes in development
    # whether or not the build carries them. This reads the build configuration instead.
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    include = config["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert include["docs"] == "simple_agents/docs"


def test_the_evaluation_document_states_the_results_version_the_writer_writes() -> None:
    """A results file carries its version, and a check reads the file rather than the document.

    The document is what a reader builds against, so a superseded number there sends them to
    fields the writer no longer emits.
    """
    from simple_agents.evaluation.results import EVAL_FORMAT_VERSION

    doc = (docs_path() / "evaluation.md").read_text(encoding="utf-8")

    assert f"`eval_format_version` `{EVAL_FORMAT_VERSION}`" in doc


def test_every_module_that_names_its_format_version_names_the_current_one() -> None:
    """A module docstring stating a version rots silently: nothing reads it and it is the first
    thing a coding agent reads. `results.py` was two bumps behind when this was written, and one
    behind at the bump before that."""
    from simple_agents.evaluation.results import EVAL_FORMAT_VERSION

    src = Path(simple_agents.__file__).parent
    stale: list[str] = []
    for path in sorted(src.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for stated in re.findall(r"Current version: ``([0-9.]+)``", text):
            if stated != EVAL_FORMAT_VERSION and "eval_format_version" in text:
                stale.append(f"{path.name} says {stated}")

    assert not stale, f"stale version in a module docstring: {', '.join(stale)}"


def test_the_trajectory_format_document_states_the_version_the_writer_writes() -> None:
    """A field table or an example carrying a superseded version is a bug in the spec.

    Every conformance check is written against this document, so a reader who takes the
    field table literally builds against a version nothing emits.
    """
    doc = (docs_path() / "trajectory-format.md").read_text(encoding="utf-8")
    current = simple_agents.FORMAT_VERSION

    assert f"**Current version: `{current}`.**" in doc
    assert f'| `format_version` | string | ✅ | `"{current}"`.' in doc, (
        f"`docs/trajectory-format.md` §2's field table does not say {current!r}, which is "
        f"what every record carries."
    )

    stale = re.findall(r'"format_version":"([0-9.]+)"', doc)
    assert stale, "no example records found, so this test proves nothing"
    assert set(stale) == {current}, (
        f"example records in the document show format_version {sorted(set(stale))}, and the "
        f"writer emits {current!r}."
    )


def test_the_manifest_document_lists_every_key_the_manifest_writes() -> None:
    """`run-envelope.md` §2 is the manifest's schema, and drift there is invisible.

    A builder reads the document to learn what a key is called. A key the writer emits and
    the document omits is an unknown key; the reverse is an unfindable key.
    """
    doc = (docs_path() / "run-envelope.md").read_text(encoding="utf-8")
    written = set(_written_manifest().keys()) | set(_written_manifest()["cassette"].keys())

    missing = sorted(name for name in written if f"`{name}`" not in doc)
    assert missing == [], (
        f"The manifest writes {missing}, and run-envelope.md does not mention them."
    )


def _written_manifest() -> dict:
    """A real manifest, from a real run, rather than a transcription of one."""
    import tempfile

    from simple_agents import Budget, Deterministic, Pipeline, RunEnvelope

    with tempfile.TemporaryDirectory() as tmp:
        result = Pipeline(
            [Deterministic(lambda inputs, ctx: inputs, node_id="noop")],
            budget=Budget(max_steps=None, max_tokens=None, max_cost=None, max_wall_clock_ms=None),
        ).run({}, envelope=RunEnvelope(run_dir=tmp))
        return result.manifest


def test_the_version_the_manifest_records_is_the_version_that_ships() -> None:
    """`library_version` is the pin FT-14's argument extends to the library itself."""
    config = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))

    assert simple_agents.__version__ == config["project"]["version"], (
        "simple_agents.__version__ and pyproject.toml disagree. Every manifest records the "
        "former, and the wheel is built from the latter."
    )


def test_the_package_exports_what_the_readme_shows() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    imported = re.findall(r"^from simple_agents import (.+)$", readme, re.MULTILINE)
    names = {n.strip() for line in imported for n in line.split(",")}

    assert names, "the README shows no imports, so this test proves nothing"
    assert names <= set(simple_agents.__all__), (
        f"The README imports {sorted(names - set(simple_agents.__all__))} from the package "
        f"root, and the package does not export it."
    )


def test_every_format_version_is_pinned_to_a_literal() -> None:
    """A bump is an edit to this test as well as to the constant.

    Item 9 found the results version could move with the whole suite passing, because the one
    test reading it compared it against the constant it came from. Six formats now carry a
    version, and a project holds files written in each.
    """
    from simple_agents.builtins.search import INDEX_FORMAT_VERSION
    from simple_agents.evaluation.results import EVAL_FORMAT_FLOOR, EVAL_FORMAT_VERSION
    from simple_agents.evaluation.variants import VARIANT_FORMAT_VERSION
    from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION
    from simple_agents.records.shelf import SHELF_FORMAT_VERSION
    from simple_agents.records.suspension import SUSPENSION_FORMAT_VERSION

    assert simple_agents.FORMAT_VERSION == "0.31"
    assert MANIFEST_FORMAT_VERSION == "0.44"
    assert SUSPENSION_FORMAT_VERSION == "0.5"
    assert SHELF_FORMAT_VERSION == "0.1"
    assert EVAL_FORMAT_VERSION == "0.31"
    assert EVAL_FORMAT_FLOOR == "0.28"
    assert VARIANT_FORMAT_VERSION == "0.3"
    assert INDEX_FORMAT_VERSION == "2.0"


def test_the_evaluation_document_states_the_variant_version_the_writer_writes() -> None:
    """A written comparison carries its version, and a reader builds against the document."""
    from simple_agents.evaluation.variants import VARIANT_FORMAT_VERSION

    doc = (docs_path() / "evaluation.md").read_text(encoding="utf-8")

    assert f"`variant_format_version` `{VARIANT_FORMAT_VERSION}`" in doc


def test_the_run_envelope_document_states_the_manifest_version_the_writer_writes() -> None:
    from simple_agents.records.manifest import MANIFEST_FORMAT_VERSION

    doc = (docs_path() / "run-envelope.md").read_text(encoding="utf-8")

    assert f"**Current version: `{MANIFEST_FORMAT_VERSION}`**" in doc


class TestTheIndexListsWhatShips:
    """`docs/index.md` is the canonical list of the documentation, and nothing read it.

    The README's table lost three documents this way, and a test now holds that one. This is
    the same rule over the document whose whole job is to be the list.
    """

    def index(self) -> str:
        return (docs_path() / "index.md").read_text(encoding="utf-8")

    def shipped(self) -> set[str]:
        """Every shipped document except the index, which does not list itself."""
        root = docs_path()
        return {str(path.relative_to(root)) for path in root.rglob("*.md")} - {"index.md"}

    def test_every_shipped_document_has_a_row(self) -> None:
        named = set(re.findall(r"docs/((?:[\w.-]+/)*[\w.-]+\.md)", self.index()))

        assert self.shipped() - named == set()

    def test_it_counts_the_documents_it_lists(self) -> None:
        """ "These sixteen documents" goes stale the moment one is added."""
        words = {
            14: "fourteen",
            15: "fifteen",
            16: "sixteen",
            17: "seventeen",
            18: "eighteen",
            19: "nineteen",
            20: "twenty",
            21: "twenty-one",
            22: "twenty-two",
        }
        [named] = re.findall(r"These ([\w-]+) documents", self.index())

        assert named == words[len(self.shipped())]


def test_the_release_workflow_reads_the_heading_the_release_script_writes() -> None:
    """The workflow grepped for `## x.y.z (` after the changelog had moved to Keep a Changelog
    form, and the first tag after the move passed CI and refused to publish."""
    import re

    workflow = (REPO / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    pattern = re.search(r'grep -q "(\^## [^"]+)" CHANGELOG.md', workflow)
    assert pattern, "release.yml no longer greps the changelog for the version"
    shell = pattern.group(1).replace("$tag", re.escape(simple_agents.__version__))
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    assert re.search(shell, changelog, re.M), (
        f"the workflow's check {pattern.group(1)!r} does not match the heading "
        f"CHANGELOG.md carries for {simple_agents.__version__}"
    )
