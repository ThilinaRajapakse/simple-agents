# Item 7 checkpoint — findings and triage

The cold-read checkpoint `archive/plan-history.md` §3.5 asks for after item 7, analysed. `runs/checkpoint-item7/setup.md`
is the brief this was run against.

**Status: both sessions run and analysed. All six held items decided and landed (§6).** Nothing here is
logged against Phase 2. The brief's §1 known gaps — no tool-authoring guide, no procedure, brief
or gates, no eval machinery, and anything environmental — are not findings.

Two sessions, from one selection, differing only in how the same 1,088 paragraphs were packed
into files:

| | Session 1 | Session 2 |
|---|---|---|
| Project | `musique-paragraphs` | `musique-volumes` |
| Corpus as delivered | 1,088 files, one entry each | 61 files, ~18 entries each |
| Model | `mistral-small-2603` | `mistral-medium-2604`, switched mid-build |
| Shape built | 3 nodes: `AgentNode` → `Deterministic` → `LLMNode` verifier | 1 `AgentNode` |
| Snapshot | `~/checkpoint-answers/session-paragraphs-snapshot/` | `~/checkpoint-answers/session-volumes-snapshot/` |

---

## 1. Method

Every claim in each session's `report.md` was reproduced against the source before being
accepted. Both reports were written to the same prompt, requiring each factual claim to be marked
`[verified]` / `[recalled]` / `[inferred]`, and in both the marking held up. Neither contains
praise of the library to discount, which is a difference from item 5.

Verification changed the answer four times: three of session 1's reported gaps are not findings
(§5), and one finding I filed against the documentation on session 2's evidence did not survive
a probe and is withdrawn (§5.1).

**Two protocol failures, recorded so they are not repeated.**

- **Session 1's artifacts were overwritten mid-analysis.** A score taken against its second full
  batch cannot be re-derived: the third batch replaced `answers.out.*` and the run directories
  forty minutes later. **Snapshot before reading, not after.** A batch that is still running is
  still writing.
- **Session 2's tree was inconsistent when it stopped.** `results/` was produced under prompt
  `musique-qa-2`; `agent.py` on disk says `musique-qa-3`, added after the batch and never run.
  This was detectable in seconds because every manifest records `prompts[].version`, which is
  FT-15 doing exactly what it was specified to do on a real project with nobody checking. Scores
  in §7.2 are attributable to `musique-qa-2`.

---

## 2. The corpus, and what it cost to make it honest

Recorded because the measurements are not cheap to retake and the brief's §4 wrinkles turned out
to understate the problem. **MuSiQue-Full** (`musique_full_v1.0_dev.jsonl`, CC BY 4.0), verified
against the brief's five criteria rather than taken on its recommendation.

**The unanswerable class does not survive pooling, and the brief names only the smallest of three
routes by which it fails.** An unanswerable record shares its `id`, question and `answer` with its
answerable twin, differing only in that one to four supporting paragraphs were swapped for
distractors (over 400 twinned pairs: one removed in 188 cases, two in 202, three in 8, four in 2).
`is_supporting` is cleared on every paragraph of an unanswerable record, so the removed paragraph
is identifiable only by differencing against the twin.

| Route | Detection | Rejected in the final build |
|---|---|---|
| The removed paragraph reappears from another question's set | Exact text, and title | 18 |
| An unrelated entry states the withheld value outright | Normalised substring over the whole pool | 5 |
| The corpus supplies the other hops and the model completes the withheld one from memory | Closed-book screen of the *resolved* withheld hop | **32** |

The third is the largest and is invisible to every check on the corpus. Screening the composed
question catches roughly half of what screening the resolved hop catches, because the composed
question is hard and its final hop is not. The screen is prompt-sensitive: under an instruction to
abstain the model answered `UNKNOWN` to hops it can in fact produce, so admission uses a
forced-guess prompt and the contamination number uses the abstaining one.

**Two matcher defects were found by reading the review output rather than by any gate.**
`normalise` stripped accented characters, so `Île de la Cité` compared unequal to the model's reply
of the same string. And a reply that is a subset of the gold ("1929" for "11 February 1929") read
as not-recalled. Both let a known answer through, and both were caught by eye.

