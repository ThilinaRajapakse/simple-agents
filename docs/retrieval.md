# Retrieval

This document describes how retrieval (lexical, semantic, and hybrid) works in the library. `DocumentIndex` is introduced in `docs/tools.md` §4.1.

Everything here applies to any corpus the project supplies. `docs/memory.md` §2.4 is the same
machinery over the agent's own memory.

---

## 1. Retrieval in Simple Agents

Lexical retrieval works out of the box if no embedding client is provided.

```python
from simple_agents.builtins import DocumentIndex, document_search

index = DocumentIndex.from_directory("corpus/", glob="*.md")
registry.add(document_search(index, top_k=5))
```

**Lexical retrieval matches whole words.** Words are lowercased and nothing is stemmed, so a
search for "book" does not find a document that says "books", and a note reading "prefers short
books" is not found by a search for "length preference". That calls for semantic (or hybrid)
retrieval.

```python
from simple_agents.adapters import SentenceTransformerEmbeddings
from simple_agents.builtins import Hybrid, RRF

index = DocumentIndex.from_texts(corpus, embeddings=SentenceTransformerEmbeddings(),
                                 ranking=Hybrid(fuse=RRF(k=5)))
registry.add(document_search(index, top_k=5))
```

**`ranking` is required wherever `embeddings` is passed**, and §4 details the options available.

`SentenceTransformerEmbeddings` needs the `semantic` extra:

```
pip install 'simple-agents[semantic]'
```

Nothing else changes. `document_search` keeps its name and its place in the model's tool list,
and the model is offered the same two arguments.

---

## 2. What an index costs to build, and how it grows

**Passing `embeddings` embeds every document once, when the index is built.** For a corpus of
ten thousand documents that is one pass over the whole corpus, so an index used more than once
is saved and loaded rather than rebuilt:

```python
index = DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
index.save("corpus.index")

index = DocumentIndex.load("corpus.index", embeddings=embedder, ranking=Semantic())
```

**`save` writes two files.** `corpus.index` holds the documents, the stopwords, the analyzer
that cut them into words, and what embedded them; `corpus.index.vec` holds the vectors as raw
`float32`. Both move together, and `load` reads the pair. A million 768-dimension vectors are
3 GB, which is why they are not in the JSON. `load` does not embed by itself.

**A save that fails leaves the corpus that was already there.** Both files are written beside
the real ones and moved into place at the end, so a refusal partway through costs nothing that
has to be embedded again.

### 2.1 Adding to a corpus that changes

A corpus that gains a document a day is added to rather than rebuilt. `add` embeds the new
documents and leaves the rest alone, `replace` re-embeds the ones whose text changed, and
`remove` drops the ones it names:

```python
index.add({"s5121": "Cormorant Bay was announced for the spring."})
index.replace({"s4870": "Harrow Lane returns in March, one season only."})
index.remove(["s3199"])
index.save("corpus.index")
```

Each of the three updates the words and the vectors together, so a search after one of them
matches on what the corpus says now. `add` refuses an identifier the index already holds, and
`replace` and `remove` refuse one it does not. Removing every document is refused too: an
index holding nothing answers every search the way a corpus without the answer does.

**A write that cannot embed changes nothing.** The embedding call is made before the corpus is
touched, so an add whose backend is down leaves the index as it was rather than holding a
document the vector search cannot reach.

**An add inside a running pipeline takes the `Retrieval` handle**, the same one a search
takes, because embedding the new documents is a model call:

```python
@tool(side_effect_class=SideEffectClass.WRITES)
def file_the_announcement(retrieval: Retrieval, show_id: str, text: str) -> str:
    """File a newly announced show so later searches find it."""
    index.add({show_id: text}, retrieval=retrieval)
    return show_id
```

Without it the call is charged to no budget, recorded in no trajectory, and made again on
every replay and every rollout of an evaluation. An add made from a build script, before any
run, needs no handle.

**Save after growing.** An index that was added to and not saved keeps the new documents for
as long as the process runs, and the file on disk still describes the corpus as it was.

---

## 3. Which model embeds, and what happens when it changes

`embeddings` takes an `EmbeddingClient`. Three come pre-built, and a project can write its own.

