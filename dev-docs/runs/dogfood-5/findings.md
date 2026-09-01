# Dogfood #5 — findings

A TV Time replacement, product-first, against the wheel at `9b8e96c`. [`setup.md`](setup.md#L1)
beside this file is how it was set up and §4 there is the list of questions this record answers
first. [`../dogfood-4/findings.md`](../dogfood-4/findings.md#L1) and the three records before it
are not restated; this document cites them. Findings numbered `DF5-Dn` and `DF5-Pn` are this
run's; `DF4-` prefixed ones are dogfood #4's.

**The run ran 2026-08-20 to 08-24 and this record was written 2026-08-25**, against a frozen copy
of the project taken at commit `ee2cc51` (2026-08-24 23:44 local, 116 commits, clean tree). The
builder kept working on the live checkout after the freeze, on an offline cache for the mobile
app, and none of that is read here.

**Two things about this record's own claims, stated first.** Three of the analysis's early
readings did not survive verification and are listed in §1.3, including the one that shaped the
first day's reading of the consultation evidence. And this run's largest findings are about a
mechanism the library shipped for the model's case and that met a product for the first time,
so several entries below cite the same two hundred lines of `nodes.py`, `context.py` and
`channels.py`; they are separate findings because each produces a different candidate.

**Project:** `/home/thilina/Projects/dogfood-5`, analysed at `/home/thilina/Projects/dogfood-5-frozen`.
Fresh coding-agent session. The prompt was [`setup.md` §3](setup.md#L74)'s two sentences and
nothing else. Nothing in this document was written into the project.

Final totals across **2,669 run directories** (2,393 agent runs and 276 evaluation rollouts
under 14 evaluations): **52,318 model calls, 12,054 tool calls, 1,654 consultation records,
$7.65 of hosted cost and 132,589 device-seconds of a local RTX 3090**, which is 36.8 GPU-hours.
`simple-agents check`: **0 failed, 19 passed at tier `evaluated`**, on the frozen copy.

| | dogfood #4 | dogfood #5 |
|---|---|---|
| Elapsed | ~47h13m, two overnight gaps | **~102h30m** setup commit to last commit, of which 51.6h is one gap spanning 2026-08-22 with no run and no log section |
| Runs in the envelope | 3,293 | 2,669, **2,313 of them corpus passes under the default role** (`DF5-D4`) |
| Model calls | 22,475 | **52,318** |
| Tool calls | 12,582 | 12,054 |
| Consultations | 104, 97 `answered`, none by a person | **1,654 records of 109 questions; 2 answered by a person, replayed as 14 `answered`** (`DF5-D2`) |
| Recorded cost | $2.7055 | **$7.65 hosted plus 36.8 GPU-hours**, 25 runs unpriced (`DF5-D15`) |
| Nodes, and kinds | 11 (7 D, 3 LLM, 1 Agent) | **28 across seven pipelines (21 D, 7 LLM, 0 Agent)** at the freeze, through 52 pipeline versions by `behaviour_fingerprint` |
| Model identities | 3 | 2: `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` on 2,326 runs and `gemini-3.7-flash` on 103 |
| Project tools written | 6 | **0**; five library tools bound, and one fetch path that bypasses the tool layer (`DF5-D13`) |
| Tier | `evaluated` | `evaluated` |
| `simple-agents check` | 11 of 11 | **19 of 19** at the freeze; 18 of 19 for most of the run, FT-25 being the builder's own open judgement |
| Brief entries | 26 | 42, two sourced to the coding agent |
| Decisions recorded | 16 | **31**: 13 `shape`, 7 `constant`, 4 `presentation`, 3 `dependency`, 3 `measurement`, 1 `prompt_rule`; 29 `agreed`, 1 `changed`, 1 `not_applicable` |
| Evaluations attempted | 33 | **15 identities**: 14 results files, 14 run directories, overlapping on 13 (`DF5-D17`) |
| Build log | 265KB, not asked for | **396KB, 6,700 lines, 68 exchanges, not asked for**, and not kept live until exchange 43 (`DF5-D6`) |
| Commits | 1, at setup | **116** |
| Product | a display over stored output, built at the end | a website, a JSON API, a Flutter app on the builder's phone, a labelling surface, cron; 51 live runs, 275 labels and 40 pairwise comparisons by the end user |

---

## 1. Method, and what did not survive verification

Every figure below is measured from the project's own artifacts unless it says otherwise, and
names the file it was read from. Where a library defect is claimed it is reproduced against the
wheel the project ran, `9b8e96c`, installed at `dogfood-5-frozen/.venv`; where the question is
whether it is still open, against the current source, and the entry says which.

### 1.1 What was read, and how

The artifacts are the instrument. Four passes over the frozen copy produced ledgers this record
cites rather than repeats, each figure in them naming its file and line or key path: a ledger of
the build log's 69 sections and every claim, quote and error in them; a ledger of the 14 results
files, the example set, the labels and the probes; a census of the code, every `Pipeline`, every
channel, and every library facility the project rebuilt by hand; and a census over all 2,669
manifests and 3.1GB of trajectories, with the time reconstruction in §1.4. The ledgers are working
files and are not committed; what they found is here with its citation, so a reader who wants the
source opens the project.

Then the reading that the ledgers cannot do: `idea.md`, `research.md`, `design.md`, all 1,484
lines of `brief.toml`, `HANDOFF.md`, `ROADMAP.md` and `README.md` read whole; the check run three
times on the frozen copy and its four notes read as findings; the library's own
`simple-agents report runs/` run once, which the project never ran (`DF5-D6`); and the wheel's
source read wherever a mechanism was claimed, because a claim about what the library does is
checked against what it does.

**Verification discipline, stated because it changed three conclusions.** A mechanism claimed
from an artifact was checked in the source before it was written down; a mechanism claimed from
the source was checked in the artifacts. §1.3 is what that cost.

### 1.2 The build log, which was not asked for and appeared, late

[`setup.md` §5](setup.md#L109) removed the build log from the prompt for the second run running,
on the ground that `docs/procedure.md` instructs one and FT-33 now reads it.

**It appeared, and it is the largest artifact of its kind any run has produced**: 396KB, 6,700
lines, 69 dated sections covering exchanges 1 to 68. It records the builder's words verbatim at
134 marked points, retracts its own claims where a measurement overturned them, and carries the
run's timings in the one form the manifests cannot: the elicitation stages, which happened before
any run existed.

**It was not kept live.** The first project commit is `169c8b2` at 2026-08-23 23:06 local, three
days and 1,233 runs after setup, and the next commit is `673c06f` "Build log: exchange 43, and
keep it live from here". Exchanges 1 to 42 were written in batches. FT-33 fired during that period
and was read as noise (`DF5-D4`); `HANDOFF.md:334` closes with "Keep `BUILD-LOG.md` live", an
instruction the coding agent wrote to its successor after having not followed it itself.

**It carries no `WAITING ON BUILDER` marker**, as predicted at setup: zero of either marker in
6,700 lines, so the waiting figure is lost for the fourth run running. What it does carry is
clock times in its prose, and §1.4 shows they are read stamps rather than composed ones.

### 1.3 What did not survive verification

Three claims this analysis made in its first hours, and what corrected each. They are here
because the record's method is that a reading is checked before it is written, and these are the
ones the check caught.

1. **"No manifest records a consultation."** A census read a key named `consultations`; the
   manifest's key is `consultation`. The trajectories carry 1,654 consultation records. Corrected
   the same hour; `DF5-D1` and `DF5-D2` rest on the corrected figure.
2. **"FT-33 fails whenever an end user uses the product."** Wrong mechanism. `_latest_run` in
   [`artifacts.py`](../../../src/simple_agents/conformance/artifacts.py#L423) `_latest_run`
   prefers a run that is not live, so the check dated the work by the newest corpus run, and the
   corpus pass the coding agent itself was running is what tripped it. The finding stands in a
   different shape as `DF5-D4`.
3. **"`used_through` is absent from the installed wheel."** A verification script read an
   attribute named `key`; the question object's attribute is `name`. The question was present,
   fourteenth at brainstorm and ninth required, as the build log of `P3-30` says.

And four claims the project's own record makes that the artifacts contradict, each carried into a
finding rather than corrected in the project:

- `design.md:186-189` and `tvtime/store.py:3-6`: the library's memory store holds the answers to
  consultations. No `MemoryStore` is constructed anywhere and `memory` is `null` on all 2,669
  manifests (`DF5-D11`).
- `brief.toml`'s `someone_there`: "A refresh the end user clicked suspends and asks them." The
  only pipeline built with `present=True` has a consultation that is dead code, and no run ever
  suspended (`DF5-D3`).
- `brief.toml`'s `budget` and `context_limit`: per-node budgets and a context policy on two
  `AgentNode`s. The project has none (`DF5-D6`, `DF5-D7`).
- `HANDOFF.md:15`: "65 exchanges". The log reaches exchange 68; the handoff was written before
  the last three.
- `BUILD-LOG.md:230-246`: FT-36 "would have reported `pass` while reading **zero** candidate
  rows" had the survey stayed under sub-headings. `_tables_under` does drop a table under a
  sub-heading, as the log read; but `ft_36` then fails on "holds no table" and again on "a
  header and no candidate under it", so the check would have failed, not passed. The log's
  method was right and its conclusion was not, and it is the one check the coding agent read
  the source of.

### 1.4 What the timestamps say, and the answer to the deferred entry

[`plan.md` §2.2's timestamp entry](../../plan.md#L303) waits on whether the run manifests carry
what the protocol asked the build log for: elapsed per stage. Measured on this run's 2,669
`started_at` and `ended_at` stamps against the log's 69 dated sections:

- **From `build` onward the manifests carry it.** Runs fall on four UTC days (08-20: 56, 08-21:
  1,357, 08-23: 583, 08-24: 673), with hour-level resolution, and every clock time the log's
  prose carries matches a run to within a minute once read as Europe/Amsterdam local time:
  `shelved.json at 03:21:18` is `queue-20260824-032118` at 01:21:18Z exactly, and the heading
  `finished (11:32)` is 0.1 minutes after the pass's last run ended. The log's few clock times
  are read stamps, and dogfood #3's finding of composed ones does not repeat here.
- **Before `build` they carry nothing.** Brainstorm, research, shape and the design were done
  between the setup commit at 15:14Z and the first run at 17:28Z on 2026-08-20, and the only
  record of how that time divided is fourteen log sections carrying a date each. The manifests
  cannot date what happened before a run existed, and that is the half of the protocol's
  question the entry's decider was asking about.

So the entry's decider is answered both ways at once: the manifests replace the requirement for
every stage after the first run, and the elicitation stages need something else, which is either
a clock on the log's headings or nothing. §4 carries it forward.

### 1.5 What this run destroyed

Nothing the checks read, and two things they do not. Every one of the 14 results files has its
seeds matching the manifests in its directory, except that `evals/results/eval_a3d8fc5f7423.json`
names a run directory that is not in the tree, and `runs/eval_7423149289e3/`'s rollouts postdate
the results file that describes them by seven minutes with different totals (`DF5-D17`). The
project's git history holds no deletion of either; the library refuses a used evaluation
directory, so the second was cleared by hand and re-run without `results.write()`.

### 1.6 What this analysis did to the project

Nothing. The frozen copy was read through `.venv/bin/python` and `.venv/bin/simple-agents`
directly, never `uv run`, so the installed wheel was not re-synced; its sha256 is the setup
commit's. The live checkout was not opened after the copy was taken.

---

## 2. What the run met

**The ship criterion, [`plan.md`](../../plan.md#L7)**: v0.1 ends "when a dogfood run produces no
library defect worth building." Not met. §3 carries twenty-nine library findings and three
documentation findings, and the first three would each have changed what the end user of this
product experienced.

**The tier.** `evaluated`, declared at `brief.toml:1`, all six stages reached, all nineteen checks
passing on the frozen copy. The headline that tier rests on is read in `DF5-D5`.

**The product, which is what this run was set up to test.** `setup.md` §4's first question was
whether the run would again end in a bare display over stored output. It did not. The product
section of `design.md` classifies fourteen interactions across all four kinds, with the sentence
"Every kind is present, which is what says the surface reaches the agent rather than being a
display over stored output" written by the coding agent unprompted (`design.md:237-238`). What
was built is a FastAPI site over seven pipelines, a versioned JSON API mirroring every route, a
Flutter app installed on the builder's phone, a labelling surface with its own session model,
and two cron lines. 51 of the 2,669 runs are live, made by the end user through the site; the
end user recorded 275 labels and 40 pairwise comparisons through it. `DF4-N14` is answered in the
opposite direction, and what it cost is `DF5-D19`: the product was mostly built after `ship`.

**The questions §4 of `setup.md` named, in its order.**

| Question | Answer, and where |
|---|---|
| Does the product concept reach the builder? | Yes, above |
| The research stage, cold | Fired and held: nine parts decomposed before anything was looked up, every candidate with an outcome, a licensing table the builder's own question produced, and the survey's central finding corrected by the builder from domain knowledge the coding agent's search did not reach (§3.6). Two entries sourced `coding_agent`; FT-36 passed |
| `DF4-Q1`, a real answerer | Two answers from a person, to one question, in four days; 109 questions asked, five reached the inbox. `DF5-D1`, `DF5-D2`, `DF5-D3` |
| `DF4-Q2`, the store split | The product kept its state in its own store beside its own data model, as dogfood #4 did. `DF5-D11`, `DF5-D12` |
| The scheduler entry's decider | cron, two lines, written on the last day; the trigger the product actually needed was resume-when-answered, and the product solved it by re-running (`DF5-D3`). The host's scheduler expressed everything else |
| `DF4-Q5`, a count seam | The project's counts are page sizes and labelling progress, which the library does not cover; the run-progress case carries no count. Not met in the form the entry describes |
| The thin-agency reading | Came true: zero `AgentNode` at the freeze, and the builder opened the post-ship conversation with "expanding the agency". `DF5-D7`, `DF5-D8`, `DF5-D9` |
| Twelve breaking changes used fresh | Used: fan-out on `LLMNode` with `keep=` and `max_failures`, `Loop`, `EvalSuite(baseline=)`, `results.report()`, `PacedClient`, `Cassette`, `Redaction`, `HostPolicy` on 1,668 runs, `SimulatedEndUser`, `Label`/`write_labels`, `Maybe`/`value_or`. Never reached: `ProgressBar`, `on_progress`, `on_rollout`, `simple-agents report`, `watch`, `node_metrics`, `results.grouped`, `compare`, `prompt_differences`, `RetryPolicy`, `on_error`, `role=`, `budget_per_item`, `ctx.fetch_policy`, `Pipeline.resume`, `MemoryStore` |

---

## 3. Findings

Library findings first, in the order a maintainer should read them, then the documents. Each
names its evidence, what it cost this project, and whether it is about the library or about the
task. Thilina's six notes are quoted verbatim where they land and numbered `DF5-N1` to `DF5-N6`
for the inventory to carry. `DF5-N6` is from sitting 1 rather than from the run.

### 3.1 Consultation met a product

### DF5-D1 — One `Unavailable` silences every later consultation in the run, and the product's inbox got 5 of 109 questions

**Acted on:** `DF5-I01`, `DF5-I37`.

**Library.** The largest finding in the run, and the one the run was set up to produce.

**The mechanism.** [`tooling.py:151`](../../../src/simple_agents/runtime/tooling.py#L151) `_run_tool`
`_execute_tool_call` asks `run.no_one_to_ask(tool.name)` before calling a `ConsultTool`, and
[`context.py:1305`](../../../src/simple_agents/context.py#L1305) `no_one_to_ask` answers from a
per-run, per-tool memo that the first `Unavailable` sets. Every later `consult` call in that run
is answered by `_no_one_answered` without reaching the channel: a `consultation` record is emitted
with `resolution: "unavailable"`, `blocking: true`, and the **first** call's reason copied onto
it. `docs/tools.md` §4.6.3 states the rule for the model's case: "The model is told once, and the
rest of the run is answered from that. Every later question to that tool returns the same thing
without reaching the channel again, and each one is recorded."

**What it met.** The queue pipeline's `resolve_ambiguity` node (`agent.py:402-430`) is a
`Deterministic` that walks the end user's queue and calls `ctx.call_tool("consult", ...)` once
per show untouched for 120 days: a distinct question per show, with two options each. The
channel (`tvtime/channels.py:56-61`) shelves the question in the project's store and returns
`Unavailable(reason="nobody is on the site; the question is shelved for later")`. The shelf is the
site's questions page, which is the product's whole consultation surface in background mode.

**Measured.** 1,654 consultation records across 36 runs, 1,640 `unavailable`; 109 distinct
question texts; per run min 1, median 17, max 99. The shelf, `data/people/builder/shelved.json`,
holds **7 entries covering 5 distinct questions**, the last added 2026-08-24 03:21 local, after
which some forty more queue runs added nothing: each run's first stale show was already pending
and `Store.shelve` deduplicates an open question (`store.py:324-325`), so the channel was reached
once per run and refused. The end user was asked five things in four days about a queue the
agent had 109 questions about, and every one of the other 104 is recorded as "shelved for later"
in the channel's own words, on a question the channel never saw.

**What it cost the product.** The design the builder specified and the brief records
(`consultation`, `someone_there`) is that a background run shelves what it cannot settle and the
person answers when they next open the site. That design worked for one question per run. The
trajectory cannot show it: the reason string on 1,640 records is the channel's, so a reader of the
record, human or check, sees 1,640 shelved questions and a shelf that does not match.

**Whether it is a defect or a design.** The rule exists so an `AgentNode` that keeps asking a
person who is not there is a count rather than a hundred round trips, and for that case it is
right. A `Deterministic` node asking one question per item is the other case, and the rule
cannot tell them apart: it keys on the tool's name. Nothing in the docs says the second case is
silenced, nothing in the record says it happened, and the channel's own text is copied onto
questions it never received. Three things to decide, and the entry does not decide them: whether
the memo is per node execution rather than per run, whether a channel that shelves declares
itself so it is reached for every question, and whether a record answered from the memo carries
its own reason rather than the first call's.

**Still open** in the current source: `_no_one_answered` and `no_one_to_ask` are unchanged at
`HEAD`.

### DF5-D2 — A consultation has no identity beyond its wording, and every count of consultations is a count of recordings

**Acted on:** `DF5-I02`.

**Library.** The measurement half of `DF5-D1`, and the answer to `DF4-Q1`.

**Two answers from a person.** The 14 `answered` records are one question about one show, *The
Lincoln Lawyer*, answered by the builder twice on the shelf: "coming back to it" on 2026-08-23
18:14 local and "gave up on it" the next day at 03:03. Every later queue run's channel found the
stored answer by exact text match (`channels.py:57-59`, `store.answered()` at `store.py:340-342`)
and returned it, and the library recorded each replay as `resolution: "answered"`, `answered_by:
"end_user"`, `read_by: "rule"`. So the artifact says the end user answered fourteen times; the
end user answered twice. The record is not wrong about who the channel was for, and it has no
field for whether a person was reached this time.

**The wording moves and the answer stops matching.** The question embeds the gap: "last watched
it 195 days ago" on the 23rd, "196 days ago" on the 24th. The shelf holds *The Lincoln Lawyer*
twice and *Record of Ragnarok* twice for that reason, one entry per day's wording, and the
builder answered each pair. A stored answer is found only while the text is identical, so the
product will re-ask an answered question the day after it was answered. That is the project's
wording, and it is also the only identity the library offers: the cassette keys a consultation on
its question text (`DF4-I01` found the same for replay), `consult` takes no `about=` or key, and
the project's own `Store.shelve` has an `about` parameter that nothing passes.

**What the library's figures then say.** `counts.consultation` on the manifest, the
`consultation_resolutions` and `unanswered_consultations` figures in a results file, the
`report`'s tool line "consult registered in 317, called in 38", and FT-25's and FT-31's readings
all count records. On this product they say 1,654 consultations, 1,640 of them unanswered. What
happened was 109 questions, five put to a person, two answered. No figure the library reports
can be read as the second sentence.

**What FT-25 and FT-31 check, and did not see.** FT-25 passes where a consult tool is registered
and offered to a node (`checks.py` `ft_25`); FT-31 passes where the latest live run's channel
names `end_user`. Both passed throughout. Neither reads whether a question reached a person, and
the answer here is that the mechanism designed to reach one did not, for 104 of 109 questions.

**Candidate shape.** An identity on a consultation separate from its wording, which is also what
a shelf, a cassette and a product's inbox each need; and a field on the record saying whether the
channel was reached, which is what separates fourteen answers from two.

### DF5-D3 — `Suspend` is an `Exception`, engaged mode never ran, and the product-first run never exercised the product story

**Acted on:** `DF5-I39`, `DF5-I03`, `DF5-I04`, `DF5-I37`.

**Library.** [`errors.py:114`](../../../src/simple_agents/errors.py#L114) `Suspend` derives from
`SimpleAgentsError`, which derives from `Exception`. `docs/pipeline.md` §1.8 and the class's own
docstring invite raising it from a `Deterministic` function or a channel. The queue node that
holds this product's only live consultation wraps the call in `except Exception: continue`
(`agent.py:423-424`), so had its channel ever raised `Suspend`, the node would have swallowed it,
continued, and left no record: no `pending` resolution, no suspension on the manifest, no error.
Python puts `SystemExit` and `KeyboardInterrupt` under `BaseException` for this reason. Nothing in
the docs says not to catch around `ctx.call_tool`, and nothing in the record can show that it
happened.

**It is latent here, and structurally so.** Zero of 2,669 manifests carry a suspension, zero
records carry `resolution: "pending"`, and `Pipeline.resume` is called nowhere in the project.
Two reasons, both in the code: the only pipeline ever built with `present=True` is discovery
(`web/app.py:1419`), whose consult in `select` reads `inputs.kept["passed_over"]`, a key nothing
emits (`agent.py:1596`, `keep=["pool_looks_like", "directions"]` at `:1716`), so it is dead code;
and the queue pipeline, which asks everything, is built `present=False` from every call site
(`web/app.py:1031`, `scripts/first_run.py:78`). The engaged mode that `channels.py:27-42`
implements, that `design.md`'s product section describes, and that the brief's `someone_there`
records as what the code does, cannot be reached.

**What that means for `docs/product.md` §4.** The product story the library ships is a request
that suspends across the surface and resumes on answer. The first product-first project used
that story for none of its 1,654 consultations, and it did so by design: a queue refreshed in the
background on every store write cannot stop and wait, and the answer the builder gave
(`brief.toml` `consultation`, verbatim) is the two modes the code implements. The product needed
shelving, and the library's shelving is `Unavailable` plus `on_reply(unavailable="proceed")` plus
whatever the project builds to hold the question, which is what `DF5-D1` measured. `DF5-P2` is
the document half.

**What `Pipeline.suspensions` was used for.** Read once, at `web/app.py:1532`, and rendered as a
count of runs "stopped to ask you", which was always zero.

### DF5-D20 — The evaluation's stand-in end user was configured on 249 rollouts and never asked

**Acted on:** `DF5-I40`, `DF5-I06`.

**Library.** `SimulatedEndUser(model=make_client())` on every evaluation since `eval_537a12d02a72`
(`scripts/evaluate.py:236`; `end_user: {"answered_by": "simulated"}` on 249 manifests), and
**zero consultation records in 276 rollouts**. The evaluated pipeline is discovery, whose consult
is the dead code above; the consultations happen in the queue pipeline, which was never evaluated.
So the evaluation half of consultation that `P3-9` built, the stand-in and the misreading figures,
measured nothing, while FT-25 passed on the tool being "offered" to a node. `evaluate.py:145-149`
says why the tool is registered: "FT-25 reads the run's manifest, and a project whose brief says
the agent asks its user should not have runs where nothing can." The check shaped the
registration and never saw that the registered tool was unreachable.

**How much of the consultation surface this project reached, measured 2026-08-25 at sitting 1**
against the frozen copy. **Two call sites in the whole project.** `select` in the discovery
pipeline (`agent.py:1596-1606`) is dead twice: it reads `inputs.kept.get("passed_over")` where the
fan-out above it declares `keep=["pool_looks_like", "directions"]` (`agent.py:1716`), so the loop
skips every candidate, **and it discards the call's return value**, so an answer could not have
changed anything had one arrived. `resolve_ambiguity` in the queue pipeline (`agent.py:402-430`) is
the one that works and the one that produced all 1,654 records. **Zero uses of `on_reply`,
`Reply.chose`, `consult(match=)`, `consult(read=)`, `ModelReader` or `ModelAnswer`**: the working
site tests its answer with `"gave up" in answer` over the reply's text. One structural reason for
part of that: `route=` is one decision per node execution and this node asks one question per show
inside a loop, so the routed pattern `docs/tools.md` §4.6 shows is unavailable to it, and no other
pattern is shown. `DF5-I05`, `DF5-I06`.

### 3.2 What the checks read

### DF5-D4 — The corpus passes ran as the agent, and every run-reading check read them as the agent's runs

**Acted on:** `DF5-I08`.

**Library.** 2,313 of the 2,669 runs are `scripts/build_summaries.py`'s Wikipedia resolution and
summary passes, under `RunEnvelope(run_dir, cost_basis, redaction=secrets)` with no `role`
(`build_summaries.py:201-202`). `docs/run-envelope.md` §2.1 documents `role=` for exactly this
and the project never set one; nothing in the procedure or the scaffolds suggests a role for a
batch pass, and the manifests carry `role: "agent"` on all 2,669.

**What that did to the checks.** `_latest_run` prefers a run that is not live, so for most of the
run `<latest>` was a corpus run: FT-13, FT-14 and FT-15 certified a two-node summariser rather
than any of the product's pipelines, and FT-33 dated the work by it. During a corpus pass a new
run finished every few seconds, so FT-33 failed continuously while the log was hours old, which
is what its rule says and not what it is for. The coding agent's reading, `HANDOFF.md:5-8`: "You
may see 2: FT-33 compares `BUILD-LOG.md`'s mtime against the newest run under `runs/`, so it
fails while any job is writing runs. That is the check working." And `BUILD-LOG.md:4813`:
"2 failed, 17 passed, which is FT-25 and the FT-33 the corpus run trips every few seconds." A check
whose failure is expected during legitimate work is a check the next session is taught to
subtract, and this handoff teaches it.

**Two things to decide.** Whether a batch pass that is not the agent needs a role the procedure
puts in front of the coding agent, since the field exists and was not found; and whether FT-33's
rule is right for a project whose runs are made by something other than the coding agent's
build work. `ft_33` is identical in the current source.

### DF5-D24 — FT-03 passes having run nothing

**Acted on:** `DF5-I09`.

**Library.** On the frozen copy `simple-agents check` prints `pass FT-03`, and under it: "No
threshold was set, so this evaluation ran no contamination check." [`checks.py` `ft_03`](../../../src/simple_agents/conformance/checks.py#L1299)
`ft_03` returns `PASSED` where the results file carries no contamination report. The brief's
`too_similar` answer explains why no threshold fits this project, and the explanation is sound;
what the report line says is that the check passed, and it did not run. The suite has an
outcome for a check that could not be made, and `ft_03` does not use it. `contamination` is
`null` in all 14 results files, and `nearest_cross_split`, which `P3-28` shipped so a builder
could judge the pairs, was never called.

### DF5-D5 — The headline the tier rests on is a pipeline that recommended nothing, three days and 100 commits old, and nothing says so

**Acted on:** `DF5-I10`.

**Library.** `brief.toml:3` names `evals/results/eval_537a12d02a72.json`, written 2026-08-21
00:49Z by the six-node pipeline at `behaviour_fingerprint sha256:37365dd7…`, judge prompt v2, on
the local model. In it **all 27 rollouts returned `recommendations: []`**: `accuracy` 0.0
[0.0, 0.2991], `surfaced_share` 0.0, `reciprocal_rank` 0.0, `false_confidence_rate` 1.0
[0.7009, 1.0], because the answer function is `lambda output: output` and an empty list is an
assertion. FT-01 to FT-07 read that file and pass: it has a held-out split, seeds, intervals and
absence cases. The number is honest and it is zero.

**What is beside it on disk.** Twelve later evaluations, and the `judge_held_out` sequence moves
`accuracy` 0.048 to 0.714 [0.4286, 1.0] between prompt v2 and v5 (`eval_0e4577077f0b` to
`eval_7423149289e3`). The shipped pipeline at the freeze has nine nodes and a different graph
fingerprint; the check's own FT-35 note reads "2,650 made by a pipeline this one has changed
since". `ROADMAP.md:142-147`, by the coding agent: "The headline number is three days stale and
the pipeline has moved a long way … This project claims tier `evaluated`, which means it reports
a number, and the number no longer describes the code that would produce it. Re-running the
suite is the single most overdue thing here."

**Nothing joins the results file to the pipeline.** The results file carries
`config.graph_fingerprint` and no `behaviour_fingerprint`; the manifests beside it carry both. So
even a check that wanted to say "the headline was produced by a pipeline that no longer exists"
has nothing in the file to compare, and the note the check does print, that the run it read and
the file it read "describe different measurements", is the whole of what the library can say. It
said it, and it was not acted on (`DF5-D6`).

**What the finding is.** A project at tier `evaluated` shipped with a headline of zero from a
pipeline it replaced twice, every gate green. `DF4-D7` asked what governs the road after the last
gate; `P3-7`'s `confirmed_against` was the answer for the brief, and a results file has no
equivalent. The candidate is the equivalent: the results file carries the behaviour fingerprint,
and `check` says, as a failure or a note, that the reported measurement was made by a pipeline
the project no longer has.

### DF5-D6 — Three instructions in `procedure.md` were not followed in 116 commits, and the one gate was run 21 times

**Acted on:** `DF5-I11`.

**Library.** `docs/procedure.md` as installed says three things without a gate behind them:

| Instruction | Line | What happened |
|---|---|---|
| "Keep a `BUILD-LOG.md` alongside them, recording each exchange with the builder as it happens" | 48 | Written in batches until exchange 43 (§1.2) |
| "Record what the entries were read against. `confirmed_against` holds `pipeline.behaviour_fingerprint(model=client)` … `simple-agents check` names the ones due when the two differ" | 63-65 | Never recorded. The check's note naming twelve entries due, with the fingerprint to record, printed on every one of 21 `check` runs the log records |
| "Read what the runs spent and what they produced, with `simple-agents report runs/`" | 252 | Never run: zero occurrences in the log, `README.md` or `HANDOFF.md`; `simple-agents check` appears 21 times |

The instruction with a gate, `simple-agents check`, was followed every time. `DF4-I30` recorded
the first of these three for dogfood #4 and `P3-7` answered it with FT-33; the other two have no
check and were not done. The builder reminded the coding agent about the log twice, *"And don't
forget the build log"* (`BUILD-LOG.md:3630`) and *"Keep build-log uptodate and live"* (`:4061`),
which is `DF4-N4` again with FT-33 in place. What `confirmed_against` would have caught is `DF5-D7`: `budget`,
`context_limit` and `agency_boundary` describe two `AgentNode`s the project does not have, and
the coding agent recorded in `decisions.no_agent_nodes` that "both are the builder's own answers,
and neither is rewritten by the coding agent", which is the rule the docs impose and which leaves
a builder's stale answer stale forever unless something makes the re-reading a gate.

**What `report` would have shown on day one.** The library's own `simple-agents report runs/`
on the frozen copy prints, under `judge_candidates`, "produced nothing: 29 unit(s) of work, 29
of them fan-out item(s), spending 251 of 3,451 model call(s)", and under `find_candidates` "5
unit(s) of work, spending 117 of 175 model call(s)": the two failures the build log spends
exchanges 15, 16 and 20 discovering by hand. `P3-22` to `P3-26` built the instrument for exactly
this project's failure, the procedure tells the coding agent to run it, and it never did.

**Candidate shape.** Put the rule where it is broken: the two instructions that matter become
gates. `confirmed_against` at `ship` is one; what a report gate looks like is the question.

### DF5-D7 — `agency_boundary` names two agentic steps in a project with none, and every check passed

**Acted on:** `DF5-I13`.

**Library.** `brief.toml` `agency_boundary`, the builder's answer at `shape`: "Agentic: discovery
… and the review hunt … only the two named ones `AgentNode`." At the freeze the seven pipelines
hold 21 `Deterministic` and 7 `LLMNode`, and `git log -S "AgentNode("` finds no construction in
`agent.py` at any commit; both were removed before the first code commit, for reasons
`decisions.no_agent_nodes` records.

**A third one ran and is named nowhere.** Measured 2026-08-26 at `P3-35`'s prototype, over all
2,393 run manifests: **18 runs hold a node whose `node_kind` is `agent`**, all on 2026-08-20
between 17:28Z and 21:44Z. Fifteen are `find_candidates` and `hunt_reviews` together; **three are
`judge_candidates` alone**, which the brief's `agency_boundary` does not name, which
`decisions.no_agent_nodes` does not name, and which this record said nothing about until now. It
was demoted to `llm` and appears as one in every later run. The two claims above stand: the runs
predate the first code commit by three days, so `git log -S` is right, and `both` is right about
the two the builder named. What was missing is that a third step decided for itself and nobody
counted it (`DF5-X9`). FT-32 passed throughout, because it reads the side-effect
words in `tool_effects` against the manifest's tools and nothing else (`checks.py` `ft_32`);
FT-34 reads whether the design's sections exist; FT-30 reads decision statuses. Nothing joins an
agency answer to the node kinds the manifest records, though both are on disk.

**The disagreement the brief records.** `decisions.no_agent_nodes`, status `changed`, the only
`changed` decision in 31: the builder's reading is *"if we aren't using AgentNode, we aren't
using agents"*; the coding agent's is that the shortlist cycle "still chooses where to look and
revises on what comes back, which is `agency_boundary`'s own test". Both are in the file, and the
library has no term for the second: `FT-11`'s rule is that a step choosing its next action from
what came back is an `AgentNode`, and the cycle is one that is not.

**Evidence for `P3-29`.** [`build-logs/what-a-decision-produced-build-log.md`](../../build-logs/what-a-decision-produced-build-log.md#L1)
proposes `produces` so a decision joins the manifest exactly. An `agency_boundary` that named its
steps would have failed the join on the first run without them.

### DF5-D8 — The tool contract blocked an agentic step, and the project found the routed loop on its own

**Acted on:** `DF5-I14`, `DF5-I40`.

**Library.** `decisions.shortlist_agency` was first recorded as an `AgentNode` over three
retrieval tools and withdrawn, in the brief's words: "`docs/tools.md` §3.3: *A tool may read
anything that is in its key, and anything a handle gives it. It may not read run state through
any other route.* A retrieval tool needs the viewer's ranked pool, which is run state and reaches
the node on an edge. Closing over it instead means closing over the store, and `scripts/evaluate.py`
builds **one** pipeline over a throwaway scratch store … Such a tool would have searched an empty
scratch store in every rollout and the builder's own taste in a live run, silently and with the
suite still green." The rule is right, and it leaves an `AgentNode` whose tools need the node's
own input with no way to be one: the input is neither in the tool's key nor a handle.

**What replaced it.** A cycle of `LLMNode` and `Deterministic` bounded by `Loop(max_iterations=3)`,
the model choosing an edge by filling a field a route reads, which `docs/pipeline.md` §1.2 names
("a revision loop with a fixed bound") without saying it is the answer to this need. The brief
calls the trap "live". The `report` line at the freeze shows the cycle running: `survey_pool` 65
executions over 7 runs, two iterations each.

**Candidate.** Either a handle that carries the node's input to its tools, or the docs stating
the loop as the pattern for an agentic step over per-run state, with the reason. The measured
cost of not having either is one sitting of the run and a decision recorded twice.

### DF5-D9 — No question is open-ended, and none asks what the builder wants the agent to do on its own

**Acted on:** `DF5-I15`, `DF5-I39`.

**Library.** Thilina's first note (`DF5-N1`, verbatim): *"The agent asks questions well, and they
are scoped better than before. But I think 'anything else' or open ended questions would be
useful for the builder to provide further info, feedback, or any other additions that were not
directly elicited."* Checked against the 46 questions in the wheel: none is open-ended, and the
procedure has no step for one. The scaffold for `agency_boundary` asks "whether the path is
known in advance or discovered from what the previous step returned. The fixed ones are
`Deterministic` and `LLMNode`; only the discovered ones need an `AgentNode` (FT-11)", which is
agency framed as a cost to justify, and no question asks what the builder wants the agent to be
able to do without them.

**What it cost.** The builder's wish had no home until after `ship`. `HANDOFF.md:24-27`, the
coding agent's own framing of the next job: *"This is what the builder wants to start with, in
their words: 'I want to discuss expanding the agency and making it usable and useful.'"* That
sentence is the third category of the protocol, something wanted and never asked for, arriving
after the last gate.

### DF5-D10 — Decisions the coding agent never noticed making, and the check that cannot see them

**Acted on:** `DF5-I16`.

**Library.** [`setup.md` for dogfood #4](../dogfood-4/setup.md#L66) said of FT-30: "What it
cannot see is a decision the coding agent never noticed making, which is the failure it exists
for." Thilina's third note (`DF5-N3`, verbatim): *"'gather_candidate_pool filters the catalogue,
ranks all 67,353 eligible shows, then truncates: return {**inputs, "pool": ordered[:pool_size]}'.
It made this unbelievably dumb decision WITHOUT asking me. I could have told it that that's
stupid."* Checked: from the first code commit `gather_candidate_pool` ranked every eligible row and
returned `ordered[:pool_size]` (`169c8b2`, then `agent.py:671-712`), 12 or 40 of 67,353; the
truncation moved to a shortlist over the top 2,000 at `33b2455`, on the builder's instruction.

**The coding agent's own count is larger.** `decisions.catalogue_intake_filters`: "the fourth
intake filter found to have been chosen without being asked"; `decisions.json_api`: "This project
has been bitten five times by a rule living in two places"; `ROADMAP.md:206-212`: "37 of 51
module-level constants are named in no document, eight of which change a judgement", and of six
constants added in one session "four were chosen by the coding agent alone and are named in no
document". FT-30 passed on every one of 21 runs. The `constant` kind exists for these and holds
seven decisions.

**Candidate.** A `constant` audit is computable: module-level numeric literals in the files that
build the pipeline, against the values named in `constant` decisions. It cannot judge which
matter, which is the coding agent's job the audit found it not doing.

### 3.3 Stores, artifacts and what the product built by hand

### DF5-D11 — `MemoryStore` was named and never built, for the second project running

**Acted on:** `DF5-I18`.

**Library.** `DF4-L8` recorded that dogfood #4 named `MemoryStore` and built SQLite instead. This
project names it in three places and builds it nowhere: `design.md:186-189` ("The library's
memory store, reached by `remember` and `recall`, scoped per person … These are answers to
consultations, and they are exactly what must survive the run that asked"), `tvtime/store.py:3-6`
(the same sentence in the store's own docstring), and the brief's `end_user` ("anything the agent
remembers is scoped per person"). No import, no `memory=`, `memory: null` on all 2,669 manifests.
What holds the answers is `Store.shelved` in the project's own JSON store; what holds refusals is
`Store.judgements` folded into `taste.disliked`; what holds corrections is four id lists.

**Where the steer came from.** `docs/product.md` §3: "Memory scope. A store serves one person per
scope (`docs/shipping.md` §5), so a request handler scopes the store to its user before the run."
The document tells a product with per-person state to reach for the memory store, the coding
agent wrote that down as the design, and then built the thing the product needed, which is a
shelf that lists pending questions, dedups them, marks answers and is read by a page. A scoped
key-value store with `remember` and `recall` offers none of those operations.

**The deferred entry's decider**, [`plan.md` §2.2](../../plan.md#L148), asked for "a second
project that persists state choosing or refusing the store for stated reasons". It did neither:
it named it, described it as in use, and never reached it. Two projects, one pattern, and the
reason both times is that the store's shape is a personal memory for an agent and what a product
persists is its own data model.

### DF5-D12 — The artifact recipe was followed in form and broken in fact for two days, and nothing could see it

**Acted on:** `DF5-I19`.

**Library, and the second store decider.** `docs/shipping.md` §6's recipe is the stamp, the
staleness query and the refresh. The project built all three by hand: `Store.put_artifact` and
`Store.is_stale` around `pipeline.behaviour_fingerprint(model=client)` (`store.py:274-281`),
`web/app.py:_fingerprint`, and a refresh path of threads and cron. Then, from the project's own
roadmap (`ROADMAP.md:303-311`): "`Store.is_stale` is called from **nowhere** … The fingerprint
that would detect this was itself broken until exchange 40: it passed an argument the method
does not take, so every call raised `TypeError` into a bare `except` and every artifact was
stamped `"unfingerprinted"`." So for two days every artifact on the site carried the same stamp,
`is_stale` compared `"unfingerprinted"` to `"unfingerprinted"`, and the discovery page rendered
output "no current pipeline would produce". The audit at `ship` found it by reading.

**What the library could see.** Nothing, by `P3-6`'s decision that no check opens project
storage, which this record does not reopen. What it could have offered is the thing the project
got wrong: the four behaviours the [shipped-store entry](../../plan.md#L159) names, "a store
that writes rows carrying the stamp and the run's provenance, answers `stale(stamp)`, and yields
the refresh worklist". The entry's decider was "dogfood #5 hand-building the same four behaviours
again with the docs naming them". It did, two of the four broke, `absorbed_through` is "written
and read by nothing" (`taste.py:236-237`), and the refresh reports staleness rather than acting
on it. The decider is met; what it decides is the sitting's.

### DF5-D13 — A node fetched 24,244 articles outside the tool layer, invisible to policy, cassette and record

**Acted on:** `DF5-I20`.

**Library.** The resolution pipeline's `attempt_fetch` node (`agent.py:1869-1889`) calls
`tvtime.enterprise.fetch`, which is raw `urllib.request` to `api.enterprise.wikimedia.com` with
its own retry, backoff and token refresh (`enterprise.py:137-186`). It ran 2,458 times across
1,313 runs with **zero tool calls**, under a pipeline that declares `fetch_policy=BULK_POLICY`
that therefore governs nothing (`agent.py:2119`); the host is not in `ALLOWED_HOSTS`; no
cassette holds a byte of it; the trajectory records the node's inputs and outputs and not what it
reached. The corpus of 20,080 summaries the product renders was built through it.

**Whether it is the project's or the library's.** The rule that a node's reach goes through
tools is what makes replay, policy and the record mean anything, and the docs state it for
tools (`docs/tools.md` §3.3) and nowhere for node bodies. The library cannot enforce it, since a
`Deterministic` body is Python. What it could do is say it, and say what a run loses when a
body does its own I/O; and the taxonomy could carry a row for it under "what the suite does not
read", beside the store. A check is not possible; a sentence is.

### 3.4 Money, time and what a killed run leaves

### DF5-D15 — A hosted evaluation that cost $5.50 reports its cost as null, and the library waited 28 minutes on a quota that could not clear

**Acted on:** `DF5-I23`, `DF5-I24`.

**Library.** Three related facts from `eval_b7c83906be49`, the only Gemini evaluation.

1. **The null.** 54 calls across 11 rollouts failed on `429: Your project has exceeded its monthly
   spending cap`. A call that raised before a response carries `unknown` for every token class,
   one unknown count makes a run's price null (`docs/run-envelope.md` §4.2), and the results
   file's `totals.cost.value` is `null` with `measured: null`, although 16 of its 27 rollouts
   carry an exact price summing $3.97 and 24 carry `charged_cost` summing $5.50. The manifest has
   a field for the measured portion and it is empty. `docs/model-clients.md` §4 says this will
   happen: "A rate-limited call reports no token counts, so enough of them leave the run's cost
   `unknown`." The project's answer was commit `8d1b8ad`, "Pace the hosted client: a rate-limited
   call reports no tokens and would leave the cost unknown", which is a workaround for a figure
   the library holds and does not print.
2. **The wait.** The shipped retry backs off six times to a 31-second total per call, and did so
   on 54 calls: `held_back_ms` sums to 1,676,000, 28 minutes of an evaluation held against a
   refusal whose message says it resets monthly. `docs/model-clients.md` §4 names the case ("A
   window measured in days needs a different answer … a wrapper raises `Suspend` instead") and
   puts the distinction on the project. The library cannot tell a per-minute 429 from a
   monthly-cap 429, though the provider's message says which, and `pacing.py`'s own module
   docstring says retries are not for quotas.
3. **The rate the results file then reports.** `left_out {no_response: 6, unreached_items: 5}`,
   `accuracy` 0.0 [0.0, 0.3903] over n=6 with `including_left_out` beside it: `P3-24`'s rules
   held, and the file says what left the denominator. This is what did not go wrong, recorded
   beside what did.

**Also in the census.** 21 rollouts of `eval_9d547bf68757` are `is_upper_bound` because a node
declared a Gemini client under a run whose cost basis was the local device, and the library
charged the hosted call as device time and said so. Honest, and the first time a per-node client
crossed a cost basis in a dogfood.

### DF5-D16 — A killed run is indistinguishable from one still executing, forever

**Acted on:** `DF5-I25`.

**Library.** 13 top-level manifests have `outcome: null`, `counts` all zero and `totals.tokens`
`{}`; their trajectories hold 153 model calls and, in five of them, calls whose parent execution
was never written. The processes were killed, which `HANDOFF.md`'s account of `pkill -f` matching
the agent's own shell three times explains. `docs/run-envelope.md:655` reads "`None` on a run
still executing", and FT-35's note on the frozen copy reads "13 that had not finished, so
nothing says yet what they produced". Nothing will ever say. The manifest is written at start and
rewritten at end, so a process that dies leaves the start copy; a check reading it a week later
reads a run still executing.

**Candidate.** Small: a run whose manifest is older than some bound with no `ended_at` is
reported as abandoned rather than running, or the trajectory's last record dates it. The docs
sentence is corrected on sight as part of this record.

### DF5-D18 — A do-nothing baseline that returns `None` is scored as a failure that avoided nothing

**Acted on:** `DF5-I27`.

**Library.** `scripts/evaluate.py:163` declares `baseline=lambda example: None`, with the
comment "An agent that did nothing: recommends nothing, ever … on the avoidance set it scores a
perfect one". [`outcomes.py`](../../../src/simple_agents/evaluation/outcomes.py#L170) `classify`
returns `FAILED` for any `None` answer, and
[`metrics.py:476`](../../../src/simple_agents/evaluation/metrics.py#L476) `score_of` scores a
non-asserted rollout 0.0 under the default `Over` without calling the project's metric. So every
`baseline[]` entry in all 14 results files reads `outcome: "failed", error: null`, and on the two
avoidance files the floor is `avoided_share: 0.0`, where the project's own function returns 1.0
for an empty slate and the brief's `improvement` entry says the baseline "scores a perfect one on
the second". `docs/evaluation.md` §4.2's example uses `Unknown(reason='did nothing')`, and the
`ConfigurationError` at `runner.py:436-442` names both shapes for a non-callable; a callable
returning `None` is accepted and misread. The floor `P3-27` built to sit beside the headline is
wrong in the artifact for this project, and nothing said so.

### 3.5 Evaluation, design and the notes that name them

### DF5-D17 — A results file and its rollouts drift apart, and only a note joins them

**Acted on:** `DF5-I10`.

**Library.** Three cases in one project. `runs/eval_7423149289e3/`'s 21 rollouts started at
11:53Z, seven minutes after `evals/results/eval_7423149289e3.json` was written at 11:46Z, with the
same seeds and different totals (230.48 against 254.27 device-seconds), so the file describes
rollouts that no longer exist and the rollouts have no file. `evals/results/eval_a3d8fc5f7423.json`
names a run directory that is not in the tree. `runs/eval_f99f6679b781/` has nine rollouts, zero
model calls and no results file. And the case the check does print: FT-13 to FT-15 read
`runs/eval_b7c83906be49/cut-2026-03-23-2` while FT-01 to FT-07 read the file the brief names,
"and neither says anything about the other".

`P3-20` made the evaluation directory's name its identity, and a re-run into a cleared directory
under the same identity leaves nothing that says the file and the directory disagree. What the
results file would need is what `DF5-D5` also asks for: the fingerprint of what produced it, and
a check that the directory it names still holds it.

### DF5-D19 — The product was built after `ship`, and the procedure has no shape there

**Acted on:** `DF5-I12`.

**Library.** `DF4-D7` again, one stage later. `ship` was reached at exchange 39 on 2026-08-23
(`BUILD-LOG.md:3628`), and 30 exchanges, 45% of the log's lines, and the JSON API, the Flutter
app, the labelling sessions, the shortlist cycle, the pairwise instrument, the tuning knobs, the
conversational tracker, cron and the offline cache all came after it. Every check was green
throughout, because every check the library has fires on a project reaching a point and this
project had reached them all. `P3-7`'s `confirmed_against` is the one mechanism that fires on
change, and `DF5-D6` records that it was never used. The road after the last gate is where this
product was built, and the library governed none of it.

### DF5-D21 — The design says what each step uses, and the builder wanted to know what flows

**Acted on:** `DF5-I22`.

**Library.** Thilina's second note (`DF5-N2`, verbatim): *"It still didn't tell me exactly how it
plans to wire things up. Now it does tell me what it uses, but not really the specifics."*
Checked against `design.md`: the "What it does, step by step" section is a table of node, kind
and a sentence each, and it says which tools a node holds; it does not say what each node
receives, what it hands on, or where the edges go, and the library's `Pipeline.to_mermaid()`,
which renders exactly that, appears nowhere in the project. The design section `P3-8` requires is
satisfied by the table, and FT-34 reads that the section exists.

**Candidate.** The design gate asks for the graph the library can draw, so a builder reading the
design sees the wiring and not a prose summary of it.

### DF5-D22 — Evaluating back to front: the instrument exists and the project built its own

**Acted on:** `DF5-I28`.

**Library.** Thilina's fourth note (`DF5-N4`, verbatim): *"Tying into the previous point, I don't
think the coding agent is making use of per node metrics. It certainly does not appear smart
enough to figure out that this needs to be evaluated back to front. Recommendation performance
for a given show -> selecting candidates -> building the pool of candidates."*

**What the project did.** The end-to-end suite has five answers on the held-out split, "so it
cannot referee this" (`decisions.pool_source_cap`). The project decomposed the pipeline itself:
71 retrieval probes over 43 dev answers with no model call (`scripts/probe_ranking.py`), a
shortlist probe that runs the survey prompt through a hand-built `ModelRequest` outside any
envelope (`probe_shortlist.py:133-155`, the shape `docs/evaluation.md` §1.4 names as recording
nothing), a judgement suite over injected candidates, and the builder's own pairwise comparisons.
That is back-to-front evaluation, reached at `measure` by hand.

**What the library ships for it.** `expected_by_node` and `EvalSuite(node_matches=...)` score a
node on its own over the rollouts that reached it (`docs/evaluation.md` §5.2); `config.node_metrics`
is `{}` in all 14 results files. And `judged_steps`, the question that asks which steps have
their own right answer, was answered at `shape` before `gather_candidate_pool` existed and was
never re-asked when the graph changed (`DF5-D6`). The scaffold says "list the steps the pipeline
takes"; nothing says to evaluate the last step first with ideal inputs and work backwards, which
is the strategy the note names and the one the project arrived at.

### DF5-D23 — The absence requirement made the project invent absence cases for a task that has none

**Acted on:** `DF5-I29`, `DF5-I40`.

**Library.** Thilina's fifth note (`DF5-N5`, verbatim, 2026-08-25): *"I think the library went
way too overboard on the whole 'absent answer' thing. It makes the coding agent try to invent
something to fill that requirement because a tv show recommender doesn't really have an
absent/unknown condition that can go into an eval set."*

**What the record shows.** FT-04 fails an `evaluated` project whose held-out split holds no
example expecting absence (`checks.py` `ft_04`). At `shape` the builder answered the absence
question *"Never absent — change the tier"* (`BUILD-LOG.md:287`). The coding agent declined to
lower the tier, citing the procedure ("A failing gate is not a reason to lower the tier",
`:288-291`), rejected the empty quarter of the builder's history as an absence case in so many
words ("an empty held-out window means *no evidence*, not *nothing should be recommended*.
Scoring the agent correct for silence there would be dishonest", `:294-297`), and found what it
called a real one: what is confirmed to air in March 2027, which TVmaze answers with nothing.
`brief.toml`'s `absence_vs_error` records the builder keeping the tier "shown the evidence
above". Then `scripts/build_examples.py:155-156` did what the log had called dishonest: a
quarter in which no kept show was started is `Unknown(reason="they took nothing new up properly
in this quarter")`, and the example set carries 20 `unknown` rows of 89, four of the nine
held-out examples (`absent_proportion` 0.4444). On the headline evaluation every one of those
scored `false_confidence`, since an empty slate inside a dict is an assertion, with `verdict`
null on the 12 rollouts of absence examples (evals ledger §9.1).

**What it cost.** A rule written for tasks where silence is an answer, a lookup that may find
nothing, applied to one where it is not: a recommender always has something to say and an empty
quarter says nothing about it. The requirement produced four held-out examples that measure
nothing, a headline whose false-confidence rate is partly those examples, and a sitting spent
on the tier. FT-04 stands down where every model-calling node declares `allow_unknown=False`, and FT-04's own
failure message names that fix verbatim. *(This paragraph read "so between the two there was no
honest way to say 'absence is not a state of this task'" until 2026-08-27, and that is `DF5-X12`.
Measured at sitting 4: the headline evaluation's pipeline has **one** model-calling node,
`judge_candidates`; `allow_unknown` appears nowhere in `agent.py`; and across all 2,669 manifests
all 2,730 model-calling node entries carry `allow_unknown: true`. The escape existed, was named in
the message the coding agent read, and was never used once.)* Decide: whether the waiver, which is
all-or-nothing across model-calling nodes, should read the node producing the scored answer, and
whether FT-04's message should name what the builder already answered under `absence_vs_error`.

### DF5-D14 — `consult` is `read_only`, and the builder says it reaches him

**Acted on:** `DF5-I07`.

**Library, and a defect after all.** `brief.toml` `tool_effects`: "`consult`: asks the
end user; the library classes it `read_only` and the builder said that undersells it, *'Consult
should count as reaching me'*, because it costs a person's attention rather than a machine's."
The four side-effect classes describe effects on the world outside the run, and a question to a
person is one.

**This entry said the class that would make an evaluation refuse to fire a real consultation is
what the stand-in mechanism already guarantees another way. It does not**, corrected 2026-08-25 at
sitting 1 against the current source. `EvalSuite.run(end_user=...)` defaults to `None`
([`runner.py:410`](../../../src/simple_agents/evaluation/runner.py#L410), `run`), and where it is
`None` the registered channel answers every rollout
([`runner.py:2556`](../../../src/simple_agents/evaluation/runner.py#L2556), `_scoped_for_rollout`).
`_refuse_unsafe_tools` reads only `irreversible` and `spends_money`, so nothing refuses it. An
evaluation of 50 examples at k=5 over a channel that emails a person sends 250 emails today.

**And the library taught the coding agent that it is safe.** `build_registry`'s own docstring,
`agent.py:182-186`: "`read_page` and `http_fetch` are both `read_only`; `consult` is `read_only`
and is recorded as a consultation. Nothing here spends money or writes anywhere permanent, **which
is what lets an evaluation run k rollouts over n examples without refusing to start.**" That is
the class system read correctly, reaching the conclusion the library offers.

What is owed is therefore a refusal rather than a word. `DF5-I07`.

### 3.6 Five smaller mechanisms, each with a measured cost

### DF5-D25 — `max_failures` hides a failure every item shares, and the run completes with nothing

**Acted on:** `DF5-I32`.

**Library.** Three times in this project a fan-out's items all failed the same way and the run
completed. `BUILD-LOG.md:375-380`: every recap was silently missing, because all three fan-out
prompt functions read the item alone where a fanned-out node passes the whole input with the
fanned key holding one item, "so each raised `KeyError` per item, `max_failures` swallowed all
of them, and the run completed successfully with nothing written." `:1737-1757`: a project bug
in `validate_prompt` failed 9 of 37 items and an 18-show test had stayed under the ceiling, so
the failures "appeared in `unresolved.json` as *no article could be confirmed*, reading like a
judgement the model had made"; the coding agent's own sentence is "A failure budget hides bugs
at exactly the rate it absorbs them." `:3861-3867` is the third. The tolerance is right for
items that fail for their own reasons; a fan-out whose every failure carries one exception type
and one message is a defect wearing a tolerance. `report`'s "produced nothing" line is the only
signal the library gives, and `DF5-D6` records that nobody ran it.

### DF5-D26 — `concurrent_items` is silent without `Pipeline.run(concurrency=)`

**Acted on:** `DF5-I33`.

**Library.** `BUILD-LOG.md:652-666`: the residue splitter ran serially at five seconds a call
with `concurrent_items=8` declared, and the trajectory showed every call starting the
millisecond the previous one ended; `docs/pipeline.md` §1.10's "Nothing in a run overlaps
until something says it may" was found afterwards. Passing `concurrency=` took the same work
from 0.2 calls a second to 1.84. Then the same thing again: `JUDGES_AT_ONCE = 14` on
`judge_candidates` never took effect, because every caller passes `concurrency=8` and the
manifests record 8 (code census §5). A node declaring more concurrency than the run permits is
not an error and not a warning, and "it is just a slow run that looks like the model being
slow", in the log's words. A line at run start saying which nodes' declarations the run's
concurrency cuts is what is missing.

### DF5-D27 — A tagged absence reached the end user's page four times, and `value_or` recognises one of its four shapes

**Acted on:** `DF5-I34`.

**Library.** [`schema.py:133`](../../../src/simple_agents/schema.py#L133) `value_or` replaces an
`Unknown` instance and nothing else, and its docstring says so. An absence that has been
through `model_dump()` or a stored artifact arrives as `{"type": "unknown", "reason": ...}`,
through `str()` as `type='unknown' reason='...'`, and from a model that ignored the schema as the
bare word. The log records each reaching a page: the tracker's preview showing the dict on every
message the model was sure about (`BUILD-LOG.md:4169-4174`, "the guard was there, `value_or` on
each `Maybe` field, and `model_dump()` had already turned the tagged absence into a plain dict"),
the discovery page printing it inside an *airs* pill 502 pixels wide (`:4370-4383`, "Every
guard written so far has missed that shape, which is why this has now happened three times"),
and the repr of an absence as a recap on the builder's front page (`:5412-5428`, "the fourth
time"). The project's answer is a `_plain()` that flattens all four shapes and an API check that
asserts none reaches a payload. A second footgun on the same type: `Field(description=...)` on
a `Maybe` field replaces the absence description the library supplies, so the model writes the
word "unknown" into the value branch; FT-09 warns and it recurred at `:362-366`, `:1029-1033`
and `:2168-2170`. `value_or` reading the JSON form, and `Maybe` appending its description rather
than losing it, are both small.

### DF5-D28 — `http_fetch` has no retry, and a throttled source reads as absence

**Acted on:** `DF5-I35`.

**Library.** [`builtins/http.py:79`](../../../src/simple_agents/builtins/http.py#L79) `http_fetch`
marks every fetch error `retryable=False` (lines 135 and 376), and the tool has no backoff. Wikipedia returns
`429` with `Retry-After: 15` after about six requests (`BUILD-LOG.md:1161-1177`); the manifests
carry 736 such errors on `tool_call` records. The project's first reading of it was "no
article" (`:601-605`, "A throttled Wikipedia request returns *empty* rather than an error, so it
reads as *no article* unless something is counting"), the builder named the fix (`:1170`, "That
means you need to have backoff implemented"), and the project layered `sources.fetch_json` over
`ctx.call_tool("wiki_fetch")` with exponential backoff, `Retry-After`, and a `Throttled` type
"precisely so it can never be caught as absence". The model clients honour `Retry-After`
(`docs/model-clients.md` §4); the fetch tools do not, and nothing says which.

### DF5-D29 — `ProjectMetric`'s default denominator dropped the worst case, in the direction that looks better

**Acted on:** `DF5-I30`.

**Library.** `BUILD-LOG.md:906-912`: the first judgement run reported `avoided_share` 80%. A
`ProjectMetric` defaults to `over=Over.VALUE_EXISTS`, so the two cutoffs whose injected pool was
all negatives, with `expected = Unknown`, left the denominator, "and one of them was where a
dropped show *was* recommended. The metric was excluding its own worst case." At `Over.ALL`, n
goes from 5 to 7 and the figure to 61.9%. The default is right for a metric over answers and
wrong for one over what the run refrained from, and the results file does not say which `Over`
a figure was computed under. Beside `DF5-D18` and `DF5-D23`, the third place this project's
absence examples moved a figure without the report saying so.

### 3.7 What did not go wrong

Recorded so the next run is read against it.

- **The research stage, first time cold.** Nine parts decomposed before a search was run and put
  to the builder ("Holds as listed"); 43 candidates each with an outcome, including "not
  investigated, because"; every source fetched for real before being recorded reachable; a
  licensing table produced by the builder's own question and read against a plan to publish;
  TMDB rejected on terms that name AI validation as commercial use. The survey's central finding,
  that TVmaze lacks upcoming data, was wrong, and the builder corrected it from domain knowledge
  with the rule TVmaze follows; the survey then rewrote §2 and §3 against the correction rather
  than annotating them. FT-36 cannot see a wrong outcome and did not need to.
- **The product concept.** `used_through` answered with a surface and a trigger mix; the four
  interaction kinds classified for fourteen interactions; the classification is what the coding
  agent cited when it said the surface reaches the agent. `DF4-N14` did not recur.
- **`FT-09` and `Maybe`.** Every output schema admits `unknown` as a tagged object; the `Maybe`
  reaching a page in four shapes was found by the project and handled (`HANDOFF.md:236-241`).
- **The unfinished-work instrument measured what the project found by hand.** `report` shows
  `judge_candidates` producing nothing on 29 items for 251 calls and `find_candidates` on 5 of 15
  executions for 117; the manifests' `unfinished` blocks on 12 runs say the same. The instrument
  was right and unread (`DF5-D6`).
- **`HostPolicy` per run** bound on 1,668 runs, 750 fetches, 19 refusals recorded as tool errors,
  admissions never used; `P3-30`'s same-day mechanism held under a site and a corpus pass at once.
- **The evaluation's reporting rules.** `P3-24`'s denominators under a 429 storm; `P3-27`'s
  baseline declared and its `rollout_noise` on every metric; intervals on everything; an
  `improvement` entry that reports the two numbers apart rather than averaged, in the
  builder's words, which the library's two-suite shape allowed.
- **The cost basis correction.** The project invented $0.12/hour for the GPU, found the
  procedure's "Do not invent an hourly rate to fill in a cost", removed it and reports
  device-seconds (`brief.toml` `prices`). The sentence did its work.
- **Run ids never collided** across 2,669 runs including 51 from a site and 2,313 from two threads
  draining a queue; `P3-30`'s eight-character id held.
- **Redaction** ran on all 2,669 runs, `secret_env` on 1,226, 45 records redacted, and the Gemini
  key that returned 17 `400`s on the first day is absent from the five trajectories and cassettes
  checked, the three runs that received them among them.
- **The cassette** recorded 58,027 exchanges and diverged on 27; replay was never used, which is
  the project's choice and not a defect.

### 3.8 The protocol's three categories

[`dogfood-protocol.md` §1](../dogfood-protocol.md#L18) step 5, read off the log's 134 marked
builder quotes and its own admissions, against `setup.md` §6's prediction that the urge to
volunteer would be the strongest of any run.

**Interventions the builder was forced into.** The builder designed the system's measurement
and its retrieval, in seven exchanges the log marks as his: the fan-out shape once the agent
design had failed (`BUILD-LOG.md:577`), the semantic ranker (`:673-675`), the two-evaluation
split (`:775-776`), isolating the judge from retrieval (`:883-886`), the retrieve, verify and
retry loop for the corpus (`:1141-1147`), backoff on a throttled source (`:1170-1171`), and
pairwise comparison as the instrument (`:6360-6363`). Each is something the library could have
put in front of the coding agent: per-node scoring (`DF5-D22`), a retry on the fetch tool
(`DF5-D28`), a win-rate answer shape ([`plan.md` §2.2's six shapes](../../plan.md#L232), G1), and
the measure stage's report (`DF5-D6`). They count as interventions because the coding agent's
own design had failed and the builder supplied the next one, and the protocol's asymmetry did
not hold for a product the builder wanted, as `setup.md` said it would not.

**Questions the library should have answered.** Four times the builder could not answer the
question as put: *"I don't get what you are asking"* (`:263`, on `answer_form`), *"what's that
random number 12? where did it come from?"* (`:4751`), *"So much jargon and no clear question,
options, or recommendation"* (`:5764`), *"I still don't get it. Give me fucking context, and
explain the jargon"* (`:6513`). `DF4-N2` recurring after `P3-28` fixed one instance of it. The
scaffolded questions are plain; the ones the coding agent composes at `measure` and after are
not, and nothing in the procedure says how a question to the builder is put.

**Wanted and never asked for.** The five notes, and what the log shows arriving after the last
gate: agency (`:5987`, `:6093`), users need the option to rate and track shows
(`:5718`), whether ratings and tags reach the recommender (`ROADMAP.md:213`, "recorded at the
builder's request"), ratings on the cards (`:5110`), sortable queues (`:4744`), and the
open-ended question itself (`DF5-D9`).

And one thing the categories do not name: the builder's reminders to keep the log (`:3630`,
`:4061`) and to commit as he goes (`:4059-4062`), process instructions the procedure owns and
the builder had to give.

### 3.9 Documents

### DF5-P1 — `docs/tools.md` §4.6.3 states the once-per-run rule for the model's case only

**Acted on:** `DF5-I05`.

**Document.** "The model is told once, and the rest of the run is answered from that. Every later
question to that tool returns the same thing without reaching the channel again, and each one is
recorded." True, and it says nothing about a `Deterministic` node calling `consult` per item,
where "the model" is not asking and the questions are distinct. The document half of `DF5-D1`;
what it says depends on what that decides.

### DF5-P2 — `docs/product.md` §4 tells one consultation story and the first product needed the other

**Acted on:** `DF5-I04`, `DF5-I37`.

**Document.** §4 is `Suspend`, `Pipeline.suspensions` as the inbox, `resume` on answer. The
shelving pattern, `Unavailable` with a reason and `on_reply(unavailable="proceed")`, is in
`docs/tools.md` §4.6.3 under "the hours or the deployments where nobody is reachable", which
reads as an edge case. For an artifact-shaped product whose runs fire on store writes and cron,
nobody is reachable on every run, and this project used shelving for 1,654 of 1,654
consultations. The product document should carry both modes and say which fits which trigger;
the brief's `consultation` answer, in the builder's words, is a good statement of the choice.

### DF5-P3 — The invocation story loads no credential, and the site answered 500 for two days

**Acted on:** `DF5-I21`.

**Document.** `docs/product.md` §3's request handler constructs a client and runs. The project's
web app never loaded `.env` (`design.md:408-411`): "every script loads it and the one entry point
a person uses did not, so every route that constructed a model client answered 500. It is why the
project had no live run before `ship` despite the site having been up for two days." The
library reads no `.env` by design and the docs say so nowhere a product builder reads; one
sentence in §3 beside `run_id`, memory scope and pacing would have cost nothing.

---

## 4. What is open

What this record does not settle. `inventory.md` is where these become candidates with a size
and a disposition.

- **The memo's scope, the channel's reach, and the record's reason** (`DF5-D1`): three decisions,
  and the entry declines to take them.
- **An identity for a consultation** (`DF5-D2`), which a shelf, a cassette and an inbox all need
  and which the wording cannot be.
- **`Suspend`'s base class** (`DF5-D3`), and whether a swallowed suspension can be detected at
  all.
- **A role for a batch pass, and FT-33's rule** (`DF5-D4`).
- **What joins a results file to the pipeline that made it** (`DF5-D5`, `DF5-D17`).
- **Which of `procedure.md`'s instructions become gates** (`DF5-D6`), and what a report gate is.
- **The agency questions**: the join for `agency_boundary` (`DF5-D7`, evidence for `P3-29`),
  run-state for an agentic step's tools (`DF5-D8`), and an open-ended question in the set
  (`DF5-D9`).
- **The two store deciders** (`DF5-D11`, `DF5-D12`), met, and what they decide is the sitting's.
- **The timestamp entry** (§1.4): the manifests answer it from `build` onward and not before.
- **Two answer shapes this project needed and declared itself**: a ranked list where position
  counts (`reciprocal_rank`, shape C2) and a pairwise preference with no key (the 40
  comparisons, shape G1). Both are in [`plan.md` §2.2's six shapes](../../plan.md#L232), whose
  decider was a project that needs them.
- **The second cold run** the protocol asks for where the task warrants it. This one's
  existence-shaped questions are answered; a second run would separate the coding agent's
  agency decisions from the local model they were measured on, since most of the "agency does
  not converge" evidence was a 4-bit 30B model with a 16k window.
- **The scan pass.** `live_records` in the brief accepted that "a person's viewing data sits in
  run records"; 3.1GB of trajectories under `runs/` carry the builder's watch history, and this
  record quotes show titles from it. [`items/going-public.md`](../../items/going-public.md#L1)'s
  scan reads this record too.
- **The tail.** The offline cache for the mobile app, committed after the freeze, is not read.
