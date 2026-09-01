# Build log — the builder quickstart

`plan.md` §1 P3-65. Started 2026-09-01, built and approved the same day.

## 1. Before any design

- `README.md` held the install commands under `## Quick start` and nothing else there: no path
  from install to a first run, and `simple-agents view` appeared in the documentation table
  alone, never in prose.
- `docs/index.md` fronts the documents for the coding agent; the builder had no walkthrough.
- `tests/test_readme_first_agent.py` executes the README's first-agent block, so the example a
  walkthrough would point at already runs under test.

## 2. Design

From Thilina, 2026-09-01: *"I think we need a quickstart for a builder. How to install, how to
set up a project, what to do/expect. It's critical that you use human facing, plain, direct
language for this."*

- **Where it lives.** `docs/quickstart.md` was the working assumption and was drafted first.
  **Thilina ruled mid-build that it lives in `README.md`**, so the Quick start section is the
  walkthrough and no twentieth document ships. The draft was unwound the same hour: the file
  deleted, `docs/index.md` back to nineteen documents, and the `prose_check`
  `ADDRESSES_THE_READER` extension reverted, since `README.md` is already the one shipped file
  that speaks to the reader.
- **The shape.** A numbered map after the install block, pointing at the README's own sections
  rather than repeating them: the staged build and the two commands, the first-agent example,
  `simple-agents view`, and measuring.
- **The register.** Human-facing, plain, direct. Second person, short declarative sentences,
  the benefit stated first.
- **The boundary.** `docs/procedure.md` stays the coding agent's full build procedure; the
  walkthrough hands over to it.

## 3. Build

`README.md` `## Quick start` gained the four-step walkthrough, and `simple-agents view` entered
the README's prose. No library code changed and no format moved. 4,114 tests.

## 4. Verification

No code changed, so no live run was owed. The README's first-agent block runs in the suite
(`tests/test_readme_first_agent.py`), `prose_check` reads the README's fenced blocks, and
`tests/test_readme.py` and `tests/test_packaging.py` pin the counts and the document table.
Thilina read the section on 2026-09-01 and approved it.

## 5. Doc consequences

`README.md` as above. `docs/` unchanged. Nothing for `CHANGELOG.md`: no artifact format moved
and no behaviour changed.

## 6. Left open

Nothing.