| Client | Needs | Backend |
|---|---|---|
| `SentenceTransformerEmbeddings(model=..., device=...)` | the `semantic` extra | runs in this process |
| `OpenAIEmbeddings(base_url=..., model=..., model_revision=...)` | an endpoint serving `/v1/embeddings` | `self_hosted` by default |
| `MistralEmbeddings(model="mistral-embed")` | `MISTRAL_API_KEY` | `hosted_api` |

A project that already runs a chat model through a hosted provider usually has embeddings from
the same endpoint and the same key. A self-hosted vLLM server loads one model and decides at
startup whether it generates or pools, so a self-hosted project runs a second server for the
embedding model and points `base_url` at it.

**Vectors from two models are not comparable.** A corpus embedded by one model and searched
with a query embedded by another returns confident results with no relation to the question, so
the mismatch is refused rather than answered:

```
The vectors in corpus.index were made by 'all-mpnet-base-v2'@e8c3b32 and the query would be
embedded by 'all-MiniLM-L6-v2'@fa97f6e. Vectors from two models occupy different spaces, so
comparing them returns confident nonsense with nothing raised.
Use the model the corpus was embedded with, or re-embed the corpus with the new one and save
it again: DocumentIndex.from_texts(corpus, embeddings=new).save(path).
```

Changing the embedding model means re-embedding the corpus. An `add` or a `replace` under a
different model is refused the same way, naming the documents rather than the query.

**Pin the embedding model.** It is a second model identity in the run: the manifest records it,
the cassette key includes it, and FT-14 reads it alongside the chat model.

Which client is used decides whether the pin has to be written down.
`SentenceTransformerEmbeddings` loads the weights itself, so it reads the commit
`sentence-transformers` resolved and records that when `model_revision` is unset.
`OpenAIEmbeddings` and `MistralEmbeddings` report what they were given and nothing else,
because an endpoint does not publish which weights it is serving. One of those with no
`model_revision` fails FT-14 the same way an unpinned chat model does.

---

## 4. Ranking

`ranking` decides which retrievers run and how their results combine. An index built without
`embeddings` is `Lexical()`. **An index built with
`embeddings` has to choose**, and one that does not is refused before it is searched:

```
DocumentIndex was given embeddings= and no ranking=. An index that can embed can rank three
ways, and which one is right depends on the queries:
    ranking=Lexical()                                  word overlap only
    ranking=Semantic()                                 meaning only
    ranking=Hybrid(fuse=RRF(k=5))                      both, combined by rank position
    ranking=Hybrid(fuse=WeightedScore(lexical=0.3))    both, combined by score
```

Passing an embedding client is a statement about what the index can do. The three options are:

| Ranking | Finds | Misses | Reach for it when |
|---|---|---|---|
| `Lexical()` | an exact identifier, a part number, a quoted phrase | a paraphrase sharing no words with the document | the corpus is identifiers and end users quote them |
| `Semantic()` | a question phrased differently from the passage | an identifier the embedding model has no meaning for | end users ask in prose and the corpus is prose |
| `Hybrid(fuse=..., depth=50)` | what either arm finds | only what both miss, though it can rank a decisive hit below two indifferent ones (§4.1) | the corpus holds both shapes, or which shape the queries take is not yet known |

`depth` is how many results each retriever contributes before the fusion.

```python
DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic())
DocumentIndex.from_texts(corpus, embeddings=embedder,
                         ranking=Hybrid(fuse=Interleave(), depth=100))
```

**Hybrid is not always better than one of its parts.** Where the embedding model suits the
corpus, fusing a weaker lexical list into it can rank the answer lower than the vector search
alone. `compare_variants` measures the difference on the project's own examples
(`docs/evaluation.md` §10).

### 4.1 Fusion

`fuse` decides how the two ranked lists become one.

#### 4.1.1 Reciprocal Rank Fusion

**`RRF(k=5)`, the default.** Each list votes by rank: a document at rank `r` contributes
`1 / (k + r)`, and the votes add up. `k` sets how fast the vote decays, and that decides a
contest between one large vote and two small ones: a document ranked first by one retriever and
missing from the other, against one ranked mid-list by both.

