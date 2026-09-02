# Build log — the brief writer

`plan.md` §1 P3-72. Scheduled at dogfood #6's sitting and built 2026-09-02. §1 and §2 are the
item's record transformed in place; §3 to §6 are the build.

## 1. Before any design

Verified against the tree before anything was decided:

- Nothing in the library writes `brief.toml`: `grep -rn brief.toml src/` finds readers only,
  and `view/serve.py:10` says so in its own words. `records/comments.py` `_write` is the one
  TOML emitter, basic strings through the JSON escapes.
- `conformance/decisions.py` `recorded_at` refuses a value that is not a timestamp or names
  no zone, and nothing reads the value against a clock.
- The CLI has seven commands and none takes text for the brief.
- Dogfood #6's brief on the frozen copy: 65 stamps, twenty of the thirty-three distinct ones
  round-minute local-time values with a `Z`; the sixteen at `01:27:31Z` written by the
  comment flow are right ([`DF6-D9`](../runs/dogfood-6/findings.md#L1)).

### Where it came from

[`DF6-I09`](../runs/dogfood-6/inventory.md#L59), from [`DF6-D9`](../runs/dogfood-6/findings.md#L258): every `recorded_at` in dogfood #6's brief was written by the
coding agent off its own reading of the clock, and twenty of thirty-three came out as local time
with a `Z` suffix, two hours off. Thilina at the sitting of 2026-09-02, choosing the writer over
a check alone: agents have no sense of time and will get it wrong.

### What the problem is

`recorded_at` is required on every answered entry and every decision since `P3-47`, the CLI has
no command that writes an entry, and `docs/conformance.md` §2.1 tells the coding agent to read
the system clock and write the value by hand. The stamps the view writes into `comments.toml`
are right, because a program wrote them; the brief's are the coding agent's word. A gate that
anchors "has the code moved since this answer" on that stamp anchors on a guess.

## 2. Design

### What had to be decided

- **The command's shape.** `simple-agents record answer <name>` and `record decision <name>`,
  reading the body from a file or stdin, writing the entry with the clock's stamp, and refusing
  a name the question set does not hold. Whether `status`, `source`, `asked_at` and a decision's
  `kind`, `from` and `produces` are flags or part of the body.
- **The Python function** beside it for a project's own scripts, and whether the view's
  amendment path writes through the same code.
- **The check.** A stamp that sits ahead of a comment thread, a run's `started_at`, or a later
  stage's stamp is refused, so an entry still written by hand is caught. Whether it is a new
  FT or a clause of FT-38.
- **The procedure.** The coding agent is told to write entries through the command and not by
  editing `brief.toml`; whether the file's header says the same.

### What was decided

- **A module, `conformance/writing.py`**, with `record_answer` and `record_decision`, exported
  from `simple_agents.conformance`, and `simple-agents record answer <key>` and `record
  decision <name>` over them. The stamp is the machine's clock in UTC to the second.
- **One table moves and nothing else.** The table under `[entries.<name>]` or
  `[decisions.<name>]` is replaced whole, its other keys kept (a project's `agreed_at` and
  per-entry `confirmed_against` survive), and the rest of the file is left byte for byte. The
  end of a table is the next header line at which the text from the header parses on its own,
  so a line opening a bracket inside a multi-line answer is not a header. A new table is
  appended.
- **Refused before the file is touched**: a name that is not a question, a status or stage or
  source outside the known ones, an answered entry with no answer, a re-asked question with
  no `asked_at`, a decision kind outside the six, a `from` naming no question. And the whole
  result is re-read as a brief before it is written, so every refusal `Brief.read` makes
  holds here and nothing changes on disk.
- **Standard input only when asked for**, as `--file -`. The first draft read it whenever it
  was not a terminal, and a coding agent's harness leaves the pipe open and writes nothing,
  so the command would have waited forever. Found in the first reverification cycle.
- **FT-44, a stamp the clock did not write**: every `recorded_at` against the clock the suite
  runs on, five minutes' tolerance, a failure at every stage. It cannot read a stamp behind
  the clock, which is what a composed one looks like once enough time has passed; the writer
  is what closes the finding and the check is what catches a hand-written stamp at the next
  gate.
- **Not taken**: a stamp checked against comment threads or runs. The relations are fragile
  and the writer removes the cause.

## 3. Build

`conformance/writing.py` (new), the `record` command in `cli/main.py`, `ft_44` in
`conformance/checks.py`, `tests/test_record.py` (22 tests: the stamp, one table moving and
nothing else, the refusals, the command, FT-44 both ways). Twenty-seven checks; the
taxonomy's 44 entries; every count the documents and tests carry moved with them. No format
moved. 4,156 tests.

## 4. Verification

**Live, against dogfood #6's real brief** (a copy of the frozen project's `brief.toml`, 2,117
lines, `"""` strings, unknown keys, per-entry `confirmed_against`): `record answer
stored_output --asked-at ship --file <two paragraphs with a quote and a bracket line>` and
`record decision split_seed ...` replaced their tables, kept `agreed_at` and `considered`,
read back through `Brief.read` verbatim, and left every other line of the file as it was
(`diff` against the copy). `simple-agents check` on that brief passed FT-44 over 65 stamps;
with `decisions.app` re-stamped two hours ahead it failed, naming the table and the stamp.
Standard input as `--file -` piped in.

**Reverification cycles**, each a read of the code against the documents, the unit tests, the
full suite and the live exercise above:

1. The command read standard input whenever it was not a terminal, which under a coding
   agent's harness waits forever; made explicit as `--file -`. Three tests assumed the
   conforming fixture lacked an entry it holds. The shape ratchet named both writers and the
   CLI parser: the writers split into a check and a merge each, the command moved to
   `cli/record.py`, and the baseline records `checks.py` at its new length.
2. The header table row in `checks.py` and the CLI's imports shifted 33 citation anchors in
   `dev-docs/`, re-resolved with `check_citations.py --fix`. Two view tests counted the checks
   by hand. A table header carrying a trailing comment was read as absent, so a second copy
   would have been appended and refused; accepted, with a test.
3. Read, unit tests, the full suite and the live exercise: nothing found. 4,156 tests.

## 5. Doc consequences

`docs/conformance.md` §2.1 rewritten around the writer and a new §2.3 with both forms;
`docs/failure-taxonomy.md` gains FT-44 and its counts; `docs/procedure.md` records through
the command at the two places it said to write the brief; `docs/view.md` §12 names it;
`README.md` shows the command and the new counts; `CHANGELOG.md` under Unreleased. The
sentence "Nothing in the library writes a brief" stopped being true.

## 6. Left open

- **A writer for the top-level keys** (`stage`, the three `*_confirmed_at`, `confirmed_against`,
  `shape_confirmed`), which the procedure still has the coding agent set by hand. Destination:
  [`plan.md` §2.1](../plan.md#L38), accepted, waits on a slot.
- **The view's amendment flow writing through the same code**, so an answer given on the page
  lands in the brief stamped rather than travelling as a thread first. Destination:
  [`plan.md` §2.2](../plan.md#L164), deferred; what decides it is whether the coding agent's
  reading of a thread before it is recorded is worth keeping.
