# Dogfood #<n> — findings

What the run produced. `runs/dogfood-protocol.md` is how it was run and `setup.md` beside this
file is how this one was set up. Delete this paragraph when copying.

**A findings record belongs to the run, not to an item.** One run touches many items, so a finding
here is cited by a build log rather than copied into one.

## 1. Method, and what did not survive verification

How each figure below was obtained, and which claims were checked and failed.

## 2. What the run met

Against the ship criterion and the conformance tier, with the numbers and where they were read
from.

## 3. Findings

One per finding, identified `DF<n>-D<m>` so another document can cite it. Each carries its
evidence, what it cost, and whether it is about the library or about the task.

**Every finding either produces a candidate or says where it closed.** `check_docs.py` generates
the `**Acted on:**` line from the inventory, and warns about a finding no candidate cites. A
finding closed outside the inventory, by an earlier pass or inside the run itself, opens a line
`**Closed ` and **names something that resolves**: a commit in backticks, a `build-logs/` path, or
a candidate id. That clears the warning.

**A sentence beginning "Closed" is not a disposition.** The requirement is the same one the
inventory's `built <log>` status carries, and it exists because `DF4-D1` opens *"Closed inside the
run, and the finding stands anyway"* about the store rather than about itself. Nothing is stamped
to satisfy the check: a finding that closed nowhere and produced no candidate keeps warning.

## 4. What is open

What this record does not settle. `inventory.md` is where these become candidates with a size and
a disposition; this section says what they are.
