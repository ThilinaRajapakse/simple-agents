"""Reports a module, class or function that is large enough to be worth a second look.

This is a question, not a rule. A long function is sometimes the honest shape for the work,
and no number here says otherwise. What it says is that this unit is among the largest in the
library, which is where a unit doing several things usually turns up, so read it again and ask
whether it is one thing.

**It ratchets rather than gating.** Everything already over a threshold is recorded in
`shape_baseline.json` with its size, and the check passes on those. It fails when a unit that
was not over a threshold crosses one, and when a recorded unit grows. So the answer to "may I
write a 300-line function" is yes, deliberately, by recording it and saying why.

The baseline is also the worklist: it is the list of units the pre-release refactor works
through, and it shrinks as that lands. A unit kept at size deliberately carries a one-line
entry in the baseline's `reasons` map, keyed like `recorded`. `--update` keeps a reason whose
unit is still recorded and drops one whose unit has gone.

    uv run python scripts/shape_check.py [--update] [path ...]

`--update` rewrites the baseline from what is on disk now. Run it after deliberately growing a
unit, and after decomposing one, so the file keeps saying what is true.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
BASELINE = Path(__file__).resolve().parent / "shape_baseline.json"
DEFAULT_PATHS = ("src/simple_agents",)

# Fixed, and deliberately not computed from the tree: a threshold derived from the current
# distribution rises as the code grows, so the check would go quiet exactly when it is needed.
# These are this library's own percentiles as measured on 2026-08-25, rounded. A function's
# 95th is 52 code lines and 11 branches, a class's 95th is 201, and a module's 90th is 832.
#
# Docstrings do not count toward any of them. `scripts/prose_check.py` governs how long a
# docstring may be, and a wide record constructor documented properly is not a unit doing
# several things.
THRESHOLDS = {
    "function lines": 50,
    "function branches": 12,
    "class lines": 200,
    "module lines": 800,
}

MEASURES = ("module lines", "class lines", "function lines", "function branches")
"""The order a message reads them in. Size first, then how much of it is branching."""

HOW_IT_COMPARES = {
    "module lines": "is longer than {rank}% of this library's modules",
    "class lines": "is longer than {rank}% of this library's classes",
    "function lines": "is longer than {rank}% of this library's functions",
    "function branches": "branches more than {rank}% of this library's functions",
}

BRANCHING = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.IfExp,
    ast.comprehension,
    ast.Match,
)


@dataclass(frozen=True)
class Unit:
    """One module, class or function, with what is measured about it."""

    key: str
    """`path::kind::name`, stable across edits above it so the baseline survives them."""

    path: str
    line: int
    label: str
    measures: dict[str, int]

    def over(self) -> dict[str, int]:
        """Every measure of this unit that is over its threshold."""
        return {name: value for name, value in self.measures.items() if value > THRESHOLDS[name]}


def _docstring_lines(node: ast.AST) -> int:
    """How many lines every docstring inside this node takes, its own included."""
    total = 0
    for child in ast.walk(node):
        body = getattr(child, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            total += first.value.end_lineno - first.value.lineno + 1
    return total


def _branches(node: ast.AST) -> int:
    """How many decision points the body holds, counting a boolean operand as one."""
    found = 0
    for child in ast.walk(node):
        if isinstance(child, BRANCHING):
            found += 1
        elif isinstance(child, ast.BoolOp):
            found += len(child.values) - 1
    return found


def _qualified(tree: ast.Module) -> dict[int, str]:
    """The dotted name of every class and function in the tree, by line number."""
    names: dict[int, str] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = f"{prefix}{child.name}"
                names[child.lineno] = name
                walk(child, f"{name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return names


def _named_from_root(path: Path) -> str:
    """The path as the baseline records it: relative to the repository where it is inside it.

    A file outside the repository keeps its own path, so pointing the check at one is a
    reading rather than a crash.
    """
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def units_in(path: Path) -> Iterator[Unit]:
    """Every unit one file holds, the module itself included."""
    source = path.read_text(encoding="utf-8")
    relative = _named_from_root(path)
    tree = ast.parse(source)
    yield Unit(
        key=f"{relative}::module",
        path=relative,
        line=1,
        label=relative,
        measures={"module lines": len(source.splitlines()) - _docstring_lines(tree)},
    )
    names = _qualified(tree)
    for node in ast.walk(tree):
        span = getattr(node, "end_lineno", None)
        if span is None or node.lineno not in names:
            continue
        name = names[node.lineno]
        if isinstance(node, ast.ClassDef):
            yield Unit(
                key=f"{relative}::class::{name}",
                path=relative,
                line=node.lineno,
                label=f"class {name}",
                measures={"class lines": span - node.lineno + 1 - _docstring_lines(node)},
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield Unit(
                key=f"{relative}::function::{name}",
                path=relative,
                line=node.lineno,
                label=name,
                measures={
                    "function lines": span - node.lineno + 1 - _docstring_lines(node),
                    "function branches": _branches(node),
                },
            )


def all_units(paths: Iterable[str]) -> list[Unit]:
    """Every unit under ``paths``, which may name files or directories."""
    found: list[Unit] = []
    for entry in paths:
        target = Path(entry)
        target = target if target.is_absolute() else ROOT / target
        files = sorted(target.rglob("*.py")) if target.is_dir() else [target]
        for file in files:
            found.extend(units_in(file))
    return found


def read_baseline() -> dict[str, dict[str, int]]:
    """What was already over a threshold when the baseline was last written."""
    if not BASELINE.exists():
        return {}
    raw = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {str(k): dict(v) for k, v in (raw.get("recorded") or {}).items()}


def read_reasons() -> dict[str, str]:
    """Why each deliberately kept unit stays at its size, keyed like the baseline."""
    if not BASELINE.exists():
        return {}
    raw = json.loads(BASELINE.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in (raw.get("reasons") or {}).items()}


def write_baseline(units: list[Unit], reason: str) -> int:
    """Record everything currently over a threshold. Returns how many were written.

    A `reasons` entry is kept where its unit is still recorded and dropped where the unit
    has gone under every threshold.
    """
    recorded = {unit.key: unit.over() for unit in units if unit.over()}
    reasons = {key: text for key, text in read_reasons().items() if key in recorded}
    BASELINE.write_text(
        json.dumps(
            {
                "why": (
                    "Units over a threshold in scripts/shape_check.py. The check passes on "
                    "these and fails on a new one or on one of these growing, so the list "
                    "only shrinks. A unit kept at size deliberately carries its reason in "
                    "`reasons`."
                ),
                "reason": reason,
                "thresholds": THRESHOLDS,
                "recorded": {k: dict(sorted(v.items())) for k, v in sorted(recorded.items())},
                "reasons": dict(sorted(reasons.items())),
            },
            indent=2,
            sort_keys=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(recorded)


def _ordered(measures: dict[str, int]) -> list[tuple[str, int]]:
    """The measures a message names, size before branching."""
    return [(name, measures[name]) for name in MEASURES if name in measures]


def _noun(name: str, value: int) -> str:
    """``2 branches``, ``1 branch``, ``51 lines``."""
    word = name.split()[-1]
    return f"{value} {word[:-2] if word == 'branches' and value == 1 else word}"


def _counts(measures: dict[str, int]) -> str:
    """``411 lines, 43 branches``, in that order."""
    return ", ".join(_noun(name, value) for name, value in _ordered(measures))


def _rank(value: int, population: list[int]) -> int:
    """What percentage of ``population`` this value is at or above."""
    if not population:
        return 100
    return round(100 * sum(1 for other in population if other <= value) / len(population))


def problems(units: list[Unit]) -> list[str]:
    """What is newly over a threshold, or over one by more than was recorded."""
    baseline = read_baseline()
    population: dict[str, list[int]] = {}
    for unit in units:
        for name, value in unit.measures.items():
            population.setdefault(name, []).append(value)

    found: list[str] = []
    for unit in sorted(units, key=lambda u: (u.path, u.line)):
        over = unit.over()
        if not over:
            continue
        recorded = baseline.get(unit.key, {})
        grown = {
            name: value
            for name, value in over.items()
            if value > recorded.get(name, THRESHOLDS[name])
        }
        if not grown:
            continue
        compared = ". It ".join(
            HOW_IT_COMPARES[name].format(rank=_rank(value, population[name]))
            for name, value in _ordered(grown)
        )
        was = "" if unit.key not in baseline else f" It was recorded at {_counts(recorded)}."
        found.append(
            f"{unit.path}:{unit.line}: {unit.label} is {_counts(unit.measures)}.\n"
            f"  It {compared}.{was} This is a question rather than a rule: is this one thing? "
            f"A unit this size is usually several. Decompose it, or keep the size deliberately "
            f"and record it with `uv run python scripts/shape_check.py --update`."
        )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", default=list(DEFAULT_PATHS))
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    parser.add_argument("--reason", default="", help="why the baseline moved")
    parser.add_argument("--list", action="store_true", help="print the recorded worklist")
    args = parser.parse_args(argv)

    units = all_units(args.paths or DEFAULT_PATHS)
    if args.update:
        written = write_baseline(units, args.reason or "updated")
        print(f"shape_check: recorded {written} unit(s) over a threshold")
        return 0
    if args.list:
        reasons = read_reasons()
        for key, over in sorted(read_baseline().items()):
            sizes = ", ".join(f"{v} {k}" for k, v in sorted(over.items()))
            kept = f"  [kept: {reasons[key]}]" if key in reasons else ""
            print(f"{key}: {sizes}{kept}")
        return 0

    found = problems(units)
    for problem in found:
        print(problem)
    print(f"shape_check: {len(found)} unit(s) to look at again" if found else "shape_check: clean")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
