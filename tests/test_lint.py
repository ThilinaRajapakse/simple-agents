"""The lint gate: `ruff check` over the whole tree stays clean.

The rule set lives in `pyproject.toml` under `[tool.ruff.lint]`: correctness-adjacent rules
(pyflakes, bugbear, builtin shadowing, comprehension misuse, pylint errors), no style
opinions. There is no recorded baseline to tolerate a violation: a finding fails this test,
and the fix is to fix the code. A deliberate exception is a `# noqa` with its rule code, at
the line that needs it.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_tree_is_lint_clean() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "src", "tests", "scripts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"ruff check found:\n{result.stdout}{result.stderr}\n"
            f"Fix the finding, or mark a deliberate exception with `# noqa: <rule>` on "
            f"that line. `uv sync` installs ruff if the command itself failed to run."
        )


def test_the_tree_is_formatted() -> None:
    """`ruff format` ran once over everything and stays run.

    Fixture projects are excluded in `pyproject.toml`: their source feeds recorded digests.
    A statement kept unformatted carries `# fmt: skip` on its last line. The formatter
    honours that marker at statement level and ignores a `# fmt: off` inside an expression.
    """
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "src", "tests", "scripts"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"ruff format --check found unformatted files:\n{result.stdout}{result.stderr}\n"
            f"Run `uv run ruff format src tests scripts` and commit what it changes."
        )