**What shipped.** 40 questions, 25 answerable and 15 unanswerable, over 1,088 paragraphs, 90,109
words, about 141,560 tokens: 2.8x Mistral's per-minute token quota and 3.5x vLLM's
`max_model_len`. Eight gates pass and the builder writes nothing if any fails.

**Second-lookup dependence, measured on the corpus that shipped**, using the library's own BM25:

| | final-hop document found, question alone | with the bridge entity added |
|---|---|---|
| volumes, top 5 of 61 | 7/25 | 17/25 |
| paragraphs, top 10 of 1,088 | 9/25 | 19/25 |

**Contamination: 0 of 25** answerable questions answered correctly closed-book. It is a floor
rather than a bound: the prompt instructed the model to abstain when unsure.

### 2.1 The document shape did not survive contact, and that is a result about the instrument

The volumes corpus was built to create per-retrieval context pressure, on the reasoning that five
1,500-word results is 7,500 words where five 80-word results is 400. Session 2 undid it in about
forty lines. `corpus.py` splits the 61 volumes back into the 1,088 entries they are made of and
indexes those, and it uses the collection README's own sentence to justify doing so: *"A file is
a storage container, not a subject ... Indexing whole files would score a match on one entry and
hand the model seventeen unrelated paragraphs with it."*

Both sessions therefore retrieved at entry granularity, and **neither ever set
`max_input_tokens`**. The grouping bought a preprocessing step rather than a different design.

**The conclusion for a future checkpoint: document packaging is not a lever on the context
decision.** A competent reader normalises the corpus to whatever unit retrieval wants before
building anything. Forcing a context decision needs a task where the material that must reach one
model call is irreducibly large, not a corpus that is merely awkwardly filed.

---

## 3. Library defects

| | Defect | Sessions | State |
|---|---|---|---|
| L1 | `finish_check` cannot see tool calls made earlier in the same turn, depending on their order | 1 | Fixed — H1 |
| L2 | A `finish_check` cannot detect that it is rejecting the same payload repeatedly | **1 and 2** | Fixed — H1 |
| L3 | `Maybe[str]` admits the bare string `"unknown"` as an asserted value | 1 | Fixed — H2 |
| L4 | The rate-limit allowance is read from the response and discarded | **1 and 2** | Fixed — H4 |
| L5 | `ToolCallSummary` carries no tool result, so a `finish_check` cannot check what was returned | **1 and 2** | Fixed — H1 |
| L6 | An output schema's absence branch is never shown to the model, on any node kind | **1 and 2** | Fixed |
| L7 | Redaction scanned an allowlist of six record fields and wrote every other field raw | found while fixing L4 | Fixed |

**L2 reproduced independently, with different guards, and that is the strongest result of the
checkpoint.** Session 1's `finish_check` rejected a stringified absence; the model believed it had
already complied and resent the identical payload four times until `max_steps` ended the run, and
two questions were lost. Session 2 added a guard requiring two distinct lookups before accepting
an `unknown`; question 29, which is genuinely unanswerable, answered the refusal by calling
`finish` again unchanged **fourteen times** until the step limit returned nothing at all —
strictly worse than the honest `unknown` it replaced.

Session 2's own statement of the cause is the sharpest anyone has made: **"A `finish_check`
refusal is a suggestion, not control flow."**

Both sessions then reached for the same workaround, a step-count proxy for repetition detection:
session 2 made its nudge lapse after step 5, session 1 stopped arguing with the model and coerced
the value instead. The cause is at `nodes.py:718`: `made.append(ToolCallSummary(...))` sits only in
the non-`finish` branch, so `finish` attempts never enter `ctx.tool_calls` and no check can count
its own rejections.

**Both sessions produced a guard that was right about what it wanted to enforce and made the
outcome worse.** That is the shape of the finding: not that the feature is missing, but that the
feature as shipped converts a correct result into nothing.

