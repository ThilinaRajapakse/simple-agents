# Absorbing the dogfood code — build items from the 2026-08-09 audit

Status: approved for implementation by Thilina on 2026-08-09 ("All of 1. All of 2."), with the
dispositions below reflecting a second generality pass he asked for. This document is the
durable record: the audit itself ran as a session task and its output is not on disk, so every
piece of evidence a builder session needs is restated here with file references.

**Built 2026-08-09. Eight of the nine shipped and item 8 was dropped**, each item's log under
`build-logs/`. Where a build changed what an item says here, the item records it; this document
is what was decided before building and the logs are what happened.

**Provenance.** A cold read of all three dogfood projects — dogfood-1 run 1
(`/home/thilina/Projects/dogfood-1`), dogfood-1 run 2 (`/home/thilina/Projects/dogfood-1-run2`),
and dogfood-2 (`/home/thilina/Projects/dogfood-2`, package `fitfinder`) — against the three
findings records in this directory, asking one question per piece of project code: should the
library have provided this? Line references below are to those projects as they stood on
2026-08-09; they are external repositories and may move.

**The test every item had to pass**, stated so the implementing session applies it rather than
inheriting conclusions:

1. **The ST mantra.** The library provides everything possible for the general use case while
   leaving the customisation door open. Machinery ships; content stays in the project
   (`plan.md` §3.4 is the authoritative statement of that line).
2. **Evidence discipline.** "A dogfood built it" is necessary, not sufficient. The three
   projects overlap in shape (two web tasks, one retrieval QA), so convergence between them is
   weaker evidence than it looks. The strongest evidence is a sibling already inside the
   library, or 3-of-3 convergence, or a builder-stated constraint the library failed to serve.
   Each item below names its evidence grade honestly.
3. **The anti-tunnel-vision check.** The failure mode to avoid is Simple Agents becoming "a
   library that facilitates the three dogfoods". Where an item is really dogfood-2's problem
   wearing a general costume, it is dropped or deferred below, with the revisit condition
   recorded — the same pattern `plan.md` §3.2.1 uses.

**What is deliberately not here.** Three things the audit touched belong to other sittings and
must not be smuggled in through this document: the loop-accumulator design (DF2-D1, its own
sitting, evidence updated under "Evidence updates for the sittings" below), measured
tool spend (DF2-D2, its own design item, same section), and the labelling machinery (item 10
below, merged with DF2-D8 into one ground-truth sitting on 2026-08-09). **The first two were
held and built on 2026-08-09**, and so was item 10. Fit arithmetic, retail heuristics,
schemas, prompts, config content and the shortlist page renderer are the projects' own and are
not candidates.

---

## Build order

