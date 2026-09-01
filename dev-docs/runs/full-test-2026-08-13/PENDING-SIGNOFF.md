# Pending sign-off

Everything from the fix pass that needs Thilina before the work is committed. Nothing here is a
question the streams could answer themselves; each is either a settled rule that was departed
from, or a decision no ruling covers.

Ordered by what blocks a commit first.

**Fully dispositioned 2026-08-20, at the P3-1 completeness audit**: every section below is
signed off, fixed, or overtaken, each with its evidence dated in place. Nothing here waits on
anything.

---

## 1. A `# prose-ok:` marker was added without sign-off. Rule departure, disclosed.

**Signed off 2026-08-14. The marker stays.** Committed in `d13e46e`.

[`CLAUDE.md`](../../../CLAUDE.md): "**a marker is added only with Thilina's sign-off**: surface the
text and the reason and wait, rather than committing it and mentioning it afterwards."

Stream C added one and disclosed it. It is in the tree now, and `prose_check` is clean **because**
of it.

[`search.py:72`](../../../src/simple_agents/builtins/search.py#L72):

```python
# prose-ok: a stopword list is data, and the second-person rule is about prose.
```

**What trips the check.** `ENGLISH_STOPWORDS` is 175 words and contains `you`, `your`, `yours`,
`yourself`, `yourselves`. `prose_check`'s second-person rule reads them as prose.

**Why dropping them is not free.** The same list holds `i`, `me`, `my`, `he`, `she`, `we`, `they`,
`him`, `her`, `us`, `them`, `it`. Removing the second-person five leaves an arbitrary hole in a
complete pronoun set, and the queries the list exists to help are exactly the ones shaped like
"what do you do when the depot is closed".

**Three ways to settle it:**

| | Cost |
|---|---|
| **Sign off the marker** | none, and the rule's exception mechanism is used as designed |
| Drop the five words | a pronoun set with a hole; the natural-language queries the list is for get a lexical vote back on `you` |
| Move the list to a data file | the package's first non-Python file, plus packaging and force-include implications |

**Recommendation: sign off the marker.** The rule exists to keep second-person *prose* off shipped
surfaces. This is a word list that happens to be written in Python, and the alternatives each cost
something real to avoid a violation that is nominal.

**If the answer is no**, either alternative is one edit and `prose_check` goes red until it lands.

---

## 2. `check_citations.py --fix` was run on two files before the instruction reached the stream

**Approved 2026-08-14, in a commit of its own.** All 80 fixed in `d821240`; 71 by `--fix`, 9 by
hand. `check_citations` is clean.

Stream C ran it on `dev-docs/build-logs/semantic-recall-build-log.md` (6 anchors) and its own
build log (5 anchors), all citations into `builtins/` that its own edits had moved. It disclosed
this. Nothing else was touched, and each file is revertable on its own.

**The lead separately ran `--fix` scoped to this checkpoint directory only**, which is inside the
free-rein grant, and then realigned four citation labels the tool had left pointing at old line
numbers while updating their anchors.

**Untouched and awaiting sign-off: 55 problems in pre-existing `dev-docs/` files**, of which
**12 are in [`plan.md`](../../../dev-docs/plan.md)**. `--fix` rewrites them. Nothing in `docs/` or `src/` is
affected. **Cleared by 2026-08-20**: `check_citations` runs clean over the whole tree, the
backlog fixed by later items' `--fix` passes; the residual relative-link question lives in
`plan.md` §2.2.

---

## 3. Stream A deviated from the letter of D1, for a measured reason

D1 said the reservation is taken before dispatching. Stream A put it **at the model call** rather
than **at the arm**.

**Its reason, which the lead agrees with.** A per-arm reservation charges a step to an arm that
makes no model call, which under overlap refuses a sibling that would have fitted; and charges one
step to an arm that makes many. On `over=`, an arm's phantom step turns `max_steps=3` into two
calls. At the call site the behaviour matches all four shipped statements exactly, and it covers
chains and delegation as well as arms.

Recorded in [`fixes/stream-a-build-log.md`](fixes/stream-a-build-log.md). **No action needed if
this reading is accepted**; it is here because it departs from what was written down.
**Signed off 2026-08-20.** The reading is accepted, and the behaviour has stood through every
item since.

---

## 4. H-6: a nested stop's `node_id` is the bare leaf. No ruling covers it.

A stop inside a pipeline used as a node reports `ask_inner`, while the manifest, the trajectory and
every other surface use `research.ask_inner`. Two nested pipelines with the same leaf name produce
indistinguishable stops.

Fixing it changes `stop.stops`, which is a shipped surface. Stream A left it open rather than
deciding. **Fixed since, verified 2026-08-20**: a stop inside a pipeline used as a node reports
`research.ask_inner` on `RunSuspended.stops` and on `Pipeline.suspensions`, matching every
other surface.

---

## 5. B-1: a redacted tool result stops a run replaying its own cassette. Design decision.

Stream D established that keying on the redacted form cannot work: pattern redaction replaces a
substring and key-name redaction replaces the whole value, so the two sides never produce the same
string.

**The fix that keeps the original promise** is to redact the tool result at the boundary, so the
model is given what the file holds. That also stops a credential reaching the provider's logs. It
is a behaviour change in `context.py`, not a repair.

**What shipped instead, pending this decision:** the cassette-miss message now diagnoses the cause,
verified live, and [`run-envelope.md`](../../../docs/run-envelope.md) §6 describes what the system
actually does rather than promising a replay it cannot deliver. **Signed off 2026-08-20.** The
boundary redaction shipped as `Tool.redact_result`, declared per tool, so the model, the node
and the cassette hold one string and the recording replays; the undeclared-tool residual stays
documented as it is.

---

## 6. Three items Stream C raised and did not decide

- **Extending the required `ranking=` to `memory_search(embeddings=...)`.** D4's follow-up ruled it
  for `DocumentIndex`. The same silent-default argument applies here and the ruling does not name it.
  **Closed 2026-08-20, fixed since**: `memory_search(embeddings=...)` with no `ranking=` is
  refused, and a test asserts the message.
- **The `Reply` matcher rejects "Yes, go ahead".** Stream C corrected the false docstring example
  rather than changing the matching rule, on the grounds that the rule is a design choice. Whether
  a natural-language affirmative should match an offered option `yes` is open. **Carried into
  dogfood #4, 2026-08-14**: a real model and a real person against it decide this rather than a
  guess made here. **Signed off 2026-08-20, answered by measurement.** `P3-9` measured 0 of 24
  prose answers matching and Thilina declined shipping a matcher; `P3-12` shipped
  `consult(read=ModelReader(...))`, so the affirmative is read into the option by a model rather
  than by a string rule.
  [`build-logs/end-user-in-an-evaluation-build-log.md`](../../build-logs/end-user-in-an-evaluation-build-log.md#L1).
- **`web_search` reports the declared price under `source: "measured"`.** A declared price is not a
  measurement, and the field says it is. **Closed 2026-08-20, fixed since**: the tool reports
  `meter.spend(..., source="declared")`.

---

## 7. The README's three review comments are still in place

`README.md` carries three `<!-- Thilina: ... -->` notes, at lines 73, 76 and 144. **None was
removed**; Stream E left them as instructed. Each asks for a section-level rewrite of tone rather
than a fix, so each is yours:

1. Line 73: "We should be focusing on what the library provides, what it does, and point the user
   to find more information about each thing, i.e., the relevant docs. WE ARE NOT TRYING TO DEFEND
   OUR CHOICES."
2. Line 76: "I'm not sure this is the right tone. I feel like this section should be an concise,
   objective description of the main parts of the library. I updated it a bit, but still not fully
   happy."
3. Line 144: "Commented this out since this is not user-facing and doesn't contribute anything
   without real users. We can add something like this back if we do ship while things are still
   sitting in the pipeline."

**What Stream E did change**, because the answer was unambiguous: the placeholder at line 95 that
rendered to the reader as "Registration without one is refused, to ensure \<what does this
provide?\>" now states what the side-effect class is for, and the empty `## Cassettes and Replays`
heading is gone.

**Closed 2026-08-20**: the three comments are gone, removed by Thilina's own README pass.

---

## 8. Four things Stream B raised while implementing D2 and D3

- **`_eval_id` covers twelve fields, not the four D2 enumerated.** `manifest_nodes()` carries
  `sampling`, `tools`, `allow_unknown` and `node_budget`, and beside them `route`,
  `consultation_route`, `finish_check`, `context_builder`, `stream`, `fan_out`, `accepts` and the
  per-node `model`. Every one decides what a number was measured over, and each was as absent as
  the four. Stream B's argument, which the lead accepts: enumerating four of twelve leaves the same
  defect under a different field name. **It is a one-line change to `_measured_configuration` to
  hold it to the literal list.**
- **`totals.tool_spend.currency` comes from the accumulated model `Cost`**, not from the tool
  spend, so a `Deterministic` pipeline with a paid tool reports an amount with no unit.
  `Recording.currency` has the same shape. Documented rather than changed; no ruling covers it.
- **`nodes.py:696`, "no model client", is a `CallerFacingError`**, so it fails k x n times rather
  than once. As a `ConfigurationError` it would fail fast under D3's new classification.
- **Eight findings remain unassigned**: finding 5 (`write_labels` raises `TypeError` on
  `Unknown`), and F-07, F-10, F-11, F-12, F-14, F-15, F-17.

**All four closed 2026-08-20, fixed or overtaken since**: `P3-18` and `P3-20` made wide
identity coverage the explicit design; `tool_spend` carries its own currency and a differing
declared one is refused; both no-client raises are `ConfigurationError`; `write_labels` holds
an `Unknown` verdict, and F-07, F-10, F-11, F-12, F-14, F-15 and F-17 were each checked
against the tree at the audit, and each is fixed.

## 9. The results file format moved, 0.10 to 0.11

`Outcome` gains `no_response` and each metric gains a `no_response` count. An 0.10 reader cannot
parse a file this version writes. Nothing outside this repository holds one. **Closed
2026-08-20**: pre-adoption, recorded in `CHANGELOG.md`.

## 10. Still open from the sitting, unchanged

`SITTING-BRIEF.md` Decision 5 asked three things that have not been answered and are not blocked by
anything above:

- Whether the lead updates [`plan.md`](../../../dev-docs/plan.md) §1.2 and [`handoff.md`](../../../dev-docs/handoff.md), and in
  what shape.
- Whether the documentation corrections go in as one item or per document, and whether they merge
  into the shipped-document review already at §1.2 item 4.
- Confirmation of the D5 ruling's carry-forward: dogfood #4's findings record checks every issue it
  hit against what has since been fixed.

**All three overtaken, closed 2026-08-20**: the plan was reorganised on 2026-08-15, the
documentation corrections merged into the shipped-document review (`P3-3`), and dogfood #4's
findings checked every issue against what had been fixed, in its §8.3.
