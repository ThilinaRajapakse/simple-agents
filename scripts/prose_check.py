"""Checks the writing rules that can be checked mechanically.

Run over the whole repository::

    uv run python scripts/prose_check.py

Or over specific paths::

    uv run python scripts/prose_check.py src/simple_agents/nodes.py

The same checks run as part of the test suite. A line that trips a rule legitimately is
marked with ``# prose-ok: <reason>`` on the line itself or the line above, and the reason
stays visible in the source.

It also checks that references resolve: a `docs/*.md` path must name a file that exists, and
an `FT-nn` citation must name an entry defined in `docs/failure-taxonomy.md`, and a `§n`
reference must name a numbered heading in the document it points at.

And it checks the examples. Every fenced Python block in `docs/`, and every literal block
after a `::` in a library docstring, has to parse; every name it imports from the library has
to exist; and every keyword it passes to a library callable has to be one that callable takes.
A block opening with a shell command is prose for a terminal and is left alone.

Two things this cannot check:

1. Whether a clause explains a consequence to the reader or defends a design decision to the
   maintainer. That distinction stays in CLAUDE.md.
2. Whether an example that parses and resolves does what it says. Nothing here executes one,
   so an example that leaves out a node, or passes a value of the wrong shape, or shows an
   output the code no longer produces, passes every rule above. Running the example is what
   finds that, and `tests/test_labelling_pass.py` is what that looks like.
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Checked. `dev-docs/` and `CLAUDE.md` are not: recording rationale and rejected
# alternatives is what they are for.
CHECKED = ("src/simple_agents", "docs", "tests", "README.md", "CHANGELOG.md")

# Two files hold the banned constructions in order to find them: this one lists them, and
# `test_prose.py` fires each rule against one deliberate defect.
SKIP = {REPO / "scripts" / "prose_check.py", REPO / "tests" / "test_prose.py"}

# Files exempt from the second-person rule alone. A reference document describes the library to
# someone who has already chosen it; the landing page addresses someone who has not, and speaks
# to them directly. Every other rule applies to these files unchanged. `findings.py` writes the
# sentences `simple-agents view` leads with: a page whose reader is the builder, addressed the
# way the landing page addresses its reader.
ADDRESSES_THE_READER = {"README.md", "findings.py"}

OPT_OUT = re.compile(r"#\s*prose-ok:\s*\S")

# Superlatives and intensifiers. Each states a ranking or a degree instead of a fact.
INTENSIFIERS = (
    "the most precise",
    "the most important",
    "the whole point",
    "the only thing",
    "almost never",
    "almost always",
    "essentially every",
    "essentially all",
    "distinctive enough",
    "precisely what",
    "exactly what",
    "exactly the",
    "far more",
    "far better",
    "vastly",
    "dramatically",
    "enormously",
    "obviously",
    "clearly the",
    "of course",
    "needless to say",
)

# Constructions that defend a decision instead of describing behaviour.
DEFENSIVE = (
    "is not bureaucracy",
    "not a bug, it is",
    "worth noting",
    "it is worth",
    "note what is",
    "deliberately",
    "on purpose",
    "by design",
    "make no mistake",
    "the real question",
    "the entire mechanism",
    "that is the answer",
    # Dismissing a lesser reading to assert importance: "a stale cassette is a finding, not
    # an inconvenience". The shape `X, not Y` is not the tell, since most uses of it state a
    # fact ("the resampling unit is the example, not the rollout"). What marks these is that
    # Y is a judgement about how to regard the thing rather than a description of it, which
    # is a vocabulary rather than a grammar. New phrasings get added here as they are found.
    "not an inconvenience",
    "not a nicety",
    "not a formality",
    "not cosmetic",
    "not pedantry",
    "not a technicality",
    "not busywork",
    "not ceremony",
)

# Emphatic X-not-Y and narrative-about-people shapes.
EMPHATIC = re.compile(
    r"(?:^|\. |\*\*)[A-Z][\w\s`'-]{1,26}, not [\w\s`'-]{1,22}\."
    r"|before anyone (?:remembers|thinks|gets)"
    r"|nobody (?:remembers|measured|notices)"
    r"|one \w+ away from",
)

# Absence stated as a chain of negatives, and the epistemology that usually follows it.
# Thilina, 2026-08-28: *"Do not describe absence using chains of negative constructions. State
# the positive conclusion directly. Prefer 'X is unknown' over 'nothing says X'."* The page
# said "No tool names it and no step has recorded reaching it, so nothing here says what it
# holds", where the sentence is "Contents and direction unknown."
NEGATION_CASCADE = re.compile(
    # "nothing says what X is": the epistemology form.
    r"\bnothing (?:\w+ ){0,3}?(?:says|tells|reports|can say|knows) (?:what|which|whether|how)"
    # "no X names it ... so nothing/so the page cannot": the cascade.
    r"|\bno \w+ (?:names|declares|says|reports|records|has recorded)\b[^.]*?\bso (?:nothing|no |the \w+ cannot)"
    # "cannot say which ... so": the reasoning written out.
    r"|\bcannot say (?:what|which|whether)\b[^.]*?\bso\b",
    re.I,
)

# "Nobody does X" for a state that has a name. Thilina, 2026-08-29: *"Never use the
# construction 'Nobody does...', 'Nobody agreed...', 'Nobody saw...'. Why the fuck do you just
# not write what you mean plainly."* "A design nobody has agreed to" is "an unconfirmed
# design"; "Nobody opens a window; the reply lands in the outbox" is "The reply is saved to the
# outbox as a draft". The word on its own is left alone: `nobody` is one of the library's
# answerer values, and "answered by nobody" reports it.
NOBODY = re.compile(
    r"\b[Nn]obody (?:has|had|have|is|was|does|did|can|will|opens|agreed|agrees|saw|sees|"
    r"answered|answers|looked|looks|asked|asks|waits|waiting|recorded|records|reads|"
    r"acting|acts|attends|remembers|measured|notices)\b"
)

SECOND_PERSON = re.compile(r"\b(you|your|yours|you're|yourself)\b", re.I)
EM_DASH = "—"
# An internal document, or an id that only resolves inside one. A filename is the obvious
# form and the id is the one that got through: `DF4-D6` shipped in a docstring inside the wheel
# because the 2026-08-16 sweep searched for filenames alone.
INTERNAL_REF = re.compile(
    r"dev-docs|simple-agents\.md|\bplan\.md|\bhandoff\.md"
    r"|\bDF\d+-[A-Z]\d+\b|\bP3-\d+\b"
)

# One of our own runs, named in a file a builder reads. `dogfood #4` is development history
# and the reader has no way to look it up. Three instances got this far because the internal-id
# pattern above reads `P3-n` and `DF5-Inn` and a run named in prose matches neither: a comment
# in `conformance/artifacts.py`, a module docstring in `view/record.py`, and a sentence in
# `docs/tools.md` shipped on 2026-08-28 and caught by hand two hours later.
OWN_RUN = re.compile(r"\bdogfood[ -]#?\d+\b", re.I)

# A path on the machine this was written on. A username in a shipped file says who wrote it and
# points at a tree the reader does not have. An illustrative path with a placeholder name is
# not that, so the names below are permitted: `/home/x/library` is an example of two paths one
# prefix apart, and reads as one.
PLACEHOLDER_HOME = ("x", "you", "user", "username", "me", "alice", "bob", "name", "someone")
MACHINE_PATH = re.compile(r"/(?:home|Users)/([A-Za-z][\w.-]*)")

# Trees a builder does not receive. `tests/` is absent from the wheel, so a citation there is a
# pointer between two records the same reader holds. Every other rule still applies to it.
MAINTAINER_TREES = ("tests",)

# References that point at nothing. The docs are a prompt surface, so a reader following one
# of these finds no file and no entry, with nothing to recover from. The lookbehind keeps
# `dev-docs/plan.md` from reading as a reference to `docs/plan.md`.
DOC_REF = re.compile(r"(?<!dev-)\bdocs/(?:[\w.-]+/)*[\w.-]+\.md")
FT_REF = re.compile(r"\bFT-\d{2}\b")
TAXONOMY = REPO / "docs" / "failure-taxonomy.md"

# Section references, and the numbered headings they have to resolve against. A reference
# following a `docs/*.md` path on the same line is resolved against that document; a bare one
# inside a shipped document is resolved against the document it appears in.
SECTION_REF = re.compile(r"§(\d+(?:\.\d+)*)")
SECTION_HEADING = re.compile(r"^#{2,6}\s+(\d+(?:\.\d+)*)\.?\s", re.M)

# A class or function docstring longer than this is doing more than the five things
# CLAUDE.md allows. Module docstrings orient a reader and get more room.
# A sentence that counts a set the code knows the size of. "the six rates" was true until an
# evaluation reported eight, and the same sentence appeared in six places across `src/`, `docs/`
# and prompt text a coding agent executes. The definite article is what separates a total claim
# from an ordinary count: "the eight rates" is checked, "two rates that are averaged" is not.
NUMBER_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
    20: "twenty",
    21: "twenty-one",
    22: "twenty-two",
    23: "twenty-three",
    24: "twenty-four",
    25: "twenty-five",
    26: "twenty-six",
    27: "twenty-seven",
    28: "twenty-eight",
    29: "twenty-nine",
    30: "thirty",
    34: "thirty-four",
    35: "thirty-five",
    36: "thirty-six",
    37: "thirty-seven",
    38: "thirty-eight",
    39: "thirty-nine",
    40: "forty",
    41: "forty-one",
    42: "forty-two",
    43: "forty-three",
    44: "forty-four",
    45: "forty-five",
    46: "forty-six",
}

# noun -> what the code says the size is. A noun goes here only where every "the N <noun>" in a
# shipped file is a claim about that whole set: `entries` is not, since `docs/run-envelope.md`
# counts two of its own.
COUNTED = {
    "rates": lambda: len(_counts()["rates"]),
    "stages": lambda: len(_counts()["stages"]),
    "node kinds": lambda: 3,
    "decision kinds": lambda: len(_counts()["decision_kinds"]),
    "checks": lambda: len(_counts()["checks"]),
    "taxonomy entries": lambda: len(_counts()["taxonomy"]),
}

COUNT_PHRASE = re.compile(
    r"\bthe\s+([a-z-]+)\s+(" + "|".join(sorted(COUNTED, key=len, reverse=True)) + r")\b",
    re.I,
)

_COUNTED_CACHE: dict[str, object] = {}


def _counts() -> dict[str, object]:
    """The sets the library defines, read once."""
    if not _COUNTED_CACHE:
        from simple_agents.conformance.checks import CHECKS
        from simple_agents.conformance.decisions import DECISION_KINDS
        from simple_agents.conformance.stages import STAGES
        from simple_agents.conformance.taxonomy import taxonomy
        from simple_agents.evaluation.metrics import METRIC_DEFINITIONS

        _COUNTED_CACHE.update(
            rates=METRIC_DEFINITIONS,
            stages=STAGES,
            decision_kinds=DECISION_KINDS,
            checks=CHECKS,
            taxonomy=taxonomy(),
        )
    return _COUNTED_CACHE


def miscounted(line: str) -> list[tuple[str, str, int]]:
    """Every "the N <noun>" on one line where N is not what the code says.

    Returns the phrase, the noun, and the number the code holds.
    """
    found = []
    for said, noun in COUNT_PHRASE.findall(line):
        lowered = said.lower()
        if lowered not in NUMBER_WORDS.values():
            continue
        actual = COUNTED[noun.lower()]()
        if NUMBER_WORDS.get(actual) != lowered:
            found.append((f"the {said} {noun}", noun.lower(), actual))
    return found


MAX_DOCSTRING_LINES = 20
MAX_MODULE_DOCSTRING_LINES = 45

# Examples. A fenced block in Markdown declares its language; a docstring's literal block is
# whatever follows a line ending in `::`, which is the convention CLAUDE.md sets.
PY_FENCE = re.compile(r"^```(?:python|py)[^\n]*\n(.*?)^```", re.M | re.S)

# The docs show these at a terminal rather than in Python, and a literal block has no way to
# say which it is. A block opening with one of them is prose for a shell and is not parsed.
SHELL_COMMANDS = ("vllm", "simple-agents", "uv", "pip", "python", "git")

# The modules an example may import from, resolved once so a name can be checked against what
# the library actually exports.
LIBRARY_MODULES = (
    "simple_agents",
    "simple_agents.evaluation",
    "simple_agents.builtins",
    "simple_agents.conformance",
    "simple_agents.adapters",
)

HINTS = {
    "em_dash": "Em-dash. Use a comma, a colon, a full stop, or brackets.",
    "second_person": "Second person. Write in the third person.",
    "internal_ref": (
        "Reference to an internal document. The reader has no access to dev-docs, "
        "plan.md, handoff.md or simple-agents.md. Cite docs/ files and FT-ids instead."
    ),
    "own_run": (
        "Names one of our own runs. A dogfood is development history, and the reader cannot "
        "look it up. State what it showed without the run: 'a run that met 736 rate limits' "
        "rather than 'dogfood #5 met 736 of them'. The record belongs in dev-docs/."
    ),
    "machine_path": (
        "A path on the machine this was written on. It names whoever wrote it and points at a "
        "tree the reader does not have. Use a relative path, or a placeholder home such as "
        "`/home/user/project`."
    ),
    "unanchored_section": (
        "Section reference naming no document. \u00a76.2 of which file? Write the "
        "`docs/*.md` path beside it, on the same line or the line above."
    ),
    "intensifier": "Superlative or intensifier. State the rule; the reader can judge it.",
    "miscount": (
        "Counts a set the code defines, and the number is not what the code holds. The same "
        "sentence is usually written in several files, so correct every copy: grep for the "
        "noun. A count that is deliberately local reads 'two of the rates' rather than "
        "'the two rates'."
    ),
    "defensive": "Defends a decision instead of describing behaviour.",
    "negation_cascade": (
        "Absence written as a chain of negatives. State the positive conclusion: 'X is "
        "unknown' rather than 'nothing says X', 'X is undeclared' rather than 'no step has "
        "declared X'. One short declarative sentence, and no account of the reasoning that "
        "reached it."
    ),
    "emphatic": (
        "Emphatic construction or narrative about people failing. Describe the mechanism."
    ),
    "nobody": (
        "'Nobody does X' for a state that has a name. Say the state: 'unconfirmed', "
        "'unanswered', 'unrecorded', 'not investigated'. 'Nobody opens a window; the reply "
        "lands in the outbox' is 'The reply is saved to the outbox as a draft'."
    ),
    "aphorism": (
        "Bolded standalone sentence in a docstring reads as an aphorism. Write the "
        "mechanism instead."
    ),
    "missing_doc": (
        "Reference to a shipped document that does not exist. Point at a file in docs/, or "
        "write the document."
    ),
    "unknown_ft": (
        "Reference to a taxonomy entry that is not in docs/failure-taxonomy.md. IDs are "
        "permanent and never reused, so a citation that resolves to nothing is a typo or a "
        "missing entry."
    ),
    "missing_section": (
        "Section reference that resolves to no heading in the document it names. A reader "
        "following it finds nothing. Cite the section that carries the fact, and name the "
        "document unless the reference is inside it."
    ),
    "unparseable_example": (
        "Example that is not valid Python. An example is what a coding agent copies, so one "
        "that does not parse costs more than no example. Write an elision as a value: a "
        "second dict entry rather than `...`, and the arguments a call needs rather than "
        "`...` after a keyword."
    ),
    "unknown_name": (
        "Example imports a name the library does not export. A reader following it gets an "
        "ImportError. Import the name the library has, or drop the line."
    ),
    "unknown_module": (
        "Example imports from a module the library does not have. A reader following it gets "
        "a ModuleNotFoundError. Import from where the thing lives now, or drop the line."
    ),
    "unknown_role_target": (
        "A :class:/:func:/:meth:/:mod:/:data: reference names something that does not "
        "resolve, absolutely or in this module. A rendered docstring links it to nothing. "
        "Name the thing as it is defined today."
    ),
    "unknown_argument": (
        "Example passes an argument the callable does not take. A reader following it gets a "
        "TypeError. Pass the parameter the signature has; an example is checked against the "
        "code, not against what the code used to be."
    ),
    "long_docstring": (
        f"Too much prose ({MAX_DOCSTRING_LINES} lines, {MAX_MODULE_DOCSTRING_LINES} for a "
        "module; example blocks after `::` do not count). A docstring says what the thing is, "
        "what it does and what the caller supplies, what it returns, how to use it, and "
        "what happens when it is used wrongly. Anything else belongs in dev-docs/.\n"
        "  Trim it. Cut what the reader can get elsewhere: what another docstring already "
        "says, what the code below says in the same words, and what a type or a cited name "
        "carries.\n"
        "  Whether the unit wants decomposing is a separate question, but this is a good "
        "point to ask that question. Judge based on SE principles, not based on convenience. "
        "A long docstring is sometimes a signal that the unit does more than one thing, and "
        "scripts/shape_check.py is what reports the size of the unit itself."
    ),
}


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    rule: str
    text: str

    def render(self) -> str:
        rel = self.path.relative_to(REPO)
        return f"{rel}:{self.line}\n  {self.text.strip()[:96]}\n  {HINTS[self.rule]}\n"


def known_ft_ids() -> set[str]:
    """Every entry id defined in the taxonomy, read from its section headings."""
    if not TAXONOMY.exists():
        return set()
    return set(re.findall(r"^### (FT-\d{2}):", TAXONOMY.read_text(encoding="utf-8"), re.M))


_SECTIONS: dict[Path, set[str]] = {}


def sections_of(path: Path) -> set[str]:
    """The numbered section headings a document defines, as strings such as ``4.1.2``."""
    if path not in _SECTIONS:
        if not path.exists() or path.suffix != ".md":
            _SECTIONS[path] = set()
        else:
            found = SECTION_HEADING.findall(path.read_text(encoding="utf-8"))
            _SECTIONS[path] = set(found)
    return _SECTIONS[path]


def _unresolved_sections(lines: list[str], index: int, path: Path, subject: Path | None) -> bool:
    """Whether any ``§n`` on this line names a section its target does not define.

    A reference is attributed to the nearest ``docs/*.md`` path before it on the line, then to
    the document it sits in. A source file has neither, so its fallback is a path on either of
    the two lines above, which is where a wrapped sentence puts one, then its subject document.
    """
    line = lines[index]
    docs = [(m.end(), REPO / m.group(0)) for m in DOC_REF.finditer(line)]
    if path.suffix == ".md":
        fallback = path if "docs" in path.parts else None
    else:
        fallback = _section_target(lines, index, subject)

    for ref in SECTION_REF.finditer(line):
        target = fallback
        for end, candidate in docs:
            if end <= ref.start():
                target = candidate
        if target is None or not target.exists():
            continue
        if ref.group(1) not in sections_of(target):
            return True
    return False


def subject_document(path: Path, text: str) -> Path | None:
    """The one document a source file's references resolve against, or ``None``.

    A module docstring naming exactly one ``docs/*.md`` states what the file is about, and
    every bare ``\u00a7n`` below it reads against that. `tests/test_trajectory_conformance.py`
    anchors twenty-nine references that way in one sentence. Naming two documents anchors
    nothing, since a reference could mean either.
    """
    if path.suffix != ".py":
        return None
    try:
        module = ast.get_docstring(ast.parse(text)) or ""
    except SyntaxError:
        return None
    named = set(DOC_REF.findall(module))
    return REPO / named.pop() if len(named) == 1 else None


# Any markdown path, which is what anchors a section reference. `DOC_REF` is narrower on
# purpose: it is the set whose sections this resolves against.
ANY_DOC = re.compile(r"[\w./-]+\.md")


def _section_window(lines: list[str], index: int) -> str:
    """The line a reference sits on and the two above it, which is where a wrap puts a path."""
    return "\n".join(lines[max(0, index - 2) : index + 1])


def _section_target(lines: list[str], index: int, subject: Path | None) -> Path | None:
    """The ``docs/`` document a ``\u00a7n`` on this line resolves against, or ``None``."""
    found = DOC_REF.findall(_section_window(lines, index))
    return REPO / found[-1] if found else subject


def _section_anchored(lines: list[str], index: int, subject: Path | None, maintainer: bool) -> bool:
    """Whether a reader can tell which document a ``\u00a7n`` belongs to.

    Any markdown path names one. A maintainer tree may name an internal record instead, since
    the reader of `tests/` holds `dev-docs/` and a build log's own sections are cited there.
    """
    window = _section_window(lines, index)
    if subject is not None or ANY_DOC.search(window):
        return True
    return maintainer and bool(INTERNAL_REF.search(window))


def _unanchored_section(
    lines: list[str], index: int, path: Path, subject: Path | None, maintainer: bool
) -> bool:
    """Whether a ``\u00a7n`` in source names no document a reader can open.

    A ``.md`` file under ``docs/`` anchors its own bare references and is not read here.
    """
    if path.suffix != ".py" or not SECTION_REF.search(lines[index]):
        return False
    return not _section_anchored(lines, index, subject, maintainer)


def _excused(lines: list[str], index: int) -> bool:
    """True when this line or the one above carries an opt-out marker."""
    if OPT_OUT.search(lines[index]):
        return True
    return index > 0 and OPT_OUT.search(lines[index - 1]) is not None


def check_file(path: Path, *, builder_facing: bool) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: list[Violation] = []

    def add(i: int, rule: str) -> None:
        if not _excused(lines, i):
            found.append(Violation(path, i + 1, rule, lines[i]))

    ft_ids = known_ft_ids()
    maintainer_surface = any(tree in path.parts for tree in MAINTAINER_TREES)
    subject = subject_document(path, text)

    for i, line in enumerate(lines):
        lowered = line.lower()
        if builder_facing:
            if EM_DASH in line:
                add(i, "em_dash")
            if SECOND_PERSON.search(line) and path.name not in ADDRESSES_THE_READER:
                add(i, "second_person")
            if INTERNAL_REF.search(line) and not maintainer_surface:
                add(i, "internal_ref")
            # The changelog is exempt for the reason it is exempt from `miscount` below: an
            # entry says what was true at a release, and the run a change came out of is part
            # of that record rather than a claim about the library now.
            if OWN_RUN.search(line) and not maintainer_surface and path.name != "CHANGELOG.md":
                add(i, "own_run")
            if any(who.lower() not in PLACEHOLDER_HOME for who in MACHINE_PATH.findall(line)):
                add(i, "machine_path")
        # A changelog holds counts that are not claims about the library now: it says what was
        # true at a release, and correcting one would falsify the history.
        if path.name != "CHANGELOG.md":
            for _phrase, _noun, _actual in miscounted(line):
                add(i, "miscount")
        for ref in DOC_REF.findall(line):
            if not (REPO / ref).exists():
                add(i, "missing_doc")
        for ft in FT_REF.findall(line):
            if ft_ids and ft not in ft_ids:
                add(i, "unknown_ft")
        if _unanchored_section(lines, i, path, subject, maintainer_surface):
            add(i, "unanchored_section")
        elif _unresolved_sections(lines, i, path, subject):
            add(i, "missing_section")
        if any(word in lowered for word in INTENSIFIERS):
            add(i, "intensifier")
        if any(word in lowered for word in DEFENSIVE):
            add(i, "defensive")
        if EMPHATIC.search(line):
            add(i, "emphatic")
        if NOBODY.search(line):
            add(i, "nobody")
        if NEGATION_CASCADE.search(line):
            add(i, "negation_cascade")

    if path.suffix == ".py":
        found.extend(_check_docstrings(path, text, lines))
    else:
        for line_number, source in _markdown_examples(text):
            found.extend(_check_example(path, line_number, source))
    return found


_LIBRARY: dict[str, object] | None = None


def library_names() -> dict[str, object]:
    """Every name the library exports, for checking that an example names real things.

    Resolved once. An import that fails leaves the table empty and every example check passes,
    so a broken package reports as a broken package rather than as a hundred bad examples.
    """
    global _LIBRARY
    if _LIBRARY is None:
        import importlib

        found: dict[str, object] = {}
        for name in LIBRARY_MODULES:
            try:
                module = importlib.import_module(name)
            except Exception:
                return {}
            for exported in getattr(module, "__all__", ()):
                found.setdefault(exported, getattr(module, exported, None))
        _LIBRARY = found
    return _LIBRARY


def _markdown_examples(text: str) -> list[tuple[int, str]]:
    """Every fenced Python block, with the line its fence opens on."""
    return [(text[: m.start()].count("\n") + 2, m.group(1)) for m in PY_FENCE.finditer(text)]


def _docstring_examples(doc: str) -> list[str]:
    """Every literal block in a docstring: what follows a line ending in `::`, indented."""
    import textwrap

    lines = doc.split("\n")
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        if not lines[index].rstrip().endswith("::"):
            index += 1
            continue
        start = index + 1
        while start < len(lines) and not lines[start].strip():
            start += 1
        if start >= len(lines):
            break
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = start
        block: list[str] = []
        while end < len(lines):
            line = lines[end]
            if not line.strip():
                block.append("")
            elif len(line) - len(line.lstrip()) >= indent:
                block.append(line)
            else:
                break
            end += 1
        source = textwrap.dedent("\n".join(block)).strip("\n")
        if source.strip():
            blocks.append(source)
        index = end
    return blocks


def _is_shell(source: str) -> bool:
    first = source.lstrip().split("\n", 1)[0]
    return first.split(" ", 1)[0] in SHELL_COMMANDS


def _check_example(path: Path, line: int, source: str) -> list[Violation]:
    """One example block: that it parses, and that every library name in it is real."""
    if _is_shell(source):
        return []
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [Violation(path, line, "unparseable_example", f"{exc.msg}: {exc.text or ''}")]
    return _check_names(path, line, tree)


def _check_names(path: Path, line: int, tree: ast.AST) -> list[Violation]:
    """Imports resolve, and a keyword passed to a library callable is one it takes.

    Only names the library exports are checked. An example calls the project's own functions
    too, and those exist in the project rather than here.
    """
    import importlib
    import inspect

    known = library_names()
    if not known:
        return []

    found: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("simple_agents"):
            try:
                module = importlib.import_module(node.module or "")
            except Exception:
                # The package itself importing is what separates a stale example from a
                # broken environment: `simple_agents.reporting` sat in an example for a
                # module retired weeks earlier, and the silent skip here is what let it.
                if library_names():
                    found.append(Violation(path, line, "unknown_module", node.module or ""))
                continue
            for alias in node.names:
                if alias.name != "*" and not hasattr(module, alias.name):
                    found.append(
                        Violation(path, line, "unknown_name", f"{node.module}.{alias.name}")
                    )
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        target = known.get(node.func.id)
        if target is None or not (inspect.isclass(target) or inspect.isfunction(target)):
            continue
        try:
            parameters = inspect.signature(target).parameters
        except (TypeError, ValueError):
            continue
        if any(p.kind is p.VAR_KEYWORD for p in parameters.values()):
            continue
        for keyword in node.keywords:
            if keyword.arg is not None and keyword.arg not in parameters:
                found.append(
                    Violation(
                        path,
                        line,
                        "unknown_argument",
                        f"{node.func.id}({keyword.arg}=...); it takes "
                        f"{', '.join(p for p in parameters if p != 'self')}",
                    )
                )
    return found


def _prose_only(doc_lines: list[str]) -> list[str]:
    """Docstring lines excluding indented example blocks.

    Examples do not count toward the length limit. The limit is on how much prose a
    docstring carries, and a usage example is the most useful thing in it.
    """
    out: list[str] = []
    in_block = False
    for raw in doc_lines:
        if raw.rstrip().endswith("::"):
            in_block = True
            out.append(raw)
            continue
        if in_block:
            if raw.strip() == "":
                continue
            if raw.startswith((" ", "\t")):
                continue
            in_block = False
        out.append(raw)
    return out


ROLE = re.compile(r":(?:mod|class|func|meth|data|attr):`~?([\w.]+)`")

_RESOLVED_ROLES: dict[tuple[str, str], bool] = {}


def _module_name(path: Path) -> str | None:
    """The importable module a source file is, or ``None`` where it is not one."""
    try:
        parts = path.resolve().relative_to(REPO / "src").with_suffix("").parts
    except ValueError:
        return None
    if parts[-1] == "__init__":
        parts = parts[:-1]
    if parts and parts[-1] == "__main__":
        return None
    return ".".join(parts)


def _role_resolves(target: str, modname: str | None) -> bool:
    """Whether a docstring role's target names something that exists.

    Tried absolutely, under ``simple_agents.``, and against the docstring's own module the
    way a Sphinx default role resolves, including a bare method name on any of the module's
    classes. Cached: one docstring names a target as often as it likes.
    """
    import importlib
    import inspect

    key = (target, modname or "")
    if key in _RESOLVED_ROLES:
        return _RESOLVED_ROLES[key]
    parts = target.split(".")
    ok = False
    for candidate in (target, f"simple_agents.{target}"):
        pieces = candidate.split(".")
        for cut in range(len(pieces), 0, -1):
            try:
                obj = importlib.import_module(".".join(pieces[:cut]))
            except Exception:
                continue
            try:
                for rest in pieces[cut:]:
                    obj = getattr(obj, rest)
                ok = True
            except AttributeError:
                continue
            break
        if ok:
            break
    if not ok and modname is not None:
        try:
            own = importlib.import_module(modname)
        except Exception:
            own = None
        if own is not None:
            obj = own
            good = True
            for rest in parts:
                if hasattr(obj, rest):
                    obj = getattr(obj, rest)
                else:
                    good = False
                    break
            if good:
                ok = True
            else:
                for _, cls in inspect.getmembers(own, inspect.isclass):
                    obj, good = cls, True
                    for rest in parts:
                        if hasattr(obj, rest):
                            obj = getattr(obj, rest)
                        else:
                            good = False
                            break
                    if good:
                        ok = True
                        break
    _RESOLVED_ROLES[key] = ok
    return ok


def _role_violations(path: Path, lines: list[str]) -> list[Violation]:
    """Every docstring role whose target resolves to nothing.

    Checked only while the library itself imports, for the reason example checking is: a
    broken package reports as a broken package rather than as a hundred bad references.
    """
    if not library_names():
        return []
    modname = _module_name(path)
    found: list[Violation] = []
    for index, line in enumerate(lines):
        for target in ROLE.findall(line):
            if not _role_resolves(target, modname):
                found.append(Violation(path, index + 1, "unknown_role_target", target))
    return found


def _check_docstrings(path: Path, text: str, lines: list[str]) -> list[Violation]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    found: list[Violation] = []
    found.extend(_role_violations(path, lines))
    targets = [tree] + [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for node in targets:
        doc = ast.get_docstring(node)
        if not doc:
            continue
        line = getattr(node, "lineno", 1)
        body = node.body[0]
        line = getattr(body, "lineno", line)

        for source in _docstring_examples(ast.get_docstring(node, clean=False) or ""):
            found.extend(_check_example(path, line, source))

        doc_lines = doc.splitlines()
        limit = MAX_MODULE_DOCSTRING_LINES if isinstance(node, ast.Module) else MAX_DOCSTRING_LINES
        # The count reported is the one checked. Reporting the docstring's whole length
        # against a limit on its prose sends a reader counting the wrong lines.
        prose = _prose_only(doc_lines)
        if len(prose) > limit and not _excused(lines, line - 1):
            found.append(Violation(path, line, "long_docstring", f"{len(prose)} lines of prose"))
        for text_line in doc_lines:
            stripped = text_line.strip()
            if (
                stripped.startswith("**")
                and stripped.endswith("**")
                and stripped.count("**") == 2
                and " " in stripped
                and not _excused(lines, line - 1)
            ):
                found.append(Violation(path, line, "aphorism", stripped))
    return found


def collect(paths: list[Path] | None = None) -> list[Violation]:
    found: list[Violation] = []
    for entry in CHECKED:
        root = REPO / entry
        if not root.exists():
            continue
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for f in files:
            if f.suffix not in {".py", ".md"} or "__pycache__" in f.parts or f in SKIP:
                continue
            if paths and not any(f == p or p in f.parents for p in paths):
                continue
            found.extend(check_file(f, builder_facing=True))
    return found


def main(argv: list[str]) -> int:
    paths = [Path(a).resolve() for a in argv] or None
    found = collect(paths)
    if not found:
        print("prose_check: clean")
        return 0
    for v in found:
        print(v.render())
    print(f"prose_check: {len(found)} violation(s)")
    print("Mark a legitimate use with `# prose-ok: <reason>` and state the reason.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
