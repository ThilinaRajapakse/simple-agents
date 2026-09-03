# Build log — An index that grows, on the CPU or the GPU

`plan.md` §1 P3-73. Started 2026-09-02. Written while building, not afterwards.

## 1. Before any design

The item's record rested on four claims about the code. Each was checked against the source
before anything was decided, and the reading found four faults nothing had seen.

**What the record said, and what is there.**

| The claim | What the code does |
|---|---|
| No `add` | [`search.py` `_build_vectors`](../../src/simple_agents/builtins/search.py#L281) embeds the whole corpus in `__post_init__`; nothing appends afterwards |
| `VectorScan` is a pure-Python loop | [`vectors.py` `VectorScan.search`](../../src/simple_agents/builtins/vectors.py#L130). Measured here at 768 dimensions: 60 ms at 10,000 documents and 590 ms at 100,000, against 3.5 ms and 7.1 ms for the numpy store. The docstring's committed times (64 ms, 620 ms) reproduce and its memory figures do not: see §3 |
| `save` base64-encodes into JSON | It did, through `array("f").tobytes()` and `base64.b64encode` |
| Construction embeds outside the handle | It does, and this is what an `add` inside a run would have inherited |

**Four faults the reading turned up.**

1. **`vectors=` a store of the project's own never embedded anything.**
   [`docs/retrieval.md` §4.2](../../docs/retrieval.md#L223) documented
   `DocumentIndex.from_texts(corpus, embeddings=embedder, vectors=MyStore())`, and
   `__post_init__` called `_build_vectors` only where `self.vectors is None`. Measured on a
   four-document corpus: `len(index.vectors)` was 0 and every semantic search returned nothing,
   with nothing raised. The one test of a custom store
   ([`test_semantic_search.py:243`](../../tests/test_semantic_search.py#L243)
   `test_a_project_may_supply_its_own`) fills the store by hand first, so it passed.

2. **`save` dropped the vectors of any store that was not a `VectorScan`.** The two `isinstance`
   guards wrote `"order": []` and `"vectors": null` for anything else, producing a file that
   looked saved.

3. **`load` of such a file re-embedded the whole corpus.** `vectors=None` reaching
   `__post_init__` is a vector ranking with no store, so construction embedded everything again.
   On lost-the-plot's 7,308 documents that is the ~1.5 minutes its own build log measured,
   paid on every load.

4. **That reload left the index with no embedding identity.** `load` set
   `index.embedded_by = identity` after construction, so the file's `null` overwrote what
   `_build_vectors` had just set, and `_check_query_model` returned early for the life of the
   index. The refusal of a query embedded by a different model was off.

**And one thing the record did not mention.** `DocumentIndex.to_record` existed, its docstring
said "How the manifest records what this index searches with", and nothing in the library
called it. Which store answered a search was recorded nowhere, so the item's record entry was
wiring rather than a new field.

**Where a record would have to go.** [`recording.py` `_tool_entry`](../../src/simple_agents/pipeline/recording.py#L147) builds the manifest's `tools` array off `Tool` attributes, and
[`declared.py` `_declarations_of`](../../src/simple_agents/evaluation/declared.py#L37) and
`_measured_configuration` read `manifest_tools()`, so a field there reaches the results file
and the evaluation's comparison without further plumbing. It also reaches
[`core.py`](../../src/simple_agents/pipeline/core.py#L2070) `behaviour_fingerprint`, which
decided the shape of §2's third decision.

**FAISS, checked on the machine rather than in the tracker.** `faiss-cpu` 1.15.0 installs from
PyPI. `faiss-gpu-cu12` 1.14.1 installs from PyPI, reports `get_num_gpus() == 1` on this card,
and `GpuIndexFlatIP` answers. `IndexHNSWFlat` takes an incremental `add` with no training step;
`IndexIVFFlat` reports `is_trained == False` until it is trained, so it cannot hold a document
before a training pass. `remove_ids` works on `IndexFlat` and compacts in place keeping the
order of what is left (measured on a 6-row identity matrix: removing 1 and 3 leaves 0, 2, 4, 5);
it raises `remove_ids not implemented` on `IndexHNSWFlat` and on `GpuIndexFlatIP`.
`reconstruct_n` works on all three.

## 2. Design

The sitting of 2026-09-02 settled the shape: numpy is the default store, FAISS with its GPU
build is an optional extra, both built now. Four questions were left, and Thilina answered them
at this build's opening sitting.

**Decision 1 — `add` covers a document that changed as well as one that is new.** The proposal
was `add` alone, with a changed document rebuilding the index; the argument for it was that
`remove` behaves differently on an approximate FAISS index, which cannot delete. Thilina:
*"Both A and B, and maybe a warning when remove is used on HNSW to consider a periodic
rebuild."* So three verbs ship, and the store that cannot delete says so at the point of use
rather than the library declining to offer the verb.

**Decision 2 — one extra, naming the CPU build.** `[ann] = ["faiss-cpu>=1.9", "numpy>=1.24"]`.
FAISS's own GPU distribution is a conda package and the PyPI wheel is a community one; both
provide the module named `faiss`, so a machine has one of the two and an extra naming both
would install a conflict. `FaissVectors(device="cuda")` on a CPU build refuses and names the
install. Weighed and not taken: a second `[ann-gpu]` extra, which would put a CUDA major
version and a community maintainer into the library's packaging metadata.

**Decision 3 — the settings are fingerprinted and the corpus size is not.** The tool entry
carries what decides which documents come back: the ranking, the fusion and its settings, the
depth, the reranker, the store and whether it is exact, the analyzer, and the embedding model.
That is inside `behaviour_fingerprint`, so a result stored under an exact scan is not read back
as though an approximate store produced it, and an evaluation compared against an earlier run
reports the store as a changed setting rather than comparing the figures.

How many documents the index holds is on the manifest's own `retrieval` array, counted when the
run ends and outside the fingerprint. The alternative put the count on the tool entry, where
**adding one document would have invalidated every result the project had ever stored**, which
is the cost this item exists to remove. Thilina took the array. `constants` is the precedent: a
module-level number is recorded and left out of the stamp for the same reason.

**Decision 4 — `load` still reads a `1.0` file.** `save` moves to a binary sidecar and the
format goes to `2.0`. Reading the old one is six lines, and the alternative tells a builder to
embed a corpus again because the library changed its file layout.

**Settled on merit, and stated at the sitting.**

- **`NumpyVectors` is a class of its own** and `VectorScan` stays as the no-dependency
  fallback, rather than one name switching its arithmetic internally. A silent switch would
  leave the record unable to say which store answered, and the two carry different measured
  figures.
- **`FaissVectors` offers `exact` and `approximate`**, over `IndexFlatIP` and `IndexHNSWFlat`.
  IVF was weighed and not taken: it holds nothing until it is trained, which an index that
  grows cannot promise. `approximate` on `cuda` is refused, since FAISS's GPU indexes do not
  include the graph.
- **The index file records the analyzer**, and a file written under another one is refused the
  way two embedding models are. This is what [`plan.md` §2.1](../plan.md#L99)'s BM25-analyzer
  entry was waiting on.
- **`DocumentIndex` takes a lock**, so an `add` on one thread cannot be read half-applied by a
  search on another.

## 3. Build

**Two new modules, and one moved.** `builtins/vectors.py` holds the `VectorStore` protocol,
`VectorScan` (moved out of `ranking.py`), `NumpyVectors`, `FaissVectors`, `default_store` and
`store_to_record`. `builtins/index_file.py` holds the file format: `write_index`, `read_index`,
the analyzer and model checks, and the format constants. Both are internal moves; the public
path is `simple_agents.builtins`, which is unchanged.

**The three verbs.** `add`, `replace` and `remove` on `DocumentIndex`, each updating the
postings, the lengths, the mean length and the store together under the index's lock, and each
returning the index. `add` refuses an identifier already held and names `replace`; `replace` and
`remove` refuse one not held and name `add`; `remove` refuses to empty the index, with the same
message construction refuses an empty corpus with. Only the documents given are embedded, and
`retrieval=` routes the call through the handle.

**The store ladder.** `default_store()` returns `NumpyVectors` where numpy imports and
`VectorScan` otherwise. `NumpyVectors` holds one `float32` matrix, and its search takes the
`take`-th largest score as a threshold, collects the rows at or above it, and breaks ties by
identifier over that handful, which is how it returns the order `VectorScan` returns without a
Python loop over the corpus. `memory_search` builds its per-search store through
`default_store()` too.

**FAISS.** `FaissVectors(kind=, device=, neighbours=)`. An exact CPU index deletes through
`remove_ids` and rebuilds its identifier list from the compaction FAISS leaves. An exact GPU
index has no removal, so it rebuilds from `reconstruct_n`. An approximate index marks the
document, filters it out of every later search, asks for that many extra candidates, and warns
naming `store.rebuild()`.

**The record.** `Tool` gains a `searches` field, which `document_search` fills.
`_tool_entry` reads `index.to_record()` into `retrieval` on each tool entry, and
`_close_manifest` walks the tree for tools carrying an index and writes `manifest.retrieval`
from `index.to_manifest()`. Manifest format `0.39` to `0.40`.

**What changed while building.**

- **`_build_vectors` became "embed what the store does not hold" rather than "embed if there is
  no store".** That is what closes fault 1 without breaking the two callers that hand in a full
  store (`load`, and `memory_search`'s per-search store), and it also completes a store carried
  over from a smaller corpus. Where a store offers no `ids()`, the rule falls back to its
  length.
- **The optional methods are probed with `callable()`, not `hasattr`.** The first pass used
  `hasattr`, and `test_a_project_may_supply_its_own`'s store holds a list named `ids`, so the
  library called a list. Found by the suite within a minute.
- **`save` takes the index lock.** [`area-de-retrieval-memory.md`](../runs/full-test-2026-08-13/findings/area-de-retrieval-memory.md#L400)
  recorded in August that `save` reads `ids()` and `all_vectors()` as two calls, so an add
  landing between them writes a file whose counts disagree. That finding was thin-coverage
  then and this item makes the interleave likely, so the lock closes it and
  `_check_what_was_written` refuses the mismatch if a project's own store produces one another
  way.
- **The shape ratchet asked a real question and the answer was to decompose.** `search.py` went
  to 858 lines and `DocumentIndex` to 545, and moving the file format into `index_file.py` took
  the module back under its threshold. The class is recorded at 492 with its reason updated:
  what is left is the corpus and the four verbs over it.
- **`VectorScan`'s committed memory figures were numpy's.** Its docstring said 10,000
  documents at 768 dimensions hold 31 MB and 100,000 hold 307 MB. Those are the sizes of a
  `float32` matrix; a Python list of Python floats holds the same two corpora in **307 MB and
  3.0 GB**, measured here as resident memory with the input freed. The figure was wrong by a
  factor of ten before this item and is corrected in both the docstring and
  `docs/retrieval.md` §4.2. The times were right and reproduce.
- **A write's embedding call now happens before anything is written.** The first pass updated
  the postings and then embedded, so an add whose backend was down left the corpus holding a
  document no vector search could reach, findable lexically and invisible semantically.
  `_vectors_for` holds everything that can fail on something outside the process, and
  `tests/test_growing_index.py::TestAnEmbeddingCallThatFails` is the three cases.
- **`NumpyVectors.add` stored a caller's matrix without copying it.** `np.asarray` returns a
  `float32` matrix unchanged, so a project that kept a reference could change what the store
  held. A list of floats, which is what the index passes, is converted and already a copy.
- **A failed `FaissVectors.rebuild` left the store with no index.** It dropped the old one
  before building the new; the new one is built first now.
- **`scripts/build_view_fixtures.py --record` had never worked end to end.** `shipped` is
  derived from `measured` and carries the same `pipeline_factory` names, and the registry is
  process-global, so importing the second was refused. `_inside` now calls
  `clear_registered_pipelines()`, which exists for exactly this. This is the first format bump
  since `shipped` was added at `P3-56`, so nothing had run the path before.

**Formats.** Manifest `0.40`. Index file `2.0`, and `INDEX_FORMAT_VERSION` joins the five
versions `tests/test_packaging.py` pins. Trajectory, results,
suspension, shelf, conversation and variant comparison are unmoved.

**Tests.** 4,254, up from 4,165. `tests/test_growing_index.py` is 72 of them and
`tests/test_faiss_vectors.py` 19, the second skipping without the extra. Surfaces touched:
`builtins/search.py`, `builtins/vectors.py`, `builtins/index_file.py`, `builtins/ranking.py`,
`builtins/memory.py`, `builtins/__init__.py`, `tools.py`, `pipeline/recording.py`,
`records/manifest.py`, `pyproject.toml`, and the conformance and view fixtures.

## 4. Verification

**The stores, against dogfood #6's own corpus.** `lost-the-plot-frozen`'s
`data/lost-the-plot.db` holds 7,308 documents and 7,308 `Qwen/Qwen3-Embedding-0.6B` vectors at
1,024 dimensions, produced by that project's own runs. Loaded into each store, on this machine:

| Store | Build | One query, top 10 |
|---|---|---|
| `VectorScan` | 0.17 s | 58.5 ms |
| `NumpyVectors` | 0.14 s | 0.49 ms |
| `FaissVectors()` exact | 0.16 s | 0.76 ms |
| `FaissVectors(kind="approximate")` | 0.20 s | 0.11 ms |

The three exact stores returned the same ten documents in the same order for every query, with
every score agreeing to within 1e-4. The approximate index returned 0.97 of the exact answer's
top ten. `add`, `replace` and `remove` over the 7,308 documents moved the postings as intended.
The index saved in 0.03 s to a 9.2 MB JSON file and a 29.9 MB vector file, loaded back in
0.74 s, and answered identically.

**The GPU**, in a second environment holding `faiss-gpu-cu12` 1.14.1 and this library: the same
corpus through `FaissVectors(device="cuda")` answered in 8.4 ms and returned the list scan's
order on every query.

**A live run, Gemini and a real embedding model.** `gemini-3.1-flash-lite` answering,
`SentenceTransformerEmbeddings(model="Qwen/Qwen3-Embedding-0.6B", device="cuda")` embedding, and
400 of the same documents under `Hybrid(fuse=RRF(k=5))`. The agent was given a newly announced
show, filed it through a `WRITES` tool calling `index.add(retrieval=handle)`, searched for it in
words the entry does not use, and finished with its identifier.

What the run wrote: two `model_call` records with `params.call_kind` of `embedding`, one for
the add and one for the search query, both under `Qwen/Qwen3-Embedding-0.6B` at revision
`97b0c614`; `models.observed` naming the chat model and the embedding model; the
`document_search` tool entry carrying `Hybrid`, `RRF`, `k: 5`, `depth: 50`, `NumpyVectors`,
`exact: true` and `whole-word`; and `manifest.retrieval` reading 401 documents and 401 vectors,
which is the corpus the run finished with rather than the 400 it started from.

**The view fixtures were re-recorded live** against Gemini, which the manifest bump requires,
and the conformance fixtures regenerated.

### 4.1 Reverification cycles

Each cycle is a read of the code, a read of the docs against the code, the unit tests, the
full suite, and the live runs above. Fifteen cycles found 26 defects, the last of them in the fourteenth. The suite was
green before every one.

**Cycle 1** found six in the code and one in a shipped figure.

- `NumpyVectors.add` stored a caller's `float32` matrix without copying it, so a project
  holding a reference could change what the store held.
- `ids()` and `all_vectors()` read the store's two tables without its lock, on all three
  stores.
- `FaissVectors.rebuild` dropped the old index before building the new, so a failure left the
  store holding nothing.
- **A write's embedding call ran after the postings were updated**, so an add whose backend
  was down left the corpus holding a document the vector search could not reach. The whole of
  what can fail is now in `_vectors_for`, before anything is touched.
- `to_record` and `to_manifest` left `store` and `exact` out for a lexical index rather than
  writing them `null`, so two manifests could not be diffed key for key.
- **`VectorScan`'s committed memory figures were a `float32` matrix's.** 31 MB and 307 MB were
  what numpy holds; a list of Python floats holds the same two corpora in **307 MB and
  3.0 GB**, measured as resident memory with the input freed. Wrong by a factor of ten, and
  shipped since the store was written. Corrected in the docstring and in `docs/retrieval.md`
  §4.2. The times were right and reproduce.

Every executable claim in `docs/retrieval.md` §2, §2.1, §4.2, §4.3 and §4.4 was run as a
script rather than read. That is what caught the `to_record` gap.

**Cycle 2** found three.

- **A loaded index adopted an embedding identity it had no evidence for.** A file carrying
  vectors and no recorded model, opened under any client, took that client's identity onto its
  own record and into the manifest. Construction now records a model only where it did the
  embedding.
- `docs/retrieval.md` §2.1 did not say that removing every document is refused, or that a
  write which cannot embed changes nothing; §4.2 did not say that a store handed in empty is
  filled. All three are behaviour a builder meets.
- An inline `FaissVectors(device="cuda")` was broken across a line inside its backticks, and
  the GPU install named `pip uninstall` without `-y`, which prompts.

**Cycle 3** found two.

- **`add` held the index lock across the embedding call.** A bulk add of five hundred
  documents blocked every search on that index for as long as the backend took, and the
  lock's own docstring claimed the opposite. The call is now made with the lock released and
  the refusal checked on both sides of it, since another thread can write the same identifier
  while it is in flight. `test_a_search_runs_while_an_add_is_embedding` fails when the call
  goes back inside.
- The shape ratchet asked about `DocumentIndex` a third time, at 525 lines and 33 methods.
  Recorded rather than decomposed, with the reason in the baseline and the question in
  [`plan.md` §2.2](../plan.md#L168): one lock covers the documents, the postings and the
  store together, and the three properties built here rest on that.

**Cycle 4** found four, all small.

- `_write` called `store.remove` on the replace path without re-checking that the store has
  one. The check ran before the embedding call, and a store empty then can be filled by
  another thread while the call is in flight.
- `remove`'s docstring named neither the refusal on a store that cannot delete nor the warning
  an approximate FAISS index raises, both of which a builder calling it meets.
- `docs/retrieval.md` §6, which lists what happens to the model calls a search makes, did not
  count an `add`'s. It is the same path: a `model_call` record with `call_kind` of
  `embedding`, charged to the budget, keyed into the cassette, and named in `models.observed`.
  The live run above writes two of them.
- §6 also did not say that a tool which adds to an index is re-executed on replay the way a
  search is, which follows from its taking the same handle.

**Cycle 5** found two, both in what is written rather than what runs. `_vectors_for`'s
docstring said it holds "the refusals" after the identifier check had moved out of it to
`_grow`, and `docs/tools.md` §4.1's new paragraph left "them" pointing two sentences back. A
run whose index is lexical was also given a test of its own: it is counted under `retrieval`
with a `null` store, which is the third shape that array takes.

**Cycle 6** found one, and it came from the fix in §1's fault 1.
`DocumentIndex.from_texts(corpus, ranking=Semantic(), vectors=NumpyVectors())`, a vector
ranking with an empty store and no embedding client, used to build an index whose store stayed
empty. Filling the store made it reach the client instead and raise
`AttributeError: 'NoneType' object has no attribute 'embed'` out of the middle of the library.
It now refuses at construction, naming how many of the corpus the store holds and what to
pass.

**Cycle 7** found two.

- `to_manifest` read the corpus size and the vector count without the lock, which is the same
  pair `save` was fixed to read together in cycle 1. It runs at run close, where a fan-out
  item can still be adding.
- **The index file carries a `format_version` and nothing read it.** A file from a later
  version was read as though it were `2.0`, which fails somewhere inside instead of at the
  door. `read_index` now names what it reads (`1.0` and `2.0`) and refuses anything else,
  including a file with no version at all.

**Cycle 8** found one. **An `add` under a different embedding model was refused with a message
about a query.** `refuse_mismatch` is shared with the search path, and it read "the vectors in
this index were made by X and **the query** would be embedded by Y" for a caller who had
written no query. It names what was about to be embedded now, and `docs/retrieval.md` §3 says
the two paths refuse alike.

**Cycle 9** found one, and confirmed the trajectory claims for the new path. **CI never
installed the `ann` extra**, so `tests/test_faiss_vectors.py` skipped there and its 16 tests
only ever ran on this machine; `uv sync` without it would have pruned FAISS out of this one
too. The workflow now syncs it beside `semantic` and `mcp`, and the handoff's extras row says
so. The read of the live run's own trajectory confirmed `docs/retrieval.md` §6 for an add: the
embedding call is a `model_call` with `call_kind` of `embedding`, parented to the
`file_a_new_show` tool call, its 51 input tokens are in the run's total, and
`models.observed` counts two calls to the embedding model beside three to the chat model.

**Cycle 10** found one, and it was a lost edit rather than a defect in the design. Cycle 1's
paragraph saying that searches of one `FaissVectors` run one at a time never reached the file:
the edit was scripted against a string that had already been reworded, and a
`str.replace` that matches nothing changes nothing and says nothing. Every scripted edit in
this build that carried no assertion was audited against the file afterwards, and that
paragraph was the only one missing.

**Cycle 11** found the largest defect of the eleven, and it was a quality loss rather than a
crash. **An approximate `FaissVectors` returned progressively fewer true neighbours the deeper
the search asked.** FAISS explores `efSearch` candidates and returns the best `k` of them, and
its default of 16 sits below most of the depths this library asks for: `Hybrid` contributes 50
per arm by default, and a reranker's `top_n` can be 100. Measured against the exact answer on
dogfood #6's 7,308 documents at 1,024 dimensions:

| Asked for | Recall, `efSearch` 16 | Recall, walk widened |
|---|---|---|
| 10 | 0.97 | 0.97 |
| 50 | 0.87 | 0.97 |
| 100 | 0.77 | 0.99 |

Nothing raised, and both figures are what an approximate store is supposed to look like, so
the only way to see it is to measure against an exact store on a real corpus. The walk is now
made at least as wide as the number of results asked for, which costs 0.35 ms against 0.18 ms
at 100. `docs/retrieval.md` §4.3 carries the figures.

**Cycle 12** found no defect and closed a hole in the tests. The item's central promise, that
a grown index is what a rebuild would have produced, was verified by hand against 800 real
documents and asserted nowhere: an index built four documents at a time scores identically to
one built whole, an index with two removed scores identically to one built without them, a
replace with a document's own text moves no score, and the same holds for the vectors.
`TestGrowingMatchesBuildingWhole` is those four.

**Cycle 13 was run at four steps of five**, and its result was reported as clean before that
was noticed. It drove the paths no earlier cycle had: `from_directory` grown after construction, an index that reranks grown, a
non-default stopword list through a save and a load, a lexical index saved over one that had
vectors (the stale vector file goes), a save into a directory that does not exist yet, an
approximate store with all but one document removed, `add({})` / `replace({})` / `remove([])`,
an empty document, a repeated identifier inside one `remove`, a store whose `ids()` and
`all_vectors()` disagree, and a corpus whose documents all tokenise to nothing, where the mean
length is zero and nothing divides by it. What it did not do is read the code and the docs,
which is the first of the five steps; the same step was skipped in cycle 12. **A cycle that
skips the reading is not a cycle**, and the reading is the step that found nineteen of the
defects above.

**Cycle 14** ran all five, and reading `index_file.py` for the first time since cycle 7 found
two.

- **A refused save destroyed the index it was saving over.** The vector file was written
  before the checks ran and the JSON after them, so a save that was refused left the new
  vectors beside the old JSON. Reproduced on a four-document index: the save was correctly
  refused, and the index that had been on disk no longer loaded. Both files are now written
  beside the real ones and moved into place at the end. Embedding a corpus is the expensive
  thing this file exists to avoid repeating, and a failed save was destroying exactly that.
- **The load path materialised the whole corpus as Python floats**, which is what the binary
  format was introduced to avoid. Measured on dogfood #6's corpus: a 30 MB file became 269 MB
  resident while loading. It is read as a `float32` matrix where numpy is installed, which is
  39 MB, and the load of 7,308 documents went from 0.74 s to 0.38 s. At the million vectors
  `docs/retrieval.md` §2 names as the reason for the format, the old path needed about 27 GB.

Both were verified against all three stores on the real corpus: each loads from the matrix,
returns the same ten documents in the same order as the exact reference, and agrees on every
score to 1e-4.

**Cycle 15 found nothing**, and this one ran all five steps. The reading was the diff of the
four modules changed outside `builtins/` and never re-read since: `Tool` gains `searches`
between `fetch_policy` and the private fields, and every construction site in the library, the
tests and the docs passes keywords, so the position is not one anything binds by. The
cross-verification was mechanical rather than by eye: the field names
`docs/run-envelope.md` §2 lists for the `retrieval` row were pulled out of the row and
compared against the keys a live run wrote, and the two sets are equal.

## 5. Doc consequences

**`docs/retrieval.md`.** §2 is now "What an index costs to build, and how it grows": the two
files `save` writes, and a new §2.1 on `add`, `replace`, `remove` and the handle an add takes
inside a run. §4.2 is rewritten around the three stores with their measured figures and the
three optional methods. §4.3 is new: FAISS, the GPU install, and what an approximate index
cannot delete. §4.4 is new: what a run records about a search, and why the corpus size is not
part of the fingerprint.

**`docs/tools.md` §4.1** gains the three verbs and points at §2.1. **`docs/run-envelope.md`**
gains the manifest's `retrieval` row and moves to `0.40`. **`docs/index.md`** and
**`docs/procedure.md`**'s feature index name the growth and the stores.

**Statements that stopped being true.** `docs/retrieval.md` §2's "Rebuild and save again
whenever the corpus changes" is gone, and so is §4.2's claim that `vectors` defaults to
`VectorScan`. The §4.2 example handing in an empty store was documented behaviour that did not
work; it works now.

**`CHANGELOG.md`** carries the three verbs, the three stores, the `ann` extra, the two format
moves and the four faults from §1.

## 6. Left open

- **The BM25 analyzer** ([`plan.md` §2.1](../plan.md#L99)) is unblocked: the index file records
  which analyzer built it and refuses a file written under another, which is what that entry
  was waiting on. It stays in §2.1 with its own slot to claim.
- **`FaissVectors` is not saved as a FAISS index.** `save` writes the vectors and `load` builds
  the store again from them, so an approximate index rebuilds its graph on load rather than
  reading one off disk. On 7,308 documents that is 0.20 s. A corpus where it matters would want
  `faiss.write_index`, and nothing has asked for it: [`plan.md` §2.2](../plan.md#L1).
