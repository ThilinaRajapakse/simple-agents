"""`docs/run-envelope.md` §4.5's re-pricing example, executed rather than read.

The first draft of the example priced a fresh two-rate basis and returned unknown on the
fixture run: a Gemini call's cache-write count is recorded unknown, and an unmeasured count
under a nonzero rate has no price. `prose_check` saw it parse and resolve. Running it is what
found that, so it stays run.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE_RUNS = REPO / "tests" / "fixtures" / "view_projects" / "branching" / "runs"


def _repricing_block() -> str:
    """The fenced Python block under `### 4.5 Re-pricing a run from its record`."""
    text = (REPO / "docs" / "run-envelope.md").read_text(encoding="utf-8")
    section = text.split("### 4.5 Re-pricing a run from its record", 1)
    assert len(section) == 2, "run-envelope.md has no §4.5 re-pricing section"
    block = re.search(r"```python\n(.*?)```", section[1], re.DOTALL)
    assert block, "the re-pricing section has no Python block"
    return block.group(1)


class TestTheRepricingExample:
    def test_it_prices_a_real_run_under_both_bases(self, tmp_path, monkeypatch) -> None:
        """The block runs unmodified against a recorded fixture run, and both totals price."""
        (tmp_path / "runs").symlink_to(FIXTURE_RUNS)
        monkeypatch.chdir(tmp_path)

        namespace: dict = {}
        exec(_repricing_block(), namespace)  # noqa: S102

        from dataclasses import replace

        from simple_agents import total_cost

        recorded = namespace["recorded"]
        records = namespace["records"]
        as_recorded = total_cost(records, recorded)
        repriced = total_cost(
            records, replace(recorded, input_uncached_per_mtok=0.15, output_per_mtok=0.60)
        )

        assert as_recorded.value is not None
        assert repriced.value is not None
        assert repriced.unpriced_calls == 0
        assert repriced.priced_calls == as_recorded.priced_calls > 0
