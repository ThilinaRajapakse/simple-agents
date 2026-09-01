# Build log — semantic recall

`archive/plan-history.md` §1.8 is the brief, widened by Thilina's steer of 2026-08-11:
semantic search is a general capability over a corpus the project supplies, with memory recall
as one caller of it rather than the only one. §1.8's fourth question is settled by that steer
(the library ships a vector index; which form is the open part), and the other three stand.

**Status: designed, not yet built.** §1 is what was measured before anything was designed, §2
is the machine, §3 is the design put to Thilina.

---

## 1. The machine, before anything else

vLLM was not running at the start of this item and the GPU held 1.4 GB of 24 GB. Mistral is out
of credits, so `mistral-embed` is unavailable and every measurement here is local.

### 1.1 `all-mpnet-base-v2` does not serve under vLLM, on two routes

The cached snapshot is `MPNetForMaskedLM`:

```
/deep_learning/.cache/huggingface/hub/models--sentence-transformers--all-mpnet-base-v2
  config.json  model.safetensors  special_tokens_map.json  tokenizer.json
  tokenizer_config.json  vocab.txt
```

Two attempts, both refused at config validation before any weight was read:

```
vllm serve sentence-transformers/all-mpnet-base-v2 --runner pooling --port 8001 \
    --gpu-memory-utilization 0.15
  -> Model architectures ['MPNetForMaskedLM'] are not supported for now.

vllm serve sentence-transformers/all-mpnet-base-v2 --runner pooling --model-impl transformers ...
  -> The Transformers implementation of 'MPNetForMaskedLM' is not compatible with vLLM.
```

vLLM 0.26.0's pooling registry holds `BertModel`, `RobertaModel`, `XLMRobertaModel`,
`ModernBertModel`, `NomicBertModel`, `GteModel` and the Qwen embedding families. MPNet is in
none of them, and the Transformers fallback backend does not accept it either. The snapshot also
lacks `modules.json` and `1_Pooling/config.json`, so nothing on disk states its pooling.

**This is a vLLM limit and not a limit on the model**, which the build found later.
`sentence-transformers` loads `all-mpnet-base-v2` in-process without complaint, fetching the
pooling configuration the snapshot lacks, and reports the commit its weights came from
(`e8c3b32edf5434bc2275fc9bab85f82640a19130`). It is the shipped default for
`SentenceTransformerEmbeddings` under D7.

### 1.2 What does serve: `msmarco-bert-co-condensor`, from the same cache

`BertModel`, 768 dimensions, already in the hub cache, and its published pooling is CLS, which
is what vLLM defaults to for BERT. No download.

```
HF_HOME=/deep_learning/.cache/huggingface \
  vllm serve sentence-transformers/msmarco-bert-co-condensor \
    --runner pooling --port 8001 --gpu-memory-utilization 0.15
```

`/v1/embeddings` answers, and reports usage:

```
POST /v1/embeddings  input=["prefers short books", "length preference"]
  data[0].embedding   768 floats
  usage               {'prompt_tokens': 9, 'total_tokens': 9, 'completion_tokens': 0}
  cosine              0.9095
```

**An embedding response carries a prompt-token count and a zero completion count.** That is the
whole of what a token budget would charge it.

Also cached and unused here: four `cross-encoder/ms-marco-*` rerankers,
`msmarco-distilbert-base-tas-b`, `msmarco-distilbert-dot-v5`, `msmarco-MiniLM-L-12-v3`
(`BertModel`, 384 dimensions, would also serve).

### 1.3 Both servers fit on the one card, and the chat model needs its settings changed

The design needs a chat model and an embedding model live at once, so this was measured rather
than assumed. Three attempts:

| Chat server settings | Result |
|---|---|
| `--gpu-memory-utilization 0.8 --max-model-len 16384` | refused: 0.14 GiB left for KV cache, needs 1.5 GiB |
| `0.9`, same | CUDA OOM warming up the sampler with 256 dummy requests |
| `0.88 --max-num-seqs 8` | **serves** |

```
embedding  8001  sentence-transformers/msmarco-bert-co-condensor       764 MiB
chat       8002  cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit       21,168 MiB
                                                            total 21,932 / 24,576 MiB
```

Both answered while the other was up: chat 54 ms for a two-token reply, embedding 8 ms.
**`--max-num-seqs 8` is what makes it fit**: the sampler's warm-up at the default 256 is what
OOMs, not the weights. The embedding server's 764 MiB is small enough that the constraint is the
30B alone, near the edge of the card either way.

Port 8001 is the embedding server here and 8002 the chat server, because 8001 was already
serving embeddings when the chat model was started. `handoff.md` says 8000 is taken by something
unrelated.