```python
lexical  = [decisive, ..., mediocre]     # decisive 1st, mediocre 11th
semantic = [...,           mediocre]     # decisive absent, mediocre 11th

RRF(k=5).combine(lexical, semantic, 1)    # ['decisive']
RRF(k=60).combine(lexical, semantic, 1)   # ['mediocre']
```

The published default for fusing many retrieval systems is 60. The default here is 5 because
two retrievers over short lists is a different problem. A project fusing more than two lists should expect to raise it.

**Documents at the same rank in one list and absent from the other score exactly equal**, and
that tie is broken by identifier. On a corpus of near-identical documents, such as a parts list
differing only in the part number, the order of a tied group is settled by their names.

#### 4.1.2 Interleaving

**`Interleave()`.** Takes each list's best in turn, so each
retriever is guaranteed its top result. This trades the rank of the answer for the chance of
finding it: reserving every second slot puts the other retriever's best guess second whether or
not it is any good. Reach for it where one retriever is decisive on some queries and useless on others.

#### 4.1.3 Weighted scores

**`WeightedScore(lexical=0.5)`.** Divides each list's scores by the largest in that list, so
the top result in each becomes 1.0, then adds the two with weights. `lexical` is the weight on
the lexical score and the semantic weight is `1 - lexical`.

The scaling happens per query, so the top lexical hit scores 1.0 whether it matched the query
closely or barely at all. A weight sets how much a list's ordering counts. It carries no
information about how strong that list's matches were.

### 4.2 Where the vectors live

`vectors` says which store holds them and answers a search against them. Three ship:

| Store | Results | Needs | Reach for it when |
|---|---|---|---|
| `NumpyVectors()` | exact | numpy | the default, up to a few hundred thousand documents |
| `VectorScan()` | exact | nothing | numpy is unavailable |
| `FaissVectors(...)` | exact or approximate | the `ann` extra | a corpus around a million documents, or a GPU to put it on |

An index that names none builds `NumpyVectors` where numpy is installed and `VectorScan`
otherwise. The two return the same documents in the same order, so which one answered changes
the time a search takes and not what comes back.

**Measured on one CPU core at 768 dimensions**, a query against:

| Documents | `VectorScan` | `NumpyVectors` | Memory |
|---|---|---|---|
| 10,000 | 60 ms | 3.5 ms | 307 MB against 39 MB |
| 100,000 | 590 ms | 7.1 ms | 3.0 GB against 306 MB |

A Python float is an object, which is where `VectorScan`'s memory goes.

A project with the corpus in a store it already runs supplies its own:

```python
class MyStore:
    def add(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]) -> None: ...
    def search(self, vector: Sequence[float], top_k: int) -> list[tuple[str, float]]: ...
    def __len__(self) -> int: ...

DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic(),
                         vectors=MyStore())
```

`search` returns `(doc_id, score)` best first, where a higher score is more similar. Vectors
reaching `add` are already unit length, so a dot product is the cosine. A store returning
approximate neighbours returns fewer true matches than an exact one for the same `top_k`, and
the project owns that trade.

**A store handed in empty is filled from the corpus** when the index is built, and one already
holding vectors is used as it is. A store holding part of the corpus has the rest embedded
into it.

**Three more methods are optional, and each one enables something.** `ids()` and
`all_vectors()` are what `save` writes, and a store without them is refused at `save`.
`remove(ids)` is what `index.remove` and `index.replace` call. The three stores above have all
three.

### 4.3 FAISS, and the GPU

`FaissVectors` needs the `ann` extra:

```
pip install 'simple-agents[ann]'
```

```python
DocumentIndex.from_texts(corpus, embeddings=embedder, ranking=Semantic(),
                         vectors=FaissVectors())                       # exact, on the CPU
DocumentIndex.load("corpus.index", embeddings=embedder, ranking=Semantic(),
                   vectors=FaissVectors(kind="approximate"))           # a graph, on the CPU
DocumentIndex.load("corpus.index", embeddings=embedder, ranking=Semantic(),
                   vectors=FaissVectors(device="cuda"))                # exact, on the GPU
```

