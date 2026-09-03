# Areas D and E: retrieval, and memory

Run 2026-08-13 on branch `main` at `1178695` with the working tree as committed plus the
uncommitted concurrency work. Live backend was Gemini `gemini-3.1-flash-lite` on the paid key,
$0.0039 spent. Local embedding and reranking models ran on CPU with `CUDA_VISIBLE_DEVICES=""`,
so nothing touched the GPU the dogfood is using.

**Area D, retrieval: 63 checks, 58 pass, 5 fail, 0 skip.**
**Area E, memory: 36 checks, 36 pass, 0 fail, 0 skip.**

Machine-readable rows are in `../runs/area-d-retrieval.jsonl`, `../runs/area-d-semantic.jsonl`,
`../runs/area-d-extra.jsonl`, `../runs/area-d-identifiers.jsonl`, `../runs/area-d-hybrid.jsonl`,
`../runs/area-e-memory.jsonl`, `../runs/area-e-eval.jsonl`, `../runs/area-e-rollouts.jsonl` and
`../runs/area-de-live.jsonl`.

The five failures are three distinct defects. Two of them are in the retrieval feature's
defaults and instrumentation; the third is shared with area A. Memory has no defect: the store,
the three built-in tools, scoping, persistence, redaction, put semantics, concurrent writes, the
`Example.memory` contract and the live write-then-read-in-a-later-run path all behave as
documented.

---

## D-1. `max_steps` does not bound an embedding or a rerank call. Blocker, and the same defect as A-1.