**L1, verified against `nodes.py`.** The loop iterates `for call in response.tool_calls` and
computes `at_step = replace(ctx, step=step, tool_calls=tuple(made))` at the top of each iteration
(`nodes.py:674`), while `made` is appended to only after a non-`finish` tool runs (`nodes.py:718`).
A response carrying `[finish, document_search]` gives the check neither call; `[document_search,
finish]` gives it one. Which order a model emits is the model's choice, and item 7's own vLLM
recording showed Qwen issuing four tool calls in one turn.

**L3, reproduced directly.**

```
schema_admits_unknown(Answer)                          -> True
Answer.model_validate({"answer": "unknown"}).answer    -> 'unknown'   (a str)
Answer.model_validate({"answer": {"type": "unknown"}}) -> Unknown(...)
```

A schema passes FT-09's own check and still cannot distinguish a report of absence from an
asserted answer. `runs/checkpoint-item5/findings.md` §5.1 recorded this behaviour in session B —
"absence written as prose in the answer field, not fabrication ... the FT-09 failure exactly" —
and attributed it to the session. It is not the session's. It is a hole in the type the library
offers as the fix for FT-09, and it has now cost two sessions.

**L4, verified.** `_http.py:130` reads `response.headers.get("retry-after")` for backoff and
discards the rest; nothing reaches `ModelResponse`. Meanwhile `docs/model-clients.md` §6 names
`x-ratelimit-remaining-req-minute` and `x-ratelimit-remaining-tokens-minute`, states the free
tier's allowance, and tells the reader that pacing is their job. Both sessions wrote a pacer and
**both estimated**, because the interface exposes nothing. Session 2's estimator ran a running
mean over per-question spend that ranged from 4,700 to 122,000 tokens; it calls this "the single
largest piece of avoidable guesswork in the build", and the exact figure was in every response.

**L5, verified.** `ToolCallSummary` carries `name`, `arguments`, `ok`. Session 2 went looking for
`.result`, `.output` and `.value` and found none, and both sessions recomputed retrieval from the
recorded *arguments* instead. The `AgentNode` docstring's own example does the same thing, reading
`c.arguments["doc_id"]`, which is the workaround appearing in the library's own teaching material.
The natural check — did you cite what you actually read — needs the results.

**L6 was found by re-recording a cassette after fixing L3, and it is the same failure one layer
out.** L3's fix was in the `finish` tool's description, and an `LLMNode` has no `finish` tool: it
requests structured output directly, so a builder writing `LLMNode(output_schema=...)` got the raw
schema and no statement of either form. The `context` cassette caught it live, the model returning
`{"answer": "unknown", "reason": "..."}` — the word in the answer field and `reason` hoisted to the
top level, which is the object flattened rather than a value asserted. `Maybe` now carries a
default field description showing both forms, so the fix reaches every node kind, and a builder's
own `Field(description=...)` still replaces it. Re-recording afterwards returned
`Unknown(type='unknown', reason=...)` on the same call. One observation against a provider measured
diverging on 23 of 376 identical requests, so it is suggestive rather than settled.

**L7 was found by writing L4's redaction test, and it had been true since redaction was built.**
Redaction walked six named record fields and wrote every other field exactly as it arrived, so
adding `provider` put a `set-cookie` header into a trajectory with nothing raised and no test
failing. The list of walked fields lives in `redaction.py` and record fields are added in
`trajectory.py`, so the two were never edited together, and the guarantee that redaction happens
by construction held only for fields somebody had remembered to enumerate. Inverting it — every
field scanned except a named set the library generates — also brought `error` into the scan, so a
credential inside an exception message no longer reaches disk in the record most likely to be
pasted into a bug report. `simple-agents.md` §10 carries the general form.

**Related, not a defect, and it belongs with item 8.** There is no per-model-call hook, so pacing
can only wrap a whole run and a single question is free to burst past a per-minute allowance
mid-run. One did, at 122k tokens, and the retries absorbed the 429s that `docs/model-clients.md`
§6 says retries are not for. There is also no record-and-replay cassette mode, so changing only
the last node's prompt re-pays for every earlier call: session 1 estimates that cost it about two
thirds of roughly 100 minutes and $0.37 of about $0.55.