`kind="exact"` compares against every vector, the same documents an exact scan returns.
`kind="approximate"` walks a graph and returns most of the true neighbours for a fraction of
the work, which is the trade a corpus of a million documents usually wants. The walk is as
wide as the number of results asked for, so `top_k` and a `Hybrid` `depth` both keep their
recall: measured on 7,308 documents at 1,024 dimensions, 0.97 of the exact answer's top ten
and 0.99 of its top hundred.

**The GPU is a different FAISS build.** The `ann` extra installs the CPU one. FAISS's own GPU
distribution is a conda package, and there is a wheel on PyPI:

```
pip uninstall -y faiss-cpu && pip install faiss-gpu-cu12
```

Both provide the module named `faiss`, so a machine has one of them. Asking for `cuda` on a
CPU build names this install in the refusal. `kind="approximate"` with `device="cuda"` is
refused, because FAISS's GPU indexes do not include the graph.

**An approximate index cannot delete.** FAISS builds the graph as vectors arrive and offers no
way to take one out, so `remove` marks the document and filters it out of every later search,
with a warning naming `store.rebuild()`. Searching stays correct and asks for more candidates
the more has been removed; `rebuild()` builds the graph again from what is left. An exact
index deletes outright.

### 4.4 What a run records about a search

The manifest's entry for the tool that searches an index carries a `retrieval` object: the
ranking, the fusion and its settings, the reranker, the `store` and whether it is `exact`, the
analyzer, and the model that embedded the corpus. It is part of `behaviour_fingerprint`, so a
result stored under an exact scan is not read back as though it were produced by an
approximate one, and an evaluation comparing two runs reports the store as a changed setting
rather than comparing their numbers.

How many documents the index held is on the manifest's own `retrieval` array instead, counted
when the run ends (`docs/run-envelope.md` §2). A corpus that gained a document during the run
leaves the count the run finished with, and a growing corpus leaves every stored result
readable, because gaining a document has not changed how the pipeline behaves.

---

## 5. Reranking

A first pass ranks the whole corpus cheaply; a reranker reads the query and each candidate
together and reorders the few that came back. It is off by default.

```python
from simple_agents.adapters import LocalCrossEncoder
from simple_agents.builtins import CrossEncoderRerank

DocumentIndex.from_texts(corpus, embeddings=embedder,
                         rerank=CrossEncoderRerank(LocalCrossEncoder(), top_n=20))
```

`top_n` is how many candidates the first pass hands over, and it does three things:

- **It bounds the cost.** A rerank reads every candidate alongside the query, so twice the
  candidates is roughly twice the tokens. The default is 20.

- **It caps `top_k`.** A search returns at most `top_n` results however many were asked for,
  because the reranker orders the pool it was given and the result is taken from that.
  `rerank=CrossEncoderRerank(client, top_n=3)` with `document_search(index, top_k=10)` returns
  three.
- **At or above the corpus size it discards the first pass.** Every document reaches the
  reranker, so `ranking` no longer decides what comes back, only what the reranker's input
  order was. On a corpus of 200 documents, `top_n=500` is a cross-encoder pass over the whole
  corpus on every search.

`compare_variants` measures a reranked search against the same search without one, on the
project's own examples (`docs/evaluation.md` §10).

**`ModelRerank` asks the run's chat model instead**, so it needs no second model and no extra:

```python
DocumentIndex.from_texts(corpus, embeddings=embedder, rerank=ModelRerank(top_n=10))
```

It reads every candidate into a prompt, so the tokens grow with `top_n` and with document
length, and what it returns is an ordering rather than a score. A reply naming only some of the
candidates leaves the rest in their incoming order behind the ones it named.

**`OpenAIReranker` calls an endpoint serving `/v1/rerank`**, which vLLM and several hosted
rerankers do, so the cross-encoder runs on a server instead of in this process:

```python
from simple_agents.adapters import OpenAIReranker

remote = OpenAIReranker(base_url="http://localhost:8004/v1",
                        model="cross-encoder/ms-marco-MiniLM-L-6-v2",
                        model_revision="c5ee24cb16019beea0893ab7796b1df96625c6b8")
DocumentIndex.from_texts(corpus, embeddings=embedder,
                         rerank=CrossEncoderRerank(remote, top_n=20))
```

