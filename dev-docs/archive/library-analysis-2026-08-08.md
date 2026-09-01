# Library analysis, 2026-08-08 — findings, decisions, and what landed

The record of a full read of the library (all 54 source files, both doc trees, the three
dogfood records) at `d41df85`, the ten decisions Thilina made over its findings on 2026-08-09,
and the positioning re-ruling that came out of the same session. Everything below is landed and
verified except where marked open: **1211 tests pass** after the batch (from 1191 before it),
`prose_check` clean, wheel rebuilt. `CHANGELOG.md` Unreleased carries the project-facing
account of each behaviour change; this file carries the rationale and the evidence, which is
the `dev-docs` half of the split.

**Method note for whoever reads this later.** Every bug claim was verified by executing a
reproduction or tracing the exact call path before it was reported, and the dogfood-2 fix
batch landed in the working tree mid-analysis (it is why test counts in the session move from
1177 to 1191 to 1211). The full findings narrative exists only in the session transcript; what
is durable is this table, the code, and the tests each fix carries.

## The ten decisions

All ten were put to Thilina with options and costs; his rulings are the middle column.

| # | Finding | Ruling | Landed |
|---|---|---|---|
| D1 | `http_fetch` followed redirects past its own allow-list and robots check (client-level `follow_redirects=True`, checks run once on the first URL) | Check every hop | `builtins/http.py`: manual hop loop, max 5, `_allowed` per hop, credential headers (`Authorization`, `Proxy-Authorization`, `Cookie`) sent only to the host the agent addressed |
| D2 | `EvalSuite` scored a dict-returning terminal node as `failure_rate` 1.0 after paying for every rollout (`getattr` on the output) | Read Mappings by key, refuse fast on a shape mismatch | `evaluation/runner.py` `_answer_of`: Mapping by key, `ConfigurationError` naming the actual fields, a top-level `Unknown` output classifies as an abstention |
| D3 | `compare_variants` rebuilt each arm's suite without `metrics=`/`node_metrics=`, so every declared `ProjectMetric` silently vanished from every variant comparison (item 8a predating item 14) | Carry both through | `evaluation/variants.py` `_with_pipeline`; declarations for nodes a variant removed are dropped rather than refusing the arm |
| D4 | Tool execution time inside an `AgentNode` charged the node's wall-clock check and never the run's, so moving work into a tool exempted it from the run axis | Charge it, without double-counting | `nodes.py` `_run_tool` charges elapsed minus what nested `ModelHandle` calls charged themselves, on every exit path; `Deterministic` fixed-point calls pass `charge_run=False` because the function timer already covers them; `docs/pipeline.md` §5 states the rule |
| D5 | `Manifest.restore` dropped `recording`, so a resumed run under a sampled envelope closed claiming `payload_rate` 1.0 | Fix | `manifest.py`, round-trip test |
| D6 | A resumed consultation's answer filed into the cassette with the tool's name as `node_id`, corrupting `Cassette.nearest` miss diagnosis | Fix | `nodes.py` `_deliver` threads the real node id |
| D7a | `cassette.load_entries` returned lists of lists, had no callers and no tests | Delete | Deleted |
| D7b | Count/version drift: `docs/conformance.md` said "Seven" and "nine" in one document; `conformance/__init__` said "Seven ship"; `trajectory.py` docstring claimed `0.14`; `plan.md` said `0.15`; `handoff.md` said "eleven shipped documents" | Fix all five | Fixed; the trajectory docstring no longer repeats the number at all, so it cannot drift again |
| D8 | FT-03 reported `PASSED` when no contamination check was ever run (`contamination_threshold` unset), a green row meaning "did not look" | Elicit rather than refuse | `too_similar`, the eighteenth question, required at `measure`; FT-03's no-check detail names the entry; refusing outright was rejected because it punishes the legitimate deduped-by-source case dogfood-1 run 2 exercised |
| D9 | `http_fetch` fetched private address space by default (loopback, RFC-1918, `169.254.169.254`), an SSRF surface once an agent runs server-side | Refuse by default, `allow_private=True` opt-out | `builtins/http.py`, applied per redirect hop |
| D10 | `MetricChange.moved` returned `False` when there was nothing to pair, reading "no data" as "did not move"; cassette docstring implied cross-process safety | `moved` is `None` there; state the lock's boundary | `evaluation/compare.py`; the metric lands in `undecided` and `reason` says why |

