# A declared schedule

`plan.md` §1 P3-77's record. **Nothing is built.**

## Where it came from

`plan.md` §2.2's entry, deferred 2026-08-20 and moved here at dogfood #6's sitting of 2026-09-02
once its decider was met. The entry, verbatim:

> **A library-owned scheduler.** *Deferred 2026-08-20.* Raised by Thilina in the inbox on
> 2026-08-18 (*"scheduling in the sense of refreshing data, like pulling from an API on a
> schedule, or watching something"*) and kept live on his call at dogfood #4's sitting 7, where
> `P3-30` took the trigger question and the documented pattern and deliberately not the
> mechanism. **What exists:** nothing in the library runs outside a call the caller made
> (`simple-agents.md` §2.1's containment), so the documented pattern is a script the host's
> scheduler calls, and the supervisor entry in this section is the adjacent shape for resuming
> suspended runs. **What it would be:** the library owning "run this pipeline on a schedule, or
> when something changes", which is execution outside a caller's call and defeats §2.1's
> amendment in writing if built. **What decides whether it is worth owning:** a product whose
> triggers the host's scheduler cannot express well, such as watching for change or
> resume-when-answered at scale, met in a real project; dogfood #5's product is the first place
> one can turn up.

Thilina at the sitting, on what the project had to write: it was not a lot of code, but it is
something the project needs to handle and the builder needs to decide or think of.

## What the problem is

Lost-the-plot's `api/scheduler.py`, 99 lines, holds what every product with a background run
will write again: a loop that ticks; a `schedule` table of last-run times so a restart neither
repeats nor skips a pass; a rule per job (every ten minutes, daily, weekly); a check of the
product's own state (the queue below five); a guard so two background jobs never overlap; a
trigger on another run's output (a daily pass that lands a new show in the top 200 starts a
recommend run); a mark so that trigger fires once; and a status endpoint. None of it was
reviewed by the builder and none of it is on the view. The third trigger is one the host's
cron cannot express, which is what the deferred entry named as its decider.

## What has to be decided

- **§2.1's containment**, first. The proposal keeps the clock the host's or the process's: a
  `tick()` the host's cron calls through `simple-agents schedule tick`, or a `serve()` the
  service process calls. The library decides what is due and records it; it runs nothing
  outside that call. **Thilina agreed the shape on 2026-09-02**, put to him as keeping the clock
  the host's; the build log records §2.1 as read that way, and §2.1's text is not changed.
- **The declaration**: `Schedule([...])` beside the pipelines, with `Every(...)`, a `when=`
  predicate, and `After(run, when=)` on a run's output; registered like `Product`.
- **The durable record** of last runs and fired triggers, and where it lives under `runs/`.
- **The manifest**: a `trigger` field on a run the schedule started, a format move.
- **One at a time**, and what happens to a job that is due while another runs.
- **The view**: the schedule on the operate page; `used_through`'s answer read against it.
- **The docs**: `docs/product.md` §6 rewritten around the declaration.

## What it waits on

none
