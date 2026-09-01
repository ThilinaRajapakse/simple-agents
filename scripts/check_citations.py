"""Checks that a citation into the source still points at what it says it points at.

`dev-docs/` cites code by file and line. Line numbers rot: every edit above a cited line
moves it, and nothing notices. Run over the whole repository::

    uv run python scripts/check_citations.py

Or over specific paths::

    uv run python scripts/check_citations.py dev-docs/dogfood-2-findings.md

`--fix` rewrites the anchors this can resolve on its own, which is `symbol-drift` and the
`blank-line` cases naming a subject it can find::

    uv run python scripts/check_citations.py --fix

What it declines: a `blank-line` whose subject is not named beside it, and one whose name is
dotted or is defined more than once in the cited file, since `Tool.resolve` and
`Workspace.resolve` are two definitions of `resolve` and nothing says which was meant.

This is deliberately not part of `prose_check.py`. That checks writing rules and skips
`dev-docs/` on purpose; this checks whether a link resolves, which is a different question
and applies wherever a citation is written.

Eight things are checked, each named in its own failure message:

- **unresolvable** — the path names no file under either convention, or the anchor is past
  the end of one that exists. Where the subject is named beside it, the message says which
  line holds it and `--fix` moves it there, as it does for `blank-line`.
- **not-clickable** — the path resolves from the repository root but not from the citing
  file, so a markdown renderer following it gets nothing. Reported separately because which
  convention is correct is a decision recorded in `CLAUDE.md` rather than a fact about a file.
- **label-mismatch** — the label says one line and the anchor says another.
- **blank-line** — the anchor lands on a blank line, which is never what was meant. Where the
  subject is named beside it, the message says which line holds it and `--fix` moves it there.
  This is the class an edit above a citation produces, so it is the one most worth fixing for
  the writer rather than reporting at them.
- **no-such-symbol** — the label names symbols in backticks and the cited file holds none of
  them anywhere, so the citation has nothing to re-resolve and `symbol-drift` cannot see it at
  all. The hole this closes: `_spend_line` written for `_spend_lines`, anchored on a real line,
  passed clean. The test is the word appearing rather than being defined, since a label names a
  local, a class attribute or a string id as readily as a function.
- **symbol-drift** — the name the citation is about is defined exactly once in the cited file,
  more than `NEAR` lines from the anchor. Two things keep this quiet: the name has to be the
  citation's subject rather than anything else the sentence mentions, and it has to have
  exactly one definition. "The library requires a `DeclaredCost` on a `spends_money` tool
  ([tools.py:351])" is about the refusal and not about `DeclaredCost`, and raises nothing.
- **dead-md-link** — a link to a markdown file that does not exist, or whose `#L` anchor is
  past the end of one that does. A record moved to `build-logs/` or `archive/` leaves these
  behind, and until 2026-08-31 nothing looked: a link to a deleted `items/` file sat in a
  build log and passed clean.
- **unnamed-anchor** — a line-anchored source citation past line 1 with no symbol in backticks
  in its label or the sentence before it. `symbol-drift` and `blank-line` repair a citation by
  its named subject, so one naming nothing is the one no check can ever re-resolve. An anchor
  at line 1 cites the module itself and cannot rot, and is exempt.

**Which name is the subject.** The link's own label first, and a declared field such as
`inputs: Any` counts there. Only where the label names nothing in backticks does this read the
sentence before it, and there a field does not count, because a field name is often an ordinary
word and `cost`, `score`, `kind` and `threshold` in running prose then resolve to one.

What this cannot check: whether a citation pointing at a statement inside a function still
points at the right statement. Nothing names that line, so nothing can resolve it.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CHECKED = ("dev-docs", "docs", "README.md", "CHANGELOG.md")
SOURCE_ROOTS = ("src", "scripts", "tests")

# How far an anchor may sit from the definition it names before it counts as drifted. A
# citation usually lands on the `def` line or on the docstring under it.
NEAR = 3

LINK = re.compile(
    r"\[([^\]\n]*?)\]\(((?:\.\./)*(?:" + "|".join(SOURCE_ROOTS) + r")/[^)#\s]+)#L(\d+)\)"
)
IDENT = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")
# A dotted name is read only out of a label, where the author named the citation's own
# subject. In the prose around it, `Held.resolve` is a mention rather than the subject.
DOTTED = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")
LABEL_LINE = re.compile(r":(\d+)`?\s*$")
"""The line a label states, if it states one.

