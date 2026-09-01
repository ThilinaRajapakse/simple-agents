# Area I: the conformance suite, the CLI, and packaging

Suite `area-i-conformance-cli`, rows in
[`runs/area-i-conformance-cli.jsonl`](../runs/area-i-conformance-cli.jsonl).

## Summary

181 claims exercised: **165 pass, 15 fail, 1 skip**. Everything ran against the wheel installed
into the clean venv at `qa-venv`, using its console script rather than the source checkout. The
eleven conformance checks all work: each was made to fail by a single mutation of a project that
otherwise passes, each named its own `FT-nn`, and each printed the failure text
`docs/failure-taxonomy.md` specifies rather than a restatement of it. Exit status is 0, 1 and 2
exactly as [`docs/conformance.md` §3.1](../../../../docs/conformance.md#L187) states. Every count
the documents claim is the count the code has: 33 elicitation questions, 13 at brainstorm with 8
required, 6 decision kinds, 11 checks, 30 taxonomy entries, 15 documents, 13 built-in tools.
`simple-agents init` registers a SKILL.md byte-identical to `docs/procedure.md` and to the
wheel's own second copy of it. `scripts/prose_check.py` is clean over the whole repository;
`scripts/check_citations.py` exits 1, and all 65 of its problems are in files this test
checkpoint wrote today rather than in the library's documents. The failures cluster in two
places: the README, which is unreviewed and shows it, and `simple-agents init`, whose AGENTS.md
pointer is wrong under two of its four flag combinations.

---

## Findings

### 1. The README ships unresolved review comments, a placeholder in visible prose, and an empty section

**Claimed.** [`README.md`](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L1) is the landing page, and
[`docs/index.md`](../../../../docs/index.md#L5) presents the documents as the reference a builder
and their coding agent read.

**Actually.** Six `<!-- Thilina: ... -->` review notes are in the shipped file, including two
that carry a superseded "Old version:" of the paragraph above them. One placeholder is not in a
comment at all and renders: [`README.md` line 95](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L95) reads "Registration
without one is refused, to ensure \<what does this provide?\>." And
[`## Cassettes and Replays`](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L126) is a heading with nothing under it but
`<!-- I think we need a section here. -->`.

**Reproduction.**

```
grep -n "what does this provide" README.md
sed -n '126,130p' README.md
```

**Severity: major.** A reader meets an unanswered editorial question in the middle of a feature
description. Checks `README-009`, `README-010`.

---

### 2. `simple-agents init --claude` writes an AGENTS.md pointing at a path that does not exist

**Claimed.** `init` "registers the procedure where a coding agent will read it", and the note it
writes is what points the agent at it:
[`cli.py` `agents_note`](../../../../src/simple_agents/cli/main.py#L63) says the procedure is in
`.agents/skills/simple-agents/SKILL.md`.

**Actually.** The note is one constant, written whatever `--claude` or `--to` put the skill at.
After `init --claude` the skill is at `.claude/skills/simple-agents/SKILL.md` and AGENTS.md names
`.agents/skills/simple-agents/SKILL.md`, which the project does not have. `--to skills` produces
the same mismatch. The README's own quick start offers `--claude` on its second line.

**Reproduction.**

```
mkdir /tmp/p && simple-agents init --claude /tmp/p
grep SKILL.md /tmp/p/AGENTS.md      # .agents/skills/... ; the file is under .claude/skills/...
```

**Severity: major.** Check `INIT-006`.

---

### 3. `init` writes no AGENTS.md note when the file already names the package anywhere

**Claimed.** `init` writes `AGENTS.md`, or appends to one that does not already carry the note.

**Actually.** The test is a substring search for `simple-agents` over the whole file
([`cli.py`, `AGENTS_HEADING`](../../../../src/simple_agents/cli/main.py#L59)), so an AGENTS.md carrying the
README's own install line, `uv add simple-agents`, is treated as already carrying the note. The
pointer to the procedure is never written and nothing is printed about it. The two lines that
produce this are consecutive in the quick start.

**Reproduction.**

```
mkdir /tmp/q && printf 'Install with: uv add simple-agents\n' > /tmp/q/AGENTS.md
simple-agents init /tmp/q
grep -c "Simple Agents" /tmp/q/AGENTS.md     # 0
```

**Severity: major.** Check `INIT-013`.

---

### 4. The README's quick start begins with an install that does not resolve

**Claimed.** [`README.md` line 14](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L14): `uv add simple-agents  # or: pip
install simple-agents`.

**Actually.** `https://pypi.org/pypi/simple-agents/json` answers 404. Followed literally, the
quick start stops on line one. The pre-alpha banner two lines above says nothing should depend on
the library yet, and says nothing about where it comes from.

**Reproduction.** `curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/simple-agents/json`

**Severity: major** while the README presents an install command. Check `README-001`.

---

### 5. The README's first agent cannot be run against the backend it names

**Claimed.** [`README.md` lines 35-60](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L35) run the first agent against
`MistralClient(model="mistral-small-2603")`.

**Actually.** The repository's own Mistral credential answers 402 to a bare completion, and the
library reports it as 401 with the credential-checking advice. The snippet itself is correct: the
identical code with `VLLMClient` substituted runs in the clean venv, prints `answer: Paris`, and
writes `runs/<run_id>/` holding `manifest.json`, `trajectory.jsonl` and `workspace/`, which is
the directory the README describes.

**Severity: minor**, and it is an account problem rather than a library one. Recorded so that
"the README's own path was exercised" is not claimed. Checks `README-005` (skip), `README-005b`,
`README-006`.

---

### 6. The README's `result.cost` comment describes something the snippet does not do

**Claimed.** [`README.md` line 58](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L58): `result.cost  # derived against the
declared basis`.

**Actually.** The snippet declares no cost basis, so `result.cost` comes back as
`{'value': None, 'currency': None, 'basis': None, 'is_upper_bound': False, 'reason': 'no cost
basis declared in the manifest'}`. The reason is good; the comment beside the line is describing
a run that declared a basis, and the reader's first run does not.

**Reproduction.** Run the snippet from [finding 5](#5-the-readmes-first-agent-cannot-be-run-against-the-backend-it-names)
and print `result.cost`.

**Severity: minor.** Check `README-011`.

---

### 7. Two shipped error messages name a count that does not match the list beside it

**Claimed and actual.**

- [`checks.py` `_first_malformed`](../../../../src/simple_agents/conformance/checks.py#L309) builds FT-13's
  reason as "declares record_type `x`, and the four are ..." and then joins `RECORD_TYPES`, which
  holds five: `node_execution`, `model_call`, `tool_call`, `consultation`, `delegation`.
  [`docs/conformance.md` §2.2](../../../../docs/conformance.md#L110) already says five.
- [`brief.py`, `_entry`](../../../../src/simple_agents/conformance/brief.py#L321) refuses a deferral
  to a non-stage with "and the three stages are brainstorm, shape, build, measure".

**Reproduction.**

```
# five listed after "the four are"
simple-agents check <project with a record_type of "invented">
# four listed after "the three stages are"
simple-agents check <project whose brief has deferred_to = "later">
```

**Severity: minor.** Both messages name the right values; only the number in front of them is
wrong. Checks `COUNT-008`, `BRIEF-003`.

---

### 8. The README's two counts of what the documents contain are stale

**Claimed.** [`README.md` line 136](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L136) says the taxonomy holds "28
characteristic failures"; [line 137](../../../../dev-docs/runs/full-test-2026-08-13/README.md#L137) says the trajectory format has
"four record types".

**Actually.** 30 entries and five record types. `docs/index.md` and `docs/conformance.md` both
carry the right numbers, so the README is the only place they are wrong.

**Severity: minor.** Checks `COUNT-006`, `COUNT-007`.

---

### 9. `docs/conformance.md` §4 counts five entries enforced by construction, and six say they are

**Claimed.** [`docs/conformance.md` line 218](../../../../docs/conformance.md#L218): "except the
five the library enforces by construction", then lists FT-09, FT-18, FT-19, FT-28 and FT-20.

**Actually.** Six taxonomy entries carry an enforcement claim in their own **Check** line, the
sixth being FT-23. A tool registered with no description raises in the clean venv, so the
enforcement is real and the document's list is one short.

**Reproduction.**

```python
from simple_agents.conformance import taxonomy
[e.id for e in taxonomy() if "nforced" in e.check]
# ['FT-09', 'FT-18', 'FT-19', 'FT-20', 'FT-23', 'FT-28']
```

**Severity: minor.** Checks `TAX-006`, `ENF-FT23`.

---

### 10. `questions --stage` omits `brainstorm` from its help and from its refusal

**Claimed.** [`cli.py` `--stage`](../../../../src/simple_agents/cli/main.py#L503) sets the help to "shape,
build or measure. Earlier stages are included".
[`main.py` `is not a stage`](../../../../src/simple_agents/cli/main.py#L474) `_questions` refuses an unknown stage with
`'bogus' is not a stage.`

**Actually.** There are four stages. `brainstorm` is the first, is what a project that has
produced nothing is at, and is what
[`docs/conformance.md` §1.2](../../../../docs/conformance.md#L54) and
[`docs/procedure.md`](../../../../docs/procedure.md#L77) both tell a coding agent to pass. The
refusal names no stage at all, which is the one refusal in the suite that does not say what to
write instead: every other one lists its accepted values.

**Reproduction.**

```
simple-agents questions --help          # brainstorm absent
simple-agents questions --stage bogus   # "'bogus' is not a stage." and nothing else
```

**Severity: minor.** Checks `CLI-020`, `CLI-021`.

---

### 11. The symlink `init` writes does not survive what its docstring says it survives

**Claimed.** [`cli.py` `_place`](../../../../src/simple_agents/cli/main.py#L651), line 200: "it is
relative so a project that commits it survives being cloned elsewhere."

**Actually.** The link is relative, and it points out of the project into site-packages:
`../../../../../qa-venv/lib/python3.12/site-packages/simple_agents/.agents/skills/simple-agents`.
Committing it and cloning the project somewhere without that venv leaves a dangling SKILL.md.
Relative helps only when project and venv move together. `--copy` is what survives a clone, and
the docstring does not say so.

**Severity: minor**, and it is the docstring rather than the behaviour. Check `INIT-004`.

---

### 12. `check_citations.py` exits 1 over the repository, entirely on this checkpoint's own files

**Actual.** 65 problems, 1 blank-line and 64 symbol-drift, distributed as
`dev-docs/runs/full-test-2026-08-13/inventory/claims-evaluation.md` 46,
`.../inventory/claims-tools-retrieval-memory.md` 18,
`.../findings/area-a-pipeline-graph.md` 1. Run over `docs`, `README.md`, `CHANGELOG.md` it is
clean, and run over every `dev-docs/` entry outside this checkpoint it is clean.
`prose_check.py` is clean over the whole repository and over the installed copy of the docs.

**Severity: cosmetic** for the library. It is a live finding for the checkpoint: the QA files
written today carry citations that do not resolve. Checks `SCRIPT-002` to `SCRIPT-006`.

---

### 13. A second `init` exits 0 when it refuses

**Actual.** `simple-agents init` over a project that already has the skill prints
"`<path>` already exists. Pass --force to replace it." and returns 0
([`cli.py` `already exists`](../../../../src/simple_agents/cli/main.py#L521) `_print_one_question`). It also returns before the
AGENTS.md step, so a project whose AGENTS.md was deleted does not get it back from a re-run.

**Severity: cosmetic.** Check `INIT-009`.

---

## Every FT-nn

"Triggered" means this area produced the condition and observed the library react. Entries with
no check are the specification of correct practice; `docs/conformance.md` §4 says so.

| Entry | What it detects | Check exists | Triggered | Result |
|---|---|---|---|---|
| FT-01 | no evaluation at tier `evaluated` | yes, artifact | yes, 4 ways | fires: no results directory, no rollouts, no `content_hash`, unparseable file. Blocks the five that read the same file rather than failing six times |
| FT-02 | one split, or an empty or unnamed held-out split | yes, artifact | yes, 4 ways | fires, and the reason names the splits it found |
| FT-03 | a contamination pair spanning two splits | yes, artifact | yes | fires, naming the pair count and the threshold. `contamination: null` passes with the reason printed |
| FT-04 | no held-out example expecting absence | yes, artifact | yes, 3 ways | fires. An absent example on the dev side does not satisfy it. `allow_unknown=False` on every model node waives it, as documented |
| FT-05 | single rollout per example | no | no | not detectable by the suite |
| FT-06 | a metric with no interval and no reason | yes, artifact | yes, 4 ways | fires on a top-level metric, a per-node `reach`, and a project's own metric. A stated reason passes |
| FT-07 | a rollout or a sampling record with no seed | yes, artifact | yes, 3 ways | fires on a null rollout seed, a null `node_execution` seed, and a `model_call` with the field absent. A `deterministic` node with a null seed passes |
| FT-08 | end-to-end metrics only | no | no | not detectable by the suite |
| FT-09 | output schema admitting no `unknown` | enforced at construction | yes | `LLMNode` refuses a schema with no absence branch |
| FT-10 | false confidence conflated with recall | no | no | not detectable by the suite |
| FT-11 | everything made agentic | no | partly | the shape is enforced: `Deterministic` takes no model, `LLMNode` takes no budget, only `AgentNode` owns a loop. No check reads the brief for a justification |
| FT-12 | agency asserted but never ablated | no | no | not detectable by the suite |
| FT-13 | no trajectory, or one nothing can read | yes, artifact | yes, 9 ways | fires on: no run directory, no `trajectory.jsonl`, a line that is not JSON, a record missing common fields, an unknown `record_type`, an empty file, no `node_execution`, runs written outside `runs/` (naming the `--run` that reads them), and runs that all declare a non-agent role (counted by role) |
| FT-14 | a model identifier that floats | yes, artifact | yes, 3 ways | fires on a hosted name carrying `latest`, on self-hosted weights whose revision is not a SHA, and on one node's own client floating while the run's is pinned, naming the node. A run that made no model call passes, saying so |
| FT-15 | prompts unversioned | no | no | not detectable by the suite |
| FT-16 | secrets in trajectory records | no | no | not detectable by the suite |
| FT-17 | context silently truncated | no | no | not detectable by the suite |
| FT-18 | a loop with no budget | enforced at construction | yes | `AgentNode` refuses without `budget` |
| FT-19 | a tool with no side-effect class | enforced at registration | yes | `@tool()` refuses without `side_effect_class` |
| FT-20 | spending or irreversible tools inside rollouts | enforced at runtime | partly | the runner names `spends_money`, `irreversible` and `max_spend`; the live refusal belongs to area E |
| FT-21 | an evaluation that cannot run offline | no | no | not detectable by the suite |
| FT-22 | errors swallowed and fed to the model | no | no | not detectable by the suite |
| FT-23 | a tool description written for a human | enforced at registration | yes | a tool with no description refuses |
| FT-24 | a required question with no answer at the current stage | yes, artifact | yes, 4 ways | fires on `unanswered`, on a question with no entry, and on a deferral to the stage the project is at. A deferral to a stage ahead settles it. Artifacts move the stage forward and the report says so |
| FT-25 | consultation treated as a fault path | no | no | not detectable by the suite |
| FT-26 | a gameable reward function | no | no | not detectable by the suite. Tier `trained` |
| FT-27 | cost recorded as a bare figure | no | no | not detectable by the suite |
| FT-28 | a node reading a type nothing reaching it can be | enforced at construction | yes | `Pipeline` refuses when the declarations disagree |
| FT-29 | no current account of the project | yes, artifact | yes, 4 ways | fires on a missing `idea.md`, an empty section, an `understanding_confirmed_at` naming an earlier stage, and the key being absent. A heading ending in a colon still counts as its section |
| FT-30 | a decision still `proposed`, or a kind with no entry | yes, artifact | yes, 2 ways | fires on both, and the reason distinguishes them |

---

## What I could not test, and why

- **The README's own backend.** The repository's Mistral credential answers 402, so the first
  agent could only be run with `VLLMClient` substituted. The snippet's shape, output and run
  directory were exercised; `MistralClient` as the README writes it was not.
- **`pip install simple-agents` from an index.** The name is not published, so the quick start's
  install path exists only as a local wheel.
- **FT-20's live refusal, and every other runtime-surface entry.** Areas E and C own those. This
  area established only that the code names the classes the document says it refuses on.
- **Whether a skill installer follows a symlinked skill directory.** `init` produces a symlink by
  default and the bytes at the end of it are right; whether Claude Code or an agent-neutral
  installer resolves a symlinked `SKILL.md` was not exercised.
- **The `--to` flag against a real second harness.** Only that the directory is created and the
  bytes land in it.
- **Concurrency, and a project that is being written while `check` reads it.** The suite reads
  files and executes nothing, so this is out of area, but nothing here establishes that a check
  running against a live run directory reports sensibly.
- **Windows and macOS.** `_place` falls back from symlink to copy on `OSError`, and only the
  Linux path was taken.

## What I might have missed

- **Mutation coverage is one-at-a-time.** Two simultaneous problems were not tried, so an
  interaction where one check's failure masks another's is not ruled out. The blocked-check
  machinery was exercised only through FT-01.
- **The conforming fixture is the library's own.** It is a real recorded evaluation, and a
  project built by hand from `procedure.md` at tier `prototype` also passes (`SCRATCH-001`), but
  no evaluated-tier project was built from scratch outside the fixture. A field the fixture
  happens to carry and a real project would not would read as passing here.
- **The elicitation questions were checked for count, uniqueness, stage validity and the presence
  of an `ask` and a `scaffold`.** Whether 33 is the right set, and whether each scaffold makes its
  question answerable, is a judgement this area did not make.
- **Taxonomy message rendering** was checked for FT-29 against the document verbatim and for the
  rest by stem match. A placeholder substituted with the wrong value would pass that.
- **`--json` was compared field by field against the text report only for the counts.** A
  difference in `detail` or `read` between the two renderings would not have been caught.
- **The wheel was the one already built at 04:56.** It matches the working tree exactly, checked
  file by file, but a rebuild after any change since would need re-running.
