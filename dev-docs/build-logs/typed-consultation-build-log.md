# Build log — a consultation answer the library can read

**Built 2026-08-12.** `archive/plan-history.md` §1.13 is the brief and the design; this is what building it
found. Trajectory format `0.20` to `0.21`, manifest `0.20` to `0.21`, 1827 tests including the two fixes at §2.3 and §4.

---

## 1. What shipped

`consult` returns a **`Reply`**, and `on_reply` routes on it.

```python
reply = ctx.call_tool("consult", question="Ship it?", options=["yes", "no"])
reply.chose        # 'yes', or None where the answer was none of the options

route=on_reply({"yes": "apply", "no": "stop"}, unmatched="amend", declined="stop")
```

`options` decides how an answer is read and constrains nothing the end user says. Matching folds
case and punctuation through `normalise_text`, and `consult(match=...)` replaces the rule.
`resolution` gains `unmatched`, the consultation record gains `chose`, and a node entry in the
manifest gains `consultation_route`. `on_reply` requires branches for `unmatched` and `declined`
unless `exhaustive=True`, which is recorded.

## 2. Three things the brief did not know

### 2.1 A `str` subclass, because of what the model sees

The brief said "a typed choice and free text alongside" and left the shape open. A dataclass was
the obvious reading and it is wrong: `_observation` sends a tool result to the model as
`content if isinstance(content, str) else repr(content)`, so a dataclass would change what every
agentic consultation shows the model, from `yes` to `Reply(text='yes', chose='yes', ...)`.

A `str` subclass carrying `chose` keeps the model's view identical, keeps `answer == "yes"`
working in the two dogfood projects that already consult, and keeps `None` meaning declined, so
`consult`'s existing docstring stays true. The typed value is additive.

### 2.2 The cassette would have made a replayed evaluation disagree with its own recording

**This is the defect the item nearly shipped with.** A `Reply` serialises as its text, so a
cassette stores `"shorts"` and a replayed run rebuilds a bare string with no `chose`. Deriving
the match inside the tool alone meant:

| | live | replayed |
|---|---|---|
| `resolution` | `unmatched` | `answered` |

A replayed evaluation disagreeing with the run it was recorded from is the one thing the
cassette exists to prevent, and no unit test then written would have caught it: every test
either recorded or replayed, never both.

**The fix is to derive wherever an answer arrives** rather than where it is produced: from the
channel, from a resumed run, and from the cassette. `ConsultTool.read_answer` is that function.
It is required to be deterministic in the answer and the options, because it now runs more than
once for one answer, and that requirement is stated on the field rather than left implicit.

`test_a_replayed_answer_records_the_same_thing_the_live_run_did` records and replays in one test
and asserts the two agree. Removing the re-derivation fails it with
`('answered', None, 'shorts') != ('unmatched', None, 'shorts')`, checked by doing it.

### 2.3 A route helper would have defeated FT-15, and the manifest field is why it does not

`manifest_nodes` records `"route": _versioned(node.route)` with the comment that a route decides
which nodes run at all, so an edit to one is traced like a prompt edit. **`source_version` digests
a closure's source, which is identical whatever the closure closed over.** Probed directly:

```
closure over {'x': '1'} : sha256:962b66f2b895
closure over {'y': '2'} : sha256:962b66f2b895
```

So two `on_reply` routes sending the run to different nodes would have recorded the same version.
A factory that returns a closure makes a route **less** traceable than a hand-written function,
which is a regression against FT-15 rather than a missing nicety. `consultation_route` records
the mapping structurally, and carries `exhaustive` so the waiver is visible for the same reason.

**This was latent for any function built by a factory**, not only a route: `source_version` also
versions prompts, matchers and a `ProjectMetric`'s `score`.

**Fixed the same day, at the general level rather than the route one.** `source_version` now
hashes the source together with what the function closed over, so `road({"a": "1"})` and
`road({"b": "2"})` differ. The trap in doing that is `repr`, which for most objects carries a
memory address and would produce a version that changes every process, which is worse than the
defect. Only data whose text its value fixes is counted, and anything else contributes its type
name, so a function closing over a client is versioned by its source exactly as before. Checked
by running the same probe in two processes and comparing.

`consultation_route` stays, because it records **what** a route maps rather than that it
changed, and a reader of a manifest can act on the first.

## 3. What was measured live

**Gemini, `gemini-3.1-flash-lite`.** One `AgentNode` told to ask three questions through
`consult`, with a channel answering by keyword so the run is deterministic while the model's
calls are not. All three outcomes came from a real model on a real wire:

```
('answered',  'blue', 'blue',                      ['blue', 'red'])
('unmatched',  None,  'actually make it a medium', ['small', 'large'])
('declined',   None,   None,                       ['yes', 'no'])
```

Replaying the same cassette reproduced all three exactly, which is §2.2 holding end to end.

**vLLM, `cpatonn/Qwen3-30B-A3B-Instruct-2507-AWQ-4bit`.** The same probe, and the same three
rows:

```
('answered',  'blue', 'blue',                      ['blue', 'red'])
('unmatched',  None,  'actually make it a medium', ['small', 'large'])
('declined',   None,   None,                       ['yes', 'no'])
```

Two backends, four outcomes each counting replay, and no difference between them. That is the
expected result rather than a surprising one, because the derivation is library-side, and it is
worth having because nothing else establishes that a second model reaches `consult` with the
options attached the same way.

**How this arm was run, given the GPU.** No server was started for it. The GPU had 1.61 GiB free
of 23.53, held by dogfood #4's own vLLM on port 8002, so the probe used that server read-only
rather than reallocating anything. **The risk that carried was `concurrent_requests`**, which is
the divisor for the compute cost basis: a probe overlapping a dogfood call would leave the
dogfood a cost figure that is wrong with nothing raised. It did not overlap, and that is
measured rather than assumed. The probe's model calls ran `21:23:44.359Z` to `21:23:45.956Z`;
dogfood #4's evaluation `eval_b4b9de4b0ea1` opened its first model call at `21:24:02.102Z`,
**seventeen seconds after the last of them**. Nothing was written anywhere under
`/home/thilina/Projects/dogfood-4`.

## 4. What it cost elsewhere

Nine tests failed on the format bump and every one was the format working as designed: the
shipped documents are the source of truth for the version and the field table, and
`test_every_format_version_is_pinned_to_a_literal` is deliberately a literal so a bump is an edit
to the test as well as to the constant.

`check_citations` caught two rounds of drift from adding lines to `checks.py` and `tools.py`,
across `items/example-projects.md`, `runs/dogfood-1/findings.md` and two build logs. **`--fix` handled
`symbol-drift` and not `blank-line`**, and rewrote none of the five, because an anchor that
slides onto a blank line is what an edit above a citation actually produces.

**Fixed the same day.** `blank-line` now resolves its subject the same way `symbol-drift` does
and carries a fix, and the two share one resolver rather than two copies of the rule. The
distance test does not apply to it: `symbol-drift` asks whether the anchor moved, so a definition
within `NEAR` lines counts as already right, while a blank line is wrong however close it is. All
five of this item's would now be rewritten. What it still declines is what it cannot decide: a
subject not named beside the citation, a dotted name, and a name defined twice in the file, which
is why `ConsultTool.resolve` needed a hand and still would. `tests/test_check_citations.py` is
the first test the script has had.