The closing backtick is optional because a label in backticks is the house style
(`CLAUDE.md`, "Name what a citation is about, in backticks"), and requiring the digits at
the very end meant this fired only on the form the conventions discourage. Twenty-six
labels had drifted from their own anchors under the stricter pattern.
"""
NOT_A_SYMBOL = frozenset({"None", "True", "False", "self", "cls"})

# A relative link to a markdown file, with or without a line anchor. A colon in the target
# excludes URLs, which are not this script's to check.
MD_LINK = re.compile(r"\[([^\]\n]*?)\]\(([^)#:\s]+\.md)(?:#L(\d+))?\)")


@dataclass(frozen=True)
class Problem:
    """One citation that does not resolve to what it claims."""

    kind: str
    path: Path
    line: int
    message: str
    fix: tuple[str, str] | None = None

    def render(self) -> str:
        where = self.path.relative_to(REPO)
        return f"{where}:{self.line}: {self.kind}: {self.message}"


def definition_lines(source: list[str], name: str, *, fields: bool = False) -> list[int]:
    """Every line defining ``name``: a def, a class, or a module-level assignment.

    ``fields`` adds the declared attribute, ``inputs: Any`` on a dataclass. It is off by
    default and on only where the citation's own label names the subject, because a field
    name is often an ordinary word: turning it on everywhere made ``cost``, ``score``,
    ``kind`` and ``threshold`` in running prose resolve to a dataclass field and produced 44
    reports against citations that were right.
    """
    alternatives = [
        rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(name)}\b",
        rf"^{re.escape(name)}\s*(?::[^=]+)?=",
    ]
    if fields:
        alternatives.append(rf"^\s+{re.escape(name)}\s*:\s*[^=\s]")
    pattern = re.compile("|".join(alternatives))
    return [i + 1 for i, line in enumerate(source) if pattern.search(line)]


def member_lines(source: list[str], owner: str, name: str) -> list[int]:
    """Every line defining ``name`` inside ``class owner``, for a dotted citation.

    ``Example.expected`` resolves to the ``expected: Any`` inside ``class Example`` and not to
    an ``expected`` somewhere else in the file, which is what makes a dotted name checkable at
    all. A name the class does not hold resolves to nothing rather than to a namesake.
    """
    opens = re.compile(rf"^(\s*)class\s+{re.escape(owner)}\b")
    member = re.compile(
        rf"^\s+(?:async\s+)?def\s+{re.escape(name)}\b"
        rf"|^\s+{re.escape(name)}\s*[:=]"
    )
    prose = _docstring_lines(source)
    found: list[int] = []
    for index, line in enumerate(source):
        start = opens.match(line)
        if start is None or index in prose:
            continue
        indent = len(start.group(1))
        body_indent: int | None = None
        for offset in range(index + 1, len(source)):
            body = source[offset]
            if not body.strip():
                continue
            depth = len(body) - len(body.lstrip())
            if depth <= indent:
                break
            if body_indent is None:
                body_indent = depth
            # A declaration sits at the class body's own indentation. `expected=...` passed as
            # a keyword argument inside a method is deeper, and is a use rather than the thing.
            if offset not in prose and depth == body_indent and member.match(body):
                found.append(offset + 1)
    return found


def _docstring_lines(source: list[str]) -> set[int]:
    """Every line index inside a triple-quoted string.

    A docstring example writes a keyword argument at the indentation a field declaration has,
    so reading those as declarations finds a class holding seven of everything and resolves
    nothing.
    """
    marks = (chr(34) * 3, chr(39) * 3)
    inside: set[int] = set()
    fence: str | None = None
    for index, line in enumerate(source):
        if fence is None:
            for mark in marks:
                if line.count(mark) % 2 == 1:
                    fence = mark
                    inside.add(index)
                    break
        else:
            inside.add(index)
            if fence in line:
                fence = None
    return inside


def check_file(path: Path) -> list[Problem]:
    """Every citation in one document, checked against the files it names."""
    found: list[Problem] = []
    lines = path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        for label, target, anchor in LINK.findall(line):
            found.extend(_check_one(path, number, lines, label, target, int(anchor)))
        for label, target, anchor in MD_LINK.findall(line):
            found.extend(_check_md(path, number, label, target, int(anchor) if anchor else None))
    return found


def _check_md(
    path: Path, number: int, label: str, target: str, anchor: int | None
) -> list[Problem]:
    """A link to a markdown file: the file exists, and any `#L` anchor is inside it."""
    from_file = (path.parent / target).resolve()
    found: list[Problem] = []
    if not from_file.exists():
        # Text moves between directories with its links written for where it used to live, so
        # the target is searched for from every ancestor up to the repository root. Found
        # anywhere, the repair is the path from the citing file, which is the one convention
        # a renderer follows (`CLAUDE.md`, 2026-08-10).
        elsewhere = next(
            (
                (base / target.lstrip("./")).resolve()
                for base in [*path.parents]
                if base.is_relative_to(REPO) and (base / target.lstrip("./")).exists()
            ),
            None,
        )
        if elsewhere is None:
            return [
                Problem(
                    "dead-md-link",
                    path,
                    number,
                    f"[{label}] names {target}, and no such file exists from this document "
                    f"or from any directory above it. Point it at where the record went, or "
                    f"drop it.",
                )
            ]
        found.append(
            Problem(
                "not-clickable",
                path,
                number,
                f"[{label}] does not resolve from this document, so a renderer following "
                f"it reaches nothing. From here the path is {_relative(path, elsewhere)}.",
                fix=(f"]({target}", f"]({_relative(path, elsewhere)}"),
            )
        )
    source_path = from_file if from_file.exists() else elsewhere
    if anchor is not None:
        length = len(source_path.read_text(encoding="utf-8").splitlines())
        if anchor > length:
            found.append(
                Problem(
                    "dead-md-link",
                    path,
                    number,
                    f"[{label}] points at line {anchor} of {target}, which has {length} "
                    f"lines. Anchor the line that holds the thing.",
                )
            )
    return found


def _check_one(
    path: Path, number: int, lines: list[str], label: str, target: str, anchor: int
) -> list[Problem]:
    found: list[Problem] = []
    from_file = (path.parent / target).resolve()
    from_root = (REPO / target.lstrip("./")).resolve()

    if not from_file.exists() and not from_root.exists():
        return [
            Problem(
                "unresolvable",
                path,
                number,
                f"[{label}] names {target}, and no such file exists from this document or "
                f"from the repository root. Correct the path, or drop the citation.",
            )
        ]

    if not from_file.exists():
        found.append(
            Problem(
                "not-clickable",
                path,
                number,
                f"[{label}] resolves from the repository root and not from this document, "
                f"so a renderer following it reaches nothing. From here the path is "
                f"{_relative(path, from_root)}.",
                fix=(f"]({target}#L", f"]({_relative(path, from_root)}#L"),
            )
        )

    source_path = from_file if from_file.exists() else from_root
    source = source_path.read_text(encoding="utf-8").splitlines()

    stated = LABEL_LINE.search(label)
    if stated and int(stated.group(1)) != anchor:
        found.append(
            Problem(
                "label-mismatch",
                path,
                number,
                f"[{label}] says line {stated.group(1)} and the anchor says {anchor}. "
                f"A reader believes the label and a click follows the anchor.",
                # The anchor is the half this re-resolves, so the label is the stale one.
                fix=(f"[{label}]", f"[{_relabel(label, anchor)}]"),
            )
        )

    if anchor > len(source):
        # Re-resolved the same way as `blank-line`, and for the same reason: an anchor past the
        # end names a subject the file still holds, so the repair is the one `--fix` already
        # makes elsewhere. Reported and abandoned until 2026-08-28, which left the most
        # obviously broken anchor as the one kind nothing could repair.
        resolved = _subject_definition(lines, number, anchor, source, label, near=False)
        fix = None
        if resolved is not None:
            _, line = resolved
            fix = (
                f"[{label}]({target}#L{anchor})",
                f"[{_relabel(label, line)}]({target}#L{line})",
            )
        found.append(
            Problem(
                "unresolvable",
                path,
                number,
                f"[{label}] points at line {anchor} of a file with {len(source)} lines."
                + (f" `{resolved[0]}` beside it is at line {resolved[1]}." if resolved else ""),
                fix=fix,
            )
        )
        return found

    if not source[anchor - 1].strip():
        # Resolved the same way as `symbol-drift` and without its distance test, because an
        # anchor a couple of lines out is exactly the case here: an edit above a citation
        # slides it onto the blank line between two definitions, which is near the right one.
        resolved = _subject_definition(lines, number, anchor, source, label, near=False)
        fix = None
        if resolved is not None:
            _, line = resolved
            fix = (
                f"[{label}]({target}#L{anchor})",
                f"[{_relabel(label, line)}]({target}#L{line})",
            )
        found.append(
            Problem(
                "blank-line",
                path,
                number,
                f"[{label}] points at a blank line. Cite the line holding the thing, and "
                f"name it in backticks beside the citation so this can check it again later."
                + (f" `{resolved[0]}` beside it is at line {resolved[1]}." if resolved else ""),
                fix=fix,
            )
        )

    found.extend(_no_such_symbol(path, number, label, target, source))
    found.extend(_symbol_drift(path, number, lines, label, target, anchor, source))
    found.extend(_unnamed_anchor(path, number, lines, label, anchor))
    return found


def _unnamed_anchor(
    path: Path, number: int, lines: list[str], label: str, anchor: int
) -> list[Problem]:
    """A citation past line 1 that names no symbol anywhere a repair could read one.

    `symbol-drift`, `blank-line` and the past-the-end repair all re-resolve a citation by the
    subject named beside it, so a citation naming nothing is the one that can never be
    repaired, only noticed once its line goes blank. Line 1 cites the module itself and is
    exempt: it cannot rot.
    """
    if anchor <= 1:
        return []
    context = " ".join(lines[max(0, number - 4) : number])
    # A dotted name in prose is not a subject `_subject_definition` will track, but it is a
    # name a later reader can re-resolve by hand, so it counts as named here.
    named = [
        name
        for name in IDENT.findall(label)
        + DOTTED.findall(label)
        + IDENT.findall(context)
        + DOTTED.findall(context)
        if name not in NOT_A_SYMBOL and not _names_a_file(name)
    ]
    if named:
        return []
    return [
        Problem(
            "unnamed-anchor",
            path,
            number,
            f"[{label}] anchors line {anchor} and names no symbol this can re-resolve "
            f"later. Name what the citation is about, in backticks, in the label or the "
            f"sentence beside it.",
        )
    ]


def _no_such_symbol(
    path: Path, number: int, label: str, target: str, source: list[str]
) -> list[Problem]:
    """A label naming symbols in backticks, none of which the cited file defines.

    Naming the symbol is what lets `symbol-drift` re-resolve a citation after the code above it
    moves. A name that is a typo, or that a rename took away, resolves to nothing, and every
    check that rests on it goes quiet: :func:`_subject_definition` skips a name it cannot find
    and moves on. So the citation keeps passing while the one thing making it checkable is
    gone.

    **The test is whether the file holds the word at all**, not whether it defines it. A label
    names a local variable, a class attribute, or a string id such as an elicitation question's
    ``name="ground_truth"`` as readily as it names a function, and each of those is findable by
    a reader even though ``symbol-drift`` cannot re-resolve it. Measured over this tree when the
    rule was written: the definition test alone reported nine citations and seven were of that
    kind, which is the noise this module's own docstring says stops it being read. What is left
    is the case the rule is for, a name the file does not contain: ``_verdict`` where the
    function is ``_criteria_verdict``.

    Only the label is read, and only where **no** name in it appears. A label naming one symbol
    from this file beside one from elsewhere is a citation whose subject is still findable, and
    prose around a citation legitimately mentions names from other files.
    """
    named = [
        name
        for name in IDENT.findall(label) + DOTTED.findall(label)
        if name not in NOT_A_SYMBOL and not _names_a_file(name)
    ]
    if not named:
        return []
    text = "".join(source)
    for name in named:
        member = name.rpartition(".")[2]
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(member)}(?![A-Za-z0-9_])", text):
            return []
    return [
        Problem(
            "no-such-symbol",
            path,
            number,
            f"[{label}] names {', '.join(f'`{n}`' for n in named)} and the cited file holds "
            f"none of them anywhere. A name that is a typo, or that a rename took away, leaves "
            f"this citation with nothing to re-resolve, so it goes on passing every check while "
            f"the line it points at drifts.\n    Name it as "
            f"{target.rsplit('/', 1)[-1]} spells it, or drop the backticks where the label is "
            f"not naming something in that file.",
        )
    ]


def _subject_definition(
    lines: list[str], number: int, anchor: int, source: list[str], label: str, *, near: bool
) -> tuple[str, int] | None:
    """The citation's subject and the one line defining it, or ``None``.

    **The label wins.** A name in backticks inside the link's own text is the citation's
    subject, and a declared field counts there. Only where the label names nothing does this
    fall back to the last name in backticks in the sentence before it, and there a field does
    not count. A sentence naming three things and citing one of them would otherwise resolve
    against whichever of the three happens to have a unique definition, which is noise, and a
    checker that raises noise stops being read.

    The label-first order is what repairs a citation to a dataclass field. ``[`inputs`]``
    pointing at ``examples.py:79`` was reported as drift against the ``Example`` named in the
    sentence above it, because the field was invisible and the class was not.

    ``near`` is whether a definition within ``NEAR`` lines of the anchor counts as already
    right. It does for `symbol-drift`, which asks whether the anchor moved; it does not for
    `blank-line`, where the anchor is known to be wrong however close it is.
    """
    context = " ".join(lines[max(0, number - 4) : number])
    context += " " + lines[number - 1].split(f"#L{anchor})")[0]
    in_label = [n for n in IDENT.findall(label) + DOTTED.findall(label) if n not in NOT_A_SYMBOL]
    in_prose = [n for n in IDENT.findall(context) if n not in NOT_A_SYMBOL]
    for names, fields in ((in_label, True), (in_prose, False)):
        for name in reversed(names):
            if "." in name:
                defined = _dotted_definition(source, name)
            else:
                defined = definition_lines(source, name, fields=fields)
            if not defined:
                continue
            if len(defined) != 1:
                return None
            if near and abs(defined[0] - anchor) <= NEAR:
                return None
            return name, defined[0]
    return None


# A label writes a file as `runner.py`, which is a dotted name and is not a member of anything.
FILE_SUFFIXES = frozenset({"py", "md", "json", "jsonl", "toml", "txt", "yaml", "yml"})


def _names_a_file(name: str) -> bool:
    """Whether this backticked name is a filename rather than a symbol.

    A label writes the file as ``runner.py``, which is a dotted name and is not a member of
    anything, so it cannot be resolved and is not evidence that the label named nothing.
    """
    return name.rpartition(".")[2] in FILE_SUFFIXES


def _dotted_definition(source: list[str], name: str) -> list[int]:
    """Where ``Owner.member`` is defined in the cited file.

    ``Example.expected`` is the declaration inside ``class Example``. ``runner._node_outputs``
    names the module the citation already points at, so it is the plain definition of
    ``_node_outputs``. A class the file holds that does not hold the member resolves to
    nothing, rather than to a namesake elsewhere in the file.
    """
    owner, _, member = name.rpartition(".")
    if member in FILE_SUFFIXES:
        return []
    owner = owner.rsplit(".", 1)[-1]
    found = member_lines(source, owner, member)
    if found:
        return found
    holds_owner = re.compile(rf"^\s*class\s+{re.escape(owner)}\b")
    if any(holds_owner.match(line) for line in source):
        return []
    return definition_lines(source, member, fields=True)


def _symbol_drift(
    path: Path,
    number: int,
    lines: list[str],
    label: str,
    target: str,
    anchor: int,
    source: list[str],
) -> list[Problem]:
    """The citation's subject, where its one definition is somewhere else in the cited file.

    :func:`_subject_definition` is what decides which name that is and where it lives.
    """
    resolved = _subject_definition(lines, number, anchor, source, label, near=True)
    if resolved is None:
        return []
    name, line = resolved
    return [
        Problem(
            "symbol-drift",
            path,
            number,
            f"[{label}] points at line {anchor}, and `{name}` beside it is defined once "
            f"in that file, at line {line}. Move the anchor to {line}, or "
            f"stop naming `{name}` beside a citation that is about something else.",
            fix=(
                f"[{label}]({target}#L{anchor})",
                f"[{_relabel(label, line)}]({target}#L{line})",
            ),
        )
    ]


def _relabel(label: str, line: int) -> str:
    """``label`` with the line it states moved to ``line``, keeping the form it was written in.

    The replacement carries the closing backtick through, because the pattern matches it and a
    substitution that dropped it would leave the label unbalanced.
    """
    if not (stated := LABEL_LINE.search(label)):
        return label
    tail = "`" if stated.group(0).rstrip().endswith("`") else ""
    return LABEL_LINE.sub(f":{line}{tail}", label)


def _relative(document: Path, target: Path) -> str:
    """``target`` as a path a renderer of ``document`` can follow."""
    up = [".."] * len(document.parent.relative_to(REPO).parts)
    return "/".join([*up, str(target.relative_to(REPO))])


def collect(paths: list[Path] | None = None) -> list[Problem]:
    """Every problem in the checked documents, or in ``paths`` where given."""
    found: list[Problem] = []
    for entry in CHECKED:
        root = REPO / entry
        if not root.exists():
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*.md"))
        for document in files:
            if paths and not any(document == p or p in document.parents for p in paths):
                continue
            found.extend(check_file(document))
    return found


def apply(found: list[Problem]) -> int:
    """Rewrite what can be rewritten without a judgement. Returns how many were changed."""
    changed = 0
    for problem in found:
        if problem.fix is None:
            continue
        old, new = problem.fix
        text = problem.path.read_text(encoding="utf-8")
        if old not in text:
            continue
        problem.path.write_text(text.replace(old, new), encoding="utf-8")
        changed += 1
    return changed


def main(argv: list[str]) -> int:
    fix = "--fix" in argv
    paths = [Path(a).resolve() for a in argv if a != "--fix"] or None
    found = collect(paths)
    if fix and found:
        changed = apply(found)
        print(f"check_citations: rewrote {changed} citation(s); re-running")
        found = collect(paths)
    if not found:
        print("check_citations: clean")
        return 0
    for problem in found:
        print(problem.render())
    counts: dict[str, int] = {}
    for problem in found:
        counts[problem.kind] = counts.get(problem.kind, 0) + 1
    summary = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items()))
    print(f"check_citations: {len(found)} problem(s) — {summary}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
