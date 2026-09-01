# A per-edge value

`plan.md` §1 P3-68's record, scheduled 2026-09-01 out of §2.2 on Thilina's call at the release sitting, behind `P3-31`. **Nothing is built.**

## Where it came from

Named 2026-08-09 at the DF2-D1 sitting; deferred the same day. The deferred entry, moved here verbatim:

**A per-edge value: a node saying what each out-edge carries.** *Deferred 2026-08-09.* Named 2026-08-09 at the DF2-D1 sitting, so the entry above closing does not take this with it. Today one output resolves every out-edge with the same object, so a node cannot send a small value one way and a large one another, and forking one field past a narrowing carries everything produced beside it. **Measured**: carrying dogfood #2's 2,762-byte `unreadable` from `fetch_pages` to `match_direct` means forking that node's whole 146,305-byte output, which is a third copy of pages the trajectory already holds twice. **What it would cost:** `ValueCodec` rebuilds a value in flight from the schema its node declared and a projection has none, so a suspend across a projected edge needs a schema per edge or a refusal; FT-28 would compare the projection rather than `output_schema`; the manifest's `successors` and `to_mermaid()` both have to show it. **What decides whether it is worth owning:** whether a node already gets the saving. A project can put a `Deterministic` node on the edge today and have it return the small value, which is one node and no format change. What that costs is the node's own record: it receives the full value, so the trajectory holds a copy for it too. Whether that is cheaper than the fork is arithmetic over the numbers this entry already carries, taken against dogfood #2's run, and it decides the entry. If a narrowing node comes out level or cheaper, the per-edge feature buys syntax and is declined. If the extra record costs more than the fork it removes, the saving is real and the cost above is what it is weighed against.

## What the problem is

The entry above carries it, with the measurements.

## What has to be decided

The arithmetic the entry itself names: the narrowing `Deterministic`'s extra record against the fork it removes, on dogfood #2's numbers. Level or cheaper declines the feature; costlier is the saving the design is weighed against.

## What it waits on

`P3-31`, the release.