---

## 4. Documentation bugs

| | Bug | State |
|---|---|---|
| D1 | The reading-order lines frame `trajectory-format.md` as a producer's document | Fixed — H3 |
| D2 | `context.md` describes the builder only as subtraction; an adding builder is undocumented | Fixed — H3 |
| D3 | `tools.md` §2 offers `ToolRegistry` and a plain list as equals | Fixed — H3 |
| D4 | `model-clients.md` §3 supplies copyable dated prices in an example | Fixed — H3 |
| D5 | `document_search` gives no signal on whether a query word can be matched at all | Fixed — H5 |

**D1 is the one both sessions paid for.** Four of the six shipped documents name
`trajectory-format.md` in their reading order, and every one frames it as defining "the record
this writes to". **Neither session read it.** Session 1 said why: *"I skipped it because I thought
I only needed to produce trajectories, not read them."* Session 2 skipped `run-envelope.md` as
well.

Session 1 then spent the back half of the session reading trajectories and paid three times:
`arguments` against `inputs`, `messages` against `inputs`, and the shape of `to_wire()`. The
second had it conclude its context builder was inert and begin designing a fix for a bug that did
not exist.

The framing is what fails, not the ordering. A builder produces trajectories by construction and
reads that document as the library's concern. Nothing tells them they will be reading their own
runs to debug, and that this is the field map when they do.

**D2.** `docs/context.md` calls a builder "a view over the conversation, not a change to it", and
§3's four answers to overflow are all about giving the model less. Session 1 used the seam to
*add* a per-turn message stating how many turns remained, and said plainly it was unsure the use
was idiomatic. It is: `runs/checkpoint-item5/findings.md` §6 identifies the context builder as the
per-step hook session B asked for. That sentence is in `dev-docs/`, where no builder reads it.

**D3.** `docs/tools.md` §2 says "An `AgentNode` takes a registry or a plain list" and gives no
reason to prefer either. **Neither session used `ToolRegistry`.** The registry exists because
FT-19's and FT-23's static checks and item 8's runner need to enumerate every declared tool
including one no node uses (`simple-agents.md` §8.3). The document states the capability and not
the consequence.

**D4, narrowed by session 2.** `docs/model-clients.md` §3 hands a reader three copyable dated
prices. Session 1 copied them into its project under a comment claiming it had read them from the
provider that day, a provenance it invented and later corrected itself. Session 2 then fetched the
live pricing page for a different model and reports that **the page's Small figures match the
documented ones exactly**. So the numbers are right and the finding is only about the copying
behaviour and the false provenance line.

**D5 is new, and the first framing of it was wrong.** It was filed as "`document_search` cannot
distinguish absence from a badly worded query", as though it should be able to. **A retriever that
finds nothing has established only that this retriever did not find it.** The corpus may hold the
fact under a synonym, a different spelling, an inflection or a paraphrase, and lexical BM25 misses
all four. "Not found" never licenses "not present", which is true of a dense retriever and a
reranker as much as of BM25, and the correct report from the agent is `unknown` because the fact
could not be established rather than because absence was proven.

**The error was about to be shipped as prompt text.** Session 2's `entries_per_word` docstring
tells the model that if the top hits are not what it wanted, *"the collection does not cover that
subject"*. A model reading that concludes absence from a retrieval miss. Shipping the same feature
with the same framing would have taught that inference to every project.

**What survives is the signal, not the strategy.** Both sessions built the same thing: session 1
wrote `lookup_title`, session 2 wrote `lookup_title` **and** per-term corpus counts. The counts say
whether a word can be matched at all, which is a fact about the index. They say nothing about
whether the collection covers the subject. Session 2 also had to import the private `_tokens` from
`simple_agents.builtins.search` so its counts would tokenise exactly as the index does, and pinned
the import with a test because the tokeniser was not public; that wall is arguably the larger half
of the finding.

