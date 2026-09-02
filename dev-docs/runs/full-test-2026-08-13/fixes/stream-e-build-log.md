# Stream E: the conformance suite, the CLI, the README

Fixes for the ten items in the stream brief, drawn from
[`area-i-conformance-cli-packaging.md`](../findings/area-i-conformance-cli-packaging.md) and the
`FLAG-2`, `FLAG-3`, `FLAG-6`, `FLAG-7` and `FLAG-8` rows of
[`area-g-model-clients.md`](../findings/area-g-model-clients.md) G-1.

Files touched: `src/simple_agents/cli/main.py`, `src/simple_agents/conformance/{artifacts,brief,checks}.py`,
`README.md`, `docs/conformance.md`, `docs/failure-taxonomy.md`,
`tests/{test_procedure,test_conformance,test_readme}.py`. `docs/procedure.md` was **not** touched,
so its word budget is where it was.

---

## 1. `init` wrote a note naming a path the layout did not have

`AGENTS_NOTE` was one constant naming `.agents/skills/simple-agents/SKILL.md` whatever `--claude`
or `--to` put on disk. Two of the four flag combinations wrote a dead path, and the README's own
quick start offers one of them on its second line.

The note is now built from the path this run of `init` registered at:
[`cli.py` `agents_note`](../../../../src/simple_agents/cli/main.py#L63). `_init` computes
`skill = (into / SKILL_NAME / "SKILL.md").as_posix()` from the same `into` that decided the
target, so the two cannot disagree.

**Why a function rather than a `str.format` on the constant.** The note is public enough that a
project might want to write it itself, and a callable with a docstring carrying the example is
what the writing rules ask for on anything a caller constructs. It is not exported from
`simple_agents/__init__.py`; `simple_agents.cli.agents_note` is where it lives.

## 2. `init` skipped the note when the file said `simple-agents` anywhere

The test was `SKILL_NAME not in note.read_text()`, a substring search over the whole file. The
README's install line, `uv add simple-agents`, satisfies it, so a project that pasted the README
got no pointer and nothing was printed about it.

Detection is now on the note's own heading, `## Simple Agents`, and three cases are separated in
[`cli.py` `_note`](../../../../src/simple_agents/cli/main.py#L591):

| The file | What happens |
|---|---|
| does not exist | written |
| carries the note, naming this path | left alone, and the command says so |
| carries the note, naming another path | the section is replaced, and the text below it is kept |
| carries no note | appended |

**The replace case is what makes running `init --claude` after `init` correct.** Without it a
project that moved harness ends up with two notes or one stale one.
[`_replaced_note`](../../../../src/simple_agents/cli/main.py#L620) takes the section from the heading to
the next heading at the same level or above, so a project's own `## House rules` below it
survives.

## 3. A second `init` exited 0 when it refused

Now exits 1, and the refusal goes to stderr rather than stdout: a command that did not do what
was asked did not succeed, and the message is not part of its output.

It also no longer returns before the AGENTS.md step. The refusal is about the skill directory,
and the pointer is a separate file, so a project whose AGENTS.md was deleted gets it back from a
re-run. The module docstring records the exit status beside `check`'s.

## 4. `_place`'s docstring claimed the symlink survives a clone

It said "relative so a project that commits it survives being cloned elsewhere". The link is
relative and resolves out of the project into site-packages, so a clone made without that
environment holds a dangling SKILL.md. Relative helps only where project and environment move
together. The docstring now says what the link points into and names `--copy` as the flag that
puts the bytes in the project.

**Behaviour unchanged.** The default is still a symlink, because tracking the installed version
is what it is for.

## 5. Counts that disagreed with the list beside them

| Where | Was | Now |
|---|---|---|
| [`checks.py` `_first_malformed`](../../../../src/simple_agents/conformance/checks.py#L310) | "and the four are" then five record types | "and the record types are", with no count |
| [`brief.py` `_entry`](../../../../src/simple_agents/conformance/brief.py#L321) | "the three stages are" then four | "the four stages are" |
| `docs/conformance.md` §3 | four `pass` rows, "3 passed", FT-30 absent | the real output of the suite over the `no-evaluation` fixture |
| `docs/conformance.md` §4 | "the five the library enforces" | six, each named with its `FT-nn` |
| `README.md` | "28 characteristic failures", "four record types" | 30 and five |

**Two different repairs, chosen per case.** Where the list is joined from a collection at runtime
the count is removed, because nothing re-derives it and a record type added to the format would
make it wrong again. Where the list is a fixed four the count is corrected and a test pins it
against `len(STAGES)`, because "the four stages" reads better than "the stages" and the pin costs
one assertion.

**The sample report is now generated rather than transcribed.**
`TestTheSampleReportIsWhatTheSuitePrints` runs the suite over `tests/fixtures/projects/no-evaluation`,
substitutes the project root and the run directory, and compares the block line for line. The
docstring says how to regenerate it. This is the same shape as `tests/test_sample_report.py`,
which pins `docs/evaluation.md` §8.1.

## 6. `questions --stage` omitted `brainstorm`

The help is now built from `STAGES` rather than transcribed, so a stage added later appears
without anything being remembered. The refusal named no stage at all, which was the one refusal
in the suite that did not say what to write instead; it now names the four in order and says that
each includes the ones before it.

## 7. FT-04's message sent the reader to the manifest

`_absence_waived` reads `config.nodes` in the **results file**. The manifest carries the same
entries, so the claim was not false about where the value is recorded, and it was wrong about
what the check opens: a reader acting on it would edit or inspect a file the check never reads.
The message now names `config.nodes` in the results file, and says `allow_unknown=False` sits on
every node that calls a model rather than "on the output schema". `docs/conformance.md` §2.5
carried the same misdirection and is corrected with it.

## 8. The README's unresolved editorial material

**Removed, because it renders:**

- Line 95's `<what does this provide?>`, in visible prose. Replaced with what the class provides,
  which is unambiguous from FT-19 and FT-20: it is what an evaluation reads before running a tool
  many times over, and a run over a spending or irreversible tool is refused.
- The empty `## Cassettes and Replays` heading. **The heading is gone and Thilina's note asking
  for the section is left exactly where it was**, so the request survives and the broken render
  does not.
- A bare `##` on line 5, between the summary and the pre-alpha banner, which rendered as an empty
  h2. Not in the brief; found by the heading test.

**Resolved, because the shipped documents answer it unambiguously:** the note asking how API keys
are stored and managed. `docs/model-clients.md` carries a Credentials row naming
`MISTRAL_API_KEY`, `GEMINI_API_KEY` and none for a local server, and the note itself says a
pointer is enough. One sentence added, the note removed.

**Left in place for Thilina, quoted verbatim in the stream report:** the six per-feature review
notes under "What the library provides", the section-level note above them, the note about
listing more providers as they land, the note asking for a cassettes section, and the note
explaining why "What is built" is commented out. Every one of them asks for a change of tone or
of framing across a whole section, which is his call rather than a defect to repair.

## 9. The quick start

**The install line is left as it is and the banner now says why it does not resolve.** The
package is not published, `https://pypi.org/pypi/simple-agents/json` answers 404, and inventing
an install line that works today would be a claim about how the library is distributed that
nobody has made.

**This one is put to Thilina rather than settled here.** `random-thoughts-questions.md`, Thilina's
Corner, says builder-facing docs are written for the released library and not for the current
state of development. The pre-alpha banner is the one line in the README whose subject *is* the
current state, and it already carries "nothing is stable, and no project should depend on this
yet", so a second clause about distribution sits in the same sentence and leaves the install line
written for release. That is a reading of the rule, not a ruling.

- Was: `> **Pre-alpha. Under construction, nothing is stable, and no project should depend on
  this yet.**`
- Now: `> **Pre-alpha. Under construction, nothing is stable, and no project should depend on
  this yet. The package is not published to an index, so the install line below is what it will
  be rather than what resolves today.**`
- Reverting is one edit and fails no test.

**The first agent keeps `MistralClient`, and now names the credential it reads.** A reader has an
API key before they have a server, so the snippet names a hosted backend, and the environment
variable belonged beside it rather than sixty lines below. The repository's own Mistral
credential answers 402, which is an account state rather than a library one; the identical
snippet on `GeminiClient` printed `answer: Paris` from the wheel.

**`result.cost`'s comment described a run the snippet does not make.** The snippet declares no
cost basis, so the field comes back with no value and a reason. The comment now says that, and a
sentence below the block says where a basis is declared.

## 10. FT-29 accepted the section heading only with a comma

`IDEA_SECTIONS` held `Where this is going, and where it is not`. `docs/procedure.md` and FT-29
both write it without the comma, and `_heading_key` stripped punctuation only at the edges, so a
project copying the heading out of either document failed a check for a comma it was never told
to write.

**Both sides moved.** `IDEA_SECTIONS` now spells it the way the documents spell it, which is what
the failure message prints back at a project. And `_heading_key` reduces a heading to its words,
so punctuation and spacing cannot fail a match at all, and both spellings pass. The conforming
fixture still carries the comma form and still passes, which is what exercises the tolerance.

A test asserts every one of the five sections appears verbatim in both `docs/procedure.md` and
`docs/failure-taxonomy.md`, so the two cannot drift apart again.

---

## Verification

Everything below ran against the wheel built from this working tree and installed into
`qa-venv`, through its console script.

| What | Result |
|---|---|
| `init --claude`, `--to`, `--copy`, default | note names the path that exists, in all four |
| `init` over an AGENTS.md holding `uv add simple-agents` | note appended, install line kept |
| second `init` | exit 1, refusal on stderr |
| second `init` after AGENTS.md was deleted | exit 1, AGENTS.md written |
| `init --claude --force` after `init` | one note, pointing at `.claude/…`, `## House rules` kept |
| `questions --stage bogus` | exit 2, names the four in order |
| `questions --stage brainstorm --json` | 13 questions, 8 required |
| the conforming fixture | 11 passed, exit 0 |
| the conforming fixture, heading rewritten without the comma | 11 passed |
| the `no-evaluation` fixture | byte-identical to `docs/conformance.md` §3 after the two path substitutions |
| FT-04 provoked | prints the corrected message |
| FT-13 provoked with an invented `record_type` | lists five types, spells no count |

**A scratch project built from the documents, not from the fixture.** `agent.py` with one
`LLMNode`, an `ExampleSet` of four examples over two splits with one held-out example expecting
absence, `contamination_threshold=0.9`, `idea.md` written with the five headings as the documents
spell them, and `brief.toml` written from `simple-agents questions --stage measure --json` and
`--decisions --json`. One run by hand and an evaluation at k=3 against the vLLM server on 8002
serving `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit`. `simple-agents check` from the wheel:
**11 passed, exit 0**.

**Mistral could not be exercised.** The credential answers 402 to a bare completion
(`Check your subscription on https://admin.mistral.ai/subscription`), which the adapter reports
as a `CallerFacingError` naming the status and the URL. Gemini stood in for the hosted path.

`uv run pytest tests/ -q` passed whole (1931 passed, 2 skipped) on a run taken between other
streams' edits. Later runs in the same working tree show failures in
`test_semantic_search.py`, `test_builtin_tools.py`, `test_suspension_integration.py`,
`test_url_cache.py`, and `test_prose.py` over `src/simple_agents/builtins/`, none of them in a
file this stream owns. `tests/{test_readme,test_conformance,test_procedure,test_packaging}.py`
pass, 280 of them, and `scripts/prose_check.py` is clean over every file this stream touched.

### The CHANGELOG block, for the lead

```markdown
### Fixed

- **`simple-agents init` wrote a pointer to a path the project did not have.** The AGENTS.md note
  was one constant naming `.agents/skills/simple-agents/SKILL.md`, so `--claude` and `--to` each
  registered the skill in one place and told the coding agent to read it from another. The note
  now names the path the skill went to. Running `init` again with a different flag moves the
  pointer rather than adding a second one, and a project's own text below it is kept.

- **`init` wrote no pointer at all when AGENTS.md said `simple-agents` anywhere.** The test was a
  substring search over the whole file, which the README's own `uv add simple-agents` satisfies,
  so a project that pasted the install line got no pointer and no message about it. Detection is
  now on the note's own heading.

- **A second `simple-agents init` exited 0 while refusing to do anything.** It exits 1, prints the
  refusal on stderr, and no longer skips the AGENTS.md step, so a project whose AGENTS.md was
  deleted gets it back from a re-run.

- **Five counts that disagreed with the list printed beside them.** FT-13's reason said "the four
  are" and listed five record types; a deferral to a non-stage said "the three stages are" and
  listed four; `docs/conformance.md` §3's sample report showed ten of the eleven checks and
  counted three passes out of four `pass` rows; §4 said the library enforces five entries by
  construction where six say so, the sixth being FT-23; and `README.md` said the taxonomy holds 28
  entries and the trajectory format four record types, where they hold 30 and five. The sample
  report is now generated from a fixture and compared line for line, and each remaining count is
  pinned to what it counts.

- **`simple-agents questions --stage` did not know about `brainstorm`.** The help named three of
  the four stages and the refusal named none, though `brainstorm` ships 13 questions of which 8
  are required and is the stage `docs/procedure.md` opens at. Both are now built from the stage
  list.

- **FT-04's failure message sent the reader to the manifest.** The check reads `config.nodes` in
  the evaluation's results file, and `allow_unknown=False` sits on a node rather than on the
  output schema. The message and `docs/conformance.md` §2.5 now say both.

- **FT-29 accepted `idea.md`'s fourth section heading only with a comma in it, which no document
  writes.** `docs/procedure.md` and the taxonomy both give it as "where this is going and where it
  is not", so a project following them failed the check. Heading matching now ignores punctuation
  and spacing, and the section list is spelled the way the documents spell it.

- **`_place`'s docstring said a committed symlink survives a clone.** It resolves into the
  environment simple-agents is installed in, so a clone made without that environment holds a
  dangling `SKILL.md`. The docstring says so, and names `--copy`.

- **The README shipped an unanswered editorial question in visible prose**, an empty
  `## Cassettes and Replays` heading, and a bare `##`. The first agent's snippet now names the
  environment variable its backend reads, and its `result.cost` comment describes what a run with
  no declared cost basis returns. The pre-alpha banner says the package is not on an index yet.
```

## What this stream did not do

- **The tone of "What the library provides".** Six review notes ask for it and each is a
  section-level rewrite. Surfaced rather than answered.
- **The cassettes section the README asks for.** Same reason.
- **Whether a skill installer follows a symlinked skill directory.** The docstring now says what
  the link points into; whether Claude Code resolves a symlinked `SKILL.md` was not exercised
  here either.
- **Windows and macOS.** `_place` still falls back from symlink to copy on `OSError`, and only
  the Linux path was taken.