Recommended order, cheapest-and-most-certain first. Items 1–3 are independent of each other.
Items 4–6 compose (they are all `http_fetch`'s surface) and should be built in that order.

| # | Item | Size | Evidence grade | Built |
|---|---|---|---|---|
| 1 | `runs()` — reading back what the envelope wrote | S | library-internal sibling, 3 consumers | `absorption-item1-build-log.md` |
| 2 | `Maybe`/`Unknown` helpers; `DocumentIndex` options | S | 3-of-3 / feature-loss | `absorption-item2-build-log.md` |
| 3 | The replay seed lives in the cassette | S | one project, mechanical gap | `absorption-item3-build-log.md` |
| 4 | Domain-scoped search | S | seam one parameter too narrow | `absorption-items4-7-build-log.md` |
| 5 | HTML reduction and `read_page` | M | largest deletion, library-owned gap | `absorption-items4-7-build-log.md` |
| 6 | Fetch policy: growth, admission, ceiling | M | tool bypassed its own control | `absorption-items4-7-build-log.md` |
| 7 | URL cache in front of the network | M | builder-stated constraint unserved | `absorption-items4-7-build-log.md` |
| 8 | `load_env`, tied to redaction | S | 3-of-3, smallest form only | **dropped**, §8 |
| 9 | Grounding helpers and the documented pattern | S | 2-of-2, mission-central | `absorption-items8-9-build-log.md` |

Two audit candidates are not in the table: the sitemap reader (dropped) and the plausibility
bounds (pattern documented, no API yet). "Dropped and demoted, with revisit conditions" below
carries both.

---

## 1. `runs()` — reading back what the envelope wrote

**What the projects built.** Dogfood-2 `fitfinder/results.py:45-89`: `collect_from_runs` and
`_run_time` iterate `runs/*/trajectory.jsonl`, parse records, filter
`record_type == "node_execution"` and `node_id == "report"`, and extract `outputs`. Dogfood-2
`run.py:218-246`: `_recorded_seed` scans manifests for the newest recording run. The library's
own `conformance/artifacts.py` `_latest_run` is a third reader of the same shape.

**Why it is general.** Three independent consumers already exist, one inside the library. The
run directory is a format the library owns and documents; a project that treats accumulated
runs as its deliverable (which dogfood-2's builder did — `runs/dogfood-2/findings.md` §10.2, §11.1)
has to hand-roll a reader against a guaranteed format. Reading back what the envelope wrote is
core machinery by any definition: it is the other half of writing it.

**What ships.** `simple_agents.runs(run_dir)` returning run handles, newest first, each with
`run_id`, `manifest` (parsed), `outcome`, `trajectory_path`, and `outputs_of(node_id)`
returning the recorded output of a node's last execution (decoded through
`evaluation.outcomes.decode_answer`, so a recorded absence comes back as `Unknown`). A
`completed()` filter reusing the DF2-D4 fix's definition of finished (`outcome` in
`completed`/`stopped_early`). Nothing here executes anything; it reads files, like the
conformance checks.

**Design questions for the implementer.**
- Reuse `read_trajectory` and the manifest reader; do not re-parse by hand.
- `conformance/artifacts.py` `_latest_run` should become a consumer of this, not a sibling.
- Payload-sampled runs (`not_recorded` payloads): `outputs_of` returns what the record holds,
  which may be the `not_recorded` object; say so in the docstring rather than hiding it.
- Docs: `docs/run-envelope.md` gains a short section; the docstring carries the example.

---

## 2. Small unwraps and `DocumentIndex` options

**2a. `Maybe`/`Unknown` unwrap helpers.** Every consumer of a `Maybe[T]` output writes the
same two functions: dogfood-2 `agent.py:116-120` (`_text(value, fallback)`),
`fitfinder/matching.py:126-134` (`_number(value)`); dogfood-1 scatters
`isinstance(x, Unknown)` throughout. Ship, beside `Unknown` in `schema.py`:
`value_or(value, default)` (the value, or `default` where it is an `Unknown`) and nothing
fancier. One helper, because the 3-of-3 evidence is for exactly one shape: "give me the value
or a fallback". Resist a family of them; `isinstance(value, Unknown)` remains the documented
test.

**2b. `DocumentIndex(stopwords=...)` and title indexing.** Dogfood-1 run 1's hand-rolled BM25
(`/home/thilina/Projects/runs/dogfood-1/retrieval.py:29-33, 63`) removed query stopwords and
indexed titles. When run 2 used the builtin instead (the D4 routing fix working), both
features were silently lost — the builtin (`builtins/search.py`) has neither. Ship both as
options with the current behaviour as default: `DocumentIndex(stopwords=frozenset(...))` (no
list ships; supplying one is the project's call, consistent with "no dataset ships") and a way
for a document to carry a title that is indexed with its text. Evidence grade: real but
single-project; the case for it is feature-parity with what the routing fix displaced.

---

## 3. The replay seed lives in the cassette

**What the project built.** Dogfood-2 `run.py:218-246`, `_recorded_seed`: a replay misses on
its first model call unless run with the recording run's seed (the seed is in the model-call
key via `derive_seed`), so the project scans `runs/*/manifest.json` for the newest manifest
whose `cassette.mode` is `record` and reads its seed. Its first version found failed replays'
manifests and was wrong in a way the log records (`runs/dogfood-2/findings.md` §6, the replay
bullet).

**Why it is a library gap.** The cassette file is the artifact a replay is run against, and it
does not carry the one value needed to replay it. Every project that replays outside
`EvalSuite` (which passes seeds itself) meets this.