**A second scoping correction, from Thilina.** BM25 is the basic retriever the library ships for
simple cases, and an ambitious project brings its own. Instructing a model in query reformulation
to compensate for a weak retriever is the wrong layer, and it costs tokens on every call in every
project. The shipped docstring states what the tool returns and that a miss does not establish
absence, and stops there.

---

## 5. Reported, and not findings

Verification prevented five entries that would otherwise have been filed.

- **No `simple-agents` CLI.** True, and the documentation says so. `docs/failure-taxonomy.md` §1.3
  states the subcommand surface is not settled and "when the commands exist, the actions become
  invocations", and the package metadata lists the machinery as still to come. Session 1 inferred
  correctly from two sentences without running `ls .venv/bin/`, and regretted not running it. This
  is *not* a recurrence of item 5's S3, which was a document asserting an enforcement that did not
  exist.
- **`RunResult` has no total token count.** By design, and documented where session 1 did not
  look: `models.py:95` says the sums "charge less than was spent on any axis the backend left
  unknown". Its inference that `total` sums the measured classes and treats `Unknown` as zero is
  correct.
- **`arguments` and `messages` absent from trajectory records.** The field is `inputs`, specified
  three times in the document neither session read. D1's consequence, not a separate bug.
- **No `pytest` or `pip` in the environment.** Environmental. Both sessions hit it; session 2
  hand-rolled a `main()` that walks `globals()` for `test_*` functions.
- **Session 1's claim that its cost figures are "conservative" under caching.** They are not. The
  basis carries `input_cache_read_per_mtok` and the library prices each class at its own rate, so
  the derived figures are correct. Its expectation was conservative, not the number.

### 5.1 The caching contradiction, withdrawn as a documentation bug and now bounded

Session 2 reported model calls with `input_cache_read > 0` and no `prompt_cache_key` anywhere,
contradicting `docs/model-clients.md` §3's *"Without one, an identical prompt sent twice reports
`cached_tokens: 0` ... a measurement rather than an assumption."* **I filed that as a documentation
bug falsifying a measured claim carried in three documents. That was premature and it is
withdrawn.**

What is established:

- **The session's observation is real.** 301 model calls, 0 carrying a cache key anywhere in its
  code, **95 reporting a cached count — and the count is exactly 1,328 every time it is non-zero**,
  across different questions and different runs. It never tracks the previous turn's prompt size,
  so it is a fixed shared prefix rather than conversational growth.
- **The documented behaviour survives every direct test.** `scripts/probe_prompt_caching.py`, four
  configurations: `mistral-small-2603` and `mistral-medium-2604`, prompts of 3,265 and 29,725
  tokens, with and without tool declarations. **Every one reports `cached_tokens: 0` without a key
  and a non-zero count with one.** The adapter sends no key of its own; it only decodes.

**One further experiment settled where the difference is not.** Session 2's trajectory stores every
request verbatim, so the call that reported `uncached=585 cached=1328` was replayed through the
adapter eight times. Every send reported `uncached=1913 cached=0`, and 585 + 1328 = 1913, so the
request is the same one and the response differs. **The difference is therefore not in the
request**, which rules out the model, the prompt size, the tool declarations and repetition in one
measurement.

What is left is the backend's own state. Session 2 made 301 calls sharing a 1,328-token prefix over
35 minutes; eight sends from cold do not reproduce it. `docs/model-clients.md` §3 now says caching
is opt-in by default, that the provider has been observed caching without a key under conditions
that have not been characterised, and that the recorded count is whatever the backend reported, so
cost derives correctly either way. Cost was never affected; the claim was.

---

## 6. Decided and landed

Six items, put as a batch as the four were at item 5. All six were decided in one pass and are
in the code; the arguments below are what they were decided on, and three of them changed during
the discussion.

**H1 — the `finish_check` contract (L1, L2, L5).** The feature item 7 shipped in answer to session
B produced a worse outcome than its absence in both sessions. Three changes, one decision:
summarise `finish` attempts so a check can see its own rejections; build `at_step` from the calls
already made in the current response as well as earlier ones; and carry the tool's result on
`ToolCallSummary` so a check can test what came back rather than recomputing from arguments.
Changes what an `AgentContext` contains, which is public surface introduced at item 7 and not yet
depended on outside the library.

