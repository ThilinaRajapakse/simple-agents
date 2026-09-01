"""What `scripts/release.py` refuses, and what it writes when it does not.

Cutting `0.1.2` on 2026-09-01 needed five steps recorded nowhere. Two surfaced as a failing
test partway through, and the changelog heading was guarded by nothing: the release workflow
checks the tag against `pyproject.toml` and never reads `CHANGELOG.md`, so a tag whose
changelog still said "Unreleased" would have published.

The subprocess half of the script is a list of commands and is exercised by running it. What
is tested here is every decision it makes on its own.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "release.py"

CHANGELOG = """# Changelog

## Unreleased

### Fixed

- Something.

## 0.1.1 (2026-09-01)
"""


def load(repo: Path):
    """The script, with its notion of the repository pointed at a temporary one."""
    spec = importlib.util.spec_from_file_location(f"rel_{repo.name}", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.REPO = repo
    return module


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A repository at `0.1.1` with an undated `## Unreleased` section."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "simple-llm-agents"\nversion = "0.1.1"\n', encoding="utf-8"
    )
    (tmp_path / "src" / "simple_agents").mkdir(parents=True)
    (tmp_path / "src" / "simple_agents" / "__init__.py").write_text(
        'A = 1\n__version__ = "0.1.1"\n', encoding="utf-8"
    )
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    return tmp_path


class TestWhatItRefuses:
    def test_a_version_that_is_not_three_numbers(self, repo: Path) -> None:
        said = load(repo).refusals("1.2")
        assert len(said) == 1
        assert "not three numbers" in said[0]
        assert "0.1.2" in said[0], "the message names the version it would have been"

    def test_a_version_at_or_below_the_one_already_held(self, repo: Path) -> None:
        module = load(repo)
        for version in ("0.1.1", "0.1.0"):
            said = module.refusals(version)
            assert any("not above 0.1.1" in one for one in said), version
            assert any("cannot be reused" in one for one in said), version

    def test_a_changelog_that_says_nothing_about_this_release(self, repo: Path) -> None:
        """The hole the release workflow leaves: it reads the tag and never the changelog."""
        (repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.1 (2026-09-01)\n", encoding="utf-8"
        )
        said = load(repo).refusals("0.1.2")
        assert any("CHANGELOG.md has no" in one for one in said)

    def test_a_changelog_already_naming_this_version_is_not_a_refusal(self, repo: Path) -> None:
        """Preparing the same release twice is not an error, so the run is repeatable."""
        (repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## 0.1.2 (2026-09-01)\n\n- Something.\n", encoding="utf-8"
        )
        assert load(repo).refusals("0.1.2") == []

    def test_a_release_that_is_ready_has_no_refusals(self, repo: Path) -> None:
        assert load(repo).refusals("0.1.2") == []


class TestWhatItWrites:
    def test_the_version_reaches_every_site_that_holds_one(self, repo: Path) -> None:
        """`test_packaging.py` fails when the two disagree, which is how the second was found
        halfway through cutting `0.1.2`."""
        module = load(repo)
        said = module.set_version("0.1.2", write=True)

        assert 'version = "0.1.2"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
        init = (repo / "src" / "simple_agents" / "__init__.py").read_text(encoding="utf-8")
        assert '__version__ = "0.1.2"' in init
        assert init.startswith("A = 1\n"), "nothing else in the file moved"
        assert all("0.1.1 -> 0.1.2" in one for one in said)

    def test_check_reports_the_same_and_writes_nothing(self, repo: Path) -> None:
        module = load(repo)
        before = (repo / "pyproject.toml").read_text(encoding="utf-8")

        assert any("0.1.1 -> 0.1.2" in one for one in module.set_version("0.1.2", write=False))
        assert "Unreleased ->" in module.date_the_changelog("0.1.2", write=False)
        assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before
        assert "## Unreleased" in (repo / "CHANGELOG.md").read_text(encoding="utf-8")

    def test_the_changelog_heading_is_dated(self, repo: Path) -> None:
        import datetime

        module = load(repo)
        module.date_the_changelog("0.1.2", write=True)
        held = (repo / "CHANGELOG.md").read_text(encoding="utf-8")

        assert f"## 0.1.2 ({datetime.date.today().isoformat()})" in held
        assert "## Unreleased" not in held
        assert "## 0.1.1 (2026-09-01)" in held, "the sections below it are untouched"

    def test_dating_a_changelog_twice_leaves_it_alone(self, repo: Path) -> None:
        module = load(repo)
        module.date_the_changelog("0.1.2", write=True)
        once = (repo / "CHANGELOG.md").read_text(encoding="utf-8")

        assert module.date_the_changelog("0.1.2", write=True) == "CHANGELOG.md: already dated"
        assert (repo / "CHANGELOG.md").read_text(encoding="utf-8") == once

    def test_a_file_that_stopped_holding_a_version_is_named(self, repo: Path) -> None:
        """The sites are matched by pattern, so one that is renamed has to say so rather than
        leaving a release half-written."""
        (repo / "src" / "simple_agents" / "__init__.py").write_text("A = 1\n", encoding="utf-8")
        module = load(repo)

        with pytest.raises(SystemExit, match="no longer holds a version"):
            module.set_version("0.1.2", write=True)
