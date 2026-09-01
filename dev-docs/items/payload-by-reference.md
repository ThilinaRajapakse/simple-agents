# A payload stored by reference

`plan.md` §1 P3-70's record, scheduled 2026-09-01 out of §2.2 on Thilina's call at the release sitting, behind `P3-31`. **Nothing is built.**

## Where it came from

Named 2026-08-06 at item 8b, which measured it and decided against building it then. The deferred entry, moved here verbatim:

**A payload stored by reference rather than rendered in full.** *Deferred 2026-08-06.* Named 2026-08-06 at item 8b, which measured it rather than reasoning about it, and decided against building it in that item. **The measurement.** On a two-turn production run of 160,837 bytes, `tool_call.outputs` was 73,294 bytes and the same three search results re-written inside `model_call.inputs.messages` was 73,691, so **91.4% of the file was one set of results written repeatedly**. A retrieved passage is recorded once where the tool returned it and again in every subsequent model call that still carries it in the conversation, which makes the growth quadratic in turns: over the seven calls of a six-turn run, cumulative `inputs` was 271,660 bytes and each turn added about 12,800. **This is a floor sampling does not reach**, because it is duplication inside a single run that was kept, and item 8b's rate governs whether a run is kept rather than what one holds. **What item 8b settled instead:** the full render stays for v0, and the question is no longer waiting on dogfood #1 for a size. **What makes it cheaper than it looks:** nothing in the library reads `model_call.inputs` or `tool_call.outputs` back, so the readers a reference would have to satisfy are a builder debugging a run and later training data, not library code. `not_recorded` and `omissions` already give a payload field a way to say it holds something other than the value, so a reference is a third state in a place that now has two. **What decides whether it is worth owning:** the share of the duplication that is the same bytes. A reference asserts that the message carried into a later model call is the tool result already recorded, and context management is what makes that false: `DropOldestTurns` and any reducer over a tool result rewrite what is sent, so a reference over a transformed message records a claim the file cannot support. The library can tell the two apart by comparing, which makes the design mechanical: a reference where the bytes match a payload already written in this run, the full render where they do not. Every record carries a `sequence`, so the addressing is done. Measuring that share on the trajectories already on disk says whether the 91.4% above is reachable or whether most copies were transformed on their way into the conversation, and it needs no project. *Exercised for the first time on 2026-08-08 by dogfood #2, and not resolved.* Its payloads are reduced retail pages of up to 24,000 characters, carried in `tool_call.outputs` and again in every later `model_call` in the same chase; the first live run spent 157,760 uncached input tokens on one chase for that reason. The project's answer was `DropOldestTurns(keep_turns=4)`, which shrinks what is **sent** and not what is **recorded**, so the growth this entry describes is untouched by it.

## What the problem is

The entry above carries it, with the measurements.

## What has to be decided

The share of the duplication that is the same bytes, measured on trajectories already on disk. The entry carries the design that follows either answer.

## What it waits on

`P3-31`, the release.