**H2 — `Maybe` and the stringified absence (L3).** Reject a bare `"unknown"` during validation with
a message naming the object form; or coerce it, which is a semantic decision about the builder's
data that session 1 made in a helper; or leave it and document the hole. The first reads
`simple-agents.md` §2.6's "never coerced to an error, empty string, or guess" in the other
direction. Reaches do-not-change #6, so the argument has to be made explicitly.

**H3 — the documentation batch (D1 to D4).** Individually cheap, collectively a decision about what
the reading order is for. D1 is a sentence. D2 is a paragraph and an example. D3 is a clause naming
the consequence. D4 is either marking the figures as an example or telling the reader to fetch
them.

**H4 — surfacing the rate-limit allowance (L4).** The library reads the headers already. The
question is whether the common surface takes a field for them, which `simple-agents.md` §2.5's rule
resists: every field in the common response type must be one the library itself reads, and nothing
in the library paces. The counter-argument is that item 8's runner will issue calls in parallel and
will need exactly this, so the field acquires a library reader at the next item.

**H5 — absence against a bad query in `document_search` (D5).** Both sessions built the same fix.
Options: return the per-term corpus counts alongside the hits; make the tokeniser public so a
project can build it correctly; or document the pattern and ship neither.

**H6 — whether `docs/context.md` should bless the adding builder (D2).** The one held item that
could change a settled position: item 6 decided the builder is "a view over the conversation", and
an injection point is a different thing wearing the same interface. Session 1's use is sound and
the record proves it, since `dropped` stayed empty and accurate.

### 6.1 What changed during the discussion, and why

Three of the six were argued down from what was first proposed. Recorded because the first
proposal was wrong in a way that would have shipped.

- **H2 was going to be a validation guard.** The proposal was to reject the bare string
  `"unknown"`, justified as "the model is naming our type rather than supplying the builder's
  data". Two questions defeated that: whether the collision is caused by choosing a common English
  word as a reserved value, and whether the model knows about the type at all. Checking what the
  model is shown answered both. It is told to use "the schema's `unknown` variant" and **never
  shown the shape**, the payload form appears nowhere it can see, and the reserved token is the
  word it would write in plain English. The fix moved upstream to showing both forms, and the
  guard is deferred until the instruction has been fixed and the failure re-measured.
- **H5's framing was wrong about retrieval**, see §4's D5.
- **H4 was going to be declined.** The proposal was to hold the rate-limit field out on the
  grounds that `simple-agents.md` §2.5 requires every common field to have a library reader.
  That is an argument from a rule rather than from the situation, and the rule was the thing
  under question. The decision went the other way, and wider: named fields for what the library
  reads, plus a general passthrough for what it does not, because discarding everything the
  library has no use for gets in the way of a builder who does have a use for it.

**The general form, which now governs more than this checkpoint: decide on merit, and where a
rule has to move, argue from what happened rather than from the rule.**

---

## 7. What the brief asked to watch, answered

**The most valuable thing this checkpoint could produce did not happen, in either session, and
that is the headline result.** The brief names a capable reader hand-rolling truncation inside a
prompt function as the single most valuable outcome. Session 1 reached for the seam instead: a real
`ContextBuilder` with `to_manifest`, holding no state between calls, reasoning explicitly about why
`dropped` stays empty and citing `docs/context.md` §4. Session 2 used the default `AppendAll` and
never needed one. **Neither hand-rolled truncation anywhere.**

