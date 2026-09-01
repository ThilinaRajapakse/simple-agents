# Rulings, 2026-08-13

Thilina's decisions on `SITTING-BRIEF.md`. These are settled. A stream implementing one of them
follows it rather than re-opening it; anything the ruling does not cover comes back to him rather
than being decided in the stream.

---

## D1. `max_steps` is a guarantee on every path. **Option A.**

Both unbounded paths reserve the step before dispatching, the way
[`calls.py:35`](../../../src/simple_agents/runtime/calls.py#L35) `_call_model` already does:

- branch arms from a route
- embedding and rerank calls inside a search
  ([`handles.py:131`](../../../src/simple_agents/runtime/handles.py#L131), `_call_retrieval_model`)

The reservation is taken under the lock the concurrency item introduced, so two arms starting
together cannot both claim the last remaining step.

**Accepted cost, stated in the brief and agreed:** a branching pipeline under a tight `max_steps`
now stops partway through its arms rather than completing them. Existing tests that rely on arms
completing are expected to change.

The four statements that say the axis is exact stay as they are, and become true.

## D2. Two identities, split by question. **Option C.**

- **`graph_fingerprint` stays a digest of shape**, which is what a resume needs: can this stored
  state still be walked? Budgets stay outside it, as
  [`run-envelope.md:88`](../../../docs/run-envelope.md#L88) already documents.
- **`_eval_id` becomes a digest of everything that decides what was measured**: shape, plus
  sampling parameters, plus tools, plus budget, plus `allow_unknown`.
- [`pipeline.md:297`](../../../docs/pipeline.md#L297) is corrected. It claims a contained pipeline's
  `tools=` and `fetch_policy=` move the fingerprint. They do not, and under this ruling they still
  will not.
- The `compare_variants` refusal names the variant and the sweep rather than only the directory.

### D2 follow-up, also ruled: surface the variant API, do not redesign it

`compare_variants(baseline, variants: Mapping[str, Pipeline], *, envelope, model, split, k, ...)`
already takes named arms, runs them, and reports. The gap is discoverability, with three measured
causes:

1. **The whole evaluation surface is missing from the top-level namespace.** `simple_agents.EvalSuite`,
   `Example`, `ExampleSet`, `compare`, `compare_variants`, `ablate` and `EvalResults` are all
   absent from `__all__` and from the module. Every other major feature is top-level.
2. `compare_variants` appears in one shipped document and the failure taxonomy, and `index.md`
   names it mid-sentence in a row listing eleven other things.
3. It fails on its own leading example, after paying for a baseline arm, with a refusal about
   directories.

**Ruled:** promote the evaluation surface to the top level, give variant comparison its own
`index.md` row, and fix the refusal. Cause 3 is to be confirmed against dogfood #4's findings
record when that is written, rather than asserted now.

## D3. Different answers per failure class. **Option D.**

Three things currently reach `Outcome.FAILED` through one bare `except Exception`
([`runner.py:1323`](../../../src/simple_agents/evaluation/runner.py#L1323), `_rollout`):

- **A suspension propagates.** `RunSuspended` reaches the caller, which is what
  [`evaluation.md:845`](../../../docs/evaluation.md#L845) §7.4 already promises.
- **A configuration error ends the evaluation.** It fails identically on every rollout, so one is
  enough to know, and failing fast saves the other k×n.
- **A transport failure gets its own outcome class**, excluded from the rates' denominators, with
  the count reported beside every rate rather than only in a corner of the results file.

The library decides which exceptions fall in which class. That decision is part of the
implementation and is recorded in the build log.

## D4. Ship a stopword list, and make the ranking explicit. **Option A, plus the follow-up.**

- A default English stopword list ships, and `stopwords=` overrides it.
- **Re-run the evidence in [`semantic-recall-build-log.md`](../../../dev-docs/build-logs/semantic-recall-build-log.md)
  against the six queries in `findings/area-de-retrieval-memory.md` D-2 before finalising**, since
  the two bodies of evidence disagree and one was built to exhibit the effect. If the re-run
  contradicts the six queries, it comes back to Thilina rather than being resolved in the stream.

### D4 follow-up, also ruled: `ranking=` becomes required

Passing `embeddings=` is a capability declaration and currently also picks a ranking silently.
Those are two decisions and one is hidden inside the other.

**Ruled:** `ranking=` is required whenever `embeddings=` is passed, and omitting it is refused. The
precedent is `Budget`, which takes all four axes with no defaults because a silent default on a
spend bound is a decision nobody made. The refusal names the option space at the point of the
decision:

```
DocumentIndex was given embeddings= and no ranking=. An index that can embed can rank three
ways, and which one is right depends on the queries:
    ranking=Lexical()                                  word overlap only
    ranking=Semantic()                                 meaning only
    ranking=Hybrid(fuse=RRF(k=5))                      both, combined by rank position
    ranking=Hybrid(fuse=WeightedScore(lexical=0.3))    both, combined by score
```

## D5. Finish this checkpoint's work, then dogfood #4.

**Carried into the dogfood #4 findings record, and not to be left to memory:** the library moved
under that run. Every issue it hit is checked against what has since been fixed before it is
written up as a finding.
