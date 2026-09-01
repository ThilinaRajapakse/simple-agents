# Kickoff prompt

The first message to a fresh session. **A pointer and an intent, not a briefing.** Delete this
paragraph when copying.

**Why it is short.** `CLAUDE.md` loads automatically, `handoff.md` says where to start, `plan.md`
is the queue, and each item has a record. A session can find all of it. What it cannot find is
what you meant and what changed since the last commit, so those are the only things the prompt
owes it.

**Ceiling: 15 lines.** If it does not fit, the excess belongs in a record. A kickoff prompt that
has to explain something is reporting that a file is missing it, and the fix is to write it there
and cite it.

---

## The shape

```
Read dev-docs/handoff.md, then <the one record>.

<Kind of session>: <the task in one sentence, naming ids>.

<What is true right now and is in no file. Omit the line if nothing is.>

<Constraint, and the reason for it. Omit if there is none.>
```

- **Kind of session** is `design sitting`, `build`, `review`, or `investigation`. It changes what
  the session should do before writing anything: a sitting decides and does not code, a build
  follows `templates/build-log.md`.
- **The task names ids** rather than describing the work. `DF4-I02` resolves to a row, its
  evidence and its blockers. A paragraph does not.
- **What is true right now** is uncommitted work, a parallel session holding a file, a machine
  change, a backend that stopped working. If a command answers it, leave it out.
- **A constraint carries its reason**, because a session that knows why a boundary exists can tell
  when it does not apply.

## What never goes in

- **Anything in `CLAUDE.md`, `handoff.md`, `plan.md` or the record.** If the session needs it, it
  belongs in the file, and putting it in the prompt hides that the file is missing it.
- **Anything a command answers**: the test count, `git status`, what is in a directory. It is
  stale on the next edit and free to obtain.
- **The generating session's conclusions.** Name the question, not the answer. A fresh session
  told what it will find stops looking, and half the reason for starting fresh is to see whether
  it finds the same thing.
- **A role preamble or a description of the project.**
- **A plan for how to do the work**, unless the approach is decided and recorded, in which case
  cite the record rather than restating it.

## What it is not

**Not the dogfood prompt.** A dogfood run is a cold start by design, its prompt is deliberately
naive, and it is recorded verbatim in that run's `setup.md` §3 so the run can be repeated.
`runs/dogfood-protocol.md` owns that. This is for work on the library itself, where the session is
meant to arrive informed.

**Not an artifact.** A kickoff prompt is single-use and is not written to the tree. The one
exception is a handover big enough to need its own record, which is a file in `runs/` that the
prompt then points at.

## The writer

The session should see the kickoff prompt as something that comes from Thilina. If you want to address the session directly, then make it clear that Thilina is quoting something that you asked him to pass along.
