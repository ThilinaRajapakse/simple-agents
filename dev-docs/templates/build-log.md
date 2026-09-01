# Build log — <subject>

`plan.md` §1 <P3-n>. Started <date>. Written while building, not afterwards.

**This file is the template `check_docs.py` reads.** The `##` headings below are the required
ones, in this order, so changing the standard means editing this file. Any section may be one
line. Delete this paragraph when copying.

## 1. Before any design

What was verified about the code as it stands, before anything was decided. Sixteen of the
thirty-six logs written before this template opened this way, and it is the step that catches a
brief resting on something untrue. Name the file and the symbol for each thing checked.

## 2. Design

What was decided, and what was weighed and not taken. If the item had a record in `items/`, its
design belongs here now and that file leaves `items/`.

## 3. Build

What shipped. What changed about the design while building, and what the build found that the
design did not know. Formats moved, test count, and the surfaces touched.

## 4. Verification

What was run live, against which backends, and what it showed. `CLAUDE.md` requires a real vLLM or
Mistral run for anything that changes code; this is where that run is recorded. A green suite is
not verification.

## 5. Doc consequences

What `docs/` and `CHANGELOG.md` gained, and which shipped statements stopped being true.

## 6. Left open

What this item did not close. **Each entry names a destination**: a link into `plan.md`, or the
word `nothing`. An entry with no destination is how something ends up in the inbox instead.