| Asked | Session 1 | Session 2 |
|---|---|---|
| Is `docs/tools.md` found? | Yes, read second of five, before any code | Yes, read in full |
| Is `ToolRegistry` used? | **No.** A plain list | **No.** A plain list |
| Built-ins found, or `document_search` rewritten? | Found and used; added `lookup_title` | **Rewrote it**, naming the builtin and saying why it was insufficient (D5) |
| Are `ModelHandle` and `Workspace` discovered? | No, neither needed | No |
| Is `AgentNode(finish_check=...)` found? | **Yes**, and it is where L1, L2 and L5 surfaced | **Yes**, same |
| Is `docs/context.md` found? | Yes, read third | Yes, read in full |
| Seam or hand-rolled truncation? | **Seam**, for injection rather than dropping | Default `AppendAll` |
| Is `max_input_tokens` set? | **No** | **No.** Manifest records `max_input_tokens: null` |
| Reaches for `AgentNode`, and says what the model decides? | Yes, with FT-11's justification: the second lookup's argument is a value the first returned | Yes, one `AgentNode` |
| How is a 429 read? | Correctly: a `ModelClient` that paces in front of the adapter and delegates `identity()`, citing §6 | Correctly, same shape, and it names the estimation it was forced into as its largest guess (L4) |
| Which documents went unread? | `trajectory-format.md` | `trajectory-format.md` **and** `run-envelope.md` |

Session 1 read five of six documents before writing any code, at turns 21 to 41 of 440.

### 7.1 The behavioural comparison with item 5

Session B at item 5 read the failure taxonomy in full and then tuned four prompt versions on one
run each, catching itself at the fourth. That is the project's strongest evidence for why the
checks must be executable.

**Session 1 revised five times on single observations too, and recorded it.** Its brief names the
five questions of forty that influenced the build, cites FT-02 on why a number over them is
uninformative, states that the diagnoses came from trajectories and `grep` rather than answers,
declines to print an accuracy claim, and declares tier `prototype` for that reason. It then lists
what it would need to claim `evaluated`: k ≥ 5 rollouts, bootstrap intervals with n, per-node
metrics, FT-10's split, and an ablation of its one `AgentNode`.

**Session 2 supplies the counter-example the taxonomy warns about, with its own evidence.** It
tuned every threshold against single runs of single questions, and it holds the measurement that
says why that fails: at `seed=41` and `temperature=0.0`, question 1 took **15 model calls and
122,164 tokens on one run and 4 calls and 14,210 tokens on another**. That is independent
confirmation of `docs/run-envelope.md` §5's claim that a hosted seed is best-effort, produced by a
session that had not read that document.

**Reading the taxonomy produced honest abstention in one session and undiagnosed n=1 tuning in the
other.** Neither is correct measurement, because the machinery to do it does not exist yet. What
item 8 has to show is whether the same readers, handed a runner, measure instead.

### 7.2 Scored against the held-out answers

| | answerable (25) | unanswerable (15) |
|---|---|---|
| Session 1, `mistral-small`, 3 nodes with verifier | 8 correct, 1 wrong, 16 unknown | 15/15 unknown, **0 false confidence** |
| Session 2, `mistral-medium`, 1 node, no verifier | 23 correct, 0 wrong, 2 unknown | 12/15 unknown, **2 false confidence** (1 run incomplete) |

**These two rows must never be compared as a measurement of anything.** They differ in model and
in architecture at once, and neither session was evaluating itself. Session 1's row is not
re-derivable (§1).

Both of session 2's false confidences were verified individually. Q27: it searched for the withheld
entry, found nothing, guessed the city itself (*"likely Dongguan"*) and asserted a date. Q40: the
corpus supplied the early hops and memory supplied the withheld one, and the value it asserted is
exactly what the model said when that hop was screened closed-book during corpus construction. The
screen admitted the question correctly, because a *wrong* confident value is real false confidence
while a *correct* one would have been mis-scored recall.

**What the pair does show, confound-free:** two builders, one corpus, one task text, opposite ends
of the precision/recall trade, and **neither was asked which end to sit at.** Session 1 chose it
alone and built three mechanisms around it. Session 2 made the same decision by omission, which is
the harder case to catch, because nothing in its artifacts records a decision at all.

---

## 8. Elicitation questions these sessions earned

Each is a question a builder should have been asked, where the absence caused something visible,
and each ships with a way to answer it. Format follows `runs/checkpoint-item5/findings.md` §7, which
item 12 reads.