**What ships.** The smallest fix that removes the failure mode: `Cassette.record` writes the
recording run's seed into each entry (or a one-line header entry), and `Pipeline.run` with a
replaying cassette and no explicit `seed=` uses the recorded seed instead of generating one.
An explicit `seed=` still wins, and a mismatch still misses loudly — the change is only to the
default. Cassette entries gain an optional field, which old files lack; a file without it
behaves exactly as today. Record the field addition in `CHANGELOG.md`.

**Design question.** Whether the seed sits on every entry or once per file: prefer per-entry
(`CassetteEntry` already has optional fields with absent-tolerant decoding), because the file
format has no header concept and inventing one is a bigger change than the problem.

---

## 4. Domain-scoped search

**What the projects built.** Dogfood-2 `fitfinder/tools.py:174-231` (`search_within_site`) and
the scoping half of `find_brand_site` (tools.py:234-301). The project's own docstring states
the gap: "The library's `web_search` takes a query and a count and nothing else, so it cannot
express 'look on this brand's own site'." The project bypassed `web_search` entirely and
called its provider directly with a `domains` argument.

**Why it is general.** Site-restricted search is the standard follow-up move for any
web-reading agent — verify at the source, find the vendor's own page — and every real search
API supports it (Linkup `includeDomains`, Brave, Bing). The provider seam worked exactly as
designed (vendor shape confined to one file); it is one parameter too narrow.

**What ships.** `web_search`'s tool schema gains an optional `domains: list[str]` argument,
passed through to a provider that accepts it. Capability is read off the provider's signature
— the same rule as `on_reasoning` on `stream` (`simple-agents.md` §2.5): a two-parameter
provider keeps working and a call passing `domains` against one is refused by name, not
silently unscoped. A silently dropped domain filter is the failure to design against: the
model believes it searched one site and searched the whole web.

**What stays in the project.** `find_brand_site`'s resolution logic (`_plausible_official`) —
deciding which result is a brand's official site is content, not machinery.

---

## 5. HTML reduction and `read_page`

**What the project built.** Dogfood-2 `fitfinder/htmlreduce.py` (278 lines, stdlib-only
`HTMLParser`): strips script/nav/footer, preserves table structure through a nested-table
stack (dropping one-row layout tables), extracts JSON-LD `schema.org/Product` facts
(`_product_facts`, `_flatten` handling `@graph`), keeps image alt text, and collects same-host
links matched against a word list. `Reduced.as_prompt(max_chars)` renders tables first, so
truncation costs prose rather than measurements. Plus `read_page`
(`fitfinder/tools.py:75-171`): fetch the whole body, reduce, and refuse a page that reduces to
almost nothing with a message telling the model the site is a JavaScript shell and not to try
its other URLs — a lesson that cost a live run 14 steps and 5 paid searches
(`runs/run_53497a8a3a8e`).

**Why the library should own it.** The gap is the library's: `builtins/http.py` returns raw
markup truncated at 100,000 characters and its docstring positions it as how an agent reads
pages. Raw truncation can cut a `<table>` in half — the exact artifact a data-bearing page is
read for — and dogfood-2's first live run spent 157,760 uncached input tokens on one chase
largely on unreduced page content. A fetch tool whose output is unusable as model input is a
half-shipped tool, and §8.1 shipped the tool. This is the same reasoning that put BM25 inside
`document_search` in pure Python: the general case served without a dependency.

**The generality check, honestly.** Evidence is one project — but the claim does not rest on
convergence, it rests on the library-owned gap: every agent that reads pages through
`http_fetch` receives markup, and no project-specific fact is in the reduction. The
project-specific parts are exactly the parameters: which link words matter
(`SIZE_LINK_WORDS`), what to do with the JSON-LD facts.

**What ships.**
- `simple_agents.builtins.reduce_html(body, base_url) -> Reduced`, stdlib-only, with `text`,
  `tables`, `json_ld` (raw parsed blocks, no schema.org interpretation beyond locating them),
  `links`, and `as_prompt(max_chars)` rendering tables first.
- A `read_page(...)` builtin composing `http_fetch` and the reduction, with `link_words=` as
  the seam for the link classifier and the empty-after-reduction case raised as a
  `ModelFacingError` carrying the whole-site implication.
