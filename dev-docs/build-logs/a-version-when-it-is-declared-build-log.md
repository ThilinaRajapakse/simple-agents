# Build log — a version is taken when the thing is declared, and FT-15 has a check

`plan.md` §1 P3-21. Started and built 2026-08-19, owed to `P3-20`'s Left open.

## 1. Before any design

**Both defects measured before anything was decided**, each two constructions differing in one
thing.

**A prompt closing over state it mutates moved the stamp.** A prompt builder holding a cache:
`behaviour_fingerprint` went `sha256:fe3b521cc80d` to `sha256:54dc12fc0703` after one call, with
nothing about the pipeline changed. `behaviour_fingerprint` is what `docs/shipping.md` §6 tells a
project to write beside a stored result, so the query that finds stale rows was reading a value
that moved on its own. The cause is
[`manifest.py`](../../src/simple_agents/records/manifest.py#L590), `_closed_over`, rendering a captured
dict by value, on a version recomputed every time the manifest was read.

**Two tools one factory built shared a version.** `make_tool("https://one.example")` and
`make_tool("https://two.example")` both hashed to `sha256:fa70563023a5`, because
`derived_version` covered the source alone. The version is in the cassette key together with the
name and the arguments
([`cassette.py`](../../src/simple_agents/records/cassette.py#L598), `tool_version`), so a call recorded
against one host is served as the other's answer.

**FT-15 specified a check and `checks.py` registered none**, so a project could carry prompts with
no version at all and pass `simple-agents check`.

## 2. Design

Thilina, on the first two being left for later:

> "But these two will also obviously bite someone at some point, right? If we can fix something
> before it costs someone something, we shouldn't wait until it breaks wtf."

**A version is what the thing was declared with, so it is taken once, at declaration.** That is
the fix for the prompt case and it is where the closure was always meant to be read: a route built
by `road(mapping)` captures its mapping when the node is built, and what happens to that object
afterwards is the run, not the declaration.

**The tool half was built, reverted, and built again on Thilina's ruling.** The first pass read
four things as blocking it. Put to him, he ruled out the one they turned on:

> "If the main issue is Mistral, I don't care. It can be replaced by Gemini or vLLM or both."

**Two of the four dissolved with it**: `document_search`'s pinned hash and the `tools` cassette
were one problem, a Mistral arm that could not be re-recorded. **The other two were misread, and
the second pass found so.** `consult` builds its version once, in
[`_derived_version`](../../src/simple_agents/builtins/consult.py#L905), so a consult tool does not
drift; the two tests that failed each called a `build()` twice around a mutation the recording had
made, and a second `consult` built after `asked` has grown is a second tool. The same for the
clock tool. Both now build once and reuse, which is what their own comments already claimed
("The same pipeline, replayed"), and both assert more than they did.

**What the first pass got wrong, recorded because it nearly cost the fix.** It reported that
consult replay "breaks for every project using consultation". It does not: the version is stable
per constructed object, and a project recording in one process and replaying in another builds
the channel from the same initial state.

**FT-15's check is what a check can read.** The taxonomy asked for "every prompt is a versioned,
addressable artifact". The library now always records a version, so the reachable failure is a
prompt whose source could not be read. The entry says that, and its surface moves from
`static + artifact` to `artifact`. This is the treatment `DF4-X6` gave FT-25.

## 3. Build

**No format move.** 2716 tests to 2719. Nothing about the recorded shape changed.

- **`_declare_edges` snapshots the route**, so every node kind and `Pipeline` are covered by one
  line. `Deterministic` snapshots its function, `LLMNode` and `AgentNode` their prompt, and
  `AgentNode` its finish check. `_node_entries` reads the snapshots, and `_versioned` is gone.
- **`Deterministic`'s `closure=False` is gone**, which `P3-20` added the day before as a special
  case for exactly this drift. The snapshot makes it unnecessary, so this build removes code.
- **`ft_15`** is registered seventeenth, reading `prompts` in the run's manifest.
  `unversioned-prompt` is the fixture that fires it, one mutation from `conforming`.
- **A tool's version covers what its function closed over.** `derived_version` reads it through
  the same `source_version` a prompt uses, so there is one rule and one implementation.
  **The Mistral `tools` arm retired**: its cassette is deleted, `TestToolSurface` runs the vLLM
  arm, `TestGeminiTools` the other, and the recorder no longer offers it. `tools-vllm`,
  `tools-gemini`, `suspend-vllm` and `suspend-gemini` were re-recorded live.

**What the build found that the design did not know.** The suite pins the tool bound in two
places, and the reverification pass found a third and a fourth surface the tool change would have
broken. That is why the tool half was reverted rather than shipped: **the four together are a
settled design, not an oversight.**

**The count of checks is written in five places**, not the four the suite's own message claims:
`docs/conformance.md` four times, `README.md` once, plus the module docstring and four test
literals.

## 4. Verification

**Live against vLLM**, `Qwen/Qwen3-1.7B` on port 8001.

| | What it showed |
|---|---|
| A prompt holding a cache, across a real evaluation | called 4 times, and the stamp was `sha256:cec59b3623c09fd8` before and after |
| `simple-agents check` on `unversioned-prompt` | `FAIL FT-15`, 1 failed, 15 passed, 1 not applicable |
| `simple-agents check` on `conforming` | `pass FT-15`, 0 failed, 16 passed, 1 not applicable |
| A factory-built tool, recorded against one host and replayed against another | refused, naming `tool_version (recorded 'sha256:d7b28b8a7689', now 'sha256:d7ce28ab1e0a')`. Before this it was served the first host's answer |
| `P3-20`'s six live cases, re-run | every evaluation id byte-identical, so nothing regressed |

**Four reverification cycles.** The first found `derived_version`'s field docstring claiming to
cover what a function closed over, which the revert had made false, and an import left unused by
it. The second found nothing. After the tool half was built back, the third found a dangling
`else` under a `pytest.skip` left by the retired arm and a citation pointing at a line the edits
had blanked, and the fourth found nothing. **`document_search`'s pinned hash moved once**, from
`sha256:fcb0c61405e7` to `sha256:e0db8ffa4e95`, and its test now says what a move costs.

## 5. Doc consequences

- **`docs/failure-taxonomy.md` FT-15** gains a "What the library provides", states the check a
  check can run, and its surface is `artifact`.
- **`docs/conformance.md`** counts seventeen checks in four places, lists FT-15 in the per-check
  table, and its sample report carries the FT-15 line and the new totals.
- **`README.md`** said sixteen checks ship. It is the fifth copy of that count.
- **`CHANGELOG.md`** carries the entry.

## 6. Left open

- **Mistral has one fewer arm.** `mistral`, `agent`, `graph` and `graph-loop` still replay and
  still cannot be re-recorded, so the next change that invalidates one of those retires it the way
  this retired `tools`. Destination: `nothing`, until one is invalidated.
- **A route or prompt built by a factory whose captured value is replaced rather than mutated**
  still records the value it was declared with, which is correct, and a node rebuilt from new
  configuration is a different node. Nothing checks that a project does not rely on the old
  behaviour. Destination: `nothing`.
- **FT-15's check cannot see a declared version that held while its source moved**, which is the
  failure the `derived` field exists for, because a check reads one run. Destination:
  [`runs/dogfood-4/inventory.md` DF4-I06](../runs/dogfood-4/inventory.md#L1), which is what the
  artifact model owes.