| Question | Scaffold that makes it answerable | Evidence |
|---|---|---|
| When the agent can find an answer but cannot prove it from what it retrieved, should it report the answer or report `unknown`? | Show the builder one worked example of each outcome from their own corpus and have them pick. **Fire it whether or not the project builds any verification**, since the decision is as often made by omission | Session 1 decided alone that a missed answer is cheaper than a wrong one, built three mechanisms around it, and wrote in its brief that the bias "is the trade the builder chose". Session 2 made the opposite choice by building nothing. 0 false confidences against 16 misses, versus 2 against 2 |
| If the agent writes the word "unknown" where the schema wants the unknown object, is that a report of absence or a malformed run? | Offer the two behaviours and what each costs: coercing decides what the model meant, refusing risks a loop the model cannot escape | L3. Session 1 coerced, in a helper, having first tried refusing and lost two questions to an unbreakable rejection loop |
| What form does a correct answer take, and who fixes it? | Show three candidate answers to one of the builder's own questions, in three formats, and have them pick | Session 1 inferred "the shortest span that answers the question" and noted that if the ground truth holds sentences its output mis-scores on formatting alone |
| Which model, at what price, and who approves a change to it? | State the per-question cost at the current model and at the alternative, from one measured example | Session 2 switched the default to a model at roughly 10x the token price on the evidence of **one question**, and spent $2.37 without asking. It flags this itself as the decision most clearly the builder's |
| How many times may this be re-run before you want to see it? | Derivable: run one example, read the cost and wall clock, multiply | Session 1 ran three full batches, about 100 minutes and $0.55, each decided without asking |
| Where do the prices in your cost basis come from, and when were they last checked? | The provider's pricing page and a date, recorded next to the figures | D4. Session 1's rates were copied from a document dated two days earlier under a comment claiming they had been read that day |

**The first outranks the rest and is now backed by two independent instances pointing in opposite
directions.** It is the same shape as item 5's "does a wrong answer cost more than a missing one",
arriving harder: these sessions did not merely fail to separate the two rates, they chose the
weighting between them, and one of them then attributed the choice to the builder in the artifact
the gates will read.

---

## 9. What this checkpoint left for item 8, and what item 8 did with it

All four are answered. `archive/plan-history.md` item 8 carries the decisions; this records which of them
this checkpoint is responsible for.

- ~~FT-20's promise is still unverified end to end.~~ **Enforced.** A rollout over a tool
  declared `spends_money` is refused before anything runs, naming the tool, the class and the
  k×n count. The test is the one item 5's session B ran by hand.
- ~~The eval runner is what turns both sessions' abstention or n=1 tuning into a
  measurement.~~ **Built.** Session 1's five conditions for claiming `evaluated` — k ≥ 5
  rollouts, bootstrap intervals with n, per-node metrics, FT-10's split, an ablation — are four
  built and one deferred to item 8a. Whether the same readers, handed a runner, measure instead
  of abstaining or tuning at n=1 is the question the next §3.5 checkpoint asks.
- ~~`cassette.diverged` … turning that into an interval is this item's job.~~ **It is the wrong
  instrument, and that is a result.** A rollout's seed is in its cassette key, so two rollouts
  of one example are two different requests and never collide; `diverged` only fires when the
  *identical* request is recorded twice. The two measure different things: `diverged` measures
  whether a backend reproduces itself at a fixed request, and the interval measures whether the
  agent reproduces itself across seeds. The second is what an evaluation needs, and the live
  recording produced it directly — one example, fixed seed, `temperature=0.0`, correct on two
  rollouts and absent on the third.
- ~~A record-and-replay cassette mode and a per-model-call hook both belong here.~~ **Both
  landed, and one of them changed shape.** The cassette mode is `Cassette.update`, sized by
  session 1's measured cost of re-recording. The per-model-call hook did **not** ship as a hook:
  pacing needs only the request and the response, both sessions independently wrote a
  `ModelClient` wrapper, and the seam is already a Protocol, so `PacedClient` is that wrapper. A
  hook on `RunEnvelope` would be the more general answer and would need its firing contract
  settled now against one known use. It can be added later without removing the wrapper.