- `http_fetch` itself is unchanged; a project that wants raw bytes keeps it.

**Named non-goals, to hold the scope line.** No JavaScript rendering, no readability-score
heuristics, no boilerplate-detection arms race, no extraction: pulling typed facts out of the
reduced text remains `LLMNode(output_schema=...)` or `extract_to_schema`, which is the
build-time/run-time split `docs/tools.md` already draws. If reduction quality on some site is
poor, the project writes its own reducer and passes it — the seam is the function boundary.
Browser tooling remains out of scope (`plan.md` §3.2).

**Design questions for the implementer.**
- The JSON-LD half: locate and parse `<script type="application/ld+json">` blocks and return
  them; do not interpret `schema.org` vocabularies. Interpretation is content.
- `read_page` is a filed tool like `http_fetch` (keyed by arguments); the reduction is
  deterministic over the body, so replay soundness is untouched.
- Contract tests over saved fixture pages, including a table-bearing product page and a
  JS-shell page. No live fetches in tests.
- Docs: `docs/tools.md` §5 row plus a short section; the docstring carries the model-facing
  guidance about shells.

---

## 6. Fetch policy: growth, admission, ceiling

**What the project built.** Dogfood-2 `fitfinder/policy.py` (150 lines): `FetchPolicy` holding
configured hosts, `admit(host, reason)` capped at `max_admitted_hosts` with the reason
recorded, `spend_fetch()` against a whole-run `max_fetches` ceiling, subdomain matching, and
`www.` normalisation — the last two paid for live (`runs/run_5ed0a8827153` burned an admission
slot re-admitting a site it already had, `policy.py:43-53`). The audit trail survives only
because the project wrote it into its report node's output (`agent.py:1085`).

**Why it is general.** It exists because `http_fetch(allow_hosts=...)` freezes at
construction: dogfood-2 passed `allow_hosts=None` and re-implemented the host check in its own
wrapper (`tools.py:87-98`) — **the project switched the library's containment off to get a
dynamic version of it**. Any agent whose reachable set legitimately grows mid-run (a brand's
own site discovered from a search result, a linked documentation host) faces the same choice.
A rigid control that real projects bypass protects nobody, and the 2026-08-09 fix batch
(redirect-hop checks, private-address refusal) made the frozen list stronger without making it
growable, which sharpens this item rather than closing it.

**What ships.** A policy object `http_fetch(policy=HostPolicy(hosts, max_admitted=...,
max_fetches=...))`, mutually exclusive with `allow_hosts` (two sources for one decision is the
ambiguity item 4 rejected). `policy.admit(host, reason)` is callable from project code — a
route, a `Deterministic` node, a project tool — and refuses beyond the cap with the reasons so
far. Subdomain and `www.` handling ship inside it, since both were paid for live. The
private-address rule and per-hop redirect checks apply unchanged on top.

**What stays in the project.** Which hosts, which caps, and who may admit — content. The
policy is the mechanism.

**Design questions for the implementer.**
- **Replay soundness.** The policy is intra-run mutable state read by a filed tool. The
  occurrence ordinal in the tool-call key (`simple-agents.md` §8.2) is what makes intra-run
  impurity replay correctly; confirm with a test that a refused-then-admitted-then-fetched
  sequence replays as exactly that sequence.
- **The audit surface.** Admissions and the fetch count deserve to outlive the run somewhere
  the library owns. There is currently no channel for a tool to write manifest entries; do not
  invent one inside this item. The honest v1 is: the refusals and admissions are visible in
  the trajectory (every refused call is a recorded `tool_call` with a model-facing error), and
  a `policy.report()` the project can put wherever it likes. If a manifest surface is wanted,
  that is its own design conversation.
- `max_fetches` overlaps conceptually with DF2-D2 (bounding what tools do); keep this ceiling
  a count, not a cost — money is that sitting's question.

---

## 7. URL cache in front of the network

**What the project built.** Dogfood-2 `fitfinder/cache.py` (154 lines): `PageCache` (URL-keyed
raw+reduced+meta with `max_age_days`) and `SearchCache` (keyed on the whole request including
domains and depth), wired through `tools.py` and `agent.py:1236-1241`, with cache hits
surfaced to the model as a `[from local cache, read N days ago]` prefix.

