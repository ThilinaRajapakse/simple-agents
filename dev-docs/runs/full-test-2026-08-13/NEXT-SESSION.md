# Kickoff for the next session

Paste the block below into a fresh session. It is written to brief a coding agent and to remind
Thilina, who lost two days to a failing SSD in the middle of this.

---

## The prompt

> Read `dev-docs/runs/full-test-2026-08-13/NEXT-SESSION.md` first, then the files it
> names. Do not start work until you have read `PENDING-SIGNOFF.md`, because two items there gate
> the commit that is the next action.
>
> Context: a full-test QA pass ran on 2026-08-13 against commit `2f4db4c`. It inventoried 2,328
> claims across the fifteen shipped documents, ran 859 checks with real pipelines against real
> backends, and found five blockers. Thilina ruled on five design decisions, five parallel streams
> implemented them, and the work is merged and verified but **not committed**.
>
> The tree carries 74 changed paths and about 6,900 lines. `origin/main` is still at `2f4db4c`, so
> none of it is on GitHub. 2089 tests pass, `prose_check` is clean, and every changed surface was
> verified live on Gemini and vLLM from the built wheel.
>
> The next action is to get Thilina's sign-off on the two blocking items, then commit and push.
> After that, dogfood #4's findings record, which does not exist yet.

---

## What happened, in one page

**The pass.** Every claim in `docs/` was extracted into `inventory/` (2,328 rows, each with how to
test it and which backend it needs). 859 checks ran, recorded one JSONL row each in `runs/`. Nine
area findings files in `findings/`. Three coding agents built from the shipped documents alone in
sealed venvs, in `docs-test/`, and one of them produced a complete evaluated agent, which is the
strongest evidence the documentation works.

**What it found.** Five blockers, summarised in `FINDINGS.md`:

1. `max_steps` did not bound a run whose nodes were in a `concurrent_nodes` group, or one that ran
   a search. The one axis documented as exact was not.
2. A refused resume deleted the suspended run. A typo in `answers=` was unrecoverable.
3. A resume into a pipeline used as a node discarded the answer.
4. An evaluation could not tell a suspension, a configuration error or a dead backend from an agent
   that failed. Nine 404s scored as `failure_rate 1.0` with complete intervals.
5. Two pipelines differing only in temperature, tools or budget shared one `eval_id`, so
   `resume_from` and `rescore` silently mixed rollouts from different configurations.

**The statistics were checked and are sound.** `wilson_ci` matches scipy to 1e-12 across 60 pairs;
the bootstrap resamples examples as documented. That was the largest open question and it closed.

**The rulings.** `SITTING-BRIEF.md` posed five decisions, `RULINGS.md` records what Thilina decided:
D1 make `max_steps` exact everywhere; D2 split `graph_fingerprint` (shape) from `_eval_id` (what was
measured); D3 different answers per failure class; D4 ship a stopword list and make `ranking=`
required; D5 finish this work, then dogfood #4.

**The fixes.** Five streams, partitioned by file ownership rather than by decision, because the
decisions overlap in `pipeline.py`, `runner.py` and two documents. Build logs in `fixes/`, one per
stream, plus `RECONCILIATION.md` where two streams reported the same thing differently.

---

## State right now

| | |
|---|---|
| `HEAD` and `origin/main` | `2f4db4c`, identical |
| Uncommitted | 74 paths, ~6,900 lines, **not pushed** |
| Tests | 2089 passed, 2 skipped, 0 failed |
| `prose_check` | clean |
| `check_citations` | 80 problems, all in `dev-docs/`, none in `docs/` or `src/` |
| `simple_agents.__all__` | 142 names, up from 108 |
| Formats | trajectory `0.21`, manifest `0.21`, suspension `0.4`, **results `0.11`**, variants `0.2` |

---

## The next three actions, in order

**1. Settle the two items that gate a commit.** Both are in `PENDING-SIGNOFF.md`:

- A `# prose-ok:` marker sits in `builtins/search.py:72` without sign-off, which `CLAUDE.md`
  requires. `prose_check` is clean because of it. `ENGLISH_STOPWORDS` contains `you`, `your`,
  `yours`, `yourself`, `yourselves` and the second-person rule reads them as prose. The lead
  recommends signing it off; the alternatives are a pronoun set with a hole, or the package's first
  non-Python file.
- Whether `check_citations.py --fix` may rewrite `plan.md`'s citations. 80 problems remain, all in
  `dev-docs/` records whose anchors moved when the streams moved code.

**2. Commit and push.** Nothing outside this repository holds anything written by the new formats,
so there is no migration to write. Once pushed, the failsafe archives under
`/deep_learning/simple-agents-backup-*` are redundant and can be deleted;
`/deep_learning/simple-agents-backup-README.md` explains them.

**3. Dogfood #4's findings record**, which is `plan.md` §1.2 item 2 and does not exist. D5's ruling
carries a condition that must not be lost: **the library moved under that run, so every issue it
hit is checked against what has since been fixed before it is written up.** Several of the five
blockers above are things dogfood #4 would have met.

Also outstanding and unscheduled: whether `plan.md` §1.2 and `handoff.md` get updated with any of
this, and whether the documentation corrections merge into the shipped-document review already at
§1.2 item 4. The lead did not touch either file.

---

## Eight things still open, none blocking

`PENDING-SIGNOFF.md` has them in full. In short: `_eval_id` covers twelve fields where D2 named four
(the stream argued the other eight equally decide what was measured; one line to narrow it); H-6, a
nested stop reporting a bare leaf `node_id`; B-1, whether a redacted tool result should be redacted
at the boundary so a replay works; three items Stream C raised; the README's three review comments,
which are Thilina's own and ask for tone rewrites; and eight findings never assigned to a stream.

---

## The machine, which cost this pass real time

- **`/home` is on a new SSD.** The Sabrent Rocket 4.0 2TB failed on 2026-08-14 after logging 80
  unrecoverable read errors across 27 sectors. Everything was migrated and verified: `git fsck`
  clean, zero paths lost. `/home` and `/deep_learning` are now both on `nvme1n1`.
- **`uv` is at `~/.local/bin/uv`** and is not on a default shell `PATH`.
- **vLLM needs its venv on `PATH`, not just its absolute path.** FlashInfer shells out to bare
  `ninja` during KV-cache sizing, so `export PATH="/home/thilina/.venvs/vllm/bin:$PATH"` is
  required. Without it, startup fails as `EngineCore failed to start` inside
  `determine_available_memory`, **after the weights load**, which reads as a memory or driver fault
  and is neither. `harness/environment-snapshot.md` has the working command.
- **Launch anything slow detached and watch it.** A foreground command awaiting approval is
  indistinguishable from a hang.
- Mistral is out of credits. Gemini free tier is roughly 25 to 30 requests a minute; the paid key is
  what the pass used, and total spend was about $0.20 against a $4 cap.

---

## Reading order

1. `FINDINGS.md` — the five blockers and everything else, with reproductions
2. `PENDING-SIGNOFF.md` — the ten open items, first two gate the commit
3. `RULINGS.md` — what was decided and why
4. `README.md` — what was tested, what was not, and what might have been missed
5. `fixes/*.md` — one build log per stream, and `RECONCILIATION.md`
6. `RESULTS.md` and `runs/*.jsonl` — the evidence, one row per check
