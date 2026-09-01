# Full-test checkpoint, 2026-08-13

A pre-release QA pass over the whole library: every shipped claim inventoried, then tested with
real pipelines and real runs against real backends in more than one configuration.

**Tested against commit `2f4db4c`**, the concurrency item, which landed at 04:49 while this pass
was being set up. The tree was clean and the wheel was rebuilt from it. Nothing in the repository
was modified: every finding is filed, none is fixed. Proposed patches are in `patches/` and are
**not applied**.

---

## 1. What this is, in numbers

| | |
|---|---|
| Testable claims extracted from the fifteen shipped documents | **2,328** |
| Checks run, with recorded evidence | **859** |
| Passing | 801 |
| Failing | 50 |
| Errored | 1 |
| Skipped, with a stated reason | 7 |
| Library test suite at this commit | **1879 pass, 2 skip, 0 fail** |
| Live model spend | **$0.16** of the $4.00 cap |
| Tokens bought | 641,822 input, 82,815 output |
| Backends exercised live | Gemini `gemini-3.1-flash-lite`, self-hosted vLLM `Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` |

Cost was never the constraint. **Rate was**, and it had to be measured because nothing publishes
it: `harness/backend-budget.md`.

---

## 2. Read in this order

| File | What it holds |
|---|---|
| **`FINDINGS.md`** | Every finding, ranked, with severity and reproduction. **Start here.** |
| **`SITTING-BRIEF.md`** | The five decisions the findings cannot be closed without. Each self-contained: what happened, what it costs, options with prices, a worked example, a recommendation |
| `RESULTS.md` | All 859 checks by suite, and every non-passing one with its detail |
| `findings/` | One file per area, with the fuller evidence |
| `inventory/` | The 2,328 claims, per document, each with how to test it and which backend it needs |
| `docs-test/` | Three coding agents building from the shipped docs alone, with their logs and verdicts |
| `runs/*.jsonl` | The machine-readable evidence. One row per check, with the proof attached |
| `harness/` | The environment snapshot, the measured backend allowances, and every script this pass ran |
| `patches/` | Proposed fixes, not applied |

`RESULTS.md` takes the **latest** verdict for each `(suite, claim)` pair. The result files are
append-only, so a check re-run after its own harness bug was fixed appears more than once; 58
superseded rows are dropped and the count is stated in the file.

---

## 3. What was tested

Everything below was exercised with a constructed pipeline and an executed run, not by reading
the source.

- **Pipeline and graph.** Three node kinds, sequential chains, branch arms from a route, joins and
  the `absent` set, bounded cycles, error edges, per-node retry, output schemas and `unknown`,
  budgets on all four axes, node input validation, and the construction refusals.
- **Concurrency**, which shipped hours before this pass. `concurrent_nodes`, `concurrent_items`,
  `concurrent_tools`, `Pipeline.run(concurrency=)`, the drain rule, non-transitivity of groups, and
  record-then-replay under overlap.
- **Delegation**, live, with a real model choosing its own decomposition, plus `max_calls` and the
  nested node ids.
- **The run envelope.** Manifest fields, trajectory records, cassette record, replay and miss,
  seeds, `runs()`, redaction, sampled payloads, and all three cost bases including the new
  `DeviceBasis`.
- **Suspension.** Single and multi-node stops, `answers=` keyed by node, nested suspension,
  version mismatch, and the new tree-shaped state at suspension format `0.4`.
- **Tools.** The contract, the registry, all thirteen built-ins, side-effect classes, host policy,
  the URL cache, the finish check, `SpendMeter`, grounding helpers, and the typed consultation
  `Reply` with `on_reply` routing.
- **Retrieval and memory.** Lexical, semantic and hybrid ranking, fusion, reranking on CPU, the
  vector store, the memory store, its three tools, and a fact written in one run and recalled in a
  later one.
- **Evaluation.** Rollouts, seed derivation, the six rates, project metrics, recording, replay,
  `rescore`, `resume_from`, `ablate()`, and variant identity.
- **Model clients.** Gemini and vLLM live, Mistral by cassette replay, token accounting, revision
  pinning, streaming, reasoning, retries, pacing, and a real 429.
- **Conformance, CLI and packaging.** All eleven checks made to fail one at a time, the four
  stages and their gates, the brief, the 33 elicitation questions, the wheel, the installed docs,
  and `simple-agents init`.
- **The documents as a prompt surface.** Three coding agents built from `docs/` alone in sealed
  venvs, forbidden the source.

---

## 4. What was NOT tested, and why

Stated plainly, because an untested claim recorded as untested is worth more than one quietly
counted as passing.

