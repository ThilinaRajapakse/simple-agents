# Build log — the undocumented APIs

`plan.md` §1 P3-67. Started and built 2026-09-01, out of the 2026-08-29 audit's finding 5.

## 1. Before any design

Each gap re-verified against the tree rather than taken from the audit:

- `OpenAIReranker` (`adapters/embeddings_openai.py`) exported from `simple_agents.adapters`,
  absent from `docs/retrieval.md` §5, which showed `LocalCrossEncoder` and `ModelRerank` alone.
- `FakeEmbeddingClient` and `FakeRerankClient` (`embeddings.py`) exported from the package
  root, named in no document. `FakeRerankClient`'s own docstring example passed it to
  `from_texts(rerank=)` directly, and that parameter takes a `Reranker`: every test wraps it
  in `CrossEncoderRerank`.
- `basis_from_manifest`, `cost_of` and `total_cost` (`cost.py`) exported from the root; the
  README promises re-pricing and `docs/run-envelope.md` §4 derived cost without showing them.
- `Pipeline.answer_shelved` returns an `AnsweredQuestion`, and `docs/product.md` §4.3
  discarded it. Verified: with `pipeline=` unset a record-only pipeline still runs, so
  `result` is always a real `RunResult`.

## 2. Design

Where each lands, as scheduled: the reranker and the fakes in `docs/retrieval.md` (§5 and §8),
re-pricing as a new `docs/run-envelope.md` §4.5, `answer_shelved`'s return in
`docs/product.md` §4.3. Writing only; the feature index already names each area.

## 3. Build

The four additions above, the `FakeRerankClient` docstring corrected to wrap in
`CrossEncoderRerank`, and `tests/test_repricing_example.py`, which extracts §4.5's fenced
block and runs it unmodified against the `branching` fixture's recorded runs. 4,115 tests.

## 4. Verification

No behaviour changed, so no live run was owed; the verification was executing the new
examples. Running §4.5's block against a recorded Gemini fixture run failed its first two
drafts: a fresh two-rate `PriceBasis` returned unknown, then a five-rate one still did,
because a Gemini call's cache-write count is recorded unknown and an unmeasured count under a
nonzero rate has no price. The recorded basis prices it by declaring cache-write `0.0`, the
backend billing storage separately. The example now starts from the recorded basis and
`replace`s the rates that moved, states the rule, and stays executed by the new test.
`prose_check` had passed both broken drafts, which is the gap it documents.

## 5. Doc consequences

`docs/retrieval.md` §5 and §8, `docs/run-envelope.md` §4.5, `docs/product.md` §4.3, and the
`FakeRerankClient` docstring. Nothing for `CHANGELOG.md`: no format moved and no behaviour
changed. Wheel rebuilt, so the installed docs carry the additions.

## 6. Left open

Nothing.
