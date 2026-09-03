"""Checks a commit message against the rules in CLAUDE.md.

A commit message is public. It is read on GitHub by people who have never seen the plan, a
run, or a build log, and the messages this was written for ran to 118 characters of clauses
joined by `and`, with an internal id in brackets and a body reporting test counts.

Run it over the message being written, which is what the hook does::

    python3 scripts/check_commit_message.py .git/COMMIT_EDITMSG

Over commits already made::

    uv run python scripts/check_commit_message.py HEAD~5..

Install it as a commit-msg hook, so a message is checked as it is written::

    uv run python scripts/check_commit_message.py --install-hook

`git commit --no-verify` skips the hook. What it cannot check is whether the subject names
the change: a short, imperative, jargon-free subject describing the wrong commit passes every
rule here.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

SUBJECT_CEILING = 72
BODY_CEILING = 72
# A body longer than this is a build log. The build log is where that belongs.
BODY_LINE_CEILING = 15

# An id, a queue position or a run number means nothing to a reader outside this repository.
INTERNAL_ID = re.compile(r"\b(?:P3-\d+|dogfood[ -]#?\d+|item \d+[a-z]?)\b", re.I)
# A maintainer document. Naming one in a commit message points the reader at a file they do
# not have: the two documentation trees split at the release, and only `docs/` shipped.
INTERNAL_DOC = re.compile(
    r"(?:\bdev-docs/[\w./-]+|\b(?:plan|handoff|simple-agents|random-thoughts-questions)\.md"
    r"|\bbuild log\b|\bthe sitting\b|§\d)",
    re.I,
)
# What a build log says and a commit message does not: how many tests ran, how many passes it
# took, how it was found.
BUILD_LOG = re.compile(
    r"\b(?:[\d,]+ tests?\b|verified against|reverification|found by|passes? found|"
    r"cycles found|test suite is green)",
    re.I,
)
ATTRIBUTION = re.compile(r"(?:Co-Authored-By:|Generated with \[Claude Code\]|🤖)", re.I)

# Not imperative. A subject completes "this commit will …", so it opens with a bare verb.
ARTICLE = re.compile(r"^(?:The|A|An|This|These|Its|Our)\b")
NOT_IMPERATIVE = re.compile(
    r"^(?:Add(?:ed|ing)|Fix(?:ed|ing)|Remov(?:ed|ing)|Chang(?:ed|ing)|Updat(?:ed|ing)"
    r"|Renam(?:ed|ing)|Mov(?:ed|ing)|Refactor(?:ed|ing)|Document(?:ed|ing)|Bump(?:ed|ing)"
    r"|Support(?:ed|ing)|Mak(?:es|ing)|Made|Introduc(?:ed|ing)|Repl(?:aced|acing))\b"
)

GUIDANCE = {
    "subject_length": (
        "subject is {actual} characters and the ceiling is {ceiling}. Name the change and "
        "stop: `Add incremental index updates`."
    ),
    "subject_empty": "the message has no subject line.",
    "subject_period": "subject ends in a full stop. A subject is a title, so drop it.",
    "subject_case": "subject opens in lower case. Capitalise the first word.",
    "not_imperative": (
        'subject opens with `{found}`. A subject completes "this commit will …", so it '
        "opens with a bare verb: `Add`, `Fix`, `Remove`, `Rename`."
    ),
    "article": (
        "subject opens with `{found}`, which makes it a statement about the tree. A subject "
        'completes "this commit will …": `Refuse a changelog that says nothing`.'
    ),
    "clause_chain": (
        "subject reads as a chain of clauses. One commit, one sentence: a subject needing "
        "`and … and`, or a colon and a clause behind it, is usually more than one commit."
    ),
    "internal_id": (
        "`{found}` is an internal id. A commit message is read by people who have never seen "
        "the plan or a run, so say what changed instead."
    ),
    "internal_doc": (
        "`{found}` is a maintainer document and is not in the published repository. Cite "
        "`docs/` or nothing."
    ),
    "build_log": (
        "`{found}` reports how the change was built. A commit message says what changed; the "
        "build log holds the rest."
    ),
    "attribution": ("`{found}` is an attribution trailer. The commits here carry none."),
    "no_blank_line": "line 2 must be blank, so the subject stays a subject.",
    "body_length": ("body line is {actual} characters and the ceiling is {ceiling}. Wrap it."),
    "body_lines": (
        "body runs to {actual} lines and the ceiling is {ceiling}. A body says what a subject "
        "cannot: a breaking change and what to do about it, or a reason that is not obvious."
    ),
}


@dataclass(frozen=True)
class Problem:
    where: str
    rule: str
    detail: str

    def __str__(self) -> str:
        return f"{self.where}: {self.detail}"


def check(message: str, where: str = "commit-msg") -> list[Problem]:
    """Every rule, over one commit message. Reports what a reader outside this repo would hit."""
    lines = [line.rstrip() for line in message.split("\n")]
    # A comment block is what `git commit` appends to the file it opens; it never lands in the
    # commit. A `diff` below the scissors line is the same.
    kept: list[str] = []
    for line in lines:
        if line.startswith("# ------------------------ >8 -"):
            break
        if not line.startswith("#"):
            kept.append(line)
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()

    found: list[Problem] = []

    def add(rule: str, **fields: object) -> None:
        found.append(Problem(where, rule, GUIDANCE[rule].format(**fields)))

    if not kept:
        add("subject_empty")
        return found

    subject = kept[0]
    if len(subject) > SUBJECT_CEILING:
        add("subject_length", actual=len(subject), ceiling=SUBJECT_CEILING)
    if subject.endswith("."):
        add("subject_period")
    if subject[:1].islower():
        add("subject_case")
    if article := ARTICLE.match(subject):
        add("article", found=article.group(0))
    elif tense := NOT_IMPERATIVE.match(subject):
        add("not_imperative", found=tense.group(0))
    # Two coordinated nouns is a sentence: `the numpy and FAISS stores`. Three joins, or a
    # colon with a join behind it, is the diffstat-in-a-subject this exists to stop.
    if subject.count(" and ") + 2 * subject.count(": ") >= 3:
        add("clause_chain")

    body = kept[1:]
    if body and kept[1].strip():
        add("no_blank_line")
    while body and not body[0].strip():
        body.pop(0)
    if len(body) > BODY_LINE_CEILING:
        add("body_lines", actual=len(body), ceiling=BODY_LINE_CEILING)
    for line in body:
        if len(line) > BODY_CEILING:
            add("body_length", actual=len(line), ceiling=BODY_CEILING)
            break

    whole = "\n".join(kept)
    for rule, pattern in (
        ("internal_id", INTERNAL_ID),
        ("internal_doc", INTERNAL_DOC),
        ("build_log", BUILD_LOG),
        ("attribution", ATTRIBUTION),
    ):
        if hit := pattern.search(whole):
            add(rule, found=hit.group(0))
    return found


def messages_in(revisions: str) -> list[tuple[str, str]]:
    """Each commit in a revision range, as its short hash and its whole message."""
    done = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x1e", revisions],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise SystemExit(f"check_commit_message: git log {revisions}: {done.stderr.strip()}")
    found = []
    for record in done.stdout.split("\x1e"):
        if not record.strip():
            continue
        commit, _, message = record.strip().partition("\x00")
        found.append((commit[:9], message))
    return found


HOOK = """#!/bin/sh
# Written by scripts/check_commit_message.py --install-hook.
exec python3 "$(git rev-parse --show-toplevel)/scripts/check_commit_message.py" "$1"
"""


def install_hook() -> int:
    directory = Path(
        subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    if not directory.is_absolute():
        directory = REPO / directory
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "commit-msg"
    if path.exists() and path.read_text(encoding="utf-8") != HOOK:
        print(f"check_commit_message: {path} already exists and was left alone.")
        return 1
    path.write_text(HOOK, encoding="utf-8")
    path.chmod(0o755)
    print(f"check_commit_message: installed {path}. `git commit --no-verify` skips it.")
    return 0


# One deliberate defect per rule, and the message it has to produce. A rule with no fixture
# here has no coverage, so this list is the coverage map as well as the suite. They run on
# every invocation, including the hook's; `--self-test` runs them alone, for working on a rule.
SELF_TESTS: list[tuple[str, str, str]] = [
    ("a subject over the ceiling", "Add " + "a thing " * 12, "72"),
    ("an empty message", "\n\n#comment\n", "no subject line"),
    ("a subject ending in a full stop", "Add the numpy store.", "full stop"),
    ("a lower-case subject", "add the numpy store", "lower case"),
    ("a subject opening with an article", "The brief has one writer", "`The`"),
    ("a subject in the past tense", "Added the numpy store", "`Added`"),
    ("a subject in the gerund", "Adding the numpy store", "`Adding`"),
    (
        "a subject of clauses joined by and",
        "Add the store and record it and refuse an old one and warn once",
        "chain of clauses",
    ),
    (
        "a subject carrying a colon and a clause",
        "Add the store: it is exact and fast",
        "chain of clauses",
    ),
    ("two coordinated nouns, which is a sentence", "Add the numpy and FAISS stores", ""),
    ("an internal queue id", "Add the numpy store (P3-73)", "internal id"),
    ("a run number", "Fix four faults found in dogfood #6", "internal id"),
    ("an item number", "Fix the join item 8c left open", "internal id"),
    ("a maintainer document", "Add the numpy store\n\nRecorded in dev-docs/plan.md.", "not in the"),
    ("a section reference", "Add the numpy store\n\nSettled at §2.6.", "not in the"),
    ("a body reporting test counts", "Add the numpy store\n\n4,254 tests.", "how the change"),
    (
        "a body reporting how it was found",
        "Add the numpy store\n\nFound by a read of the shipped code.",
        "how the change",
    ),
    (
        "an attribution trailer",
        "Add the numpy store\n\nCo-Authored-By: Someone <a@b.c>",
        "attribution trailer",
    ),
    ("a body with no blank line under the subject", "Add the numpy store\nExact.", "line 2"),
    ("a body line over the ceiling", "Add the numpy store\n\n" + "word " * 20, "Wrap it"),
    (
        "a body as long as a build log",
        "Add the numpy store\n\n" + "A line.\n" * 16,
        "runs to 16 lines",
    ),
    ("a message that follows every rule", "Add the numpy vector store", ""),
]


def self_test() -> list[str]:
    """Each fixture, against the message it has to produce. Reports the ones that did not."""
    failed = []
    for name, message, expected in SELF_TESTS:
        said = " ".join(str(one) for one in check(message))
        if expected and expected not in said:
            failed.append(f"{name}: expected {expected!r}, got {said!r}")
        if not expected and said:
            failed.append(f"{name}: expected no problem, got {said!r}")
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a commit message.")
    parser.add_argument(
        "target",
        nargs="?",
        help="a message file, or a revision range such as HEAD~5.. (default: the last commit)",
    )
    parser.add_argument("--install-hook", action="store_true", help="install the commit-msg hook")
    parser.add_argument("--self-test", action="store_true", help="run the fixtures alone")
    args = parser.parse_args(argv)

    broken = self_test()
    for line in broken:
        print(f"check_commit_message: self-test: {line}")
    if broken:
        return 1
    if args.self_test:
        print(f"self-test: {len(SELF_TESTS)}/{len(SELF_TESTS)} rules fire")
        return 0
    if args.install_hook:
        return install_hook()

    if args.target and Path(args.target).is_file():
        subjects = [(Path(args.target).name, Path(args.target).read_text(encoding="utf-8"))]
    else:
        subjects = messages_in(args.target or "HEAD~1..")

    found = [problem for where, message in subjects for problem in check(message, where)]
    for problem in found:
        print(f"check_commit_message: {problem}")
    if found:
        print(
            f"\n{len(found)} problem(s) in {len(subjects)} message(s). CLAUDE.md's "
            "`Commit messages` section has the rule and an example of each."
        )
        return 1
    print(f"check_commit_message: clean, {len(subjects)} message(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