**One deviation from a ruling, flagged at landing and standing unless overruled.** D9 as
approved said "resolve the host"; what shipped checks the URL itself — IP literals and
`localhost` — and does not resolve hostnames. A `getaddrinfo` per host breaks the offline hard
requirement (`simple-agents.md` §10): in offline CI each lookup hangs to its resolver timeout,
and a fail-open DNS check adds little against a rebinding-grade attacker anyway. The
limitation is stated in the tool's docstring, `docs/tools.md` §5, and `CHANGELOG.md` ("a
hostname that resolves privately is not detected").

**One convention moved, with approval.** The skill's word budget
(`tests/test_procedure.py` `WORD_BUDGET`) rose from 1200 to 1300. The file was at 1199 before
the gate-flow sentences landed, so the ceiling was saturated before any change; the budget's
purpose (the skill must not restate the documents) is unchanged and the test's docstring still
states it. The skill sits at 1242.

**Re-recording note.** D1 and D9 changed `http_fetch`'s body, so its derived version changed
and recorded calls to it miss. None of the library's own test cassettes hold one; dogfood-2's
do, and that project is an artifact rather than a maintained dependency.

## The positioning re-ruling, and the edits it produced

Thilina's framing, 2026-08-09, ruling on the session's usefulness assessment: the goal is a
library that helps people do something **easily, correctly, and with less effort** — the right
tool at the right time for some people, not the only way; the Simple Transformers value shape.
A 2026 coding agent can implement PyTorch from scratch; it should not have to. The
moat-flavoured framing in the docs ("coding agents get the statistics wrong") had drifted from
that goal, and dogfood-2 produced a counterexample to it: DF2-D8's hand-rolled Wilson interval
was correct, chosen for the right reason. What the evidence supports instead is the process
claim — three sessions measured the wrong thing, at an n a tool default chose, in artifacts no
check could see — and the routing lesson: for a library read by coding agents, convenience
must be legible at decision time, which is why refusals hold the path and prose does not.

Seven edits landed under that ruling (each proposed with original text and options, decided
individually, **no amendment notes anywhere** on Thilina's instruction — they get taken out of
context):

| Where | What changed |
|---|---|
| `README.md` "Why this exists" | The failed-prediction vignette replaced with the positive claim: the discipline as tested code, "a coding agent could build all of it from scratch; it should not have to" |
| `handoff.md` coding-agent objection | Restated to the process claim with DF2-D8 cited, plus the Simple Transformers value-shape paragraph |
| `handoff.md` "not Simple Transformers" | Split: the value shape is ST's, the market analysis is not |
| `simple-agents.md` §1.2 | "A convenience wrapper of any kind" row is now "A thin wrapper whose only value is saved glue"; ease of use named as a goal, not a disqualifier |
| `simple-agents.md` §1.5 | The crypto analogy replaced with the PyTorch one |
| `docs/procedure.md` | Stage gates flow forward: the tier line says most projects move to `evaluated` at stage 3, and both early gates end by setting the next stage in `brief.toml` — the DF2 §10 gate-reads-as-an-ending finding, closed structurally |
| `docs/index.md` | Opening sentence matches the README's |

## Open from this session, undecided

**The headline project for launch.** Thilina judged dogfood-2's task a poor headline case: its
fate depended on the world (retailers publishing measurements), so the punchline was about the
market rather than the library. The criteria he set for a launch article, against the ST
precedent: an artifact someone can hold and find cool, value obvious, the whole fate inside
the repo; numbers support the story rather than being it. His proposal, discussed but not
decided: **a personal book-recommendation and library agent** over his own Goodreads export
plus open book-metadata APIs (Open Library). The design that makes it measurable rather than
vibes: backtest against his own already-rated books (hold out 40–50, predict would-like,
ground truth already on disk), with false confidence reading as "it confidently recommended
books I already know I hated"; absence occurs naturally in Open Library metadata;
consultation has a real role (ask instead of guessing when the history is ambiguous); the
holdable artifact is the generated library-and-shortlist page. Known risks recorded:
recommendation quality itself has no cheap ground truth (only the backtest does — keep the
librarian and the recommender separate), and star ratings are noisy labels, which makes
`matches=` a real elicitation question. D2 and D3 above were prerequisites and are landed.
Not scheduled, not in `plan.md`; a decision for Thilina.