It goes inside `CrossEncoderRerank` the way `LocalCrossEncoder` does, since how many candidates
to rerank is the index's setting. A host that needs a key takes `api_key=`, held as a
`SecretStr`.

---

## 6. What a search costs, and where it is recorded

Embedding the query is a model call, so is a rerank, and so is embedding the documents an
`add` puts in (§2.1). All three go through the same path every model call goes through:

- each is a `model_call` record in the trajectory, parented to the tool call that made it, with
  `params.call_kind` of `embedding` or `rerank`
- each is charged to the run's `max_tokens` and `max_steps` budget
- each is keyed into the cassette, so a replay serves it rather than calling out
- the model that served it appears in the manifest's `models.observed`, and FT-14 reads it

The record carries what was asked and the shape of what came back, not the vector itself.

**A search that makes model calls is re-run during a replay** rather than served from the
cassette, and its embedding and reranking calls are served instead, so a replayed run writes the
same records the live run wrote. A purely lexical search is stored as one entry. A tool that
adds to the index takes the same handle and is replayed the same way.

**Declare a rate per model.** An embedding model and a chat model are priced differently, so a
single `PriceBasis` prices the embedding calls at chat rates:

```python
cost_basis={
    "Qwen/Qwen3-8B": PriceBasis(currency="USD", input_uncached_per_mtok=0.30,
                                output_per_mtok=1.20),
    "mistral-embed": PriceBasis(currency="USD", input_uncached_per_mtok=0.01,
                                output_per_mtok=0.0),
}
```

A `by_model` basis that names no rate for the embedding model leaves those calls unpriced, and
one unpriced call makes the run's total unknown with the reason on the record.

---

## 7. Reading a result

```json
{"results": [{"doc_id": "policy-2", "score": 0.9159, "retriever": "semantic", "rank": 1,
              "text": "Deliveries to the Ashford depot are refused after 4pm on weekdays."}],
 "documents_containing": {"deliver": 2, "late": 0}}
```

`retriever` names what found it: `lexical`, `semantic` or `rerank`. It appears only where more
than one retriever produced the results, so a purely lexical search returns the three fields it
always returned.

**Two retrievers' scores are not comparable.** A BM25 score is unbounded, a cosine is in
`[-1, 1]`, and a cross-encoder's is an unbounded logit that is commonly negative. Compare a
score only against another carrying the same `retriever`.

`documents_containing` counts the query's words across the corpus and is lexical whatever the
ranking is. A count of zero means the index cannot match that word; it says nothing about
whether the corpus covers the subject.

---

## 8. Writing an embedding client

A custom adapter needs to implement two methods.

```python
class MyEmbeddings:
    def identity(self) -> ModelIdentity:
        return ModelIdentity(backend="hosted_api", request_model="my-embed-v2")

    def embed(self, texts: Sequence[str]) -> EmbeddingResponse:
        ...
```

`embed` returns one vector per text, in the order given, and batches inside itself where the
backend has a limit. Returning a different number of vectors than texts is refused, because the
caller pairs them by position.

`identity` reports which model without making a call. It is what the manifest records, what the
cassette key includes, and what FT-14 reads.

An `EmbeddingResponse` carries the token count the backend reported, with `output` of `0`. A
backend reporting no usage cannot be charged to a budget, and reporting zero would understate
it, so an adapter over one either counts the tokens it sent or refuses.

A `RerankClient` is the same shape with `rerank(query, documents)` returning a `RerankResponse`,
which scores every document it was given rather than filtering.

**Tests run against the fakes.** `FakeEmbeddingClient` hashes each text into a fixed vector,
and `FakeRerankClient` scores by how many query words a document holds, so both are
deterministic, make no call, and need no server:

```python
from simple_agents import FakeEmbeddingClient, FakeRerankClient
from simple_agents.builtins import CrossEncoderRerank, DocumentIndex

index = DocumentIndex.from_texts(
    corpus,
    embeddings=FakeEmbeddingClient(),
    rerank=CrossEncoderRerank(FakeRerankClient(), top_n=20),
)
```

The vectors and scores mean nothing about relevance, so a test built on them exercises the
plumbing: what a search returns, what a store records, what a replay serves. Retrieval quality
is measured against the real clients on the project's own examples.
