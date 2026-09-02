# Handoff — Simple Agents

**What this file is.** The first thing a new session reads. It gives the reading order, what is in
flight right now, and the facts about this machine that are recorded nowhere else. **It is a
pointer, not a summary.** Anything with a home in `CLAUDE.md`, `simple-agents.md`, `plan.md`, a
build log, a findings record or `docs/` is cited from here and written there. The ceiling is 120
lines.

## Read in this order

1. **`CLAUDE.md`** — the conventions, the writing rules and the glossary, and authoritative on all
   three. The vocabulary is fixed; these docs are a prompt surface and an ambiguous term is a bug.
2. **`simple-agents.md`** — what to build, and why each decision is what it is. **§9 is the
   do-not-change list**, and changing one means arguing against its stated rationale.
3. **[`plan.md`](plan.md#L1)** — the only queue, and it holds items and nothing else. §1 is
   scheduled, §2.1 accepted, §2.2 deferred, §3 out of scope, §4 done. A thought that is not scoped
   yet is the inbox, and nothing is in two places.
4. **`docs/index.md`** — the front door to the nineteen shipped documents, and when to open each.
   `docs/` is authoritative on what the library does today.
5. **`random-thoughts-questions.md`** — read before touching anything in `docs/`. Thilina's Corner
   is his: read it, do not edit it, and ask rather than assume. An item there is resolved only when
   he says so.

## Where the build stands

**v0.1 in progress.** 4,102 tests. Trajectory format `0.29`, manifest `0.39`, results file `0.29`,
suspension `0.5`, shelf `0.1`, conversation `0.2`. Six dogfoods have run; [`runs/dogfood-protocol.md`](runs/dogfood-protocol.md#L1) is the protocol. **Dogfood #6 is `lost-the-plot`, Thilina's own build against the public package, 2026-09-01 to 02**, recorded 2026-09-02 after the fact: [`runs/dogfood-6/findings.md`](runs/dogfood-6/findings.md#L1), 19 candidates, 0 open: the sitting was taken 2026-09-02 and scheduled `P3-72` to `P3-77`. **`P3-72` is built, 2026-09-02** ([build log](build-logs/the-brief-writer-build-log.md#L1)): `simple-agents record` and FT-44.

**A project built against an older version of the library breaks**, and `CHANGELOG.md` is the
record of every change that does it. It comes up on a frozen dogfood copy under
`simple-agents check` and on a cassette that has to be re-recorded; a new dogfood builds
against a fresh wheel and meets none of them.

**Dogfood #5 ran 2026-08-20 to 24.** [`findings.md`](runs/dogfood-5/findings.md#L1) is the evidence,
[`inventory.md`](runs/dogfood-5/inventory.md#L1) §3 the queue `P3-32` worked through: 40 candidates,
0 open. **`P3-32` is done, 2026-08-28**; `P3-31` waits on `P3-64`, working the ratchet down, scheduled 2026-08-31. **A sitting's work is built before the next**, agreed 2026-08-25.
**Sitting 3 scheduled six and five are built**: `P3-29`, `P3-35`, `P3-36`, `P3-37` and
**`P3-38`, built 2026-08-27** ([build log](build-logs/an-mcp-server-build-log.md#L1)), which
amended [`simple-agents.md` §2.1](simple-agents.md#L104). **`P3-39` is built, 2026-08-27** ([build log](build-logs/a-conversation-that-outlives-the-run-build-log.md#L1)). **Sitting 4 was taken 2026-08-27** and scheduled `P3-44` to `P3-48`, all five before `P3-31`; four `plan.md` §2.2 entries closed with it and the answer-shapes entry narrowed from six to four. **Four of the five are built, 2026-08-27**: `P3-44`, `P3-45`, `P3-46` and `P3-47`, in one pass on Thilina's call, with five reverification cycles over the four together. **`P3-48` is built, 2026-08-28** ([build log](build-logs/a-figure-that-is-not-a-mean-build-log.md#L1)): a figure that is one total over another, a figure over judged pairs where there is no answer key, and **the last four of the survey's twenty-four answer shapes**. Results file to `0.26`, variant comparison to `0.3`, and a written comparison gains a version of its own. **Sitting 5 was taken and built 2026-08-28** as `P3-50` ([build log](build-logs/what-a-run-says-it-cost-build-log.md#L1)), out of `DF5-I23`, `DF5-I24` and `DF5-I25`: a run's record now says what it spent where part of it could not be priced, stops rather than waiting on an allowance that will not clear, says whether a run with no outcome is still going, and records what the run was given. Manifest `0.38`, results file `0.27`, trajectory `0.29`. It carried `plan.md` §2.1's `Cassette.update` entry and created [`P3-51`](plan.md#L1), a dedicated results visualiser, which needs its own sitting, waits on nothing now, and **carries the view's fixtures**: `tests/fixtures/view_projects/` has no generator and no currency check and sits at manifest `0.32` against `0.38`, which Thilina ruled a gap on 2026-08-28. **Sitting 6 was taken 2026-08-28** and scheduled two items, both built the same day and both on `main`: [`P3-52`](plan.md#L1), the floor a do-nothing agent sets, out of `DF5-I27` ([build log](build-logs/the-do-nothing-floor-build-log.md#L1)), results file `0.28`, ten reverification cycles and seven defects the suite could not see; and [`P3-53`](plan.md#L1), evaluating back to front, out of `DF5-I28` ([build log](build-logs/evaluating-back-to-front-build-log.md#L1)), results `0.29` and manifest `0.39`, built on a branch in parallel with `P3-52` and rebased onto it. `P3-53` gave `Pipeline.slice`, an edge whose other end is outside a slice, `ExampleSet.entering`, a per-node `ProjectRatio` and `EVAL_FORMAT_FLOOR`; one third of `DF5-I28` was found already built and corrected as `DF5-X19`. **Sitting 7 was taken and built 2026-08-28** as [`P3-54`](plan.md#L533) ([build log](build-logs/dogfood-5-fixes-build-log.md#L1)), four surfaces that read as working: a fan-out raises where every item failed with one exception type and one message, a caller-facing failure inside an item ends the run, the fan-out bar shows failures and a resumed count, a run warns where its `concurrency` cuts a node's `concurrent_items`, `value_or` and `str(Unknown)` cover an absence's other shapes, a `Maybe` field is always told how to send an absence, and a throttled source is waited out through a new `Throttled`. No format moves. It closed one `plan.md` §2.1 entry and one §2.2 entry and opened three. **The `graph` Mistral arm is retired and `graph-gemini` replaces it.** **Sitting 8 was taken 2026-08-28**, the last: `DF5-I36` folded into `P3-31` rather than becoming an item, and the scan's shape was settled there. It reads `dev-docs/` alone, since nothing from a dogfood project goes public; `prose_check` gained `own_run` and `machine_path`, both at zero after six rewrites; and the reading is triaged rather than read line by line, 143 files and 48,968 lines being too many. **`P3-32` is done.** **Four reverification cycles across everything dogfood #5 has landed were run 2026-08-28** and are in that build log's §4: three shipped statements corrected (`DF5-X15` to `DF5-X17`), a hole closed in `prose_check`'s `missing_section` rule, and the suite made independent of exported keys, timezone and working directory. **`P3-49` renamed `run(thread=)` to `conversation_id=` on 2026-08-28**, which `P3-44` raised. **Runs are now filed by what they are** (`runs/live/<date>/`, `runs/dev/<date>/`, `runs/eval/<eval_id>/`, `runs/<role>/<date>/`) and no reader counts slashes; a project on the old flat layout needs no migration. `P3-38`'s own investigation declined MCP tasks into
[`plan.md` §3](plan.md#L521) and scheduled `P3-43` behind the release. `P3-40` to `P3-42` are a
separate chain and all three are built. `simple-agents view` exists now:
[`design/view.md`](design/view.md#L1).

**The results visualiser (`P3-51`) is done, 2026-08-29**, built after a sitting taken in session
on 2026-08-28 as `P3-58` the fixtures, `P3-59` the stage-page shell and `P3-60` the measure page,
which was reopened and rebuilt the same day as a grid of drawings against a new fixture,
`view_projects/measured` ([build log](build-logs/the-measure-page-as-a-visualisation-build-log.md#L1)).
[`design/results-visualiser.md`](design/results-visualiser.md#L98) holds the rulings. **The same
sitting designed every other page**, in build order `P3-61`, `P3-62`, `P3-56`, `P3-57`, `P3-55`;
Thilina on all six was *"Looks okay, but I'll need to see the final thing"*, so each built page is
read in a browser, and [`design/view.md`](design/view.md#L1) decisions 28 and 29 govern the wording.
**All six are built 2026-08-29**: [shape](build-logs/the-shape-page-build-log.md#L1),
[build](build-logs/the-build-page-build-log.md#L1),
[ship](build-logs/the-product-on-the-page-build-log.md#L1),
[operate](build-logs/the-operations-page-build-log.md#L1) and
[brainstorm and research](build-logs/the-view-before-there-is-code-build-log.md#L1). No format
moves. `P3-56` added `Product`/`Surface`/`product_factory` and the derived `shipped` fixture,
which `P3-57` gave a background pipeline and a run of every live state. **All six were read as a builder at laptop width and against the served page on 2026-08-29 and fixed the same day**, each build log's last §5 subsection and `CHANGELOG.md`. **`P3-63`, the pre-release refactor, is built, 2026-08-31** ([build log](build-logs/pre-release-refactor-build-log.md#L1)): `runtime/`, `nodes/` and `pipeline/` exist, the recorded graph is read one way, the public surface is unchanged, and live Gemini and vLLM runs passed. **`P3-64`, working the ratchet down, is built, 2026-08-31** ([build log](build-logs/ratchet-down-build-log.md#L1)): the lint and format gates, eight sittings over the recorded units, and every keep reasoned in the baseline. **The `P3-31` scan pass ran clean 2026-09-01** and gates in the suite; the same day settled a fresh public repository off the scanned tree (this one stays the private archive), renamed `claude-docs` to `dev-docs`, and scheduled `P3-65` (builder quickstart), `P3-66` (feature index, carrying `P3-3`'s remainder) and `P3-67` (undocumented APIs) ahead of the release, with the elicitation gaps accepted into §2.1 behind it. [`build-logs/going-public-build-log.md`](build-logs/going-public-build-log.md#L1) has the rulings. **`P3-65` is built and approved, 2026-09-01** ([build log](build-logs/the-builder-quickstart-build-log.md#L1)): `README.md`'s Quick start is the walkthrough. **`P3-66` is built, 2026-09-01** ([build log](build-logs/the-feature-index-build-log.md#L1)): the feature index ships inside `docs/procedure.md`, which is the skill verbatim, and its carried `P3-3` read closed that item, correcting twenty-plus stale `runs/<eval_id>/` path shapes. **`P3-67` is built, 2026-09-01** ([build log](build-logs/the-undocumented-apis-build-log.md#L1)): the reranker, the fakes, re-pricing and `answer_shelved`'s return documented, the re-pricing example executed by a test. **The `P3-31` release sitting settled every open decision, 2026-09-01** ([the rulings](build-logs/going-public-build-log.md#L1)): `0.1.0` and `v0.1.0`, the README pass closed, the example project and the format-stability question unchanged behind the release, `P3-68` to `P3-70` scheduled out of §2.2, and this repository renamed `simple-agents-prototype` with the fresh public `simple-agents` built from the scanned tree. **`P3-31` closed 2026-09-02**: three releases on PyPI, the public repository, the scan in CI.

Facts that cost a session time to rediscover. None are design decisions.

| | |
|---|---|
| Mistral key | `MISTRAL_API_KEY` in `/home/thilina/Projects/simple-agents/.env`, gitignored. Nothing reads it automatically; export it. **Out of credits.** |
| Gemini key | `GEMINI_API_KEY` in the same file, paid tier. The model is `gemini-3.1-flash-lite`, and `docs/model-clients/gemini.md` §2 says why the cheaper one cannot be called. |
| Mistral's free tier | 50 requests and 50,000 tokens per minute, published on every response header. Gemini publishes no allowance on any response, so nothing paces it. |
| Cassettes that cannot be re-recorded | `mistral`, `agent` and `graph-loop` are Mistral arms and Mistral is out of credits. They replay; the next change that invalidates one needs a new arm. `context` was the first and is now `context-vllm`; **`tools` retired on 2026-08-19** when `P3-21` moved every tool version, and **`graph` retired on 2026-08-28** when `P3-54` changed what `str(Unknown)` renders into a prompt, replaced by `graph-gemini`. |
| Default `python` | A conda 3.7.7, which the library refuses to install into. **`uv venv --python 3.12`**, always. |
| The `semantic` extra | `uv sync` without `--extra semantic` prunes it, and one pacing test needs it. |
| `node` and `npx` | **Node 24.19.0, npx 11.17.0.** `tests/test_view_runs.py` executes the view page's own script under a stub DOM, and skips without a JS engine on `PATH`. CI pins Node 22. **`npx -y @modelcontextprotocol/server-everything <stdio\|sse\|streamableHttp>` is the reference MCP server** `P3-38` is designed and tested against: 13 tools carrying the four hints, ~400ms to spawn and initialize on a warm cache, port 3001 under `streamableHttp`. |
| Looking at the view | `google-chrome --headless --screenshot=out.png --window-size=1600,1200 file://<page>` renders it, and `--dump-dom` carries a measuring script's result back out. **Headless Chrome reports `prefers-color-scheme: dark`**, so an unstamped page is the dark palette. **A theme is selected by seeding `localStorage` before the page boots**, since the page restores the reader's choice and would otherwise clear an attribute stamped by hand. |
| vLLM | Its own environment at `~/.venvs/vllm`, deliberately outside the project. The serve command is in `docs/model-clients/vllm.md` §2. |
| **A reasoning model with no output ceiling** | `Qwen3` under `--reasoning-parser qwen3` generates until the context runs out, and a `Budget` is checked between steps rather than inside a call, so it bounds nothing. **Set `max_output_tokens` on every node, and preflight one call before any live run.** Without it a run shows `Running: 1 reqs` and climbing KV cache for as long as anyone waits; cost 12 minutes on 2026-08-18 and the same failure on 2026-08-17. **A ceiling that is set can still be too low, and it fails differently.** Measured 2026-08-18: a short reading prompt at 1200 returned `finish_reason=length` with **empty content**, the whole ceiling spent on the chain of thought, and at 4000 it returned in 7.1s at 1261 output tokens. Budget for the reasoning, not for the answer. |
| GPU | One RTX 3090, 24GB, about 4GB held by other processes. `--gpu-memory-utilization 0.6` fits `Qwen/Qwen3-1.7B`; 0.85 fails at startup. Port 8000 is taken, so use 8001. |
| Re-recording cassettes | `uv run python scripts/record_backend_cassettes.py {mistral,vllm,gemini,agent,context}`, with `-gemini` arms. The vLLM one needs `--base-url` off port 8000 and reads the weights' commit from `HF_HOME`. |
| Building the wheel | `uv build`. The docs are force-included, so **rebuild after changing anything in `docs/`** or an installed copy goes stale. Each dogfood holds its own copy under `<project>/wheels/`, so a rebuild here disturbs nothing running. |

## The tree, and where an answer lives

Four files at the root and six directories. `CLAUDE.md` has the naming rules and what may go where.

| Question | Where |
|---|---|
| What are we doing, and what next? | [`plan.md`](plan.md#L1). §1 scheduled, §2.1 accepted, §2.2 deferred, §3 out of scope, §4 done |
| Why is the design this way? | [`simple-agents.md`](simple-agents.md#L1), and §9 is the do-not-change list |
| What is open but not scoped? | [`random-thoughts-questions.md`](random-thoughts-questions.md#L1). Temporary; every entry leaves |
| What is this planned item? | `items/`, one file per open item, linked from its `plan.md` row |
| What can a right answer be? | [`design/answer-shapes.md`](design/answer-shapes.md#L1): twenty-four kinds, what each needs, and where each stands |
| How was X built, and what did it find? | `build-logs/`, named for the item. Six sections, [`templates/build-log.md`](templates/build-log.md#L1) |
| What did a run find? | `runs/<run>/findings.md`, with `inventory.md` beside it for what to do about each |
| How do I run a dogfood? | [`runs/dogfood-protocol.md`](runs/dogfood-protocol.md#L1), and the run's own `setup.md` |
| How does one subsystem work? | `design/`: the `brainstorm` stage, and what each format bump cost |
| Was this already decided, and why? | [`archive/plan-history.md`](archive/plan-history.md#L1), every built item's record verbatim |
| What does the library do today? | `docs/`, authoritative on detail. `CHANGELOG.md` for what changed |

**Do not add a decisions log, a feature list, a dogfood summary or a glossary to this file.** Each
was here once and each was a second copy of a file above.

## How to work with Thilina

- He is not a novice. Do not explain what a decorator is, do not pad, do not hedge.
- He pushes back hard on overclaiming. If you are unsure, say so, and say what would resolve it.
- When he corrects you, update visibly and say what changed in your reasoning.
- He would rather be told an idea is wrong than be agreed with politely. Disagree when you do.
- Argue from the situation, not from the rule. `CLAUDE.md` says why a bare §-reference is not one.

## Things that will tempt you, and shouldn't

- **Build more than v0.** The scope in `archive/plan-history.md` is deliberately, uncomfortably small.
  [`simple-agents.md` §9 item 12](simple-agents.md#L596) rules out a DSL and nothing else, and the
  graph it protects is already built. [`plan.md` §3](plan.md#L299) is what rules out a distributed
  executor, training, browser tooling and multi-agent, and it means out for now rather than out
  forever.
- **Make everything agentic.** The library's own opinion is that agency is expensive and should be
  justified per node. Practice what it preaches.
- **Trust a suite that only ever exercised one thread.** The concurrency item found seven defects
  with the suite green for all of them, because a lost update changes a number in the manifest
  rather than an answer. `build-logs/concurrency-build-log.md` §3.6 and §3.9.
- **Trust a green suite that never used a real backend.** `CLAUDE.md` carries what this has cost.
  `scripts/record_backend_cassettes.py` is how a recording is captured once and replayed free.