### 1.4 One embedding call, and a corpus of 10,000

Against the server in §1.2, over the network on localhost:

```
one query embed        median 2.9 ms   (min 2.6, max 3.3)      13 tokens
   100 documents        0.16 s     615 docs/s        18,156 tokens
 1,000 documents        1.47 s     682 docs/s       182,148 tokens
10,000 documents       14.57 s     686 docs/s     1,820,791 tokens
```

**A corpus of 10,000 documents is 1.8 M tokens to embed once.** That is the figure that decides
where the embedding call goes: at a hosted embedding model's rates it is cents, and repeated per
run it is not.

### 1.5 What `memory_search` costs today, before a vector version is designed around it

[`builtins/memory.py` `memory_search`](../../src/simple_agents/builtins/memory.py#L108) builds a
`DocumentIndex` from every entry in the store on every call. Measured on entries of about
20 words:

```
store of     10 entries     0.35 ms per memory_search call
store of    100 entries     0.46 ms
store of  1,000 entries     4.46 ms
store of 10,000 entries    51.19 ms
```

**Rebuilding a BM25 index per call is free at any store size a memory reaches.** That is why
nothing has complained about it.

A vector version of the same shape re-embeds the store per call, against the live server:

```
store of     10 entries      11.4 ms per call
store of    100 entries      56.8 ms
store of  1,000 entries     585.7 ms      182,000 tokens per tool call
```

**130x slower at 1,000 entries, and 182,000 tokens on every search.** A run with a 200,000-token
budget is ended by two recalls. The same shape does not transfer, and the vectors have to be
written once and read back.

### 1.6 `DocumentIndex` at scale, and what a pure-Python scan costs

BM25 build and search, documents of about 120 words:

```
   100 documents   build     3.6 ms   search 0.01 ms   peak alloc  1.0 MB
 1,000 documents   build    25.4 ms   search 0.06 ms   peak alloc  3.6 MB
10,000 documents   build   316.1 ms   search 0.54 ms   peak alloc 27.1 MB
```

Brute-force cosine over normalised vectors, no dependency, on this machine's CPU:

| | 1,000 x 768 | 10,000 x 768 | 10,000 x 384 | 100,000 x 768 |
|---|---|---|---|---|
| `math.sumprod` over lists (3.12+) | 6.1 ms | **63.7 ms** | 32.6 ms | 624.5 ms |
| `math.sumprod` over `array('f')` | 9.9 ms | 95.5 ms | 48.2 ms | 955.9 ms |
| `sum(map(operator.mul, ...))` (3.11) | 13.3 ms | 145.6 ms | 73.4 ms | 1452.7 ms |
| ranking the scores, `heapq.nlargest` | 0.0 ms | 0.3 ms | 0.2 ms | 2.4 ms |
| float32 in memory | 3 MB | 31 MB | 15 MB | 307 MB |

numpy is not installed in this project and was not measured. The library's dependencies are
`httpx` and `pydantic`.

**A 10,000-document corpus scans in 64 ms with nothing installed**, against a query embedding
that costs 2.9 ms locally and more over a hosted API. `array('f')` is slower than a plain list
because indexing it boxes a float per element. The library requires Python 3.11, where
`math.sumprod` does not exist and the fallback is 146 ms.

Persisting the vectors:

```
10,000 x 768 float32 packed      30.7 MB    pack 89 ms    load 171 ms
10,000 x 768 float32 + zlib      28.5 MB    compress 725 ms   (random vectors do not compress)
10,000 x 768 JSONL at 5dp        72.3 MB    load ~494 ms
```

And one vector inside a trajectory record:

```
JSON list of 768 floats     17,002 bytes
float32 base64               4,096 bytes
dimensions + count              31 bytes
```

### 1.7 One corpus, ten queries, one embedding model

**Read this section as what it is.** It is a single synthetic corpus, ten queries, one embedding
model chosen because it was the one that served on this machine (§1.1). It is enough to show
that a fusion rule can lose what one of its inputs already found, and it is not enough to rank
retrieval methods in general. §1.12 is the wider measurement that picks a default; this section
is the probe that showed a default had to be picked carefully.

*(Written first as a general claim about fusion, and corrected on Thilina's push-back of
2026-08-11: "Did you just try to solve Information Retrieval in one contrived test?" He is
right. What survives is the failure mode below, not an ordering of methods.)*

Measured on 600 documents: 200 part records differing only in the identifier
(`AX-7700-A` through `AX-7899-B`), 200 order records, 200 prose notes. Ten queries with a known
answer, five naming an exact identifier and five phrased as a question sharing no words with the
note. `recall@3`:

| | exact identifier | paraphrase | overall |
|---|---|---|---|
| BM25 alone | **5/5** | 1/5 | 6/10 |
| dense alone | 2/5 | **3/5** | 5/10 |
| RRF, k=60, depth 50 | 2/5 | 3/5 | **5/10** |
| RRF, k=5, depth 20 | 5/5 | 3/5 | 8/10 |
| max-normalised weighted sum, 0.5 | 2/5 | 3/5 | 5/10 |
| **interleave** | **5/5** | **3/5** | **8/10** |

**Reciprocal rank fusion at its published default is worse than the BM25 that already ships.**
The diagnosis, on `AX-7717-B`:

```
BM25 top 3   [('part17', 8.31), ('part1', 2.70), ('part101', 2.70)]     gap 3.1x
dense top 3  [('part45', 0.916), ('part18', 0.916), ('part30', 0.915)]  gap 1.000x
gold rank    BM25 #0,  dense #80
```

RRF scores a document by `1/(k+rank)` and discards the score. The gold document is first
lexically and past the dense list's depth, so it gets one vote; the documents that beat it get
two each.

*(This paragraph said something else until the build, and §3.2 is the correction. The original
said the gold document "ties with noise" and that a smaller k "sharpens the discount enough to
recover it". Both were guesses at the arithmetic and neither is what happens.)*

Interleaving takes each list's best in turn and compares nothing across them. Across `top_k`:

| method | k=1 | k=3 | k=5 | k=10 |
|---|---|---|---|---|
| BM25 | 5 id, 1 para | 5, 1 | 5, 1 | 5, 1 |
| dense | 1 id, 3 para | 2, 3 | 2, 3 | 2, 4 |
| RRF k=60 d=50 | 2 id, 2 para | 2, 3 | 2, 3 | 2, 4 |
| RRF k=5 d=50 | 3 id, 2 para | 5, 3 | 5, 3 | 5, 4 |
| **interleave** | **5 id, 2 para** | **5, 3** | **5, 3** | **5, 4** |

On this corpus interleave ties or beats every fusion at every k, and it is the only one with no
constant in it. **Its own cost is visible at k=1**: it spends the single slot on BM25 and loses
one paraphrase that dense alone finds.

**What generalises from this and what does not.** What generalises is the failure mode: a
rank-only fusion discards the margin between the first and second result, so a retriever that is
decisively right about a query is outvoted by one that is uniformly indifferent to it. That is a
property of the arithmetic, and any corpus holding identifiers can produce it. What does not
generalise is the ordering of the six rows. Ten queries on one synthetic corpus with one
mediocre embedding model cannot establish that interleaving beats RRF, and it is not being
claimed. It establishes that the published RRF default cannot be shipped as the only behaviour
without checking it, which is what §1.12 does.

### 1.8 FT-14 is blind to an embedding identity, and `models.observed` does not save it

[`checks.py` `_serving_models`](../../src/simple_agents/conformance/checks.py#L447) reads
`manifest["nodes"]` filtered to `node_kind` in `("llm", "agent")`, falling back to
`models.configured`. Four manifests, one unpinned embedding identity, FT-14 run over each:

| Where the floating embedding identity sits | `_serving_models` sees | FT-14 |
|---|---|---|
| nowhere in the manifest | chat only | **PASSED** |
| `models.observed`, with 11 calls against it | chat only | **PASSED** |
| a `nodes[]` entry with `node_kind: "tool"` | chat only | **PASSED** |
| a `nodes[]` entry with `node_kind: "llm"` | chat and embedding | FAILED, 1 finding |

**An embedding model that floats passes FT-14 today**, and recording its calls under
`models.observed` does not change that: `observed` is read only to decide whether the run made
any model call at all ([`checks.py` `observed`](../../src/simple_agents/conformance/checks.py#L423)).
This is the §1.8 question about a store embedded under one model and read under another, one
level up: the check that exists for exactly this failure does not currently reach it.

### 1.9 `ModelHandle` cannot carry an embedding call, and this is the load-bearing finding

`archive/plan-history.md` §1.8 offers "an adapter method beside `complete`" as one of two places the embedding
call could go, and the steer points at the seam a tool already has. Neither is available as it
stands.

- **`ModelClient` is chat-shaped.** Two methods,
  [`models.py:420`](../../src/simple_agents/models.py#L420): `complete(ModelRequest) ->
  ModelResponse` and `identity()`. A `ModelRequest` carries messages, tools and an output
  schema; a `ModelResponse` carries content, tool calls and a finish reason. An embedding takes
  a list of strings and returns a list of vectors. It is not this protocol with a field unused.
- **`ModelHandle` is bound to the calling node's chat client.**
  [`agent.py:1151`](../../src/simple_agents/nodes/agent.py#L1151) `_nested_call` fills it with
  `self._nested_call(run, model, ...)`, where `model` is the node's resolved client. A tool
  holding one cannot reach a second model. An embedding routed through it would be sent to the
  30B chat model as a prompt.

So whichever way this goes, **an embedding client is a new protocol, not a third method on the
existing one**.

### 1.10 What a handle does to the cassette, measured on both shapes

Two versions of a search tool against the live 30B, one taking no handle (what
`document_search` is today) and one taking a `ModelHandle` and making one nested call. Recorded,
then replayed:

```
document_search, no handle                document_search, taking a ModelHandle
  trajectory  model_call 3                  trajectory  model_call 4
              tool_call 2                               tool_call 2
              re_executed [False, False]                re_executed [True, False]
  cassette    4 entries                     cassette    4 entries
              {model_call: 3, tool_call: 1}             {model_call: 4, tool_call: 0}
  tokens      23 unc / 1760 read / 51 out   tokens      27 unc / 1760 read / 16 write / 54 out
  replay      4 hits, 0 misses              replay      4 hits, 0 misses
```

Both replay clean. The differences are the whole decision:

- **The stored tool's result is a cassette entry; the handle-taking tool's is not.** The
  handle version stores zero `tool_call` entries, because the tool is re-executed and only its
  nested model call is served.
- **The handle version's nested call is in the trajectory, the tokens and the budget.** The
  stored version's would be in none of them: the four extra tokens and the fourth `model_call`
  record appear only on the right.
- **On replay, the stored tool's body does not run.** An embedding inside it would not be made.
  The handle version's body runs again, over whatever state it reads, with its model call served.

`Memory` is already in
[`RE_EXECUTED_HANDLE_TYPES`](../../src/simple_agents/tools.py#L668) alongside `ModelHandle` and
`Workspace`, so `memory_search` is re-executed today and `document_search` is stored.
`memory-build-log.md` §2.9 is the record of why that matters and of a scoping fix that was
approved and then found to break the documented workflow for `spends_money` tools.

### 1.11 A single cost basis prices an embedding at chat rates

[`cost.py` `basis_for`](../../src/simple_agents/cost.py#L335): one basis prices every call, and
a `by_model` mapping prices the models it names and nothing else, returning an unpriced `Cost`
with a reason for one it does not name. So if an embedding becomes a `model_call` record:

- under a single `PriceBasis`, its tokens are priced at the chat model's rate. An embedding
  model is one to two orders of magnitude cheaper per token, so the run's cost is overstated
  with nothing saying so.
- under a `by_model` basis, it needs its own entry or every embedding call is unpriced, and
  `total_cost` makes the whole run's total unknown.

This is the same shape as the per-node model item's finding, which is why `cost_basis` takes one
basis per model at all (`per-node-model-build-log.md`).

### 1.12 The wider measurement, on real judgments, and it reverses §1.7's recommendation

Run after Thilina rejected §1.7 as a basis for a shipped ranking rule. Three corpora, two
embedding models, a cross-encoder reranker, `recall@5` and `MRR@10` over 200 queries each:

- **MS MARCO passage** (`Tevatron/msmarco-passage-aug`, from the hub cache): 200 real queries
  with real relevance judgments, 2,597 passages, twelve of each query's hard negatives pooled in.
- **Natural Questions open** (`florin-hf/nq_open_gold`): 200 real questions, 1,184 gold
  passages, the other queries' golds as distractors. Distractors are random rather than hard.
- **The §1.7 depot corpus**: 600 documents, 25 identifier queries and 5 paraphrase queries. No
  public benchmark covers near-identical identifiers, and a builder's corpus can.

**Every model here was trained on MS MARCO**, including the reranker, so that column is
in-domain and flatters all three. NQ is the closer thing to a held-out reading.

```
                     MS MARCO 768      MS MARCO 384      NQ 768            NQ 384
                     R@5     MRR       R@5     MRR       R@5     MRR       R@5     MRR
BM25 only            0.785   0.615     0.785   0.615     0.815   0.735     0.815   0.735
dense only           0.840   0.674     0.955   0.794     0.875   0.803     0.900   0.825
RRF k=60             0.865   0.685     0.910   0.730     0.925   0.845     0.910   0.823
RRF k=5              0.875   0.695     0.930   0.743     0.920   0.850     0.920   0.837
interleave           0.845   0.641     0.925   0.677     0.925   0.778     0.915   0.775
BM25 + rerank20      0.915   0.770     0.915   0.770     0.915   0.863     0.915   0.863
dense + rerank20     0.925   0.767     0.950   0.780     0.920   0.868     0.925   0.880
RRF60 + rerank20     0.935   0.777     0.945   0.782     0.950   0.890     0.935   0.887
interleave+rerank20  0.940   0.779     0.945   0.782     0.940   0.885     0.945   0.887
```

```
depot corpus            identifier R@5  MRR       paraphrase R@5  MRR
                        768     384     768/384   768     384     768     384
BM25 only               1.000   1.000   1.000     0.200   0.200   0.200   0.200
dense only              0.640   0.720   .491/.594 0.600   0.400   0.625   0.400
RRF k=60                0.760   1.000   .708/.933 0.600   0.600   0.525   0.500
RRF k=5                 1.000   1.000   .893/.980 0.600   0.600   0.525   0.500
interleave              1.000   1.000   1.000     0.600   0.600   0.525   0.500
RRF60 + rerank20        1.000   1.000   1.000     0.800   0.600   0.800   0.600
interleave + rerank20   1.000   1.000   1.000     0.800   0.600   0.800   0.600
```

**Four things this says, and the first contradicts §1.7.**

1. **Interleaving is not better. It is the worst hybrid on `MRR` in all four real-data runs**
   (0.641, 0.677, 0.778, 0.775, against RRF's 0.685 to 0.850). It puts the weaker retriever's
   best guess at rank 2 by construction, which lifts `recall@5` and depresses the rank of the
   answer. §1.7 measured `recall@3` on a corpus where that trade happened to pay, and read a
   ranking off it. **Reciprocal rank fusion at the published k=60 is a reasonable default after
   all**, and its one failure is the near-identical-identifier corpus with the weaker embedding
   model (0.760).
2. **k=5 is better than or equal to k=60 in all six runs**, and much better on the identifier
   corpus (0.893 against 0.708 `MRR`). §1.7's diagnosis of why was right even though its
   recommendation was not: a smaller k restores the margin the rank discount flattens. Two
   retrieval systems over short lists is not what k=60 was published for.
3. **Hybrid is not always better than its parts.** With the stronger embedding model on MS
   MARCO, dense alone beats every fusion (0.955 against 0.910 to 0.930). A rule that always
   fuses is wrong in that case, which is the argument for making it a builder's choice rather
   than a library constant.
4. **Reranking is the largest single lever, and it flattens the choice of fusion.** It adds
   0.05 to 0.13 `recall@5` and up to 0.19 `MRR`, and after it every fusion lands within 0.01 of
   every other. A builder who reranks does not need to care which fusion is underneath.

Reranking latency, against the local cross-encoder:

```
rerank top-5     3.9 ms      200 tokens
rerank top-10    4.9 ms      400 tokens
rerank top-20    7.4 ms      800 tokens
rerank top-50   13.0 ms    2,000 tokens
```

**What is still not established.** Two embedding models, one reranker, three corpora, all
English, and every neural model trained on one of the three. This is enough to choose a default
and to say what the default is chosen on. It is not enough to tell a builder their corpus will
behave this way, and the documentation says so rather than reprinting the table as guidance.

---

## 2. The design

Put to Thilina 2026-08-11 as six decisions. D1, D4, D5 and D6 approved as put; D2 and D3 sent
back, re-put with §1.12 behind them, and approved 2026-08-11. Two further questions settled at
the same sitting, D7 and D8.

### 2.0 What the first pass got wrong

Two of the six went back, and the reasons are the same reason.

- **D2 read a ranking rule off one contrived corpus.** "Did you just try to solve Information
  Retrieval in one contrived test?" §1.12 is the answer: on real judgments the recommendation
  inverts, and the method §1.7 recommended is the worst of the hybrids on `MRR`. What ships is a
  default with the evidence for it stated, and every part of it settable.
- **D3 let this machine's constraints set the library's ceiling.** It measured a pure-Python
  scan, found 64 ms at 10,000 documents, and wrote a ceiling into the design. The scan is the
  right thing to ship as a default because it needs no dependency; it is not a reason to hold a
  project to it.

**A third correction, made at the D7 sitting.** The argument for shipping a local embedding
model leaned on self-hosted builders finding a second vLLM server hard to stand up. Thilina:
"They'll have a coding agent. Getting a second vllm server up is one message." The decision
does not rest on that and the documentation does not mention it. What it rests on is a builder
with no endpoint at all.

### 2.1 A mode on `DocumentIndex`, not a second index (D1)

`DocumentIndex.from_texts(texts, embeddings=client)` searches hybrid; without `embeddings=` it
is what it is today. No `semantic_search` tool, and `document_search` keeps its name and its
place in the model's tool list.

**Why not a second tool.** Two search tools over one corpus is a routing decision, and routing
is the recurring failure mode across all three dogfoods (`handoff.md`). It also keeps
`_tool_factories()` at thirteen, so `docs/procedure.md`, its word budget, the six tests in
`tests/test_procedure.py` and `handoff.md` do not move.

**What it costs.** `DocumentIndex` is two things under one name, and `Hit.score` stops meaning
one thing. `Hit` gains `retriever` and `rank`, and the docstring states that two retrievers'
scores are not comparable.

### 2.2 Everything about ranking is settable, and the defaults are stated as defaults (D2)

```python
index = DocumentIndex.from_texts(
    corpus,
    embeddings=embedder,
    ranking=Hybrid(fuse=RRF(k=5), depth=50),      # the default when embeddings= is given
    rerank=CrossEncoderRerank(client, top_n=20),  # default None
    vectors=None,                                 # default: the scan in 2.3
)
```

- `ranking=` takes `Lexical()`, `Semantic()` or `Hybrid(fuse=...)`. `Lexical()` is the default
  when no `embeddings=` is given, and is exactly today's behaviour.
- `fuse=` takes `RRF(k=...)`, `Interleave()` or `WeightedScore(lexical=...)`.
- `rerank=` takes `CrossEncoderRerank(...)` or `ModelRerank(...)`, which reranks through the
  chat model over the seam 2.4 builds. Both are model calls and fall under 2.5's identity rule.

**`RRF(k=5)` is the default rather than the published `k=60`**, on §1.12: k=5 is better than or
equal to k=60 in all six runs and much better on a corpus of near-identical identifiers, which
is a shape builders have and no public benchmark covers. The documentation says the default was
chosen on three corpora and two embedding models, and does not reprint the table as advice.

### 2.3 A scan by default, a `VectorStore` protocol underneath (D3)

The default holds vectors in memory and scans them exactly: no dependency, no recall parameter
to get wrong, and §1.6's numbers are what it costs. A project past that points `vectors=` at its
own store, which is one protocol rather than a new index or a new tool.

### 2.4 A new protocol, and the query embedding is a recorded `model_call` (D4)

`ModelClient` cannot carry an embedding (§1.9), so `EmbeddingClient` is a second protocol with
`embed` and `identity`. The corpus embed happens when the index is built, outside the run, and
`save`/`load` means once ever. The query embed is one recorded `model_call` per search, through
an `Embedder` handle filled from the envelope, which puts `document_search` in
`RE_EXECUTED_HANDLE_TYPES`.

**What it costs**, measured in §1.10: `document_search`'s result stops being a cassette entry,
so turning semantic search on invalidates an existing recording. Re-recording is free at this
stage.

### 2.5 A mismatch is a refusal, and FT-14 is extended to see it (D5)

The index records the identity that embedded it and refuses at load and pre-flight against a
different one. The manifest records every embedding and reranking identity, and
`_serving_models` reads them, because §1.8 measured that an unpinned embedding model passes
FT-14 today. `MemoryEntry` gains a vector and the identity that made it, written at `remember`
time, so `memory_search` embeds only the query rather than §1.5's 586 ms and 182,000 tokens.

### 2.6 No thirty-first elicitation question (D6)

`backend` already asks which model this runs against, at what price, and who approves a change.
Its scaffold is amended to name the embedding model; the set stays at 30.

### 2.7 A local model ships, behind an optional extra (D7)

`pip install simple-agents[semantic]` pulls `sentence-transformers`, and
`SentenceTransformerEmbeddings()` needs no endpoint and no key. Alongside it and with no
dependency: `MistralEmbeddings()`, and an OpenAI-compatible client covering vLLM and the rest.

**Why the extra rather than adapters alone.** A builder who has configured a chat provider
usually has embeddings from the same endpoint and key, and for them the adapters are enough. A
builder who has neither gets nothing from the adapters, and semantic recall that requires an
endpoint before it does anything is not something that runs off the shelf. The cost is an
optional dependency with torch underneath, and a second code path.

### 2.8 The default reranker is a local cross-encoder (D8)

`CrossEncoderRerank` over `cross-encoder/ms-marco-MiniLM-L-6-v2`, under the same `[semantic]`
extra. §1.12 measured it as the largest single lever, and §1.4 measured it at 7.4 ms for twenty
candidates. `ModelRerank` through the builder's existing chat model ships beside it and needs no
dependency, and its quality is not yet measured.

---

## 3. The build

### 3.1 The lexical tool's version had to be held still, and Mistral is why

2.4 says turning semantic search on invalidates a project's recording, and that is accepted.
What was not intended is that it invalidated **every** recording, including the ones for a
purely lexical index.

The first build restructured `document_search` into one closure covering all four cases.
[`derived_version`](../../src/simple_agents/tools.py#L1050) hashes a tool's source, and the source
of a nested function includes the indentation it is written at, so moving the lexical body
inside an `if` changed its hash and every recorded `document_search` call missed:

```
tool_version (recorded 'sha256:fcb0c61405e7', now 'sha256:d131da53692c')
20 errors, 4 failed
```

**Re-recording was not available.** `tests/cassettes/tools.jsonl` and `suspend.jsonl` are
`mistral-small-2603`, and Mistral is out of credits, so the two files could not be regenerated
at any price.

That forced the question rather than settling it, and the answer holds on its own: **the lexical
path's behaviour did not change, so its version should not.** Two things were done.

- `Hit.to_record()` gained `attributed=`, and `retriever` and `rank` appear only where more than
  one retriever produced the results. A lexical index returns the three fields it always
  returned. A field carrying one value on every row tells a reader nothing and costs the model
  context on every call, so this is the better shape independently.
- The variant that makes model calls moved into `_searching_with_a_model`, leaving the lexical
  closure byte-identical to what shipped.

**1635 tests pass with no cassette re-recorded.**

**The trap this leaves.** A future edit that reindents that closure moves the version again,
silently, and invalidates every project's recording. `derived_version`'s docstring already
records the same weakness in the other direction, that data closed over does not change the
version. `tests/test_semantic_search.py` pins the hash so the next reindentation fails a test
rather than a builder's replay.

### 3.2 What `k` actually does, which is not what §1.7 said

Writing `RRF`'s docstring meant stating the mechanism rather than gesturing at it, and the
statement did not survive being run. §1.7 said a small `k` "sharpens the discount" enough to
recover a decisive lexical match that ties with noise. Neither half holds.

The real arithmetic, on `AX-7717-B` against the §1.7 corpus at depth 50:

```
gold part17: lexical rank 0, semantic rank None (past the depth)
  k=1   [('part17', 0.5),     ('part45', 0.5),     ('part1', 0.33333)]
  k=5   [('part17', 0.16667), ('part45', 0.16667), ('part1', 0.14286)]
  k=60  [('part105', 0.02729), ('part129', 0.02633), ('part117', 0.02608)]
```

**A document in one list gets one vote and a document in both gets two.** At k=60 the discount
is nearly flat across fifty ranks, so `part105`, mid-list in both, scores 0.0273 against the
gold document's single 1/61 = 0.0164. At k=5 one first place is worth 1/6, which two mid-list
votes cannot reach. It is a contest between one large vote and two small ones, and `k` sets the
exchange rate. Nothing is being sharpened, and nothing ties with noise: `part17` and `part45`
tie with each other, at exactly `1/(k+1)`, because each is first in one list and absent from the
other.

**Which means one of the three part-number wins at k=5 was a tie-break, not a scoring win.**
Across the five identifier queries, at rank 1:

```
query           gold      lex   sem    k=5 top1      tie?   k=60 top1
AX-7717-B       part17    0     None   part17        TIE    part105
AX-7788-A       part88    0     None   part30        TIE    part126
AX-7843-B       part143   0     None   part129       -      part129
order 80035     order5    0     0      order5        -      order5
order 80840     order120  0     2      order120      -      order120
```

`part17` came first because `part17` sorts before `part45`. The library breaks ties by
identifier so that a result is reproducible, and on a corpus of near-identical documents that
tie-break is what settles the order. Both facts are now in `RRF`'s docstring, and
`tests/test_semantic_search.py` holds a case for each.

**This does not move the default.** §1.12's recall@5 and MRR@10 over 200 real MS MARCO and
Natural Questions queries is what k=5 rests on, and there it matched or beat k=60 in all six
runs on judgments no tie-break touches. What changes is the explanation, and the identifier
corpus is now a supporting case with a caveat rather than a clean win.

### 3.3 What shipped

| | |
|---|---|
| Seams | `EmbeddingClient` and `RerankClient` in `embeddings.py`, each two methods |
| Handle | `Retrieval`, a fifth handle type, in `RE_EXECUTED_HANDLE_TYPES` |
| Ranking | `Lexical`, `Semantic`, `Hybrid`; `RRF`, `Interleave`, `WeightedScore`; `VectorStore` and `VectorScan` |
| Reranking | `CrossEncoderRerank` and `ModelRerank`, over the `Reranker` surface |
| Adapters | `OpenAIEmbeddings`, `MistralEmbeddings`, `OpenAIReranker`; `SentenceTransformerEmbeddings` and `LocalCrossEncoder` under the `semantic` extra |
| Index | `DocumentIndex(embeddings=, ranking=, rerank=, vectors=)`, with `save` and `load` |
| Memory | `MemoryEntry.vector` and `.embedded_by`; `memory_search(embeddings=)` |
| Cassette | `embedding` and `rerank` entry kinds, with keys and codecs |
| Conformance | `_serving_models` reads `models.observed`, so FT-14 sees a model on no node |
| Tools | still thirteen: `document_search` gained a mode rather than a sibling |

### 3.4 Live, against three models on one card

```
chat      8002  cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit   --gpu-memory-utilization 0.84
embedding 8001  sentence-transformers/msmarco-bert-co-condensor            --runner pooling
rerank    8004  cross-encoder/ms-marco-MiniLM-L-6-v2                       --runner pooling
                                                              23,533 MiB of 24,576 in use
```

**1. A hybrid search records and replays.**

```
live     records      {model_call: 4, tool_call: 2, node_execution: 1}
         by kind      {chat: 3, embedding: 1}
         tokens       41 uncached / 1,744 cache read / 1,008 cache write / 95 output
         observed     [(Qwen3-30B, 3), (msmarco-bert-co-condensor, 1)]
cassette 4 entries    {model_call: 3, embedding: 1}
replay   4 hits, 0 misses, 0 diverged; identical tokens; same answer
```

**2. The embedding call in the trajectory**, which is §1.9's question answered in a file:

```
call_kind      embedding
request_model  sentence-transformers/msmarco-bert-co-condensor
parent_id      rec_35c01ed36558          (a tool_call: True)
inputs         {'texts': ['how long can a pallet sit before it is moved']}
outputs        {'dimensions': 768, 'vectors': 1}
tokens         {'input_uncached': 13, ..., 'output': 0}
cassette_key   ck_cdce1de8f60daf2f
```

The vector is not in the record. 768 floats is 17 kB of JSON per search, and the dimension and
the count are what a reader of the trajectory uses.

**3. FT-14 over the run**, which is §1.8's gap closed:

```
both pinned        PASSED  "2 models served this run, each pinned: cpatonn/Qwen3-30B... on
                            <lambda>; sentence-transformers/msmarco-bert-co-condensor on
                            calls it served."
embedding floats   FAILED  1 finding, naming the embedding model
```

**4. The cost basis**, which is §1.11 confirmed on a real trajectory:

```
one PriceBasis for the run       embedding 0.00000390     total 0.00025206
by_model, both named             embedding 0.00000013     total 0.00024829
by_model, embedding unnamed      embedding None           total None
```

**A single basis prices the embedding at chat rates and overstates it 30x.** Naming both is
right; naming only the chat model leaves the call unpriced and the run's total unknown, with
the reason on the record. Both are the behaviour the per-node model item built, reached by a
second kind of call rather than a second node.

**5. Semantic memory finds what lexical returns nothing for.** Three facts stored, none sharing
a word with the query:

```
query 'length preference'
  lexical   NOTHING
  semantic  [('diet', 'semantic'), ('reading_habit', 'semantic')]
vector written back: 768 dimensions, by msmarco-bert-co-condensor
second search embedded 1 text (the query alone)
```

**This is the item's reason for existing, and the result is also honest about the model.**
`reading_habit` is "puts down anything over 300 pages unfinished" and is found. It is ranked
second, behind `diet`, which is "no dairy" and has nothing to do with the question. On three
entries with a 2021 MS MARCO bi-encoder that is what the scores say. The wording gap is closed;
the ranking is the builder's to measure on their own store.

**6. Reranking changes the answer, and not always for the better.**

```
'when is it too late to deliver'   hybrid  [policy-2, policy-1, part-1]
                                  +rerank  [policy-2, policy-3, policy-1]
'AX-7719-B'                        hybrid  [part-1, part-3, part-2]
                                  +rerank  [part-1, part-3, part-2]
'what happens to an old pallet'    hybrid  [policy-1, policy-2, policy-4]
                                  +rerank  [safety-1, part-2, policy-1]
```

The third row moves the right answer from first to third. §1.12 measured reranking as the
largest gain over 400 real queries and this is eight documents, so the disagreement is what a
sample of one corpus looks like rather than a contradiction. It is why `rerank` is off by
default and why the documentation tells a builder to measure it against no reranking at all.

**7. Save, load and the refusal.** 33,857 bytes for eight documents at 768 dimensions; loading
re-reads the vectors and embeds nothing; loading under a second embedding model is refused
naming both.

### 3.5 What Mistral's absence leaves unverified

`MistralEmbeddings` is written and not run: the key is out of credits, so no hosted embedding
call was made. Nothing in the path branches on backend, and `OpenAIEmbeddings` against vLLM
exercised the same code with `backend="self_hosted"`, but a `hosted_api` embedding under a
`PriceBasis` with real per-token rates has not been made end to end.
