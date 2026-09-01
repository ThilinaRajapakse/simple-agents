# The full-test QA pass of 2026-08-13 — the build

Run 2026-08-13 and 2026-08-14 against `2f4db4c`, outside the `plan.md` §1 queue rather than as
an item in it. Everything it produced is in
[`runs/full-test-2026-08-13/`](../runs/full-test-2026-08-13/), and this log exists so
the pass is findable from the build logs rather than only from that directory. It is a pointer,
not a summary; the detail is all there.

## 1. What was run

Every claim in the fifteen shipped documents was extracted into `inventory/` as 2,328 rows, each
carrying how to test it and which backend it needs. 859 of them were checked with real pipelines
against Gemini and a self-hosted vLLM, one JSONL row per check in `runs/`, and written up as nine
area files in `findings/`. Separately, three coding agents built from the shipped documents alone
in sealed venvs with the source forbidden, in `docs-test/`; one produced a complete evaluated
agent.

## 2. What it found, and what shipped

Five blockers and a long tail, ranked in [`FINDINGS.md`](../runs/full-test-2026-08-13/FINDINGS.md)
with a reproduction against each. `max_steps` did not bound a run whose nodes overlapped or one
that searched; a refused resume deleted the suspended run; a resume into a pipeline used as a node
discarded the answer; an evaluation could not tell a suspension, a configuration error or a dead
backend from an agent that failed; and two pipelines differing only in temperature, tools or budget
shared one `eval_id`.

Thilina ruled on five decisions in [`RULINGS.md`](../runs/full-test-2026-08-13/RULINGS.md).
Five streams implemented them, partitioned by file ownership because the decisions overlap in
`pipeline.py`, `runner.py` and two documents; `fixes/` holds a build log each and
`fixes/RECONCILIATION.md` settles three points where two streams reported the same thing
differently.

Committed 2026-08-14 as `d13e46e`, with the citation sweep it triggered as `d821240`. The results
file moved to `0.11`; every other format is unchanged. 2089 tests pass, `prose_check` and
`check_citations` are clean, and every changed surface was verified live from the built wheel.

## 3. What the pass did not close

- **Eight findings were never assigned to a stream** and are still reproducible: finding 5
  (`write_labels` raises `TypeError` on `Unknown`), and F-07, F-10, F-11, F-12, F-14, F-15, F-17.
  Finding 5 is `findings/area-f-evaluation.md` §5 and the seven flags are its §8, each confirmed
  there against a reproduction.
- **Items 3 to 10 of [`PENDING-SIGNOFF.md`](../runs/full-test-2026-08-13/PENDING-SIGNOFF.md)**,
  which are open decisions rather than unfinished work. Items 1 and 2 are signed off.

## 4. What to read

[`NEXT-SESSION.md`](../runs/full-test-2026-08-13/NEXT-SESSION.md) carries the pass in one
page and names the reading order. `README.md` beside it says what was tested, what was not, and
what might have been missed.
