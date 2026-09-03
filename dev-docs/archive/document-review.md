# The shipped-document review

`plan.md` §1 P3-3's record, archived 2026-09-01. **Folded into `P3-66` and closed with it**:
the post-review sections got their correctness read at that build
([`build-logs/the-feature-index-build-log.md` §4](../build-logs/the-feature-index-build-log.md#L44)),
and nothing surfaced needing Thilina's language call. **Moved out of `handoff.md`
on 2026-08-15**, which is a pointer rather than a place state lives.

## Where it came from

Thilina's own pass over the shipped documents, begun 2026-08-09, recorded in the inbox until
2026-08-15. His standing guidance from it is §3.

## What the problem is

**What the review is.** A read of each shipped document with Thilina, one at a time. It is a
conversation rather than a task, and it is sixteen of sixteen documents in.

**What the split is**, on his ruling at the dogfood #1 run 2 sitting: he reviews language,
ambiguity and contradiction, and correctness is ours. Prose that is clear and false is a code
defect that happens to live in a document (`runs/dogfood-1/run2-findings.md` §7.1).

**A documentation correction is applied when it is found, never held for this item.** What is
merged into this item is reading each corrected document once, so no document is read twice. The
full-test pass's corrections landed in 2026-08-13's merge
(`runs/full-test-2026-08-13/FINDINGS.md`) and dogfood #4's on 2026-08-15
(`build-logs/consultation-build-log.md` §4).

## What has to be decided

Nothing structural. Which document is read next, and when.

### Where each document is

**Every document has been read once**, as of 2026-08-19. `evaluation.md`, `run-envelope.md`
and `shipping.md` were read before this item began; the other thirteen were read into it. What
is left is the text those three gained afterwards, which the table's third column carries, and
`evaluation.md` is still queued behind `P3-14` and `P3-20`.

**`docs/product.md` was read on 2026-08-21**, at `P3-31`, on Thilina's own reading rather than
in a sitting. His verdict was "no comment, LGTM", so the document stands as written and this
item's remainder is unchanged by it. It was the newest shipped document and the only one that
had never been read, having been written the day before at `P3-30`.

**`index.md` was read on 2026-08-19.**

**`retrieval.md` was read on 2026-08-19.**

**`conformance.md` was read on 2026-08-19**, straight after `procedure.md`, because the
procedure sets the gates and conformance is what a gate runs.

**`memory.md` was read on 2026-08-19**, on Thilina's call that it is small enough for the
conversation, the same as `procedure.md`.

**`docs/evaluation.md` gave up the marker on 2026-08-18**, having held it since the table was
written. It is in another session's working tree for `P3-19`, and two scheduled items will add to
it: `P3-14` puts the judging pattern into §12, and `P3-19` touches `progress_of` and
`on_rollout=`. Reading it now repeats what its row already records, which is a document reviewed
in the item before the one that adds to it.

**Two documents were read out of the table's order on 2026-08-18**, both on Thilina's call.
`README.md` was picked off the backburner while `P3-12` was building, being the one document
whose review comments were still sitting in the shipped file. `procedure.md` followed it because
it ships as the skill, so it is the text a coding agent loads before anything else.

| Document | Reviewed | Text added since, and by what |
|---|---|---|
| `failure-taxonomy.md` | yes | item 13; FT-29; the `ship` stage's FT-31 |
| `trajectory-format.md` | yes | the delegation item's §4.4; the Gemini item's §4.1.4 |
| `run-envelope.md` | yes | the delegation item's §2.5; memory's §2.2; the Gemini item's §4.2; the `ship` stage |
| `tools.md` | yes | item 13; the delegation item's §1; semantic recall's §4 and §4.1; memory's §4; the paid-evaluation item's §1.5; the `ship` stage's §4.6.2 |
| `pipeline.md` | yes | the delegation item's §2.5; two sentence shapes corrected 2026-08-19 under the rule the `memory.md` review produced |
| `context.md` | yes | — |
| `model-clients.md` | yes, re-read 2026-08-19 | the Gemini item's §1 and §2, both read at the re-read |
| `evaluation.md` | no | items 9, 8a, 13 and 14, including a whole §10 and §11; the paid-evaluation item rewrote §7.2 and added §6.3 and §7.7, so it gained three sections in the item before the one that reviews it |
| `index.md` | yes, 2026-08-19 | rewritten in place; the record is §4 below |
| `conformance.md` | yes, 2026-08-19 | rewritten in place; the record is §4 below |
| `procedure.md` | yes, 2026-08-18 | rewritten in place; the record is §4 below |
| `retrieval.md` | yes, 2026-08-19 | rewritten in place; the record is §4 below |
| `memory.md` | yes, 2026-08-19 | rewritten in place; the record is §4 below |
| `shipping.md` | no, and new | — |
| `model-clients/mistral.md`, `vllm.md` | yes, 2026-08-19 | — |
| `model-clients/gemini.md` | yes, 2026-08-19 | — |
| `README.md` | yes, 2026-08-18 | rewritten whole; the record is §4 below |

**Five of the seven documents finished before 2026-08-18 have gained text since they were
reviewed.** A finished document can carry unreviewed text, because later items edit the documents
they need when they need to rather than waiting for this item.

### `docs/procedure.md` is also the skill

It is force-included into the wheel a second time at
`simple_agents/.agents/skills/simple-agents/SKILL.md`. Editing it edits both. Six tests in
`tests/test_procedure.py` hold every command, stage, path and citation it names, and one holds it
to a word budget. **The budget moved from 1355 to 1600 at the `ship` stage**, on Thilina's
approval, to hold a fifth stage, then to 1700 and to 1775 as later items added to it. **The
review of 2026-08-18 spent nearly all of what was left**: it sits 2 words under, and the tier
table is what took it. A review comment counts toward the budget too, so the file failed this test for as long
as Thilina's three sat in it.

### Standing guidance from Thilina

**Moved here from `random-thoughts-questions.md` on 2026-08-15, with permission**, because it
governs every document read rather than one of them. His words, dated 2026-08-09.

- He is doing a pass stripping out the more flowery, defensive, hedging and weird language.
- **The README's tone. Discharged 2026-08-18**, and read before the evaluation item rather than
  after it as this said. *"The README might be pushing the idea that this library is written for
  coding agents a bit too much. It's not FOR coding agents, it's ALSO for coding agents."* And not
  to over-correct: the answer is to bring the places where the message is pushed to him, not to
  add defensive language in the other direction. **The quote still governs every document.** Five
  places in the README pushed the framing; three were kept and two removed, recorded in §4.
- **No bare section references.** *"Multiple bare references like 'See §6.2.'. These are not
  helpful. Section 6 of which doc and where? If I can't follow them, it's unlikely that a coding
  agent or builder can either."*
- **No question-and-answer format.** *"Docs disseminate information, not arguments."*
- **Write for release, not for now.** Builder-facing docs are written as of the released library
  rather than the current state of development.
- **What a proposed change has to carry**: the original wording, the proposed wording, and the
  comment of his that triggered it.

**Added 2026-08-18, at the README sitting.** The first four are his words from that sitting; the
last two are notes moved out of `README.md` when its HTML comments were deleted.

- **No contrastive where a plain statement does the work.** *"The contrastive is not needed. And
  in general, I don't like the X-not-Y sentence structure."* "with intervals rather than a single
  number" became "with a confidence interval on every figure". Now in `CLAUDE.md` under "How to
  write it", because it governs `docs/` as well. Wider than `prose_check`'s `EMPHATIC` rule,
  which catches `X, not Y.` at a sentence opening and no `rather than` clause at all.
- **Present tense in prose describing what a snippet does.** "The model decided when to search"
  became "The model decides when to search".
- **`README.md` may address its reader as "you".** Decided 2026-08-18, against the third-person
  rule that governs everything else, on the argument that a landing page speaks to someone who
  has not chosen the library. `prose_check.py`'s `ADDRESSES_THE_READER` holds the exemption and
  it names one file. **This does not extend to `docs/`**, which was the option offered and
  declined.
- **A count stated without the definite article loses `prose_check`'s guard.** "Eight rates are
  reported" reads better than "The eight rates", which promises a set the reader has not been
  shown, and `COUNT_PHRASE` matches only `the <number> <noun>`. Where the article goes, a
  file-local test takes the count over. `tests/test_readme.py` now holds three.
- **The README carries no HTML comments.** *"Don't leave the comment in the readme. That doesn't
  need to go public along with the repo."* A note between us goes here instead. Two are parked
  from that deletion: **a provider list** once a fourth model adapter ships, and a **"What is
  built"** section if the library ever ships while items are still in the pipeline.
- **Who the README is for**, his note of 2026-08-09, moved here from the file itself: *"The readme
  should be written for the builder and not the coding agent. It's most likely to be read by a
  human landing on the Github page... That does not mean we should explicitly say it, just that
  the writing style should be builder facing."*

## What each document's review found

One section per document, appended as it is read. A document reviewed before 2026-08-18 has no
section: the reviews were conversations and left no record beyond the table above.

### `README.md`, read 2026-08-18

**Why it was read out of order.** Picked off the backburner while `P3-12` was building. It was
the one document still carrying its review comments in the shipped file.

**One question was raised here and left**, whether `builder` should be `developer`. It is in the
inbox, dated 2026-08-18, and the rewrite left the word in one sentence of the README.

**What was verified before anything was proposed.** All 17 HTML comments; `git log -S` over two
of them; [`tests/test_readme.py`](../../tests/test_readme.py#L1) in full, because four of its
tests pin strings a rewrite would move; [`scripts/prose_check.py`, `CHECKED`](../../scripts/prose_check.py#L46);
and the API surface behind every sentence the rewrite would claim, which is `RunResult.cost`
([events.py:47](../../src/simple_agents/pipeline/events.py#L47), `cost`), `MistralClient.api_key`
([mistral.py:84](../../src/simple_agents/adapters/mistral.py#L84)), `_refuse_unsafe_tools`
([runner.py:2129](../../src/simple_agents/evaluation/runner.py#L2129)), `DocumentIndex.from_directory`,
`document_search`, `Interval`, `TokenUsage`, `RECORD_TYPES`, `taxonomy()`, `CHECKS`, `STAGES` and
`cli._parser`. Thilina's Simple Transformers README and docs site were read for register; Medium
returns 403 to fetching, so the articles he named were not.

**Two statements were false before anything was written.** The tools bullet described
`spends_money` and `irreversible` with the behaviour of one: `_refuse_unsafe_tools` refuses
`IRREVERSIBLE` outright and names record-then-replay, while `SPENDS_MONEY` runs whenever
`max_spend` is declared. And `result.cost` is a dict, beside prose that read as though it were a
value.

**A comment of Thilina's had been orphaned.** `<!-- I think we need a section here. -->` was
written under `## Cassettes and Replays` in `bfc3bd8`; `d13e46e` deleted the heading and kept the
comment, because
[`test_every_heading_has_something_under_it`](../../tests/test_readme.py#L73) fails a heading
whose only content is a review note. The section is now written.

**Three shipped documents were missing from the table**: `retrieval.md`, `memory.md`,
`shipping.md`. `tests/test_readme.py` checked that every path named resolves and never the
reverse, which is the direction that failed.

**Four decisions Thilina took**, each put with its alternatives.

| Decision | Taken | Declined |
|---|---|---|
| Voice | Second person in `README.md` alone | Third person throughout; second person across `docs/` too |
| First example | An `AgentNode` searching the builder's own documents | Two nodes and one model call; keeping the capital-of-France toy |
| New sections | Cassettes and replays, Building with a coding agent, Measuring the agent, badges | — |
| "Why this exists" | Rewritten, kept | Folded into the opening; cut |

**The voice decision moved a shipped rule.** `CLAUDE.md` said "Third person. No 'you' or 'your'"
with no exception and `prose_check.py` enforced it over `README.md`. The argument put was that a
reference document describes the library to someone who has already chosen it, and a landing page
addresses someone who has not. `ADDRESSES_THE_READER` names one file and exempts one rule.

**What shipped.** `README.md` rewritten whole, ten sections, and no HTML comment survives.
`prose_check.py` gained `ADDRESSES_THE_READER`, and `tests/test_prose.py` joined `SKIP` on the
ground that already had it carved out of the count rule: its fixtures are one deliberate defect
per rule. `tests/test_readme.py` went from 10 test functions to 13, three guards following the claims
they guard rather than being deleted and three new; `tests/test_prose.py` went from 11 to 15.
`CLAUDE.md` gained the voice exception and the no-contrastive rule. Suite 2629 passed, 2
skipped.

**The exemption matches on a file name**, so a second `README.md` anywhere under `src/`, `docs/`
or `tests/` would be exempted without anyone choosing it. There is none today and
`test_the_exemption_reaches_one_file_in_the_checked_trees` is what says so.

**The rate count needed a new home.** "The eight rates" promises a set the README does not show,
so the article went; `prose_check`'s `COUNT_PHRASE` matches `the <number> <noun>` and requires
the article on purpose, so that "two rates that are averaged" is not a false positive. The guard
moved into `tests/test_readme.py`, beside the taxonomy count and the record-type count that are
there for the same reason.

**Five more statements were corrected during the verify pass, after the text was written.** Each
was believed true when drafted.

| Said | Is |
|---|---|
| 34 characteristic failures, "each with a check" | 16 of the 34 have a shipped check |
| the taxonomy is "the failures the conformance suite checks for" | the taxonomy is the specification, wider than the suite |
| "Every node validates its output against a schema" | `Deterministic` may have none; required on `LLMNode` and `AgentNode` |
| a schema with no absence branch is "refused when the pipeline is built" | refused when the node is built |
| trajectory holds "one entry per node execution, model call and tool call" | five record types, including `consultation` and `delegation` |

**Live verification**, which nothing in the suite does for this file. A three-document
`policies/` corpus in the scratchpad and the first-agent snippet copied verbatim.

- **Mistral returned 402** on `mistral-small-2603`: "Check your subscription". The account is out
  of quota, so the snippet could not be exercised on the backend it names.
- **The same pipeline on `gemini-3.1-flash-lite` completed.** `result.output.answer` came back
  `'You have thirty days from the date of delivery to return a damaged item.'`, which is now the
  string the README prints rather than the shorter one drafted for it. `source` was `'returns.md'`.
  The run passed no envelope and its directory held `manifest.json`, `trajectory.jsonl`,
  `cassette.jsonl` and `workspace/`, which is the four entries the README lists and what "nothing
  has to be switched on" claims.
- **The cassettes section ran end to end.** Recorded, then replayed with `GEMINI_API_KEY` removed
  from the environment and a bogus key on the client: identical output, `cassette.mode` `replay`,
  3 hits, no network. A changed prompt raised `CassetteMiss` naming the node and the field that
  differed with both character counts, which is what the section claims.
- **No vLLM server was running**, so the third adapter was not exercised. The README makes no
  claim specific to it beyond its constructor line, which is unchanged.

### `docs/procedure.md`, read 2026-08-18

**Read in the conversation rather than in a plan-mode sitting**, on Thilina's call that the
document is small enough for it. Three comments of his, and six corrections owed under the split.

**What was verified before anything was proposed.** `STAGES` and
[`STAGES_BY_TIER`](../../src/simple_agents/conformance/stages.py#L49); the three tier names at
[`ORDER`](../../src/simple_agents/conformance/taxonomy.py#L50); `DECISION_KINDS`, which is six;
the question counts behind "thirteen questions, eight required"; the thirteen built-in tools; the
word budget and what `tests/test_procedure.py` pins; and every `§n` this file cites, resolved to
the heading it lands on rather than to whether one exists.

**The file was failing its own test when it arrived.** 1825 words against a budget of 1775,
because `test_it_is_under_the_word_budget` counts a review comment like any other word. Removing
the three left 1722 and 53 words to spend.

| Comment | Taken |
|---|---|
| The tier paragraph is *"vague and confusing. Can we communicate this better using a table? Or is that a worse format for a coding agent to read?"* | A table, three rows |
| The builder-and-coding-agent paragraph is not *"helpful or needed. This doc is a skill."* | Deleted whole |
| *"I think it's risky to use a real example in procedure.md."* | Domain removed, TOML shape kept |

**A table is the right format here, and the prose proved it.** "At `prototype` there is no
`measure`, so **its** questions are not asked" has two candidate antecedents one word apart. A
cell belongs to its row and has none.

**The first attempt at the table was rejected, and Thilina was right.** It had two rows and a
sentence reading "a project goes live from any of the three", and it still never said what a tier
is: the word arrives in the third paragraph of the file with nothing introducing it. The shipped
version gives each tier a row and a `What it claims` column, which is what defines the term, and
"the three" then resolves against what is on the page.

**What could not be written.** `docs/conformance.md` §1.1 has `trained` covering "the RL hazards,
plus everything below", and `evaluated` and `trained` run the same sixteen checks. Nothing
distinguishes them today, so the row says what the project claims rather than what runs.

**The paragraph was also false.** "a project goes live from **either**" counts two tiers where
there are three.

**One clause was argued for and lost.** "the questions it leaves out are the ones a particular
project turns on" was the only part of the deleted paragraph that changes behaviour, and Thilina
ruled the whole thing goes.

**Six corrections owed under the split**, five of which saved the words the tier table spent.

| Was | Is |
|---|---|
| `on_rollout=` cited to `docs/evaluation.md` §6.5 | §6.5 is resuming; watching is §6.6 |
| "written rather than left absent" | "is written as `not_applicable`" |
| "from one example's consumption rather than from round numbers" | "from what one example consumed" |
| "says the run was recorded, not that the agent works" | "says only that the run was recorded" |
| "to a split rather than drawing examples one by one" | "to a split", since the colon clause already says it |
| "Where the project keeps it rather than returning it" | "Where the project stores the result for later reading" |

The last five are the no-contrastive rule from the README sitting, applied to a second document.
The `prose_check` section rule passes a citation whose section exists, so a reference landing on
the wrong section is found by reading and not by a check.

**No live run.** This document names commands and cites sections; it claims nothing a backend
answers. What stands in for it is `tests/test_procedure.py`, which resolves every command, stage,
path and citation the file names: 106 tests, all passing. Suite 2682 passed, 2 skipped.

**Nothing to update in the skill copy.** `simple_agents/.agents/skills/simple-agents/SKILL.md` is
generated from this file by hatch at build time
([`pyproject.toml`, `force-include`](../../pyproject.toml#L43)), so there is no second file in the
tree to drift.

### `docs/memory.md`, read 2026-08-19

**Read in the conversation**, the third document taken that way. Two of Thilina's three comments
recorded deletions he had already made; the third asked for a sentence structure rather than a
fix to one sentence.

**What was verified.** `MemoryStore(directory, scope)`, its `forget`, `keys`, `get`, `entries`
and `__len__`; `MemoryEntry.embedded_by`; `MAX_KEYS_ON_EMPTY`, which is the 50 the text names;
both import paths in the examples; and all four external section citations resolved to the
heading they land on. `pipeline.md` §1.3 is Joins, `tools.md` §3.2 is handles,
`run-envelope.md` §6 is Redaction, `retrieval.md` §4 is Ranking. Every one was right.

**Thilina deleted two "Measured against a live model" passages** and called them defending a
position. **Nothing was lost twice over**: the measurements are in
[`build-logs/memory-build-log.md`](../build-logs/memory-build-log.md#L417) and
`semantic-recall-build-log.md`, and the shipped text already carried the same point in one
clause, that a fact stored as "prefers books under 300 pages" is not found by a search for
"length preference". A measurement belongs in a build log; in a shipped document it reads as the
library arguing for itself with a war story.

**The rule the third comment produced.** *"I am not telling you not to use counts. That would be
stupid. I am telling you to write the same content but in a different structure. E.g. 'There are
three built-in tools.' A full sentence instead of an awkward short clause."* The objection is the
fragment and the welded clause, and never the count.

**A first reading of that comment was wrong and he corrected it.** It was read as an objection to
counting at all, and the proposal removed the count. What he wanted was the same content as a
full sentence.

| Was | Is |
|---|---|
| "Three built-in tools." | "There are three built-in tools." |
| "**Three limits, and they follow from the store outliving the run.**" | "**Redaction here has three limits.** Two of them follow from the store outliving the run that wrote it." |
| "Refused before the run starts, read off the tool declarations." | "The library reads this off the tool declarations and refuses before the run starts." |
| "**What this measures and what it does not.**" | "**This measures what the agent does with what it remembers**", the label deleted since the sentences under it already said it |

**The welded clause was also false.** "Three limits, and they follow from the store outliving the
run" led three bullets, and the first is the general redaction limit: rules match known
credential formats and declared values, which is as true inside a run and in a trajectory. Only
two of the three follow from outliving. A clause glued on to give a count something to be about
invented a cause that covers two thirds of its list.

**Two more corrections.** The opening's "a value routed around the graph is a value the records
cannot explain" defended the design and went. And "on the rule that covers every re-run tool"
named a rule and pointed at nothing; it is `docs/tools.md` §3.2, which this file already cites
twelve lines earlier.

**`docs/pipeline.md` was reopened for two sentences**, on Thilina's instruction, and it is a
document already marked reviewed. "Three things stop a run, and all three are continued the same
way" and "Three limits, and only one of them ends the run" are the same shape. Both are now full
sentences, and both counts stay.

**No live run.** This document's claims are about an API and about what is written to a store,
and all of them were resolved against the code. Suite 2682 passed, 2 skipped.

### `docs/conformance.md`, read 2026-08-19

Thirteen comments, and the largest of the three inline sittings. It is also the first review to
change shipped output rather than only prose.

**What was verified.** The sixteen rows in §2 against `CHECKS`; the nine taxonomy entries naming
`prototype`; the five notes assembled at [`run.py`](../../src/simple_agents/conformance/run.py#L81);
the exit statuses; `STAGES_BY_TIER`; and the text the command actually prints when a brief is
missing, at [`_MISSING`](../../src/simple_agents/conformance/brief.py#L420).

**Five comments were one problem: nothing said what a tier or a stage is.** §1.1 opened with a
table whose columns were *Covers*, *Its stages* and *Of the sixteen, it runs*, three answers to
what a tier does and none to what it is. Thilina named the consequence himself: *"This might not
even be needed if the tiers and stages were actually explained properly."*

**"A tier is what the project claims to be" was wrong, and he caught it.** He asked whether a
tier is what a project claims to be or what it wants to be. Neither: a tier is declared before
the project has met it, and an `evaluated` project fails FT-01 from that moment until it has an
evaluation. It is an intention the checks enforce, which is what §1.1 now says.

**`trained` shadows `evaluated`.** Its one distinct taxonomy entry, FT-26 "Reward function
trivially gameable", is not among the sixteen shipped checks, so the two tiers run the same
sixteen. The document's "the RL hazards, plus everything below" implied otherwise. It now says
`trained` is on the roadmap, which is the correction Thilina asked for.

**Three sentences said something the reader could not recover.**

| Was | Is |
|---|---|
| "the command exits 2 saying which line to write" | "The command exits 2 and prints the `tier =` line to write", which is what `_MISSING` does |
| "**The two** are found separately" | "**The run and the results file** are found separately" |
| "the usual way to meet FT-03 is that the evaluation never ran" | contamination is caught by `EvalSuite.run` before the first rollout, so FT-03 is the backstop for a results file produced some other way |

**§2.2 read as a continuation of its own heading.** Thilina: *"Is this paragraph somehow using the
section header as two questions and answering them?"* It opened on a list of conditions with no
subject. It now opens "FT-13 passes when the newest run holds a readable trajectory."

**The design-decision sweep he asked for.** He deleted one and wrote *"check for other instances
of this... these design decision explanations do not belong in docs/"*. Four more were in this
file, at §1, §2.2 twice and §3, each keeping its operative statement and losing the argument for
it. **One of them carried a typo he had introduced**, "the list in `from` is ready by whoever
wrote it", and deleting the sentence resolved it. **The sweep of the other documents is not
done** and is a sitting of its own.

**The report stopped printing glyphs.** *"Why use symbols instead of just saying blocked and n/a
or something?"* `----` and `--` were a legend a reader had to look up in a different document,
while the summary line on the same report already counted them in words.
[`LABELS`](../../src/simple_agents/conformance/report.py#L151) now holds `pass`, `FAIL`,
`blocked` and `n/a`, right-aligned in the width of the longest. `Outcome.BLOCKED` and
`Outcome.NOT_APPLICABLE` were already those words in JSON, so nothing machine-readable moved.

**Four surfaces referenced the old glyphs and all four were found before changing them**:
`docs/conformance.md` twice and its sample report, `docs/procedure.md`, `docs/failure-taxonomy.md`,
and the regex at `tests/test_conformance.py`. `dev-docs` references were left, since they
record what was true when they were written. **`procedure.md` sits 2 words under its budget and
the swap cost nothing**, because each glyph and each word is one token to `split()`.

**The sample report is asserted equal to real output**, by
`TestTheSampleReportIsWhatTheSuitePrints`, so it was regenerated from the `no-evaluation`
fixture rather than hand-edited.

**Two tests were rewritten rather than relaxed.** `test_the_prototype_row_lists_the_checks_that_tier_runs`
read FT ids out of a table cell that no longer holds them, so it became two: one pinning the
row's count and one pinning the ids in the sentence under the table, which now names what the
tier drops rather than what it runs. And the nine-entries assertion became case-insensitive,
because the sentence it reads now starts one.

**No live run.** Every claim here is about files the suite reads and text it prints, and all of
it was resolved against the code. 2618 passed with this work in the tree.

**A second pass on 2026-08-19, on three more comments after the first was committed.**

- **The document defined its terms after using them.** `1.1 Tiers and stages` was a subsection
  of `1. The brief`, so the brief's `tier` key was described before anything said what a tier is,
  and line 31 forward-referenced its own subsection. Thilina: *"shouldn't 1.1 come before the
  subsection above it?"* Tiers, stages and gates is now `§1`, `The brief` is `§2`, and everything
  after it moves up one. `Which stage a project is at` went with it, since it is about how a
  stage is determined rather than about a key in the file.
- **Eight cross-references followed the renumbering**, plus one in `CHANGELOG.md` that
  `prose_check` caught. A changelog is exempt from the count rule and not from this one: a stale
  count is a record of what was true, and a pointer that resolves to nothing is only a reader
  going nowhere.
- **"Gate" was two words.** Asked whether `§1` should explain gates, and it should, which forced
  a choice. `docs/procedure.md` defined a gate as the command a stage ends at; nine taxonomy
  failure messages and three sentences here use it for a single check that fires. **The majority
  sense wins on cost**: gate as a check makes all twelve existing uses correct, including nine
  shipped strings and the sample report that quotes one, and leaves one sentence in
  `procedure.md` to change, which came in shorter than what it replaced.
- **The note wording was coy.** "the answer to the note is `tier = \"evaluated\"`" became
  "gets a note suggesting `tier = \"evaluated\"`", which is what
  [`_stages_the_tier_drops`](../../src/simple_agents/conformance/run.py#L728) actually prints.
- **Renumbering by two passes double-applied itself**, turning `2.1` into `3.1` and then into
  `4.1`. Caught by reading the headings back, and redone as one pass through a marker.

**Seven tests and 93 integration tests were failing on arrival**, from another session's
in-flight `src/simple_agents/tools.py`, which moves `tool_version` and misses every cassette
keyed on it. Confirmed not this work's by stashing these files and seeing the same seven fail.

### `docs/retrieval.md`, read 2026-08-19

**Thilina edited the document himself before handing it over**, and left one comment. Most of
the review was reading what his pass had done.

**He stripped every measurement**, as at `memory.md`: the MS MARCO comparison, `k=5` against 60,
the `VectorScan` timings, the 17 kB vector, the reranker's measured gain, "one to two orders of
magnitude cheaper". **Each was checked and each is in `dev-docs`**, in
`build-logs/semantic-recall-build-log.md` and the `full-test-2026-08-13` records. Nothing left
the record.

**Two sentences went with them that were instructions rather than measurements**, and both are
back, pointed at the library's own machinery rather than at retrieval advice, which answers his
objection that *"it's not the library's job to teach Information Retrieval"*: `compare_variants`
measures hybrid against one arm, and a reranked search against the same search without one.

**Three defects the edit pass introduced.**

| Was | Is |
|---|---|
| a truncated sentence, "introduces `DocumentIndex` and ." | he fixed it himself mid-review; a double space was left and went |
| "Three comes pre-built" | "Three come pre-built" |
| "**Lexical retrieval relies on (sub)word overlap.**" | it matches whole words and stems nothing |

**The third was factual and the truth is more useful than the claim.**
[`tokens`](../../src/simple_agents/builtins/search.py#L109) is `[a-z0-9]+` over lowercased text.
Measured over a two-document index, `"books"` returns only the document saying *books* and
`"book"` only the one saying *book*. "(sub)word" would have a builder expect a plural to find its
singular.

**That produced a `plan.md` §2.1 entry, and his framing was narrowed.** He asked for BM25 to be
"implemented properly, not this half assed whole word match".
[`lexical_scores`](../../src/simple_agents/builtins/search.py#L674) **is** textbook BM25:
smoothed Robertson IDF, `K1 = 1.5`, `B = 0.75`, length normalisation against the mean. The gap
is the analyzer in front of it, which is a smaller and differently-shaped piece of work, and the
entry says so rather than accepting the premise.

**One comment, on `WeightedScore`.** *"This explanation is confusing and reads very much like AI
slop. Especially the 'nothing matched'."* The sentence described real behaviour by the worst
route: [`combine`](../../src/simple_agents/builtins/ranking.py#L212) divides by
`max(abs(score))` per list, so each list's top result becomes 1.0 on every query. It now says
that. **The same sentence was in the docstring the document was copied from**, and both moved.

**The Hybrid row's `Misses` cell had gone circular**, reading "things that neither Lexical() nor
Semantic() can find", which is true of any union. It carries the real caveat again: hybrid can
rank a decisive hit below two indifferent ones.

**Five of his own rules had survived his pass**: an X-not-Y opening, a hedge ("likely cheaper")
where the measured figure had been, a fragment ("20 by default."), a "Note that", and a markdown
anchor link where every other document uses a plain `§n`.

**No live run.** The claims are about an API and a scoring function, and the tokenizer claim was
settled by running a search rather than by reading it.

**A repo-wide `check_citations --fix` was run and reverted.** It re-anchored 24 `dev-docs`
files against another session's mid-edit `src/`, which is the hazard this session had already
recorded two commits earlier. **`--fix` is for a tree whose source is settled**, and the one
citation that needed correcting was written by hand instead.

### `docs/index.md`, read 2026-08-19

Two comments. One was a question about a claim, and the other handed the table over: *"I didn't
read the whole table, but you know what to look for now."*

**The claim was false, and his instinct about what should replace it was right.** *"'it says
when to open each of the others'. Is this true? ... I would imagine that the more useful thing
for a coding agent is clear signposting to send it to the docs it needs at a given point."*
`docs/procedure.md` names nine of the sixteen: `conformance`, `evaluation`, `failure-taxonomy`,
`index`, `model-clients`, `pipeline`, `retrieval`, `shipping` and `tools`. It never names
`context.md`, `memory.md`, `run-envelope.md`, `trajectory-format.md` or the three adapter pages.
**And what it does is signposting**, at the point of need: "Read `docs/pipeline.md` first",
"Read `docs/tools.md` §4 before writing a tool the library already ships". The sentence now says
each stage points at the documents that stage needs, and a second sentence gives the table's
right column the job for the seven no stage names.

**Two rows in the table were wrong.**

| Row | Was | Is |
|---|---|---|
| `failure-taxonomy.md` | "The failures the conformance suite checks for" | 34 entries and 17 checks, so it names what no check enforces yet. The same overstatement was fixed in `README.md` on 2026-08-18 and this copy was missed |
| `conformance.md` | "the brief and the tier a project declares" | stale since the 2026-08-19 restructure put tiers, stages and gates in `§1` |

**The opening was the README's old sentence**, the one Thilina called corporate bullshit, still
here after that document was rewritten: "It ships an agent shape as tested code, a run envelope
that records what every run did, and an evaluation that reports rates with intervals rather than
one number." It also ends on the contrastive banned the day before. It now matches the opening
he approved for `README.md`.

**Nothing guarded this file, which is the one whose job is to be the list.** `README.md` lost
three documents that way in August and gained a test for it; the canonical index had no test at
all. `tests/test_packaging.py` gains two: every shipped document has a row, and the count in
"These sixteen documents" is the number of documents that ship. Both were checked to bind rather
than pass vacuously.

**No live run.** Every claim is about which files exist and what other documents say, resolved by
reading them.

### The three adapter pages and `model-clients.md`, read 2026-08-19

Taken as one sitting. Thilina edited `gemini.md` and `mistral.md` and left no comment; `vllm.md`
and `model-clients.md` were a pass under the rules the earlier sittings settled.

**His edit pass broke the build in two places**, both inside code blocks.

- `gemini.md`'s price block became `input_uncached_per_mtok=<input_uncached_per_mtok>`, which is
  not valid Python, and `prose_check` fails a fenced block in `docs/` that does not parse. The
  obfuscation is right and the syntax was not: named figures (`INPUT_RATE`, `CACHE_READ_RATE`,
  `OUTPUT_RATE`) parse and say the same thing. `input_cache_write_per_mtok=0.0` stays a literal,
  because §3 says that specific zero is what makes a Gemini call priceable at all.
- `mistral.md` carried a review note **inside the shipped code block**: `input_uncached_per_mtok
  = 0.15, # Thilina: I would also obfuscate the actual numbers here`. Done, the same way, and the
  note removed.

Two smaller ones went with them: a double full stop left by a deletion in `gemini.md` §4, and
"As of writing" in §5, which is the hedge the "write for release" rule exists for.

**What he stripped, and the line it draws.** Prices, the dates they were read, and specific
provider figures: the OpenAI-compatible endpoint's token under-reporting, a listed model that
answers 404, a 6,129-token prompt reporting 4,076 cached, thinking tokens falling to none.
**Three measurements were left in place and should stay**, and they are a different kind:
`model-clients.md` §2's dates qualify a table whose own preface says its rows go stale,
`mistral.md` §6's date qualifies a universal claim about every model that API serves, and
`vllm.md` §5's is the evidence that the concurrency reading can be trusted at all. Each is about
what was measured of the library or the seam, and none is a figure a provider republishes.

**`model-clients.md` §4 said the same thing three times.** "An evaluation running rollouts at
once through a client that does not pace warns", "A run that waits through a client that does not
pace warns, once", and "A per-minute quota is cleared by pacing rather than by retrying" between
them stated one behaviour, one cause and one consequence, twice over each, and the
`max_wall_clock_ms` and `held_back_ms` facts a third time after the `PacedClient` paragraph had
already carried them. They are one paragraph now. A fourth, "Writing a different one is a matter
of standing an object with `complete` and `identity` where the adapter stands", sat between two
pacing paragraphs with no antecedent and is what §7 is for.

**Four design justifications and a subject-verb error.** "An absent divisor makes cost an upper
bound, and an invented one makes it wrong" restated the sentence above it; "inventing a rate
would be a claim about a limit nobody stated"; "rather than quietly wrong"; and the assumed-
concurrency paragraph in §7. **The two floors are what decide**, not decides. And "A window
measured in days is not paced, it is waited out" was a comma splice.

**Every figure the pass leaned on was checked against the code**: `Retry`'s shipped defaults sum
to exactly 31.0 seconds over five waits, `RateLimit` carries the three fields named,
`PacedClient` has `expect_callers` and `request_floor`, `MistralClient` takes
`stream_without_usage`, and the manifest carries the `totals.held_back_ms` the section names.

**No live run.** Backend behaviour is what the adapter pages describe and what the cassettes
already hold; nothing here changed code. 2681 passed.

## What it waits on

Nothing. It proceeds one document at a time, and a correction found anywhere is applied on sight
rather than held for it.