**Why it is general — and the honest scope line.** The builder's constraint in `plan.md`
§4.3(c) is "cache everything — pages and extractions — into a local store", and the library's
current answer (`builtins/http.py` docstring: the cassette is the cache) is right for replay
and wrong for the second run: a new run with different queries re-fetches every page the last
run read. Two independent pressures converge on the same store: politeness to origins during
development iteration, and metered spend (a cached search is $0.005 not spent — also the datum
that makes DF2-D2's declared totals 6× wrong). That said, caches are a classic scope sink.
The scope line: **this is a cache for the two shipped network tools, not a general
memoisation framework.** No eviction beyond `max_age_days`, no size accounting, no locking
beyond atomic writes with last-writer-wins, all stated in the docstring.

**What ships.** `http_fetch(cache=UrlCache(dir, max_age_days=7))` and the analogous
request-keyed cache usable by `web_search` (offered to the provider seam, since only the
provider knows a request's full identity). A hit is stated in the tool's return value the way
the project did it, so the model knows the page's age. The cassette records whatever the tool
returned, hit or miss — replay soundness is untouched, and the occurrence ordinal covers a
run in which the same URL is fetched before and after expiry.

**Design questions for the implementer.**
- Cache directory is project-supplied and project-owned; the library never picks a location.
- An evaluation replaying from a cassette never touches the cache; a recording evaluation
  does, and the cassette then holds cache-served bodies — say this plainly in
  `docs/run-envelope.md` §3, because "which run is the ground truth for this page" is a
  question a builder will ask.
- Interacts with item 5: cache the raw body, reduce on read, so a reducer change does not
  invalidate the cache.

---

## 8. `load_env`, the smallest form — dropped

**Dropped 2026-08-09, on Thilina's ruling: outside the scope of the library.** The generality
check below reached the same conclusion and then argued itself back on the
`Redaction(secret_env=...)` composition; the ruling is that the composition does not make env
parsing agent machinery. Nothing was built. Revisit condition: none recorded. The section as
approved follows.

**What the projects built.** Three hand-rolled `.env` loaders: dogfood-1 `agent.py:237-245`
and `verify_unanswerable.py:57-65` (duplicated within one project), dogfood-2
`fitfinder/config.py:31-53`; dogfood-1 run 2 punted to a shell incantation in an error
message. 3-of-3, each citing the same reason: nothing in `simple_agents` reads `.env` and
python-dotenv is not a dependency.

**The generality check, honestly.** Env loading is generic Python tooling, not agent
machinery, and on the pure ST test this would be dropped — except for one library-shaped
fact: the library already holds the *names* of secret env vars, in
`Redaction(secret_env=[...])`, and dogfood-2's loader deliberately returns names-not-values
for exactly that reason. The value here is the integration, not the parsing.

**What ships.** `simple_agents.load_env(path=".env")`: stdlib parsing of the common subset
(KEY=VALUE, comments, blank lines; no interpolation, no multiline), environment-wins
semantics, returning the tuple of names it set — so the one-line composition the projects
were reaching for exists: `Redaction(secret_env=load_env())`. Twenty lines and a hard scope
statement in the docstring; anything fancier is python-dotenv's job and the docstring may say
so. If this still feels like scope creep at review, the fallback position is documentation
naming python-dotenv in `docs/run-envelope.md` — but that puts a dependency into every
project to avoid twenty stdlib lines in one place, which is the trade the library usually
makes the other way.

---

## 9. Grounding helpers, and the pattern documented once

**What the projects built.** Both dogfoods built a grounding check — the same shape twice,
independently. Dogfood-1 run 2 `agent.py:246-299` (`finalize`): the asserted span and quote
must appear, after normalisation, in the passage cited. Dogfood-2 `agent.py:897-931`
(`chase_is_grounded`, a `finish_check`): `evidence_url` must be a page this node actually
read, checked against `ctx.tool_calls`, with the two-strike accept rule from `docs/tools.md`.

**Why it is general.** *A claimed source must be backed by material the run observably
touched* is the false-confidence mission (FT-09/FT-10) applied to citations, and it is
checkable from data the library already records. The seams both projects used —
`finish_check` plus `ctx.tool_calls`, or a `Deterministic` verifier node — worked; what
recurred is the boilerplate.

**What ships.** Two small helpers and one documented pattern, not a framework:
`url_was_read(ctx, url)` (was this URL an argument to a successful tool call this node made,
with the `www.`/scheme normalisation dogfood-2 needed), and a normalised-containment check
(`contains_normalised(haystack, needle)` with the case/whitespace/punctuation folding both
projects wrote). The pattern — reject a finish citing something never read, and read
`ctx.finish_attempts` before rejecting twice — gets one worked example in `docs/tools.md` §5
where `finish_check` is already documented. What counts as grounded (exact span? same host?
quote match?) stays a project decision; the helpers are string and tool-call plumbing.

---

## Dropped and demoted, with revisit conditions

**Sitemap catalogue reading — dropped.** Dogfood-2 `fitfinder/sitemaps.py:57-113`
(`CatalogueReader`: robots → declared sitemaps → one level of index → URL list, bounded).
Single-project evidence, and it fails the anti-tunnel-vision check: sitemap traversal is a
crawling concern, and the dogfood protocol's own constraint (`plan.md` §4.3(c)) is "search
via API, not crawling". Shipping a crawler-shaped component against the library's own stated
posture, on n=1, is how "a library for the dogfoods" happens. Revisit condition: a second
independent project builds one despite items 4–7 existing. The project's ranking half
(`TEE_WORDS`, `score_url`) would stay project-side in any case.

**Plausibility bounds — pattern documented, no API yet.** Dogfood-2
`fitfinder/matching.py:63-73,142-147,160-167` (`PLAUSIBLE_CM`): a model-read number outside
physical bounds is treated as a mis-read — discarded, the reason recorded, the row demoted —
never corrected and never a schema failure. The semantic is genuinely interesting and
mission-aligned: pydantic `ge`/`le` cannot express it, because a constraint violation
triggers a schema retry where the wanted meaning is "accept the payload, read this value as
absent with a stated reason". But it is n=1, and a `Bounded[float]`-style annotation whose
violation *validates to a different type* is deep pydantic surgery with sharp edges
(serialisation, schema generation, the `Maybe` union). Ship it first as a documented pattern
in `docs/pipeline.md` §4 beside the output-schema material — a `Deterministic` node applying
project bounds and folding violations to `Unknown(reason=...)`, which is exactly what the
project did and what its log defended ("a prompt is not a guarantee"). Revisit as an API when
a second project writes the same node.

**Search-provider budget counters — redirected.** Dogfood-2 `providers/linkup.py:63-71,
101-107,144` grew live/cached counters, a live-search ceiling, and a `usd_spent` figure. That
is DF2-D2's evidence, not a seam item: the code that knows whether a call hit the network is
the provider, at call time, and that fact is the concrete shape for the measured-spend design
item. Nothing to build here until that sitting.

**Cumulative store merge policy — stays project-side.** Dogfood-2 `results.py:91-236`
(`merge`/`revalidate`, keep-measurements-recompute-verdicts): a fitfinder decision, and a good
one, served by item 1's read surface rather than absorbed.

---

## Evidence updates for the sittings

Recorded here so the audit's findings reach their owners; nothing in this section is a build
item of this document. **Both entries are settled as of 2026-08-09**, and each says what its
sitting made of the evidence. Two of the figures below were wrong; the corrections are in
place and say so.

- ~~**DF2-D1 (loop accumulator).**~~ **Settled at its sitting, 2026-08-09**, and both figures
  here were checked against `agent.py` and the runs rather than taken. **Four workspace files is
  right about the code and overstates the artifacts**: `candidates.json` reaches only 2 of the
  18 runs, having been added near the end, and it is written [where the builder can read
  it](../../runs/dogfood-2/agent.py#L521) rather than to reach a later node, which makes it a weaker
  instance than the other three. **"~200 lines of deletable plumbing" is about double.** The
  cited ranges total 242 lines, of which roughly 150 are domain logic that survives the change
  unaltered: `_record_finding` is 61 lines, the `report` body 45, and `finalise`'s bucketing
  another 11. What actually goes is the four constants, the five read and write helpers, the
  three writes and their comments, and about ten call sites: **near 90 lines net, with one node
  added.** `build-logs/loop-accumulator-build-log.md` is the record, and §1.6 carries the
  measurement that mattered more than either of these, which is in dogfood #1 run 2 rather than
  in this project.
- ~~**DF2-D2 (measured tool spend).**~~ **Settled at its sitting, 2026-08-09**, and this
  evidence is what shaped it: a tool now reports what it was charged through a `SpendMeter`,
  which is the "tool reports what it actually spent" shape §9.1 of the findings left open.
  `build-logs/tool-spend-build-log.md` is the record.

---

## 10. ~~Undecided:~~ Settled: the labelling and ground-truth machinery

**Held and built 2026-08-09; `build-logs/ground-truth-build-log.md` is the record.** What
shipped: `docs/evaluation.md` §1.4 rewritten to a fan-out, `RunEnvelope(role=...)` so a
labelling pass written into `runs/` is not read as the agent's run, `Label` with
`evals/labels.jsonl`, and `who_labels` moved to stage `build`. A conformance check over the
label file was declined on the `simple-agents.md` §3.2 ceiling, and the one-call envelope was
declined a second time, this time on a measurement: §1.4's shape is 10 lines against the ~50 it
replaces, and a one-line helper would save about four more. **Two things in the paragraph below
did not survive the sitting** and are marked where they appear: the test cited as met was never
administered, and the three artifacts are not one shape. The entry as written follows.

Left out of the approved list and **not** handled elsewhere, so it is recorded as an open
decision rather than silently dropped. **Merged with DF2-D8 into one ground-truth sitting on
2026-08-09**, on Thilina's ruling: `label.py` is the artifact behind both, and where a label is
stored and who can see it is not separable from how it was made. Three sessions built it by hand (~565 lines): dogfood-1
`verify_unanswerable.py` (182 lines, hand-built `ModelRequest`, hand-rolled retry, no record
written), dogfood-1 run 2 `tools/verify_unanswerable.py` (219 lines, same shape, and its
unrecorded first pass was the one that was wrong), dogfood-2 `label.py` (164 lines: label
store, interactive CLI, Wilson at 56-69, projections at 80-85, importing nothing from
`simple_agents`, labels in `evals/labels.json` where no check can see them). ***Corrected at
the sitting: "three sessions built it by hand" counts three files and describes one shape,
and there are two.*** The first two are a model constructing labels before a run; `label.py`
makes no model call at all and adjudicates what eighteen finished runs produced. Two more
artifacts of the same class went uncounted: dogfood-1's `data/hand_review.json`, a human
adjudication store with a hand-written provenance header, and run 2's `MANUAL` dict inside
`tools/build_examples.py`, which is human verdicts kept in source code. Five stores, three
projects, five formats. R2-D7's
disposition was prose-only with an explicit test — "If a third does it with §1.4 in place,
the docs are not the problem". ***Corrected 2026-08-09 at the ground-truth sitting: the third
session received neither §1.4 nor the scaffold, so the test was not administered.*** The
measurement is in `runs/dogfood-1/run2-findings.md` §9.3. `wilson_ci` landed at the DF2 sitting; the
store, the session shape, and the one-call envelope did not. What a library offering would be
(a labelling store the checks can read? a `label` CLI? the one-call envelope made one line?)
is a design question with real scope risk in both directions, and it needs a sitting
rather than a paragraph here. **That sitting also carries DF2-D8**, which is where the label
lands and who can see it: `evals/labels.json` against `DEFAULT_RESULTS` of `evals/results`
([artifacts.py:41](../../src/simple_agents/conformance/artifacts.py#L41)).

**Which of the three options was taken.** A labelling store shipped and **no check reads it**,
which is the half of "a labelling store the checks can read" that survives the ceiling. The
`label` CLI did not ship: an interactive session is the project's own, and the store is the
part that was rebuilt five times. The one-call envelope did not ship, for the third time.
What was not in the list of options is what mattered most: a run saying what it is for, which
came out of measuring what `runs/labels` did to FT-13 and FT-14 rather than out of the
artifacts.
