# The meta-eval of the documentation

`plan.md` §1 P3-4's record. **Nothing is built.** Waits on dogfood #4's findings being worked
through, P3-1.

## Where it came from

A phase in `plan.md` since the plan was written, moved here on 2026-08-15 (`archive/plan-history.md`
§5). It is not a
dogfood finding; it falls out of the design.

## What the problem is

If the docs are the product, the docs need evaluating, and nothing measures them. Every claim
about whether the procedure works rests on four dogfood runs the same person set up.

## What has to be decided

**The protocol**, which is settled in outline and not in detail.

Run N coding agents against M task descriptions, given the library and its docs. Measure how often
they produce a working, correctly-evaluated, conformance-passing agent. Read the failures to find
where the docs were misread.

`runs/dogfood-protocol.md` is the single-run protocol this reuses, and its §2 note that the build
log carries no Simple Agents vocabulary exists for this item: the unguided arm has to be able to
produce the same log, and a log naming stages and gates cannot serve both arms.

### Why it is worth building

- It is adversarial testing of a prompt surface, closer to Thilina's red-teaming work than to
  library maintenance, and the technique transfers directly.
- It is the best marketing artifact available: agents following this procedure produce correct
  evaluation code X% of the time against Y% unguided.
- It is the eval-first philosophy applied to ourselves, which is the credibility test people will
  apply anyway.
- It answers `simple-agents.md` §11's open question 5, whether the procedure transfers across
  models and generations.

## What it waits on

P3-1. A meta-eval measures the procedure as it stands, so running it while dogfood #4's findings
are still changing that procedure measures something that no longer exists.
