"""The check that asks whether a large unit is one thing, and its ratchet.

`scripts/shape_check.py` reports a module, class or function among the largest in the library.
It is a question rather than a gate: everything already over a threshold is recorded, and what
fails is a unit crossing a threshold it was not over, or a recorded one growing.

The fixtures here are the coverage map. A threshold with no fixture is a threshold nothing
proves fires.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import shape_check  # noqa: E402
from shape_check import (  # noqa: E402
    THRESHOLDS,
    Unit,
    all_units,
    problems,
    read_baseline,
    units_in,
)  # noqa: E402


def _written(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "sample.py"
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _named(units: list[Unit], label: str) -> Unit:
    [found] = [unit for unit in units if unit.label == label]
    return found


class TestWhatIsMeasured:
    def test_a_docstring_does_not_count_toward_a_function(self, tmp_path):
        """`prose_check.py` governs docstring length; this one is about the code."""
        source = '''
        def documented():
            """One.

            Two.
            Three.
            Four.
            """
            return 1
        '''
        [unit] = [u for u in units_in(_written(tmp_path, source)) if u.label == "documented"]
        assert unit.measures["function lines"] == 2

    def test_a_method_is_named_for_its_class(self, tmp_path):
        source = """
        class Holder:
            def held(self):
                return 1
        """
        units = units_in(_written(tmp_path, source))
        assert _named(units, "Holder.held").key.endswith("::function::Holder.held")

    def test_a_boolean_operand_counts_as_a_branch(self, tmp_path):
        source = """
        def decides(a, b, c):
            return a and b and c
        """
        assert (
            _named(units_in(_written(tmp_path, source)), "decides").measures["function branches"]
            == 2
        )

    def test_a_comprehension_counts_as_a_branch(self, tmp_path):
        source = """
        def gathers(xs):
            return [x for x in xs]
        """
        assert (
            _named(units_in(_written(tmp_path, source)), "gathers").measures["function branches"]
            == 1
        )

    def test_a_module_is_measured_too(self, tmp_path):
        [unit] = [u for u in units_in(_written(tmp_path, "x = 1\ny = 2\n")) if u.line == 1]
        assert unit.measures == {"module lines": 2}


class TestTheThresholdsFire:
    """One fixture per threshold, which is what says the threshold is reachable at all."""

    @pytest.mark.parametrize("measure", sorted(THRESHOLDS))
    def test_every_threshold_has_a_fixture(self, measure):
        assert measure in {
            "function lines",
            "function branches",
            "class lines",
            "module lines",
        }

    def test_a_long_function_is_over(self, tmp_path):
        body = "\n".join(f"    a{n} = {n}" for n in range(THRESHOLDS["function lines"] + 5))
        unit = _named(units_in(_written(tmp_path, f"def long():\n{body}\n")), "long")
        assert "function lines" in unit.over()

    def test_a_branching_function_is_over(self, tmp_path):
        body = "\n".join(
            f"    if a == {n}: return {n}" for n in range(THRESHOLDS["function branches"] + 2)
        )
        unit = _named(units_in(_written(tmp_path, f"def forks(a):\n{body}\n")), "forks")
        assert "function branches" in unit.over()

    def test_a_long_class_is_over(self, tmp_path):
        body = "\n".join(f"    a{n} = {n}" for n in range(THRESHOLDS["class lines"] + 5))
        unit = _named(units_in(_written(tmp_path, f"class Big:\n{body}\n")), "class Big")
        assert "class lines" in unit.over()

    def test_a_long_module_is_over(self, tmp_path):
        source = "\n".join(f"a{n} = {n}" for n in range(THRESHOLDS["module lines"] + 5))
        [unit] = [u for u in units_in(_written(tmp_path, source)) if u.line == 1]
        assert "module lines" in unit.over()

    def test_an_ordinary_function_is_not(self, tmp_path):
        unit = _named(units_in(_written(tmp_path, "def small():\n    return 1\n")), "small")
        assert unit.over() == {}


class TestNothingIsDefinedTwice:
    """A module-level name bound twice is the second one, silently.

    Found 2026-09-04: a block of four constants was pasted into `view/prompts.py` twice while
    moving code, and the file imported, linted and passed 4,546 tests. `ruff` reports a
    redefined function and not a redefined constant.
    """

    def test_no_module_level_name_is_bound_twice(self) -> None:
        import ast

        root = Path(__file__).resolve().parent.parent
        bad = []
        for path in sorted((root / "src" / "simple_agents").rglob("*.py")):
            seen: dict[str, int] = {}
            for node in ast.parse(path.read_text(encoding="utf-8")).body:
                names: list[str] = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names = [node.name]
                elif isinstance(node, ast.Assign):
                    names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                    names = [node.target.id]
                for name in names:
                    if name in seen:
                        bad.append(
                            f"{path.relative_to(root)}:{node.lineno}: {name} was already "
                            f"defined at line {seen[name]}"
                        )
                    seen[name] = node.lineno
        assert not bad, "\n".join(bad)


class TestTheRatchet:
    def _over(self, key: str, **measures: int) -> Unit:
        return Unit(key=key, path="sample.py", line=1, label="grew", measures=measures)

    def test_a_new_unit_over_a_threshold_is_reported(self):
        unit = self._over("sample.py::function::fresh", **{"function lines": 400})
        assert problems([unit])

    def test_the_report_says_what_to_do_with_it(self):
        unit = self._over("sample.py::function::fresh", **{"function lines": 400})
        assert "is this one thing?" in problems([unit])[0]
        assert "--update" in problems([unit])[0]

    def test_a_recorded_unit_at_its_recorded_size_passes(self):
        key, recorded = next(iter(read_baseline().items()))
        assert problems([self._over(key, **recorded)]) == []

    def test_a_recorded_unit_that_grew_is_reported(self):
        key, recorded = next(iter(read_baseline().items()))
        grown = {name: value + 1 for name, value in recorded.items()}
        [reported] = problems([self._over(key, **grown)])
        assert "It was recorded at" in reported

    def test_the_library_itself_is_at_its_baseline(self):
        """What fails here is a unit that grew, and the message says which."""
        assert problems(all_units(["src/simple_agents"])) == []


class TestKeepReasons:
    """A kept unit's reason lives in the baseline and follows its unit."""

    def _big(self, key: str) -> Unit:
        return Unit(
            key=key, path="sample.py", line=1, label="big", measures={"function lines": 400}
        )

    def _seeded(self, tmp_path, monkeypatch, reasons: dict[str, str]) -> None:
        import json

        baseline = tmp_path / "shape_baseline.json"
        baseline.write_text(
            json.dumps(
                {"recorded": {k: {"function lines": 400} for k in reasons}, "reasons": reasons}
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(shape_check, "BASELINE", baseline)

    def test_a_reason_survives_an_update_while_its_unit_is_recorded(self, tmp_path, monkeypatch):
        key = "sample.py::function::kept"
        self._seeded(tmp_path, monkeypatch, {key: "one loop, one subject"})
        shape_check.write_baseline([self._big(key)], "updated")
        assert shape_check.read_reasons() == {key: "one loop, one subject"}

    def test_a_reason_is_dropped_with_its_unit(self, tmp_path, monkeypatch):
        key = "sample.py::function::decomposed"
        self._seeded(tmp_path, monkeypatch, {key: "was kept, then decomposed"})
        shape_check.write_baseline([], "updated")
        assert shape_check.read_reasons() == {}


class TestTheWorklistIsWorked:
    """P3-64's end state: every recorded unit is gone or carries a written reason."""

    def test_every_recorded_unit_carries_a_reason(self):
        unreasoned = sorted(set(read_baseline()) - set(shape_check.read_reasons()))
        assert not unreasoned, (
            f"{len(unreasoned)} recorded unit(s) carry no reason, starting with "
            f"{unreasoned[:3]}. A unit kept at size states why in the baseline's `reasons` "
            f"map; decompose it, or add its reason to scripts/shape_baseline.json."
        )

    def test_no_reason_outlives_its_unit(self):
        stray = sorted(set(shape_check.read_reasons()) - set(read_baseline()))
        assert not stray, (
            f"{len(stray)} reason(s) name a unit the baseline no longer records, starting "
            f"with {stray[:3]}. `--update` drops these; remove them from "
            f"scripts/shape_baseline.json."
        )
