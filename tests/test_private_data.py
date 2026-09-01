"""Runs the private-data sweep, so a record that lands with a finding fails the suite.

The rules and the allowlist live in `scripts/check_private_data.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from check_private_data import ALLOWED, scan_text, self_test, tracked  # noqa: E402


class TestThePrivateDataSweep:
    def test_every_rule_fires_on_its_own_defect(self) -> None:
        assert self_test() == []

    def test_no_tracked_file_carries_a_finding(self) -> None:
        findings = []
        for path in tracked():
            try:
                text = (REPO / path).read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            findings.extend(scan_text(path, text))

        assert findings == []

    def test_every_allowed_file_exists(self) -> None:
        """An entry naming a deleted file is a skip nothing uses; remove it."""
        missing = [path for path in ALLOWED if not (REPO / path).exists()]

        assert missing == []
