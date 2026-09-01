# The feature index

`plan.md` §1 P3-66's record, archived 2026-09-01 when the item was built.
[`build-logs/the-feature-index-build-log.md`](../build-logs/the-feature-index-build-log.md#L1)
is the record of the build; this file keeps the origin quotes verbatim.

## Where it came from

A §2.1 entry accepted 2026-08-15, raised by Thilina, promoted 2026-09-01 for the release. The
entry, verbatim:

> **A feature-indexed lookup of the shipped documents, and an index a builder can follow.**
> Accepted 2026-08-15, raised by Thilina, two of his notes taken as one item because they are the
> same surface. `docs/index.md` indexes by document; this indexes by **feature**, so a builder or a
> coding agent finds where a capability is described without knowing which document owns it, and it
> is the first thing to hit when making a design decision. The second half is that the index and
> table of contents a builder follows probably belongs in `README.md`, saying what is in each
> document and what each is for.
> **Waits on:** P3-3, since indexing documents that are still being reviewed means doing it twice.

Thilina's 2026-08-29 audit of the docs, finding 6, confirmed the gap (paths rewritten to
repo-relative links; the wording is his agent's):

> Medium — feature discoverability remains incomplete. This is already acknowledged in
> [`plan.md`](../plan.md#L1). The current index is document-oriented. Its broad rows, and the
> corresponding `README.md` table, do not surface features such as fan-out, concurrency, slicing,
> rerunning, partial cost, ratios, paired figures, baseline, rollout noise, or grouped results.

His instruction for the writing, 2026-09-01: *"Do not get overly verbose when writing this. Keep
it simple, straightforward (no weird language patterns, direct language, no negative chaining, no
X-Y structures, etc. etc.)."*

## What the problem is

[`docs/index.md`](../../docs/index.md#L1) answers "which document do I open", and a reader who
does not know which document owns a capability cannot ask it. The features named in the audit
are each documented in a reference document and findable only from that document's own table of
contents.

## What has to be decided

- The shape: a feature table inside `docs/index.md`, or a separate `docs/features.md` that
  `index.md` fronts.
- The granularity: what counts as one feature row. The audit's list is the seed.
- The `README.md` half: what is in each document and what each is for, for the builder.

## Carries P3-3's remainder

Folded 2026-09-01, on Thilina's ruling that the index precedes the release. Building the index
reads every document, so the six sections P3-3 had left are read at this item's sitting:
`evaluation.md`, `run-envelope.md` and `shipping.md`'s post-review text, and `conformance.md`
§3.7, `run-envelope.md` §8.2 and `pipeline.md` §2.3.
[`items/document-review.md`](document-review.md#L1) is P3-3's record and stays open under this
item until they are read.

## What it waits on

none
