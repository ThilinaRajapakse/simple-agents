# Build log — going public

`plan.md` §1 P3-31. Scheduled 2026-08-20, built in pieces to 2026-09-01, closed 2026-09-02.
This file is the item's record transformed in place: §1 and §2 are what `build-logs/going-public-build-log.md`
held, under the six headings, and §3 to §6 are the build.

## 1. Before any design

### Where it came from

Thilina, 2026-08-20, at the P3-1 completeness audit: *"I am thinking of doing DF-5 today and
going public with the library tomorrow-ish. Is there anything waiting that should be done first
before it's public-ready?"* The readiness sweep from that conversation is what this record
carries.

### What the problem is, checked 2026-08-20

The repository is not release-shaped, checked 2026-08-20:

- **No LICENSE file**, against `license = "Apache-2.0"` in `pyproject.toml`.
- **`version = "0.0.0"`**, and `CHANGELOG.md` opens with "Nothing is released yet".
- **No `.github/`**: no CI, though the suite is built to run offline in CI
  (`simple-agents.md` §10).
- **`simple-agents` looks unclaimed on PyPI**: 404 on the project page. Claim it at release.
- **`dev-docs/` needs a scan pass before it is public.** Nothing secret is committed (keys
  are gitignored; the handoff names variable names only), and the dogfood records carry
  material derived from Thilina's own Goodreads export and viewing history. **Measured
  2026-08-28**: 143 tracked files and 48,968 lines; 33 occurrences of a home path on this
  machine, 14 of a key's variable name, and no email address. A scan for media titles in the
  three tracked dogfood #5 records found none, which the pass confirms rather than assumes.
  *(`DF5-I36`'s row read that `findings.md` quotes show titles from the trajectories; nothing
  found one.)*
- **The README pass is open**: Thilina's Corner, since 2026-08-09, and the front door is the
  first thing a public reader meets.
- **`P3-3`'s remainder is unreviewed shipped text**, now including `docs/product.md`, written
  2026-08-20 and never reviewed to the document-review standard.
- **No example project exists** (`P3-2`): the on-ramp a public library is judged by, six tasks
  decided and none built.

## 2. Design

Every decision below is Thilina's, at the sitting named beside it.

### What had to be decided

**Settled 2026-08-20, ahead of dogfood #5:**

- `evals/questions.jsonl` is **`evals/examples.jsonl`**, renamed before the run starts on the
  final layout, because after the first public project the rename is a breaking change.
- **`builder` stays.** `developer` is ambiguous against the library maintainer, which is the
  ambiguity the glossary exists to remove. The inbox entry closed on it.
- **`dev-docs/` goes public after a scan pass**, deliberately not performed in the deciding
  session.
- **What the scan covers, settled 2026-08-28 at dogfood #5's sitting 8**, which folded `DF5-I36`
  in here. Three decisions, Thilina's:

  **It reads `dev-docs/` and nothing else.** The dogfood projects are repositories of their
  own and **nothing from one goes public**, so the 3.7GB of trajectories under
  `dogfood-5/runs/`, which carry his viewing history, are out of scope rather than in it. This
  repository tracks three files from that run, `setup.md`, `findings.md` and `inventory.md`,
  and they are in scope like anything else here.

  **Rules hold what rules can hold.** `prose_check` gained `own_run` and `machine_path` at the
  sitting: one of our own runs named in a shipped file, and a path on the machine this was
  written on. Both are at zero, which cost six rewrites in `conformance/run.py` and
  `docs/failure-taxonomy.md`. `CHANGELOG.md` is exempt from the first for the reason it is
  exempt from `miscount`: an entry says what was true at a release.

  **The reading is not Thilina's line by line.** His call, in answer to whether he reads each
  one: *"There are far too many lines for me to read each one. So you + rules will do the bulk
  of it."* 143 tracked files and 48,968 lines. So the pass is three layers: the rules above,
  reported by the suite; a pattern sweep over the tree that a coding agent triages; and a short
  list of what needs a judgement, which is what he reads. **What reaches him is material
  derived from his own data**, and anything the triage cannot settle.

**The scan pass ran 2026-09-01 and is clean.** The three layers as settled at sitting 8: the
rules at zero; the pattern sweep (`scripts/check_private_data.py`) triaged to zero, with a
per-rule allowlist recording each ruling; and a sweep for titles, author names, ratings, email
addresses and personal identifiers that found none anywhere in the tree. The judgement list put
to Thilina came back: the Goodreads aggregate statistics in `items/example-projects.md` and
`runs/dogfood-3/setup.md` are kept, the home paths are kept, and the git author metadata going
public with the repository is intended. The sweep now gates in the suite through
`tests/test_private_data.py`, so a record that lands with a finding fails CI.

**Settled 2026-09-01:**

- **A fresh public repository**, initialized from the scanned tree. This repository stays as
  the private archive, so its commit-hash citations keep resolving for the maintainer. The
  ruling's basis: the scan certifies the tip alone, and history holds what the scan removed
  (`2b774e8` deleted 112 files of dogfood transcripts).
- **`claude-docs` renamed `dev-docs`**, done the same day, before the snapshot.
- **This item follows the normal lifecycle**: build log, §4 Done line, record dispositioned.
  The scan record stays public.