**What is claimed.** [retrieval.md §6, line 236](../../../../docs/retrieval.md#L236): an embedding
and a rerank are "each charged to the run's `max_tokens` and `max_steps` budget".
[budget.py:129](../../../../src/simple_agents/budget.py#L129), `Budget`: "``max_steps`` is exact:
the step is taken before the call."

**What actually happens.** The step is charged after the call returns, and the run budget is
only consulted between nodes, so a node that searches is not bounded at all when it is the last
node to run.

`RETR-057`: a one-node pipeline under `max_steps=1, max_tokens=10` whose node ran four semantic
searches with a reranker **made 8 model calls and completed**. No `BudgetExceeded` was raised
and the manifest records `completed`.

`RETR-058`, the contrast in the same file: an `LLMNode` in the same position under `max_steps=0`
raises before the call is made.

`RETR-052`: with a second node after the searching one, the run does stop, on `max_steps` at
`spent=2, limit=1` and on `max_tokens` at `spent=40, limit=1`. The charge is real. The bound is
what is missing.

**Mechanism.** `run.one_step`, the reservation that makes the axis exact, is called from exactly
one place in the library, [`run.one_step`, context.py:603](../../../../src/simple_agents/context.py#L603) in
`_call_model` *(at the record's writing, in `LLMNode._fan_out`)*. `_call_retrieval_model` charges after the fact at
[handles.py:131](../../../../src/simple_agents/runtime/handles.py#L131) and reserves nothing.

**Reproduction**, no backend required:

```python
from simple_agents import (Budget, Deterministic, FakeEmbeddingClient, FakeRerankClient,
                           Pipeline, RunEnvelope)
from simple_agents.builtins import CrossEncoderRerank, DocumentIndex, document_search

index = DocumentIndex.from_texts({f"d{i}": f"document {i} about ashford" for i in range(6)},
                                 embeddings=FakeEmbeddingClient(),
                                 rerank=CrossEncoderRerank(FakeRerankClient(), top_n=3))

def go(inputs, ctx):
    for _ in range(4):
        ctx.call_tool("document_search", query="ashford depot")
    return "done"

result = Pipeline(
    [Deterministic(go, node_id="find", tools=[document_search(index, top_k=2)])],
    budget=Budget(max_steps=1, max_tokens=10, max_cost=None, max_wall_clock_ms=None),
).run({}, envelope=RunEnvelope(run_dir="/tmp/qa"))

print(result.outcome)    # 'completed', after 8 model calls under max_steps=1
```

**Why it matters here specifically.** A search issues one embedding call and one rerank call
each time it runs, and an `AgentNode` decides how many times that is. A builder who set
`max_steps` as the guard on a retrieval agent, against a hosted embedding endpoint or a rerank
over `top_n=20`, has no guard.

**Same root cause as `A-1` in `area-a-pipeline-graph.md`**, reached from the other side. The
combined picture:

| Path | Is `max_steps` honoured? |
|---|---|
| A chain of `LLMNode` | yes, exactly |
| A fan-out with `over=` | yes, at every concurrency |
| Branch arms from a route (A-1) | no, all arms run at any limit |
| Embedding and rerank calls inside a search (D-1) | no, charged after the call |

The correction is one decision, not two: either both paths reserve before dispatching, or the
shipped statements stop calling the axis exact and name the paths it bounds.

---

## D-2. The shipped default ranking loses the paraphrase on five of six queries. Major.

**What is claimed.** [retrieval.md §1, line 32](../../../../docs/retrieval.md#L32) sells the feature
on one line of change: pass `embeddings=` and a query sharing no words with a document finds it.
Passing `embeddings=` also silently selects the ranking, [retrieval.md §4, line
107](../../../../docs/retrieval.md#L107): "It defaults to `Lexical()` without `embeddings` and
`Hybrid(fuse=RRF(k=5))` with it."

**What actually happens.** On the query shape the feature exists for, the default fusion
discards the retriever that answered.

`RETR-091`, six queries, each built so the answer shares no word with the query and one decoy
holds most of the query's words. Corpus of 18 short documents. Position of the correct document
in the top five, `None` meaning absent:

| Ranking | Answer in top 5 | Ranks per query |
|---|---|---|
| `Semantic()` alone | **5 of 6** | 1, 1, 2, –, 4, 3 |
| **Default `Hybrid(fuse=RRF(k=5))`** | **1 of 6** | –, –, 5, –, –, – |
| `Hybrid(fuse=RRF(k=60))` | 1 of 6 | –, –, 5, –, –, – |
| `Hybrid(fuse=Interleave())` | 4 of 6 | 2, 2, 3, –, –, 5 |
| `Hybrid(fuse=WeightedScore(lexical=0.3))` | 5 of 6 | 2, 2, 2, –, 5, 4 |
| Default plus a 33-word `stopwords` list | 5 of 6 | 2, 2, 3, –, 5, 4 |

`RETR-092`, the same six queries over 318 documents: `Semantic()` 4 of 6, the default 2 of 6,
stopwords 4 of 6, `Interleave()` 4 of 6, `WeightedScore(lexical=0.3)` 4 of 6.

`RETR-090` establishes the cases are the shape claimed: in all six the answer is absent from the
lexical top five and the decoy is first.

**Mechanism**, from `RETR-009` on the single query it was first seen on. BM25 returns every
document holding any query word, and no stopword list ships
([search.py:176](../../../../src/simple_agents/builtins/search.py#L176), `DocumentIndex.stopwords`
defaults to `frozenset()`; [tools.md line 459](../../../../docs/tools.md#L459), "No list ships").
A natural-language question therefore hands a lexical vote to nearly every document through
words like `the` and `does`. `RRF` at [ranking.py:80](../../../../src/simple_agents/builtins/ranking.py#L80)
compares rank alone and cannot tell a BM25 score of 3.9 from one of 0.14, so two weak votes beat
one strong one. The paraphrase, absent from the lexical list by construction, has one vote:

```
query: 'does the reader finish long books'

lexical  (9 of 10 documents, on 'the', 'does', 'long', 'books')
   1. library-hours    3.904      6. commute        0.150
   2. extension-form   0.248      7. cable-spec     0.145
   3. bearing          0.213      8. parking        0.145
   4. invoice-terms    0.203      9. depot-hours    0.141
   5. coffee           0.161

semantic (10 of 10)
   1. reader-note      0.472   <- the answer, by a margin of 0.15
   2. library-hours    0.320

RRF(k=5) votes
  0.3095  library-hours    lexical 1   semantic 2
  0.2679  extension-form   lexical 2   semantic 3
  0.2111  coffee           lexical 5   semantic 4
  ...
  0.1667  reader-note      lexical -   semantic 1     <- 8th of 10
```

At `k=5` a single first place is worth `1/6 = 0.1667`, and any two votes at ranks up to about
six beat it. The doc's own worked example at [retrieval.md §4.1, line
141](../../../../docs/retrieval.md#L141) shows `RRF(k=5)` preferring the decisive single vote, but
its mediocre document sits at rank 11 in both lists. Above rank six the arithmetic goes the
other way, which is where a small corpus always lands.

**Reproduction** is `scratchpad/qa/area_d_hybrid.py`, and the shortest form is
`DocumentIndex.from_texts(corpus, embeddings=embedder)` against
`DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())` on any corpus where
the answer is a paraphrase.

**What bounds this finding.** One embedding model, `all-mpnet-base-v2`, two corpus sizes, one
query shape, hand-built corpora. It is not a benchmark and does not reproduce the MS MARCO
figures [retrieval.md §4, line 122](../../../../docs/retrieval.md#L122) cites. What it does show is
that the documented caveat, "Hybrid is not always better than one of its parts", understates
what a builder following §1 gets: not a lower rank, but the answer absent from the results.

**Two cheap changes would move it**, and either is a decision rather than a repair: ship a
default stopword list for the query side, or make the default `Semantic()` when `embeddings=` is
passed and leave `Hybrid` to be asked for. `hybrid_stopwords` and `hybrid_weighted_semantic`
both reach parity with `Semantic()` in the table above.

---

## D-3. An embedding's `model_call` is not parented to the tool call in a `Deterministic` node. Minor.

**What is claimed**, in three places, one of them a shipped docstring:

- [retrieval.md §6, line 234](../../../../docs/retrieval.md#L234): "each is a `model_call` record in
  the trajectory, parented to the tool call that made it".
- [memory.md §2.4, line 148](../../../../docs/memory.md#L148): "a `model_call` record parented to
  the tool call".
- [handles.py:83](../../../../src/simple_agents/runtime/handles.py#L83), `_retrieval_handle`: "emits a
  ``model_call`` record parented to the tool call ... so the tokens a search spends are
  attributable to the search that spent them".

**What actually happens.** `RETR-051`, one run each way over the same index:

- From an `AgentNode`: the parent is the tool call. Correct.
- From a `Deterministic` node with `tools=[...]`: the parent is the **node execution**, and the
  tool call is a sibling rather than the parent.

`MEM-012`'s trajectory shows the cost, two searches in one node:

```
model_call  rec_2e53e6ddbd14 <- rec_dfd014795b78  embedding
model_call  rec_2af1756eb47c <- rec_dfd014795b78  embedding
tool_call   rec_b16f3cddad75 <- rec_dfd014795b78  memory_search
model_call  rec_a05acc8526ac <- rec_dfd014795b78  embedding
tool_call   rec_4e14586e2c26 <- rec_dfd014795b78  memory_search
node_execution rec_dfd014795b78 <- None
```

Nothing in the record says which search made which embedding call.

**Mechanism.** The `AgentNode` path fills the handle with the tool call's own record id,
[deterministic.py:29](../../../../src/simple_agents/nodes/deterministic.py#L29). The `Deterministic` path builds its
handles at [deterministic.py:29](../../../../src/simple_agents/nodes/deterministic.py#L29) from the node's
`parent_id`, before any tool call record exists, and `_deterministic_handle`
([handles.py:45](../../../../src/simple_agents/runtime/handles.py#L45)) passes that straight through.

**Reproduction**: run `document_search` over an index with `embeddings=` from
`Deterministic(fn, tools=[search])` and compare `parent_id` on the `model_call` against the
`record_id` on the `tool_call`. The pattern is the one [memory.md §2.1, line
78](../../../../docs/memory.md#L78) recommends.

**Severity is minor** because the calls are recorded, charged and replayed correctly; only the
attribution is wrong. It is worth fixing rather than documenting, since the docstring's stated
purpose is exactly the attribution that is lost.

---

## D-4. A run whose only calls are memory or workspace tools cannot be replayed. Minor.

`MEM-033`: a pipeline whose single node calls `remember` writes **no cassette file at all** under
`Cassette.record(path)`, because every tool holding a `Memory` is re-executed rather than stored.
Replaying that run is then refused: "The envelope replays from ... and that file does not exist."

The refusal message is accurate and names the fix, and this is the correct behaviour falling out
of a correct rule ([memory.md §5, line 217](../../../../docs/memory.md#L217): a `Memory` tool is re-run during
replay). It is recorded because a builder who records a memory-only pipeline and expects to
replay it meets an error that reads like a missing file rather than like "there was nothing to
record".

---

## E-1. The measured claim in `memory.md` §2.4 holds only for some keys. Cosmetic.

[memory.md §2.4, line 132](../../../../docs/memory.md#L132) states that over a store holding "puts
down anything over 300 pages unfinished", a search for "length preference" "returned nothing
lexically and found the fact semantically".

`MEM-011` reproduces both halves and shows the result depends on the key, because search is over
the key and the value together ([memory.md §2, line 50](../../../../docs/memory.md#L50),
[builtins/memory.py:149](../../../../src/simple_agents/builtins/memory.py#L149) `search`):

- key `reading_habit`: the lexical search returns nothing and comes back with `keys`. As claimed.
- key `max_reading_length_pages`, which is the key [memory.md §2, line
  57](../../../../docs/memory.md#L57) itself uses in the neighbouring narrative: the lexical search
  **finds it**, at score 0.6633, on the word `length` in the key.

Both behaviours are correct. The two passages next to each other imply a lexical miss that the
second key does not produce.

---

## D-5. `VectorScan` and `RRF` settle a tie in opposite directions, and neither direction is documented. Cosmetic.

[retrieval.md §4.1, line 149](../../../../docs/retrieval.md#L149) raises the tie explicitly, on the
case a parts list produces: "that tie is broken by identifier. On a corpus of near-identical
documents, such as a parts list differing only in the part number, the order of a tied group is
settled by their names." It does not say in which direction, and the two components disagree.

`RETR-035`, three documents that embed identically:

| Path | Order of the tied group |
|---|---|
| `VectorScan.search` | part-0003, part-0002, part-0001 |
| `Semantic()` through the tool | part-0003, part-0002, part-0001 |
| `RRF().combine` on tied lists | part-0002, part-0001, part-0003 |

`VectorScan` sorts by `(score, doc_id)` descending
([ranking.py:80](../../../../src/simple_agents/builtins/ranking.py#L80)); `RRF` sorts by
`(-votes, doc_id)`, so identifiers ascending
([ranking.py:80](../../../../src/simple_agents/builtins/ranking.py#L80)). No hit was mispaired in
any of them.

---

## The two gaps the lead flagged, now closed

**`Example.memory` gives each rollout its own store.** `MEM-056` and `MEM-057`, run twice: at
`concurrency=4` where rollouts overlap and at `concurrency=1` where they run in strict sequence,
3 examples at k=4, 12 rollouts each time. Each rollout reads the seeded key, **overwrites it**
with a marker no other rollout can produce, then asks for all twelve rollouts' marker keys by
name.

- Every rollout's first read returned its own example's declared value, in all 24 rollouts. A
  shared store would have handed a later rollout the marker an earlier one wrote, which is what
  the sequential run is for.
- Every rollout found exactly one marker, its own. Not one saw another's.
- Every rollout started from exactly 2 stored facts, the two its example declared, and ended
  with 3.
- `MEM-058`: the store the project declared on the envelope was untouched; it still holds its one
  entry and none of the rollouts' writes.
- `MEM-059`: two evaluations at seed 41 reported identical rollout answers.
- `MEM-059B`: each rollout has its own store directory under its own run, at
  `memory/<scope_digest>`, holding exactly 3 files. The scope the project declared is preserved.

**`VectorScan` files each vector under its own document's identifier.** `RETR-026` to `RETR-035`,
seven checks, attacking the pairing from construction rather than from threads. The corpus uses
twelve identifiers that are not positional, not sorted and not uniform (`zeta-9`, `alpha`,
`MX-4471-B`, `007`, `Ω-14`, `z`, `doc 10`, `doc 2`, `doc 1`, ...), each document's text stamps its
own identifier, and the embedding client returns a one-hot vector unique to the document. A
query is therefore one document's exact vector, and any mispairing shows as a hit whose `doc_id`
disagrees with the identifier printed inside its own `text`.

- `RETR-026`: every one of the twelve documents probed by its own text returned itself, at score
  1.0, with document order and vector order identical.
- `RETR-027`: after rebuilding with two documents removed, one re-added at the end and a new one
  appended, all twelve probes still returned themselves, and the removed document did not come
  back.
- `RETR-028`: after save, load, save, load, the file's `documents` order and `order` array agree
  and every probe still returns itself.
- `RETR-029`: 24 direct comparisons of the vector on disk and in memory against the hot slot the
  document's own text implies. None misfiled.
- `RETR-033`: `VectorScan` fed four batches of uneven size (1, 4, 1, 6) pairs every identifier
  with its own vector.
- `RETR-034`: the same corpus under `Hybrid`, and a lexical search for a stamped identifier.
- `RETR-035`: the tie case above, no mispairing.

The thread cases from the first pass stand: `RETR-022`, 8 threads and 320 concurrent adds with
zero mispairings and zero identifier/vector length mismatches, and `RETR-023`, a reader
searching throughout 400 concurrent adds with zero inconsistent scores. The changelog fix holds.

---

## What else was verified and passed

**Retrieval.** BM25 ordering and result fields; `stopwords` dropped from the query with an
all-stopword query searched as written; `documents_containing` lexical under every ranking; an
empty result rather than a raise; `RRF(k=5)` against `RRF(k=60)` reproducing the documented
worked example exactly; `Interleave` and `WeightedScore` behaviour; six construction refusals;
`Hybrid.depth` asking each retriever for `depth` and returning `top_k`; save and load with no
re-embedding; a model mismatch refused naming both models; a project's own `VectorStore` used
instead of `VectorScan`; a reranker deciding the order and carrying its own scores; `top_n`
bounding what reaches it; `ModelRerank.order_from` on every reply shape; the handles each index
shape asks for and that none is offered to the model; `call_kind` of `embedding` and `rerank` on
the records with no raw vector in the trajectory; `max_chars` and a model-supplied `top_k`;
`FakeEmbeddingClient` and `FakeRerankClient`. A real `all-mpnet-base-v2` on CPU inverted the
ranking against a lexical decoy (`RETR-005`), missed a part number a lexical search found
(`RETR-007`), and a real `ms-marco-MiniLM-L-6-v2` changed the order on all three queries it was
given and recovered one answer the first pass had not returned at all (`RETR-071`).

**Memory.** Write, read, persistence verified from a second OS process; two scopes over one
directory sharing no entry with the scope never written to disk or to the manifest; three
refusals for a missing scope; a run with a memory tool and no store refused before the node
runs; put rather than append; 480 concurrent writes of one key by 8 threads with a concurrent
reader, no partial value, no leftover scratch file, one entry left (the second changelog fix);
`forget`; key limits as `ModelFacingError`; all three built-in tools through recorded tool calls
with `replaced`, `found` and the `keys` fallback on a miss; the manifest's `memory` object;
redaction on the way in with the rules recorded on the entry and a later rule not reaching it;
re-execution rather than cassette service on replay, with the store rebuilt and a fresh
`stored_at`; `spends_money` and `irreversible` refused on a `Memory` tool; a project's own
memory tool.

**Live, against Gemini.** `MEM-060` a real model called `remember` and the fact landed;
`MEM-061` a **separate later run**, sharing only the directory on disk, searched memory and
answered out of it ("Since I know from the stored fact `reading_habit_preference` that you rarely
finish books longer than 300 pages, I recommend ..."); `MEM-062` another scope over the same
directory read nothing; `MEM-063` reproduced §2.4 both ways on a live store; `RETR-080` a real
model searched a semantic index and returned `MX-4471-B`, with the embedding call recorded,
parented to the tool call, and both models in `models.observed`.

---

## What could not be tested, and why

- **`OpenAIEmbeddings` and `MistralEmbeddings` against a live endpoint.** No embedding endpoint
  was available and no key was provided for one. Both adapters were read; neither was executed.
  The `EmbeddingClient` seam itself is covered through `FakeEmbeddingClient`, a hand-written
  client and `SentenceTransformerEmbeddings`.
- **`Qwen/Qwen3-Reranker-4B`.** Cached, but the GPU was at 22 of 24 GB with another project's
  vLLM server on it, so only the small cross-encoders ran, on CPU. `LocalCrossEncoder` was
  therefore never exercised on a GPU, and `DEFAULT_RERANK_MODEL`'s "single-digit milliseconds on
  a GPU" is unverified.
- **The performance figures in [retrieval.md §4.2, line 170](../../../../docs/retrieval.md#L170)**:
  10,000 documents at 768 dimensions in 31 MB answering in 64 ms, and 100,000 in 620 ms. The
  largest corpus tested here is 318 documents. Nothing contradicts the figures; nothing confirms
  them.
- **The benchmark claims.** MS MARCO passage at 95.5% against 91.0%, and the 0.05 to 0.13 rerank
  gain, are measurements on public corpora that this pass has no way to reproduce.
- **`ModelRerank` against a live chat model.** Exercised with `FakeModelClient` through an
  `AgentNode` (`RETR-045`) and its ordering logic directly (`RETR-042`), but never against
  Gemini, so how well a real model reranks is unmeasured. Note that a `ModelRerank` index cannot
  be reached from a `Deterministic` node at all (`RETR-044`): the node kind refuses a tool taking
  a `ModelHandle`. That refusal is correct and undocumented in `retrieval.md`.
- **Cassette replay of a semantic search end to end.** `RETR-043` confirms a semantic search is
  `re_executed` and a lexical one is not, and `MEM-030` confirms the re-execution path on
  memory, but a record-then-replay of an embedding call served from a cassette file was not run.

---

## What might have been missed, and where coverage is thin

- **`VectorScan.ids()`, `all_vectors()`, `dimensions` and `__len__` read the two lists without
  the lock** that `add` and `search` take ([`VectorScan`, vectors.py](../../../../src/simple_agents/builtins/vectors.py#L88)
  onward). `DocumentIndex.save` calls `all_vectors()` and then `ids()` as two separate reads
  ([`write_index`, index_file.py](../../../../src/simple_agents/builtins/index_file.py#L55)), so an
  add landing between them would write a file whose vector count and identifier count disagree.
  `RETR-025` hammered exactly that, 4000 adds against a continuous saver, and produced **zero**
  mismatches, so this is a code reading with no evidence behind it. It is recorded because the
  changelog fix covered `add` and `search` and stopped there.
  **Closed at `P3-73`, 2026-09-02.** `add` made the interleave reachable, so `save` takes the
  index lock, `ids()` and `all_vectors()` take the store's, and a mismatch between the two is
  refused rather than written. `tests/test_growing_index.py::TestTwoWritersAndAReader::
  test_an_add_cannot_land_inside_a_save` runs the add inside the window and fails without the
  lock.
- **Retrieval quality is measured on hand-built corpora only.** D-2's numbers are six queries of
  one shape against one embedding model. They are enough to say the default behaves this way on
  this shape, and not enough to say what it does on a project's real corpus, which is what
  [retrieval.md §4, line 126](../../../../docs/retrieval.md#L126) already tells a builder to measure.
- **Only one embedding model.** Everything semantic used `all-mpnet-base-v2`. A weaker or
  stronger model changes the balance between the two arms and therefore changes D-2 directly.
- **Concurrency inside a single search.** Two nodes searching the same index at once, or an
  `AgentNode` with `concurrent_tools` over two searches, was not run. The `VectorScan` and
  `MemoryStore` concurrency was tested with raw threads rather than through the pipeline's own
  concurrency, which area A covers.
- **`memory_search(embeddings=...)` write-back under concurrency.** `MEM-012` confirms a fact is
  embedded once and the vector written back, and that a later search embeds the query alone. Two
  rollouts searching one store at the same time, both finding the vector missing and both writing
  it back, was not tested. The write is idempotent so the outcome should be the same vector, but
  it is unverified.
- **Redaction reaches the value only.** `MEM-020` confirms the value is scanned; a secret placed
  in the **key** was not tested and, reading `MemoryStore.put`, is not scanned. Keys are model
  supplied, so a model can write a secret into one.
- **Large or unusual memory values.** Values were short strings. No test covers a value of
  megabytes, invalid UTF-8, or a key that collides after the 32-character SHA-256 truncation in
  `MemoryStore._path`.
