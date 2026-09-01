# Absorption item 2 — `value_or` and the `DocumentIndex` options — build log

**Kept while building.** Design of record: `archive/dogfood-absorption.md` §2, approved 2026-08-09.

**Status: sitting held 2026-08-09, built. Baseline 1238 tests at item 1.**

---

## 1. What was measured, before any design

### 1.1 The unwrap: 11 sites want a test, 2 want a fallback, and neither wants `value_or`

Every `Maybe` consumer across the three dogfood projects:

| Shape | Sites |
|---|---|
| `isinstance(x, Unknown)`, no default wanted, mostly routes and guards | 11 |
| A helper returning a fallback | 2, both dogfood-2 |

The two helpers are `_text(value, fallback="") -> str` (`agent.py:116`) and
`_number(value) -> float | None` (`fitfinder/matching.py:126`). **Both do two things
`value_or` does not**: they coerce the type, and they fold `None` in with `Unknown`.

The spec's claim that "every consumer writes the same two functions" is therefore not what the
code shows. What recurs is the `isinstance` test, which already ships.

### 1.2 Stopwords and titles do not improve retrieval on the corpus that motivated them

dogfood-1's corpus and eval set, 60 documents in 5 topics, 59 questions each with a gold
document. Probe under the session scratchpad:

| Index | recall@5 | top-1 |
|---|---|---|
| body only, query as asked (what ships today) | **58/59** | 53/59 |
| body only, stopwords removed from the query | 57/59 | **54/59** |
| title indexed with the body | 57/59 | 53/59 |
| both | 57/59 | **54/59** |

Stopword removal reshuffles the top-5 on 57 of 59 questions and moves the score by one question
in each direction. Title indexing changes 12 of 59 lists.

### 1.3 The mechanism a stopword list exists for is real even where the effect is not

BM25's IDF discounts a term only when it is in most documents. On this corpus:

| term | documents | IDF |
|---|---|---|
| `the` | 60/60 | 0.008 |
| `is` | 31/60 | 0.661 |
| `what` | 5/60 | 2.406 |
| `how` | 3/60 | **2.858** |
| `turbine` | 3/60 | 2.858 |

A question word that happens to be rare scores exactly as hard as the topic term. IDF is not a
stopword list, and a corpus rarer in question words than this one has no lever today.

### 1.4 Half the feature-loss claim is wrong

The spec says run 2 silently lost both features when it adopted the builtin. Run 2's corpus
builder **drops titles at build time**: `corpus/passages.jsonl` carries `doc_id` and `text` and
nothing else, and the topic is encoded into the identifier (`Oxygen#0`), which the index does
not match on. Only run 1 ever had a title field.

---

## 2. The sitting, 2026-08-09

Presented with §1. Thilina took all three recommendations, and added an instruction about how
the shipped documentation is to be written: **factual, concise, saying what the library does.
No defending, no arguing, no reference to what was measured or to the dogfoods.** The docs are
for the builder and the coding agent. That instruction governs every doc edit from here.

1. **`value_or` ships, `Unknown` only.** Folding `None` in would contradict the rule the
   false-confidence split rests on, which `schema.py` and `docs/trajectory-format.md` §5.1 both
   state: `null`, `""` and a missing field never mean `unknown`.
2. **`stopwords=` ships**, no list, query side only, with the fallback for a query made
   entirely of them.
3. **Title indexing does not ship.** The composition is one f-string and it is documented.
   Revisit if a second project holds titles and wants them separate from the body.

---

## 3. Where building sharpened a decision

### 3.1 `documents_containing` had to move with `search`

The tool returns both, and they read one query. Leaving the counts over every token while
search ran on the filtered list would report a count for a word that decided nothing. Both now
go through `query_terms`, which is public for the same reason `tokens` is: a project computing
anything that has to line up with search results needs the same rule rather than its own.

### 3.2 A stopword list is normalised through the tokeniser

`stopwords={"What", "THE"}` would otherwise be a silent no-op, since the index matches
lowercased tokens. `__post_init__` runs each entry through `tokens()`, so declared case and
punctuation stop mattering. Pinned by a test.

### 3.3 The empty-query fallback is in `query_terms`, not in `search`

Both callers need it, and a query of nothing but stopwords should report counts for the words
it was actually searched on rather than an empty mapping.

## 4. Doc consequences

| Document | What changed |
|---|---|
| `docs/pipeline.md` §4 | `value_or` beside the `isinstance` test |
| `docs/tools.md` §4.1, new | The document index: building it, indexing a title, and `stopwords` |
| `docs/tools.md` §4 table | The `document_search` row points at §4.1 |
| `CHANGELOG.md` | Two `Added` entries |

`consult` and `extract_to_schema` moved from §4.1 and §4.2 to §4.2 and §4.3. No document, test
or docstring cited either number.

## 5. Tests

Nine added, all in existing files: seven in `test_builtin_tools.py::TestStopwords`, including
the documented title composition, and two beside the existing `Unknown` behaviour tests in
`test_loop_and_budgets.py`. **1247 pass**, from 1238.
