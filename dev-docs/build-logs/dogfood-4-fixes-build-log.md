# Dogfood #4's cheap fixes — the build

Built 2026-08-15. Four items from `runs/dogfood-4/inventory.md` §F, all sized `cheap`, proposed as one
short pass in `build-logs/consultation-build-log.md` §5.1 and ruled on the day. No design sitting:
each was decided by the finding that produced it.

**What they have in common.** Three of the four are a library surface that reads as working and is
not: a check that a project can pass two ways, a retry that never fires, and a version that moves
for the wrong reason. None of them fails loudly, and each cost a real project something before
anyone noticed.

---

## 1. DF4-I08 — a routed-around node read as an unseeded one

`_emit_skip` writes `seed=None` for a node every edge into which was absent, and `_unseeded`
exempted only `deterministic` nodes, so a routed-around `LLMNode` or `AgentNode` failed FT-07.

**What it cost.** `DF4-D6`: FT-07 failed on 2 rollouts of 108, the project made the route
unconditional to clear the gate, and the node then burned its whole 18-step budget on 30 of 102
rollouts in one arm and 88 of 100 in another. **1,584 model calls in that arm**, the largest single
line item in the evaluation, buying nothing.

**The fix is one clause**: `termination == "skipped"` is exempt alongside `deterministic`. A node
that did not execute sampled nothing, and the record already says which it was.

**Verified live** against vLLM rather than only over a fixture, because what a fixture cannot show
is that the library writes the pair in the first place:

```
  start        kind=deterministic  seed=None    termination=None
  look_closer  kind=llm            seed=None    termination=skipped
  always       kind=llm            seed=41      termination=None
  _unseeded(records) -> False
```

Two tests, both directions: a skipped agentic node passes, and one that ran and recorded no seed
still fails. The second is what keeps the exemption from becoming a hole.

## 2. DF4-I09 — a retry a fan-out could never reach

`_Failures.saw` returns without raising while the count is within `max_failures`, and a
`RetryPolicy` re-executes a node only when the node raises. At the default, `max_failures=None`,
the two are configured independently and the retry is inert.

**What it cost.** `DF4-D4`: 28 of 1,233 fan-out items, 2.3%, died on schema validation across the
project's whole life. `retry=RetryPolicy(attempts=2)` was added to close it, the build log recorded
that it had, and the loss stayed open.

**Refused at construction** rather than warned about, because the two settings contradict each
other and the builder cannot see it from either surface. The message names both ways out and what
each costs: `max_failures=0` makes the first failed item raise and re-executes the whole node,
re-attempting the items that succeeded; dropping `retry=` keeps the failures on the result to be
re-sent as the project decides.

**Not refused** where `max_failures` is set to a number: a failure past the limit does raise, so
the retry is live.

## 3. DF4-I15 — a library edit invalidated every project's recorded consultations

Found by the consultation build rather than by dogfood #4. `consult()` derived its version from
three sources and the first was **the library's own tool function**. Editing that function moved
every project's consult tool version, so every recorded consultation missed on the next upgrade,
silently.

**Measured the day it was found**: the consultation item changed that body and both suspend
fixtures had to be re-recorded although nothing about what the backend saw had changed. This build
changed it again and re-recorded them a second time, which is the last time an edit to this module
can force it.

**The version now covers the project's channel and its matcher.** What a consultation stores is
what the end user said, and no edit to this module changes that. Every other built-in keeps the
library body in its version and should: a change to `read_page` genuinely changes what it returns.

**One behaviour change worth stating.** A channel with no readable source, such as one built by
`functools.partial`, now derives no version at all rather than one hashed from library source.
`None` is honest, and it was never a version of anything: it was the same string for every
unreadable channel and moved whenever the library was edited. `version=` is what declares one.

## 4. `progress_of` — exported, and invisible

Ruled at the full-test pass (`RULINGS.md` D2 follow-up) that the evaluation surface goes to the
top level. `progress_of` and `RolloutProgress` were importable from `simple_agents.evaluation` and
in neither module's `__all__`, so nothing reading the surface could find them.

**What it cost.** Dogfood #4 went looking for exactly this and did not find it: `watch.py` imports
nothing from the library and reimplements it by globbing manifests, wrongly twice.

Both are now in `simple_agents.__all__` and in `simple_agents.evaluation.__all__`, the documented
example imports from the top level, and `docs/evaluation.md`'s "What to reach for" table has a row
for watching an evaluation from another terminal, which is the table a reader scans first.

**And a check, which turned out not to need a sitting.** The reason nobody noticed is that a name
imported into an `__init__` and left out of `__all__` still imports, so no test fails: what cannot
find it is everything that reads the surface rather than guessing at it. The rule that catches it
is mechanical, so it was tried before being argued about: **every name a package `__init__`
imports from inside the library appears in that module's `__all__`.** It holds across all five
packages with no exemption, and the reverse direction holds too, so `tests/test_packaging.py`
asserts both. Reintroducing the bug fails the test on `progress_of` by name. An exemption
mechanism was not added: nothing needs one, and adding one before anything does would weaken the
rule to nothing.

---

## 5. What the pass did not change

**No format moved.** Trajectory `0.22`, manifest `0.23`, results file `0.13`, all as the
consultation item left them. DF4-I08 reads a field that already existed and DF4-I15 changes a derived
value rather than a shape.

**2193 tests pass**, `prose_check` and `check_citations` clean.

**Both suspend cassettes were re-recorded**, `suspend-gemini.jsonl` and `suspend-vllm.jsonl`.
