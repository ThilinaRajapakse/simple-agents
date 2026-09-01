# Build log — When a decision was made

`plan.md` §1 `P3-47`. Built 2026-08-27. Closes `DF5-I26` and `plan.md` §2.2's timestamp entry,
open since dogfood #2.

## 1. Before any design

**What the brief carries, read off the two dataclasses.**
[`BriefEntry`](../../src/simple_agents/conformance/brief.py#L62) held `name`, `status`, `answer`,
`deferred_to`, `source` and `asked_at`; [`Decision`](../../src/simple_agents/conformance/decisions.py#L166)
held `name`, `kind`, `status`, `chose`, `considered`, `because`, `stage`, `rests_on` and
`produces`. `asked_at` and `stage` both hold **a stage name**, one of the six. No clock anywhere.

**Nothing in the library writes a brief.** [`brief.py`](../../src/simple_agents/conformance/brief.py#L40)
reads it with `tomllib` and no writer exists in the package, so whatever is required is required
of the coding agent and enforced when the file is read.

**How every other required key behaves.** `status`, `kind`, and `deferred_to` on a deferral all
raise `ConfigurationError` at parse, naming the entry and the line to write. That is the shape a
new required key takes, and it is why this one is a refusal rather than a check failure.

**The fixtures are generated.** [`scripts/build_conformance_fixtures.py`](../../scripts/build_conformance_fixtures.py#L394)
writes all 18 project briefs, so a format move is one edit there and a rebuild. Found after
patching the fixture files by hand, which `test_every_fixture_holds_what_the_library_writes_today`
then reported as stale.

## 2. Design

**Settled at dogfood #5's sitting 4**: `recorded_at` on every brief entry and every decision,
ISO 8601, written by the coding agent off the system clock; required on an `answered` entry and
on a recorded decision; validated as a timestamp and no further; and the build-log timestamp
requirement leaves the dogfood protocol. Rejected there, as over-engineering on Thilina's call:
`check` stamping the field itself, a git cross-check, and a `simple-agents brief` write command.

**The two open questions, answered in the build.**

*A `deferred` or `unanswered` entry may carry one and is not held to it.* Nothing has been
answered, so there is nothing to date, and requiring it would put a timestamp on the absence of
an answer.

*A re-asked question moves it with `asked_at`, whether or not the answer changed.* The field
dates the writing rather than the wording, which is one sentence and covers every status. The
alternative, keeping the older stamp where a re-ask confirmed the same answer, makes the field
mean "when this was first said", and Thilina's use for it is whether the code has moved since,
which wants the later date.

**A timestamp with no zone is refused, decided in the build.** "Validated as a timestamp and no
further" was about accuracy: the clock is the coding agent's and is trusted. A value with no
offset is not a timestamp two machines can order, which is the whole of what the field is for, so
the parse requires `tzinfo`. An offset other than UTC is accepted.

## 3. Build

[`recorded_at`](../../src/simple_agents/conformance/decisions.py#L244) is one reader in
`decisions.py`, which `brief.py` already imports from, so the two callers share it and the message
names whichever thing is missing it. `BriefEntry.recorded_at` and `Decision.recorded_at` carry it.

**Surfaces touched.** `brief.py`, `decisions.py`, the fixture generator, 18 generated briefs, and
`docs/conformance.md`, `docs/procedure.md`, `dev-docs/runs/dogfood-protocol.md`.

**Two units grew past a threshold and were decomposed rather than recorded.** `_entry` 51 to 57
lines: the deferral validation is `_deferred_to` now, beside `_asked_at` and `recorded_at`.
`decisions_from` to 56 lines: `_kind_of` and `_status_of`. `shape_check` is clean with nothing
newly recorded.

**`docs/procedure.md` was at its 3,000-word budget**, and the four words `recorded_at` costs in
the decision example put it at 3,003. One paragraph was tightened by four words. The document a
coding agent reads first cannot gain a required field's example without losing a sentence.

**Eight tests**, covering both statuses that need it, both that do not, a value that is not a
timestamp, one with no zone, an offset other than UTC, and a decision at every status.
**3,607 tests pass.**

## 4. Verification

**Through the shipped command**, on the `conforming` fixture copied out:

| What | What `simple-agents check` did |
|---|---|
| A brief carrying it | exit 0 |
| The same brief with the key stripped, which is what a project built before this has | exit 2, naming the entry, why it matters, and the line to write |
| `recorded_at = "build"`, a stage name where a clock belongs | exit 2, "which is not a timestamp", with the format |
| [`utc_now()`](../../src/simple_agents/records/trajectory.py#L119) `to_record_data` read into the field | exit 0, and read back byte for byte |

The house clock's own format is what the field takes, which was the design's claim and is now a
measurement.

**3,607 tests pass.** `prose_check`, `shape_check`, `check_docs` and `check_citations` clean.

**Verified again across eight reverification cycles over `P3-44` to `P3-47` together**, and one
found a defect this build shipped. **`simple-agents questions` prints the `record:` line a coding
agent copies into `brief.toml`, and it still said `status = "answered", answer = "..."`**, so
following the library's own instruction produced a brief the library refuses. The `--decisions`
preamble had the same gap. Both name the key now, a test asserts every printed line carries every
key an answered entry needs, and a brief written by copying all fifteen printed lines was
measured to read back and pass FT-24.

**What this costs a real project, measured on dogfood #5's own brief**: it is refused, and fixing
it is 73 additions, 42 answered entries and 31 decisions. The refusal names the first one it
meets, which is how every other required brief key behaves, so `CHANGELOG.md` says to add them in
one pass rather than re-running between each.

## 5. Doc consequences

`docs/conformance.md` §2's example carries the key on both entries, §2.1 says what it is, what is
validated and what is not, and §2's decision paragraph says every decision needs it.
`docs/procedure.md`'s decision example carries it. `CHANGELOG.md` records the brief format move
and what a project on disk has to do.

**[`runs/dogfood-protocol.md` §2](../runs/dogfood-protocol.md#L24) loses the timestamp
requirement**, with what measured it against 2,669 manifests recorded in its place: redundant for
four stages of six, untrustworthy for the other two.

## 6. Left open

**Nothing reads `recorded_at` back.** It is recorded and no gate compares it to anything. What it
would enable is a report line naming answers older than the pipeline they describe, which is
`confirmed_against` extended from a fingerprint to a date. `plan.md` §2.2 is where that goes if a
run asks for it; nothing queued now, since the field has to exist before anything can want it.

**`simple-agents check` is what enforces it, and a project between formats is refused rather than
reported.** That is how every other required brief key behaves, and it is what a pre-release
format move costs. Nothing queued.
