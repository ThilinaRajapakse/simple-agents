# Public APIs the docs do not show

`plan.md` §1 P3-67's record, archived 2026-09-01 when the item was built.
[`build-logs/the-undocumented-apis-build-log.md`](../build-logs/the-undocumented-apis-build-log.md#L1)
is the record of the build; this file keeps the audit's finding 5 verbatim.

## Where it came from

Thilina's 2026-08-29 audit of the docs, finding 5, verbatim except paths rewritten to
repo-relative links:

> Medium — several public APIs are not actionable from the docs.
>
> - Exported [`OpenAIReranker`](../../src/simple_agents/adapters/embeddings_openai.py#L239) is
>   absent from retrieval docs, whose reranking section only demonstrates `LocalCrossEncoder`
>   and `ModelRerank` at [`docs/retrieval.md`](../../docs/retrieval.md#L211).
>   `FakeEmbeddingClient` and `FakeRerankClient` are also undocumented.
> - The README says old runs can be repriced at [`README.md`](../../README.md#L89), but no
>   documentation shows the public
>   [`basis_from_manifest`](../../src/simple_agents/cost.py#L366),
>   [`cost_of`](../../src/simple_agents/cost.py#L466), or
>   [`total_cost`](../../src/simple_agents/cost.py#L521) APIs.
> - `Pipeline.answer_shelved` returns an
>   [`AnsweredQuestion`](../../src/simple_agents/pipeline/answering.py#L48) containing the new
>   run ID and result, but [`docs/product.md`](../../docs/product.md#L1) discards and never
>   describes the return value.

The audit's finding 7 named two stale statements, and both were corrected on 2026-09-01 under
the corrections-are-never-queued rule: the elicitation scaffold's tool count (thirteen to
fourteen, now pinned by a test in `tests/test_procedure.py` reading the count off the built-in
set) and `docs/run-envelope.md`'s field table ("into two" to "into three" for `liveness`).

## What the problem is

Three public names are exported and promised, and a coding agent reading the docs cannot use
them: `OpenAIReranker` ([`embeddings_openai.py`](../../src/simple_agents/adapters/embeddings_openai.py#L239)),
the repricing functions in [`cost.py`](../../src/simple_agents/cost.py#L366), and
`answer_shelved`'s return value.
[`FakeEmbeddingClient`](../../src/simple_agents/embeddings.py#L219) and
[`FakeRerankClient`](../../src/simple_agents/embeddings.py#L260) are the test doubles a project
writes its offline tests with, and no document names them.

## What has to be decided

Where each lands: the reranker and fakes in `docs/retrieval.md`'s reranking section, repricing
in the document the README's promise points to, `answer_shelved`'s return in
`docs/product.md`. The item is writing, with no design open.

## What it waits on

none