**A session limit at 05:28 cut seven subagents short.** Their recorded evidence survived and their
write-ups mostly did not. **A second pass on 2026-08-13 afternoon resumed them from transcript**,
which worked: each still held its context and named its own stopping point. Everything that pass
listed as untested has since been closed except where noted below. Three findings files written by
the lead from evidence rows in between were overwritten by their own agents.

**Closed in the second pass**, and no longer gaps: the interval arithmetic (verified sound), all 17
evaluation flags, `compare_variants`, contamination, the labelling pass, per-node reach and
accuracy, paid evaluation under `max_spend`, `Example.memory` isolation, the `VectorScan`
identifier fix, `ContextOverflow` live, the vLLM `--reasoning-parser` path, and the vLLM
tool-refusal path.

**Still not tested, and why:**

- **Mistral, live.** The account is out of credits and answers 402. Cassette replay covers part of
  it; prompt caching, the model-list and alias claims, the five rate-limit header names and the
  `prompt_mode` refusal are not covered by any recording. `findings/area-g-model-clients.md` lists
  them. **This is the one gap no amount of time would have closed.**
- **`Qwen/Qwen3-Reranker-4B`** and any GPU-resident reranker: the GPU was needed for the served
  model throughout. Only the small cross-encoders ran, on CPU.
- **Retrieval quality against the published benchmark corpora.** The ranking finding is measured
  over 18 and 318 hand-built documents, not over the corpora `docs/retrieval.md` cites.
- **PyPI installation.** `uv add simple-agents` 404s because the package is not published, which is
  expected before release but means the README's first line cannot be followed today.
- **A soak or adversarial workload.** No long-running test, no hostile model output beyond what the
  two backends produced naturally.

**Deliberately not done:**

- **Nothing was fixed.** Findings are filed with reproductions and, where the fix is obvious, a
  patch in `patches/`. Applying changes to a tree that had just absorbed a trajectory-format
  change, unreviewed and overnight, would have made the QA harder to trust rather than easier.
- **No `dev-docs/` file outside this directory was edited**, and nothing in `docs/`. Every
  proposed documentation correction is written here as a proposal.
- **Retrieval quality at scale.** Everything is small hand-built corpora. Nothing here reproduces
  the benchmark figures `docs/retrieval.md` cites.

---

## 5. What might have been missed

- **A claim counted as tested may be tested shallowly.** The inventory says how each claim *should*
  be tested; the 859 checks do not cover all 2,328 claims, and the mapping between them was never
  completed. **Coverage is not 859/2328 either**, because one check often settles several claims
  and some checks settle none. No honest coverage percentage can be given from what was run.
- **Agent-written checks can be wrong in the library's favour.** Several early failures in this
  pass were the harness using the wrong shape, not the library misbehaving. Those were caught
  because they errored loudly. A check that passes for the wrong reason is silent, and some
  certainly did.
- **The concurrency surface is hours old.** It behaved well everywhere it was pushed, but it has
  had one night of exposure, and the defects found near it were older ones it made visible.
- **Three coding agents is not a sample.** The docs-implementability result is real evidence and
  is not a measurement of the documentation as a whole.
- **Nothing here tested the library under a long-running or adversarial workload**: no soak test,
  no large corpus, no many-hour run, no deliberately hostile model output beyond what the two
  backends produced naturally.

---

## 6. The environment, and how it was left

`harness/environment-snapshot.md` records the machine as found, including the exact vLLM serve
command, so it can be restored.

- **The vLLM server on port 8002 was left exactly as found**: same model, same revision, same
  `--max-model-len`, and a live tool call verified after restore. It was reconfigured twice in the
  afternoon, once with `--reasoning-parser` and once without the tool flags, for about fifteen
  minutes in total, and only after dogfood #4 was confirmed finished (idle eight hours, zero
  running and zero queued requests, no project process). `logs/vllm-restarts.md` is the record.
- **Dogfood #4 was not touched.** It was running for the first hour of this pass, which is why
  vLLM work was sequenced behind it and kept to a concurrency of two while it ran.
- **One cost of that restart is recorded rather than hidden.** An area F suite was mid-run against
  the old model id and took nine 404s, which the library scored as an ordinary `failure_rate` 1.0
  with complete rates and intervals and no refusal. The agent caught it, purged those rows and
  re-ran them. The contaminated rows are not in the results; the library behaviour it exposed is
  `B4` in `FINDINGS.md`.
- **The repository working tree is clean apart from this directory.** No tracked file was modified.
- The wheel in `dist/` was rebuilt from `2f4db4c` at 04:56, which the handoff calls for after a
  `docs/` change and which the concurrency commit made.

---

## 7. The one-line verdict

**The library does what it says in most places, and the exceptions cluster in three areas:
budget containment, resume, and what an evaluation does with an agent that stops to ask a
question.** Two of those three are blockers by the standard of a library whose stated purpose is
that a number about an agent can be audited later. `FINDINGS.md` ranks them.
