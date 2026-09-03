"""Prepares a release: everything a version bump touches, and every gate it has to pass.

Cutting `0.1.2` took five steps held in nobody's head. Two were found by a failing test
mid-release, one by reading the previous release's diffstat, and the changelog heading was
guarded by nothing at all: a tag whose changelog still said "Unreleased" would have published.
So the steps live here rather than in a checklist::

    uv run python scripts/release.py 0.1.2
    uv run python scripts/release.py 0.1.2 --check

`--check` reports what would change and writes nothing.

**It stops before anything leaves the machine.** The commit, the tag and the push are the
irreversible part and stay with the person: a published version number cannot be reused. What
this leaves behind is a working tree whose diff is the release, and every gate green over it.

What it does, in order:

1. Refuses a version that is not three numbers, is not above the current one, or already has
   a tag.
2. Refuses when `CHANGELOG.md` has neither an `## Unreleased` section nor one already naming
   this version. A release whose changelog says nothing about it is the failure this exists
   to prevent.
3. Writes the version to `pyproject.toml` and `__init__.py`, which
   `tests/test_packaging.py` requires to agree.
4. Dates the `## Unreleased` heading.
5. Rebuilds the conformance fixtures. Every manifest records `library_version`, so a bump
   leaves 168 of them holding a version the library no longer writes.
6. Re-locks, since `uv.lock` records the project's own version.
7. Runs the gates: the suite, the writing rules, the citations, the shape ratchet, the
   linter, the formatter, the `dev-docs` rules, and a wheel build.
"""

from __future__ import annotations

import argparse
import datetime
import re
import subprocess
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Each is `pyproject.toml`'s version under a different name, and `test_packaging.py` fails
# when the two disagree.
VERSION_SITES = (
    (Path("pyproject.toml"), re.compile(r'^version = "([^"]+)"$', re.M), 'version = "{}"'),
    (
        Path("src/simple_agents/__init__.py"),
        re.compile(r'^__version__ = "([^"]+)"$', re.M),
        '__version__ = "{}"',
    ),
)

GATES = (
    ("the suite", ["uv", "run", "pytest", "-q"]),
    ("the writing rules", ["uv", "run", "python", "scripts/prose_check.py"]),
    ("the citations", ["uv", "run", "python", "scripts/check_citations.py"]),
    ("the shape ratchet", ["uv", "run", "python", "scripts/shape_check.py", "src/simple_agents"]),
    ("the linter", ["uv", "run", "ruff", "check", "src", "tests"]),
    ("the formatter", ["uv", "run", "ruff", "format", "--check", "src", "tests"]),
    ("the wheel", ["uv", "build"]),
)

# `dev-docs/` holds the maintainer's design of record and is not tracked here, so a clone has
# no copy of it. The gate runs where the directory is present and is skipped where it is not.
_DEV_DOCS_GATE = ("the dev-docs rules", ["uv", "run", "python", "dev-docs/check_docs.py"])


def gates() -> tuple[tuple[str, list[str]], ...]:
    """The gates a release runs, in order."""
    if (REPO / "dev-docs" / "check_docs.py").exists():
        return (*GATES[:-1], _DEV_DOCS_GATE, GATES[-1])
    return GATES


def _run(command: list[str]) -> subprocess.CompletedProcess:
    """One command in the repository. `REPO` is read here rather than bound as a default, so
    a test pointing the module at a temporary tree is obeyed by everything below."""
    return subprocess.run(command, cwd=REPO, capture_output=True, text=True)


def current_version() -> str:
    raw = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    return str(raw["project"]["version"])


def _as_numbers(version: str) -> tuple[int, ...] | None:
    """``0.1.2`` as ``(0, 1, 2)``, and ``None`` where it is not three numbers."""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return None
    return tuple(int(part) for part in version.split("."))