- **A CI workflow ships first**: `ci.yml` at `2b774e8`, running the suite, the citation check
  and the wheel-contents check.
- **Three items precede the release**, scheduled 2026-09-01: `P3-65` the builder quickstart,
  `P3-66` the feature index carrying `P3-3`'s remainder, `P3-67` the undocumented APIs.

**Settled 2026-09-01, at the release sitting, all Thilina's calls:**

- **The version is `0.1.0` and the tag is `v0.1.0`.** Releasing before v0.1's recorded
  criterion (*"a dogfood run produces no library defect worth building"*) is a knowing
  override, ruled at the sitting.
- **The README pass is closed** on Thilina's read. The Corner item closes with it.
- **The example project follows the release.** `P3-2` stays queued behind it.
- **Release does not start the format-stability clock.** Breaking format bumps stay allowed
  pre-1.0, recorded in `CHANGELOG.md` as they always were; `simple-agents.md` §9 item 7 stands
  unchanged.
- **The three §2.2 entries due for re-decision are scheduled**, as `P3-68` (per-edge value),
  `P3-69` (OpenAI and Anthropic adapters) and `P3-70` (payload by reference), behind the
  release.
- **The repositories.** This repository is renamed `simple-agents-prototype` and stays the
  private archive; the fresh public repository takes `simple-agents`, initialized from the
  scanned tree and holding only what `git ls-files` holds here.
- **The PyPI name is `simple-llm-agents`**, ruled 2026-09-01 after the upload was refused:
  `simple-agents` is blocked by PyPI's similarity rule against `simpleagents` (a one-release
  0.0.1 placeholder from 2025-02) and `simple-agent` (one release, 2023). The import stays
  `simple_agents` and the CLI stays `simple-agents`. A PEP 541 request for `simple-agents`
  and a transfer request for `simpleagents` go to pypi/support; either succeeding reopens the
  name question at a later release.

### What it waited on

`P3-32`, working through dogfood #5's findings, all of it. Decided 2026-08-25: the whole of
[`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L1) is dispositioned and what it
schedules is built before the repository is public. *(Until then it was "dogfood #5, running
first: a defect it finds lands before the repository is public".)* **`P3-32` closed 2026-08-28**,
all 40 candidates disposed.

**`P3-63`, the pre-release refactor, scheduled 2026-08-31 ahead of this item** on Thilina's
2026-08-17 call that the refactor precedes the public release.
[`build-logs/pre-release-refactor-build-log.md`](../build-logs/pre-release-refactor-build-log.md#L1) is its record.

## 3. Build

Nineteen commits on the public repository, 2026-09-01 to 02, all mechanics as §2 left them:

- **`46bcaef` Simple Agents 0.1.0**, the scanned tree as the first commit; `v0.1.0` tagged.
- **`becf370`**: the first CI run failed on a tracked record linking an untracked machine
  artifact, fixed the same hour.
- **`8e52a6b`**: the distribution renamed `simple-llm-agents` after PyPI refused the upload
  under its similarity rule; import and CLI names unchanged.
- **`e22e127`, `1dc3065`**: `0.1.0.post1` and `.post2`, the package summary and the PyPI page's
  quick start, which had not worked from an empty directory (`98adf3d`).
- **`77a85aa`, `2d4d24d`, `6ba9763`**: a coding agent is told where the installed docs live,
  and a fifth asking rule; released as **`0.1.1`** (`30eb4cb`).
- **`f81297e`**: `release.yml`, so pushing a `v*` tag runs the CI workflow and publishes by
  trusted publishing with no token in the repository.
- **`d36c71c`**: **`0.1.2`**, five view fixes found by the first public project.
- **`5982abb`**: cutting a release is one command, and a changelog that says nothing about the
  version refuses.

No format moved. 4,134 tests at close.

## 4. Verification

Three releases went through `release.yml` on the tag and landed on PyPI. Dogfood #6 installed
`0.1.1` from PyPI cold, upgraded to `0.1.2` mid-build with every pipeline still importing, and
met no packaging defect ([`runs/dogfood-6/findings.md` §2](../runs/dogfood-6/findings.md#L1),
`DF6-L1`). `tests/test_private_data.py` gates the scan in CI and passes over the tree as closed.

## 5. Doc consequences

`CHANGELOG.md` gained `0.1.0`, `0.1.1` and `0.1.2` in short bullets; `README.md`'s quick start
runs from an empty directory; `AGENTS.md` and the skill name `docs_path()`; `docs/procedure.md`
gained the fifth asking rule. "Nothing is released yet" stopped being true.

## 6. Left open

- **The PyPI name.** A PEP 541 request for `simple-agents` and a transfer request for
  `simpleagents` are with pypi/support; either succeeding reopens the name at a later release.
  Nothing here can act on it. Destination: nothing.
- **The example project** stays [`plan.md` §1 `P3-2`](../plan.md#L1), behind the release as ruled.
- **v0.1's own criterion** stays unmet: dogfood #6 produced nineteen candidates,
  [`plan.md` §1 `P3-71`](../plan.md#L1).
