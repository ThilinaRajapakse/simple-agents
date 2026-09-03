"""Read every tracked file for material that should not be in a public repository.

Run before publishing, and after any run record lands::

    uv run python scripts/check_private_data.py [--self-test]

Six rules: credential formats, email addresses, absolute paths naming a person's home
directory, references to a personal data file, cookies in a recorded response, and routable
IP addresses. Each reports the file, the line and what matched.

**The allowlist is what gets skipped, and it is enumerated here.** A rule that protects
something has to fail closed, so a new fixture holding a fake credential is reported until
somebody adds it below with a reason. That is `simple-agents.md` §10's rule about redaction
applied to this scan: adding a file is routine, and remembering a list in another module is
not. An entry names the rules it skips, each with its reason, and every other rule still
reads the file. A whole-file entry (a plain string) is reserved for a file that states the
patterns themselves.

**Every rule carries a self-test**, which is one deliberate defect and the message it has to
produce, and they run on every invocation. A rule with no self-test has no coverage, so the
list below is also the map of what this reads for.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Files whose match is deliberate. A dict names the rules skipped for that file, each with the
# reason; every other rule still reads it. A plain string skips every rule, and is reserved for
# a file that states the patterns themselves. Nothing else is skipped.
_FIXTURE = "fake credentials are what the redaction tests assert on"
_HISTORY = "a maintainer record naming where a dogfood project sat; ruled kept 2026-09-01"
ALLOWED: dict[str, str | dict[str, str]] = {
    "scripts/check_private_data.py": "this file states every pattern it looks for",
    "tests/test_boundary_redaction.py": {"credential": _FIXTURE},
    "tests/test_memory.py": {
        "credential": _FIXTURE,
        "email": "a placeholder address is the scope the digest test hashes",
    },
    "tests/test_reasoning.py": {"credential": _FIXTURE},
    "tests/test_redaction.py": {
        "credential": _FIXTURE,
        "response cookie": "the fake cookie is what the redaction assertions read",
    },
    "tests/test_prose.py": {"home path": "the machine_path rule's own firing fixture"},
    "tests/test_runs.py": {"credential": _FIXTURE},
    "tests/test_conversation.py": {"credential": _FIXTURE},
    "tests/test_recording_a_resource_access.py": {"credential": _FIXTURE},
    "tests/test_view_the_whole_record.py": {"credential": _FIXTURE},
    "tests/test_what_a_run_cost_and_what_it_is_doing.py": {"credential": _FIXTURE},
    "tests/test_answer_keys.py": {"credential": "a fake key is the subject of the test"},
    "tests/test_adapters.py": {
        "credential": "a fake key is the subject of the test that it does not render",
        "response cookie": "the fake cookie is what the redaction assertions read",
    },
    "src/simple_agents/redaction.py": {
        "credential": "the module states the credential formats it detects"
    },
    "docs/run-envelope.md": {
        "credential": "the document states the credential formats redaction detects"
    },
    "docs/memory.md": {
        "credential": "the document states the credential formats redaction detects"
    },
}

# Suffixes worth reading. A binary file is skipped: nothing here can read it.
TEXT = {".py", ".md", ".toml", ".yml", ".yaml", ".json", ".jsonl", ".txt", ".cfg", ".ini"}


class Rule:
    def __init__(self, name: str, pattern: str, message: str, *, flags: int = 0) -> None:
        self.name = name
        self.regex = re.compile(pattern, flags)
        self.message = message


# An illustrative path with a placeholder name says who wrote nothing. The same names
# `prose_check.py`'s `machine_path` rule permits.
_PLACEHOLDER_HOMES = "x|you|user|username|me|alice|bob|name|someone"

RULES = [
    Rule(
        "credential",
        r"\b(sk-[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}"
        r"|xox[baprs]-[A-Za-z0-9-]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)",
        "a credential format. Remove it, or add the file to ALLOWED with the reason it is a "
        "fixture.",
    ),
    Rule(
        "email",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "an email address. Use a placeholder such as builder@example.com.",
    ),
    Rule(
        "home path",
        r"(/home/(?!(?:" + _PLACEHOLDER_HOMES + r")\b)[a-z][a-z0-9_-]*"
        r"|/Users/(?!(?:" + _PLACEHOLDER_HOMES + r")\b)[A-Za-z][A-Za-z0-9_-]*"
        r"|[A-Z]:\\\\Users\\\\[A-Za-z]+)",
        "an absolute path naming a person's home directory. Write a relative path, or a "
        "placeholder home such as /home/user/project.",
    ),
    Rule(
        "personal file",
        r"(Downloads/|Documents/|Desktop/|\.ssh/|\.aws/credentials|\b\w+_export\.(?:csv|tsv|json|zip)\b)",
        "a reference to a personal file. Name the shape of the file rather than where it sat.",
    ),
    Rule(
        "response cookie",
        r'"?set-cookie"?\s*[:=]\s*"(?![^"]*\[redacted\])[^"]+"',
        "a cookie from a recorded response. Redact the value before the fixture is committed.",
        flags=re.IGNORECASE,
    ),
    Rule(
        "routable ip",
        r"(?<![\w.-])(?!0\.0\.0\.0|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.)"
        r"(?:\d{1,3}\.){3}\d{1,3}(?![\w.-])",
        "a routable IP address. Use a hostname, or a documentation range such as 203.0.113.1.",
    ),
]

# One deliberate defect per rule, and the rule it has to be reported by.
SELF_TESTS: list[tuple[str, str, str]] = [
    ("credential", "notes.md", "the key sk-abcdefghijklmnopqrstuvwx was left in"),
    ("email", "notes.md", "write to somebody@example.com about it"),
    ("home path", "notes.md", "it read /home/somebody/Projects/thing"),
    ("personal file", "notes.md", "the export sat in Downloads/ before it moved"),
    ("response cookie", "wire.json", '  "set-cookie": "__cf_bm=abcdef; Path=/"'),
    ("routable ip", "notes.md", "the server answered on 8.8.8.8"),
]

# One line per exemption that has to stay quiet, and the rule it exercises.
QUIET_SELF_TESTS: list[tuple[str, str, str]] = [
    ("home path", "notes.md", "a project at /home/user/library, installed at /home/x/lib"),
]


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    )
    return [p for p in out.stdout.splitlines() if Path(p).suffix in TEXT]


def scan_text(path: str, text: str) -> list[str]:
    """Every finding in one file, as a printable line each."""
    allowed = ALLOWED.get(path)
    if isinstance(allowed, str):
        return []
    skipped = allowed or {}
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        for rule in RULES:
            if rule.name in skipped:
                continue
            match = rule.regex.search(line)
            if match:
                found.append(f"{path}:{number}: {rule.name}: {match.group(0)!r} is {rule.message}")
    return found


def self_test() -> list[str]:
    """Each rule fires on its own deliberate defect. Reports the ones that do not."""
    broken = []
    for expected, path, line in SELF_TESTS:
        reported = scan_text(path, line)
        if not any(f": {expected}: " in entry for entry in reported):
            broken.append(
                f"the {expected!r} rule did not fire on {line!r}. A rule that cannot be shown "
                f"to catch its own defect is not a check."
            )
    for expected, path, line in QUIET_SELF_TESTS:
        reported = scan_text(path, line)
        if any(f": {expected}: " in entry for entry in reported):
            broken.append(
                f"the {expected!r} rule fired on {line!r}, which its exemption says is quiet."
            )
    covered = {name for name, _, _ in SELF_TESTS}
    for rule in RULES:
        if rule.name not in covered:
            broken.append(f"the {rule.name!r} rule has no self-test, so nothing covers it.")
    broken.extend(_allowlist_self_test())
    return broken


def _allowlist_self_test() -> list[str]:
    """A per-rule entry skips the rules it names and no others, shown on a live entry."""
    broken = []
    defects = {name: line for name, _, line in SELF_TESTS}
    path, rules = next((p, r) for p, r in ALLOWED.items() if isinstance(r, dict))
    allowed_rule = next(iter(rules))
    other_rule = next(name for name in defects if name not in rules)
    if scan_text(path, defects[allowed_rule]):
        broken.append(
            f"{path!r} skips {allowed_rule!r} and a {allowed_rule!r} defect was reported anyway."
        )
    if not scan_text(path, defects[other_rule]):
        broken.append(
            f"{path!r} skips only {sorted(rules)} and a {other_rule!r} defect went unreported."
        )
    whole = next((p for p, r in ALLOWED.items() if isinstance(r, str)), None)
    if whole and scan_text(whole, defects["credential"]):
        broken.append(f"{whole!r} skips every rule and a defect was reported anyway.")
    return broken


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true", help="run the self-tests alone")
    args = parser.parse_args()

    broken = self_test()
    if broken:
        for entry in broken:
            print(f"  self-test: {entry}")
        return 1
    print(f"self-test: {len(SELF_TESTS)}/{len(RULES)} rules fire")
    if args.self_test:
        return 0

    findings = []
    for path in tracked():
        try:
            text = (ROOT / path).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        findings.extend(scan_text(path, text))

    for entry in findings:
        print(f"  {entry}")
    if findings:
        print(f"check_private_data: {len(findings)} finding(s)")
        return 1
    print("check_private_data: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