def refusals(version: str) -> list[str]:
    """Every reason this release cannot be prepared, each saying what to do about it."""
    found: list[str] = []
    numbers = _as_numbers(version)
    if numbers is None:
        found.append(
            f"{version} is not three numbers. A release is `MAJOR.MINOR.PATCH`, so a fix "
            f"release off {current_version()} is {_next_patch(current_version())}."
        )
        return found

    held = _as_numbers(current_version())
    if held is not None and numbers <= held:
        found.append(
            f"{version} is not above {current_version()}, which pyproject.toml already "
            f"holds. A published version number cannot be reused, so the next one is "
            f"{_next_patch(current_version())} or higher."
        )

    tags = _run(["git", "tag", "--list", f"v{version}"]).stdout.split()
    if tags:
        found.append(
            f"v{version} is already tagged. Pick the next version, or delete the tag if it "
            f"was never pushed: git tag -d v{version}."
        )

    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    if "## Unreleased" not in changelog and f"## {version} (" not in changelog:
        found.append(
            "CHANGELOG.md has no `## Unreleased` section, and none naming this version. "
            "Write what changed under `## Unreleased` first: a release whose changelog says "
            "nothing about it is what this refuses."
        )
    return found


def _next_patch(version: str) -> str:
    numbers = _as_numbers(version)
    if numbers is None:
        return "0.0.1"
    return f"{numbers[0]}.{numbers[1]}.{numbers[2] + 1}"


def set_version(version: str, write: bool) -> list[str]:
    """The version written to every site that holds it. Reports each, written or not."""
    said = []
    for relative, pattern, form in VERSION_SITES:
        path = REPO / relative
        text = path.read_text(encoding="utf-8")
        found = pattern.search(text)
        if found is None:
            raise SystemExit(f"release: {relative} no longer holds a version this can set.")
        if found.group(1) == version:
            said.append(f"{relative}: already {version}")
            continue
        said.append(f"{relative}: {found.group(1)} -> {version}")
        if write:
            path.write_text(pattern.sub(form.format(version), text, count=1), encoding="utf-8")
    return said


def date_the_changelog(version: str, write: bool) -> str:
    """``## Unreleased`` becomes ``## <version> (<today>)``."""
    path = REPO / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    heading = f"## {version} ({datetime.date.today().isoformat()})"
    if f"## {version} (" in text:
        return "CHANGELOG.md: already dated"
    if write:
        path.write_text(text.replace("## Unreleased", heading, 1), encoding="utf-8")
    return f"CHANGELOG.md: ## Unreleased -> {heading}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare a release.")
    parser.add_argument("version", help="the version to release, as MAJOR.MINOR.PATCH")
    parser.add_argument(
        "--check", action="store_true", help="report what would change and write nothing"
    )
    args = parser.parse_args(argv)
    write = not args.check

    found = refusals(args.version)
    if found:
        for refusal in found:
            print(f"release: {refusal}")
        return 1

    for line in set_version(args.version, write):
        print(f"  {line}")
    print(f"  {date_the_changelog(args.version, write)}")

    if args.check:
        print("release: --check wrote nothing. The fixtures, the lock and the gates were skipped.")
        return 0

    for step, command in (
        (
            "the conformance fixtures",
            ["uv", "run", "python", "scripts/build_conformance_fixtures.py"],
        ),
        ("the lock", ["uv", "lock"]),
    ):
        print(f"  rebuilding {step}…")
        done = _run(command)
        if done.returncode != 0:
            print(done.stdout[-2000:] + done.stderr[-2000:])
            print(f"release: rebuilding {step} failed. Nothing further ran.")
            return 1

    failed = []
    for name, command in gates():
        done = _run(command)
        print(f"  {'ok  ' if done.returncode == 0 else 'FAIL'} {name}")
        if done.returncode != 0:
            failed.append((name, (done.stdout + done.stderr)[-3000:]))
    for name, output in failed:
        print(f"\n--- {name} ---\n{output}")
    if failed:
        print(f"release: {len(failed)} gate(s) failed. The tree holds the version bump.")
        return 1

    print(
        f"\nrelease: {args.version} is prepared and every gate is green.\n"
        f"Read the diff, then publish it:\n"
        f"  git add -A && git commit\n"
        f"  git tag -a v{args.version} -m 'Simple Agents {args.version}'\n"
        f"  git push origin main && git push origin v{args.version}\n"
        f"Pushing the tag publishes to PyPI, and a published version cannot be reused."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
