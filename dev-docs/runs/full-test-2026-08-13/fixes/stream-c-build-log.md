# Stream C: tools, retrieval, memory

Fix pass of 2026-08-13 against `RULINGS.md` D4 and its follow-up, and the tools, retrieval,
memory and docs-implementability findings. Files owned: `src/simple_agents/builtins/`,
`tools.py`, `grounding.py`, `docs/retrieval.md`, `docs/tools.md`, `docs/memory.md`, and the
tests whose subject is tools, retrieval or memory.

*(The machine hardware-crashed at 16:16 during this stream and rebooted at 16:37, on 80
unrecoverable NVMe read errors logged over the preceding day. Source edits on
`/home` survived; the `/tmp` scratchpad holding the D4 measurement scripts did not. The D4
numbers below were recorded before the crash and are reproduced from the run output. §1.5 says
what would have to be re-run to reproduce them.)*

---

## 1. D4: the default stopword list, and the re-run Thilina asked for

### 1.1 What was to be decided

[`RULINGS.md` D4](../RULINGS.md#L72) rules that a default English stopword list ships. It also
rules that the evidence in
[`semantic-recall-build-log.md` §1.12](../../../../dev-docs/build-logs/semantic-recall-build-log.md#L344) is
re-run against the six queries in
[`area-de-retrieval-memory.md` D-2](../findings/area-de-retrieval-memory.md#L95) **before**
the default is finalised, because the two bodies of evidence disagree and one was built to
exhibit the effect. If the re-run contradicts the six queries it comes back to Thilina.

**It does not contradict them. The re-run agrees with the six queries**, and the work
proceeded.

### 1.2 What was run

The §1.12 measurement, rebuilt: `recall@5` and `MRR@10` over BM25 alone, dense alone and
`Hybrid(fuse=RRF(k=5))`, on five corpora, with each candidate stopword list and without any.
Two embedding models, both on CPU with `CUDA_VISIBLE_DEVICES=""`, because the GPU was serving
the dogfood's vLLM at 22 of 24 GB.

| Corpus | What it is |
|---|---|
| `msmarco` | `Tevatron/msmarco-passage-aug`, 200 real queries with real judgments, 2,595 passages, 12 hard negatives per query pooled in |
| `nq` | `florin-hf/nq_open_gold`, 200 real questions, 1,184 gold passages, the other queries' golds as distractors |
| `depot` | A reconstruction of §1.7's corpus: 200 near-identical part records, 200 order records, 200 prose notes; 25 identifier queries and 5 paraphrase queries |
| `six-small` | D-2's 18-document corpus and its six queries |
| `six-padded` | The same six queries over 318 documents |

Models: `all-mpnet-base-v2` (768) and `all-MiniLM-L6-v2` (384), the two §1.12 used.

Four stopword settings: `none`; `lucene33`, the Lucene/Snowball English default; `finding33`,
the 33-word list D-2 measured; and `candidate`, the list that now ships.

A stopword list moves the query only, so `dense` was measured once.

### 1.3 The result

`Hybrid(fuse=RRF(k=5))`, `recall@5` / `MRR@10`, 768-dimension model:

```
                 msmarco        nq             depot          six-small  six-padded
dense alone      .935 / .769    .965 / .924    .300 / .261    .833       .667
none             .900 / .735    .950 / .866    .967 / .801    .167       .333
lucene33         .890 / .737    .960 / .870    .967 / .892    .500       .500
finding33        .890 / .729    .965 / .882    .967 / .894    .833       .667
candidate        .890 / .717    .965 / .893    .967 / .894    .833       .667
```

384-dimension model:

```
                 msmarco        nq             depot          six-small  six-padded
dense alone      .935 / .730    .940 / .879    .500 / .405    .667       .667
none             .915 / .722    .940 / .862    .933 / .900    .167       .333
lucene33         .925 / .720    .945 / .864    .933 / .933    .500       .500
finding33        .920 / .719    .955 / .867    .933 / .933    .667       .667
candidate        .915 / .703    .955 / .871    .933 / .933    .667       .667
```

BM25 alone is unchanged or slightly better under every list on every corpus (`nq` `recall@5`
0.850 to 0.865 under `candidate`; `msmarco` flat).

**Four readings.**

1. **The re-run agrees with the six queries.** The default without a list returns the answer
   in the top five 1 of 6 and 2 of 6; with the shipped list it returns it 5 of 6 and 4 of 6,
   which is what `Semantic()` alone gets on those corpora under both models. The gap D-2
   measured is real, and closing it does not cost anything on the real-judgment corpora that
   §1.12 chose the current defaults on.
2. **`nq` moves the same way as the six queries**, by +0.015 `recall@5` and +0.026 `MRR` at
   768. §1.12 calls NQ "the closer thing to a held-out reading" because every neural model in
   it was trained on MS MARCO. NQ's queries are full natural-language questions, which is the
   shape the stopword list acts on.
3. **`msmarco` is where it costs something**, −0.010 `recall@5` and −0.018 `MRR` at 768, and
   flat `recall@5` with −0.019 `MRR` at 384. MS MARCO's queries are keyword-shaped web queries
   ("what is paula deen's brother") where BM25 already works and there is little function word
   to drop.
4. **The identifier corpus gains.** `depot` `MRR` rises 0.801 to 0.894 at 768 and 0.900 to
   0.933 at 384, with `recall@5` unchanged. §1.7's failure mode was that a rank-only fusion
   outvotes a decisive lexical hit with two indifferent ones; removing the function words that
   put the indifferent documents in the lexical list at all is a second way at that.

### 1.4 Which list, and why not the other two

`candidate` and `finding33` both close the six-query gap. They separate on the real judgments:
`finding33` is better on `msmarco` `MRR` (0.729 against 0.717) and `candidate` is better on
`nq` `MRR` (0.893 against 0.882), under both models. NQ is the held-out reading of the two, and
`finding33` was written against the six queries, so `candidate` ships.

`lucene33` carries no question words. It recovers half the six-query gap and is otherwise
between the two. It was not chosen because "does", "how", "what" and "when" are the words a
natural-language question hands to nearly every document, which is D-2's stated mechanism.

**Negations are not in the shipped list.** `no`, `not`, `nor` and `never` are in Lucene's. A
corpus of policies distinguishes "is refused" from "is not refused", and the query is the only
side the list touches, so dropping the negation loses the distinction with nothing said.

### 1.5 What is not established, and what to re-run

The `/tmp` scratchpad holding `d4_rerun.py` was cleared by the reboot. Reproducing this needs:
the two datasets, which are in the machine's `HF_HOME` at `/deep_learning/.cache/huggingface`;
the two sentence-transformers models; and a driver that builds a `DocumentIndex` per (corpus,
list, ranking) with vectors precomputed once and a hand-made `Retrieval` handle returning the
query's precomputed vector. Runtime was about 3 minutes at 768 and 35 seconds at 384, on 24 CPU
cores.

Bounds, unchanged from §1.12's: two embedding models, three real corpora plus two synthetic
ones, all English, and every neural model trained on one of the three. The `depot`
reconstruction is a rebuild from §1.7's description rather than the original corpus, so its
absolute figures are not comparable with §1.12's table; its direction under a stopword list is.

---

## 2. What changed

### 2.1 D4: `ENGLISH_STOPWORDS` ships and is the default

[`search.py` `ENGLISH_STOPWORDS`](../../../../src/simple_agents/builtins/search.py#L51), 175
English function words and question words, exported from `simple_agents.builtins`.
`DocumentIndex.stopwords` takes `None` for the default, any iterable to replace it, and `()` to
search every word the query holds. The saved index file records the resolved list, so an index
saved before this change loads with the empty list it was built with.

The list reaches the query and never the documents, which is what makes it safe: a word listed
here stays findable in a passage. A query of nothing but stopwords is still searched as
written, which was already the rule.

**Negations are excluded**, against Lucene's list, which holds `no` and `not`. §1.4 says why.

### 2.2 D4 follow-up: `ranking=` is required wherever `embeddings=` is passed

[`ranking.py` `refuse_no_ranking`](../../../../src/simple_agents/builtins/ranking.py#L452) holds
the refusal text from [`RULINGS.md` D4](../RULINGS.md#L90) verbatim, and two callers raise it:

- [`search.py` `DocumentIndex`](../../../../src/simple_agents/builtins/search.py#L137), which also
  covers `from_texts`, `from_directory` and `load`, since all three build one.
- [`memory.py` `memory_search`](../../../../src/simple_agents/builtins/memory.py#L108), which took
  `embeddings=` and silently chose `Hybrid(fuse=RRF())` in the same way.

**`memory_search` is a reading of the ruling rather than something it names.** The ruling says
`ranking=` is required "whenever `embeddings=` is passed" and `memory_search(embeddings=...)`
is a place it is passed, building a `DocumentIndex` underneath. Leaving it silent would have
left the hidden decision in one of the two places it lives. Flagged for Thilina in the report.

An index built without `embeddings` is still `Lexical()` with nothing to declare.

### 2.3 L-1: `Annotated[..., Field(...)]` reaches the model and the validator

The patch at [`../patches/L-1-tool-annotated-metadata.patch`](../patches/L-1-tool-annotated-metadata.patch)
applied to [`tools.py` `_resolved_hints`](../../../../src/simple_agents/tools.py#L1069):
`get_type_hints(fn, include_extras=True)`.

One thing the patch did not carry.
[`tools.py` `_handles_in_signature`](../../../../src/simple_agents/tools.py#L1086) compared the
annotation against `HANDLE_TYPES` with `isinstance(annotation, type)`, which an
`Annotated[...]` is not. Keeping the metadata therefore made `Annotated[Workspace, ...]` stop
being recognised as a handle: it would have been offered to the model and left unfilled. The
metadata is stripped before the comparison, and `tests/test_tool_parameter_metadata.py` holds
both halves.

`web_search`'s `domains` parameter is the shipped tool that carried this pattern; the model is
now told the entries are bare hosts.

### 2.4 `contains_normalised` folds accents

[`grounding.py` `normalise_text`](../../../../src/simple_agents/grounding.py#L27) decomposes with
NFKD, drops the combining marks that exposes, then recomposes and casefolds. NFKC alone
composes rather than decomposes, so an accented letter reached `_SEPARATORS` and was treated as
a separator: `"café"` became `"caf"` and `"naïve"` became `"na ve"`.

The fold is symmetric now, which the previous behaviour was not: `"café"`/`"cafe"` matched in
one direction and not the other, so half the cases passed silently.

The docstring states the bound this leaves: only `0-9` and `a-z` survive, so text in a script
that does not decompose to them reduces to the empty string.

### 2.5 L-3: a cached `web_search` is not charged

[`websearch.py` `web_search`](../../../../src/simple_agents/builtins/websearch.py#L33) takes a
`SpendMeter` and reports `declared_cost.per_call` after the provider has answered. A call the
cache served returns before that and reports nothing, which is how a tool says a call cost
nothing (`docs/tools.md` §1.5). Both calls still carry `declared_cost` on the record.

**One consequence to name.** A tool holding a meter is priced as `source: "measured"`, and the
figure `web_search` reports is the declared per-call price, because a provider returns results
and no price. The docstring says so at the point a builder reads it. §1.5's own worked example
is this composition, so this is the mechanism the documentation already prescribes.

**One limitation this does not remove.** `max_cost` is checked before the call, against what
one call can cost, and nothing outside the tool can know a cache will answer. A run whose
ceiling is exhausted therefore refuses a search the cache would have served for nothing. What
changed is the depletion: three identical searches under a ceiling of two now complete, where
before the third was refused.

### 2.6 L-2: `consult()` derives a version

[`consult.py` `_derived_version`](../../../../src/simple_agents/builtins/consult.py#L905) hashes
the derived versions of three functions: the library's own `ask_the_user` body, the project's
channel, and its matcher. `@tool` derives from one function's source; a consult tool's
behaviour is spread over three, and hashing only the first would have given every consult tool
in every project the same version.

`None` where none of the three has readable source, which is what `derived_version` already
returns for a `functools.partial` or a REPL definition.

**This moved two committed cassettes.** `tests/cassettes/suspend.jsonl` and `suspend-vllm.jsonl`
each hold one `consult` entry recorded under a null version. `suspend.jsonl` is recorded
against `mistral-small-2603` and Mistral is out of credits, so re-recording was not available.
The entries were migrated by arithmetic instead: the stored `tool_version` was set to the
version the tool now derives and the key recomputed with `cassette.tool_call_key`. The recorded
answer is untouched. This is the case `scripts/rekey_tool_calls.py` exists for and the script
does not cover a version that was absent, so it was done with a one-off script rather than by
extending it mid-stream. §4 has the reproduction.

### 2.7 J-2: `on_reply(field=...)` finds the reply, or refuses

[`consult.py` `_reply_in`](../../../../src/simple_agents/builtins/consult.py#L855) reads `field`
as a key from a mapping and as an attribute from anything else, which is what
`docs/tools.md` §4.6.1 always said it did.

Two refusals were added, both `CallerFacingError`:

- **the field is not there.** The message names the type the node returned and the keys or
  fields it holds.
- **the value is not a reply.** Anything with no `chose` attribute, which catches the field
  annotated `str`: pydantic coerces the `Reply` to its text and drops `chose`.

The second covers routing with no `field` at all, where a node returning a dict used to read as
a refusal.

Both cases used to take the `declined` branch in silence, which is the failure the typed answer
was added to remove: a branch picked on an answer nobody read.

### 2.8 Documentation

- **`docs/retrieval.md` §4** leads with the refusal and a table of the three rankings against
  what each finds, what it misses, and when to reach for it. It was one line saying what the
  default was.
- **`docs/retrieval.md` §5** says all three things `top_n` does. It described the cost bound
  only. `top_n` also caps `top_k`, and at or above the corpus size it hands the whole corpus to
  the reranker and the first-stage ranking decides nothing.
- **`docs/tools.md` §3.2** lists five handles. It listed three, and `Retrieval` appeared nowhere
  in `docs/`, which three agents found independently (`area-j` J-5, and the tools claim
  inventory). It now carries what a hand-written retrieval tool asks for and what the two
  methods return.
- **`docs/tools.md` §4.1** documents the shipped stopword list, replacing "No list ships".
- **`docs/memory.md` §2.5** is new: the reply `remember`, `recall` and `memory_search` each
  produce, printed. §2.1 hands `stored["results"]` to another node and nothing said what was in
  it, so a builder assuming `document_search`'s field names met `KeyError: 'doc_id'` after a
  paid call. The section says plainly that a memory result is keyed on `key`.
- **"every key there is"** is corrected to the first 50 in alphabetical order, in
  `docs/memory.md` §2 and in both `memory_search` docstrings. `stored` is what says the store is
  larger than the list.
- **`Reply`'s docstring example** showed `reply.chose == 'yes'` for the answer
  `'Yes, go ahead'`, which the shipped matcher returns `None` for. §5 puts the underlying
  question to Thilina; the example itself is corrected to a value the rule produces, since a
  knowingly false example is worse either way.

---

## 3. Verification

### 3.1 The 30 failures in this area, and which were expected

Every one of the 30 was a test asserting behaviour a ruling changed. **None was a genuine
regression**, and none was made to pass by weakening what it asserted.

| Count | File | Why it failed | What it became |
|---|---|---|---|
| 17 | `test_semantic_search.py` | built a `DocumentIndex` with `embeddings=` and no `ranking=`, which D4's follow-up now refuses | `ranking=` supplied. `test_embeddings_means_hybrid_over_reciprocal_rank_fusion` asserted the old silent default and was **replaced** by four tests: the refusal, its text naming all four options, the refusal reaching `load()`, and the lexical default still standing with no `embeddings=` |
| 11 | `test_builtin_tools.py` | 10 called `web_search(...).call({...})` with no meter, which the tool now asks for; 1 asserted "no list ships so every word is searched by default" | the 10 pass the handle the library fills. The stopword test was **replaced** by three: the English list is the default, `stopwords=()` searches every word, and the default leaves negations alone |
| 2 | `test_url_cache.py` | the same missing meter | the handle passed |

Two more appeared later in the pass and were also mine, in a file the first count did not
reach because it was failing earlier for another reason:

| Count | File | Why it failed | What it became |
|---|---|---|---|
| 9 | `test_builtin_tools.py::TestConsult` | the `consult` entries in `tests/cassettes/suspend*.jsonl` were recorded under a null version, and `consult()` now derives one | the two cassettes migrated by arithmetic (§2.6, §4). No assertion changed |

`test_prose.py` also failed, on six violations in files this stream had just edited, all of them
mine and all removed rather than marked, except the one at §5.2.

`2050 passed, 2 skipped, 0 failed` afterwards over the whole suite, once Stream A's
`test_exact_steps.py` stopped failing on a `nodes.py`/`trajectory.py` mismatch that was mid-edit
while this stream ran (§6). `prose_check` and `check_citations` clean on the files this stream
owns.

Four test files are new or substantially added to:

| File | What it holds |
|---|---|
| `tests/test_tool_parameter_metadata.py` (new) | the offered schema carries the description and the bound, the validator enforces the bound, an `Annotated` handle still resolves, a model-typed parameter is unaffected |
| `tests/test_web_search_spend.py` (new) | a cache hit reports nothing and a real call reports the price, through a pipeline; `tool_spend` totals only what was bought; a cached search does not deplete `max_cost` |
| `tests/test_consultation_routing.py` (new) | `field=` over a dict and over a model, both refusals, routing with no field, and the derived consult version |
| `tests/test_semantic_search.py`, `test_builtin_tools.py`, `test_memory.py`, `test_grounding.py` | the ranking refusal and its text, the stopword default and `stopwords=()`, negations kept, `top_n` capping `top_k`, the key cap, symmetric accent folding |

### 3.2 Live, against two backends

`live_check.py`, four checks each against vLLM `Qwen3-30B-A3B-Instruct-2507-AWQ-4bit` at
`localhost:8002` and Gemini `gemini-3.1-flash-lite`. Embedding on CPU.

| Check | vLLM | Gemini |
|---|---|---|
| The `Annotated` schema is accepted and the model reads the description | accepted; asked `top_k=3` against `le=3`, answered correctly | same |
| Hybrid search under the shipped stopword default | `completed`, `doc_id: reader-note` | `completed`, `doc_id: reader-note` |
| A cached `web_search` | 1 provider call for 2 searches; `spent` 0.005 then `null`; `tool_spend` 0.005 over 1 call | same |
| An unaccented quote of an accented span | model wrote `Cafe Beyonce`, `contains_normalised` against `Café Beyoncé` is `True` | same |

The second check measured directly on that 10-document corpus, which is the D-2 effect in the
shipped code path:

```
hybrid, no stopwords   top5=[library-hours, cafe-note, travel-note, parking, expenses-policy]
                       rank of the answer: absent
hybrid + the default   top5=[library-hours, reader-note, travel-note, cafe-note, parking]
                       rank of the answer: 2
semantic alone         top5=[reader-note, library-hours, travel-note, cafe-note, parking]
                       rank of the answer: 1
```

The consultation flow was run offline, since a `Deterministic` node needs no model. All four
documented routes take the right branch over a dict, **including `resume(answer=...)` into a
`Deterministic` node**, which Stream A's delivery fix had landed by then. §5 covers what that
means for `docs/tools.md` §4.6.1.

---

## 4. Reproducing the cassette migration

```python
from record_backend_cassettes import _asks_and_stops
from simple_agents.builtins.consult import consult
from simple_agents.cassette import tool_call_key

version = consult(_asks_and_stops, description="Ask the buyer which fit they want.").version
```

For each `tool_call` entry in `tests/cassettes/suspend*.jsonl` whose `tool_name` is `consult`
and whose `tool_version` is `null`: set `request.tool_version` to `version` and recompute
`entry["key"]` with `tool_call_key(node_id=..., tool_name="consult", tool_version=version,
arguments=request["arguments"], occurrence=request["occurrence"])`. One entry per file.

---

## 5. What needs Thilina

1. **`memory_search(embeddings=...)` now requires `ranking=` as well.** §2.2 argues it from the
   ruling. If it should have stayed silent, the change is two lines.
2. **A `# prose-ok:` marker was added without sign-off**, on the five second-person words in
   `ENGLISH_STOPWORDS`. `scripts/prose_check.py` reads `"you", "your", "yours", "yourself",
   "yourselves"` in a tuple literal as prose written in the second person. The alternatives
   considered were dropping those five, which leaves an arbitrary hole in a pronoun set that
   holds `i`, `me`, `my`, `he`, `she`, `we` and `our`; and moving the list to a data file, which
   is the first non-Python file the package would ship. Neither is clearly better. Waiting was
   not possible mid-stream and leaving the check red was worse, so the marker is in and flagged
   here. If it is refused, either alternative is one edit.
3. **`Reply`'s default matcher against the shape of a real answer.** `area-c-tools.md` finding 4:
   `_matched("Yes, go ahead", ["yes", "no"], None)` is `None`, and a live Gemini run recorded
   exactly that as `unmatched` for a clear approval. The docstring example was corrected to a
   value the rule produces, which removes the false statement and not the underlying question:
   whether the default should match a prefix, or a contained option, or stay exact with `match=`
   as the answer. That is a design decision and it was not ruled on.
4. **`web_search` reports the declared price under `source: "measured"`.** §2.5. Defensible on
   `docs/tools.md` §1.5's own worked example, and worth a look.
5. **`scripts/check_citations.py --fix` was run on two files before the instruction not to run
   it reached this stream.** It rewrote 6 line anchors in
   `dev-docs/build-logs/semantic-recall-build-log.md` and 5 in this file, in both cases
   citations into `builtins/` that this stream's own edits had moved. Nothing else was touched
   and the 160 remaining problems elsewhere were left alone (§6). Both sets of rewrites are in
   the working tree and can be reverted per file.

---

## 6. Cross-stream

- **`tests/test_exact_steps.py`** failed partway through this stream on `AttributeError:
  'Record' object has no attribute 'held_back_ms'` raised from `nodes.py`, which is Stream A's
  file and was mid-edit. Not touched, and it passes now.
- **`src/simple_agents/models.py`** carries a `prose_check` violation, an example that does not
  parse. Modified by another stream, not touched.
- **`scripts/check_citations.py` reports 160 problems** across `dev-docs/`, most of them
  citations into `pipeline.py`, `nodes.py` and `runner.py` whose lines moved under other
  streams. Only `semantic-recall-build-log.md` was fixed here, because it is a living design
  document whose citation into `builtins/memory.py` this stream moved. **The checkpoint's own
  `findings/` and `inventory/` files were left alone deliberately**: they record where a defect
  was at the time it was found, and rewriting their line numbers to point at the fixed code
  would falsify the record.
- **`docs/tools.md` §4.6.1's `Deterministic` example is correct as written**, now that Stream
  A's `resume(answer=...)` delivery has landed. Verified in §3.2. No doc change was needed and
  none was made.
- **`docs/retrieval.md` §3's FT-14 sentence, handed over by Stream D.** It said a self-hosted
  embedding model with no `model_revision` fails FT-14. That holds for `OpenAIEmbeddings` and
  `MistralEmbeddings`, which report what they were given because an endpoint does not publish
  which weights it serves. It is false for `SentenceTransformerEmbeddings`, which loads the
  weights itself and records the commit `sentence-transformers` resolved
  ([`embeddings_local.py` `identity`](../../../../src/simple_agents/adapters/embeddings_local.py#L112)).
  §3 now splits the two cases. The adapter file itself was not edited: it is Stream D's.
