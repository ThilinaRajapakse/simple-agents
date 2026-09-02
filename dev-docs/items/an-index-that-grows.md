# An index that grows, on the CPU or the GPU

`plan.md` §1 P3-73's record. **Nothing is built.**

## Where it came from

[`DF6-I14`](../runs/dogfood-6/inventory.md#L64), from [`DF6-D14`](../runs/dogfood-6/findings.md#L344): `DocumentIndex` cannot be added to, so lost-the-plot wrote
its own vector store and used the library's index for the lexical half only. Thilina at the
sitting of 2026-09-02: numpy by default, and FAISS with GPU support for those who need it, so
the capability exists before a project asks; a million vectors is a reasonable size for some
project and the dogfoods are chosen small.

## What the problem is

- **No `add`.** An index is built once from a mapping and embeds everything at construction;
  a corpus that gains a document a day rebuilds or leaves.
- **`VectorScan` is a pure-Python loop** over lists of floats: about 80 ms a query at ten
  thousand documents and 800 ms at a hundred thousand, against 1 ms and 10 ms for a numpy
  dot product on the same machine, and about 8 s at a million. Both dogfoods that embedded
  anything real left it.
- **`save` base64-encodes the vectors into JSON**, which does not scale to a file of gigabytes.
- **Construction embeds outside the `Retrieval` handle**, so an `add` made inside a node
  during a run would be a model call recorded nowhere.

## What has to be decided

- **`add(texts)`**: postings and lengths updated, only the new texts embedded, through the
  handle where one exists; an id already held refused.
- **The default store**: numpy where it imports, the list scan otherwise. Whether a GPU exact
  store through torch is part of the default ladder or left to FAISS.
- **FAISS**: an optional extra (`[ann]`) with a store over `faiss-cpu`, exact and approximate
  index kinds, and GPU through FAISS's own GPU build. How the GPU build is declared to `pip`,
  since FAISS's official GPU distribution is conda; whether the extra names a community wheel.
- **The save format**: vectors as a binary sidecar beside the JSON, index format `1.0` moving.
- **The record**: which store answered a search, on the manifest and the results file, since an
  approximate store returns fewer true neighbours for the same `top_k` and two figures measured
  on different stores are not compared.
- **The existing §2.1 entry** on the BM25 analyzer waits on the index file recording its
  analyzer; the same field records the store.

## What it waits on

none
