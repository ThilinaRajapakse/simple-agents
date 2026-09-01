# Build log — Four surfaces that read as working

`plan.md` §1 `P3-54`. Started 2026-08-28. Written while building, not afterwards.

Dogfood #5's sitting 7, over `DF5-I32` to `DF5-I35`. All four are one genre, which is
[`dogfood-4-fixes`](dogfood-4-fixes-build-log.md#L1)'s own framing: *"a library surface that
reads as working and is not. None of them fails loudly, and each cost a real project something
before anyone noticed."* Unlike that pass, three of the four carried a decision the finding does
not make, so this one had a sitting.

## 1. Before any design

Every claim in the four findings was re-measured against the tree before anything was decided.
Three of the four reproduced exactly; the fourth found more than the finding said.

**The fan-out.** `max_failures` defaults to `None`, which is unlimited
([`nodes.py`](../../src/simple_agents/nodes/deterministic.py#L75), `Deterministic.__init__`), and
[`_Failures.saw`](../../src/simple_agents/nodes/fanout.py#L481) raises only above a limit. The record is
complete, `FanOutResult.ok` and `.failures`, and nothing raises, warns or prints. **The progress
bar counted a failed item as a finished one**: the event carries `error` and
[`_item`](../../src/simple_agents/progress.py#L101) ignored it.

**Concurrency**, measured rather than read:

```
ceiling=1 (the default), concurrent_items=8  -> 0.40s, peak 1 in flight
ceiling=8,               concurrent_items=8  -> 0.05s, peak 8 in flight
ceiling=8,              concurrent_items=14  -> 0.05s, peak 8 in flight
```

Both halves of `DF5-D26`, including the second one where a node declared 14 against a run at 8.

**The absence**, reproduced in four shapes: `value_or` replaced the `Unknown` instance and passed
through the dict, the `str()` form and the bare word. A `Field(description=...)` on a `Maybe`
field replaced the library's description rather than adding to it.

**`http_fetch`.** Every fetch failure was `retryable=False` and there was no backoff, and the 429
path told the model something false: *"Try a different URL; requesting this one again will answer
the same way."* Two copies of that, `FETCH_DESCRIPTION` and `READ_DESCRIPTION`, both prompt text.

**Three things the findings did not say**, found in this pass:

1. **`http_fetch` is the only builtin that reaches the network.** Nothing else in `builtins/`
   imports an HTTP client, and `web_search` takes a project-supplied provider, so the library
   never sees a response to read a header from. This answered whether the fix generalises to the
   other fetch tools: there are none.
2. **`ModelFacingError(retryable=...)` is recorded and read by nothing.** Written to the
   trajectory, restored from a cassette, set deliberately by two builtins, branched on nowhere,
   and named in no builder-facing document.
3. **`retryable` defaults to `True`** ([`errors.py`](../../src/simple_agents/errors.py#L28)),
   which is harmless while nothing reads it and would mean *retry every tool failure in every
   project* the moment something did.

## 2. Design

Taken at the sitting on 2026-08-28. `items/dogfood-5-fixes.md` held it while the item was open.

**A fan-out raises where every item failed, there were at least two items, and every failure
carries the same exception type and the same message.** Independent of `max_failures`: that says
how many items may fail, this says whether the node worked at all.

*Weighed and not taken.* A first proposal fired on any two identical failures whatever the
success count, which would have caught the finding's second instance (9 of 37 items failing on a
project bug). Thilina refused it: *"Isn't that a little too strict? Maybe the builder will be
legitimately okay with 2 or 3 failures, as long as the majority go through?"* That is right, and
it also shows why the narrow rule is enough: in that instance the builder had declared a
tolerance and 9 was under it, so raising would override a deliberate declaration. **Visibility is
that instance's answer, not a refusal**, which is the progress bar below. Also not taken: a
warning rather than a raise, argued down by this run's own evidence that a warning on this
project was ignored three times; and a check reading the trajectory afterwards, since the cost is
paid while a coding agent is debugging a run.

At least two items, because at one the sameness clause carries no information and the rule would
silently become "a one-item fan-out that failed raises". No waiver knob: a project that
legitimately meets this is the evidence for one.

**A failure saying the run is invalid is raised from inside an item rather than collected**, which closes
`plan.md` §2.1's `ConfigurationError`-in-a-fan-out entry and answers its stated decider,
*"whether a `ConfigurationError` raised inside an item is ever one item's problem rather than the
node's"*. It is not.

*The design said all of `CallerFacingError` and the build proved that wrong.* See §3.

**The fan-out bar shows failures, and a resumed fan-out reports like the evaluation's**, which
closes `plan.md` §2.2's resumed-fan-out-bar entry and decides its question, *"whether the two
displays are allowed to disagree"*: they report the same way. Pulled in on Thilina's call so the
event is edited once rather than twice.

**A run warns where its `concurrency` cuts a node's `concurrent_items`.** A refusal was rejected:
the evaluation runner passes `concurrency=run_concurrency`, which defaults to 1, so a refusal
would refuse every evaluation of a pipeline that declares `concurrent_items`. Silent while
replaying, on the reasoning `_pace_clients` already skips pacing under replay.

**`value_or` reads the tagged dict as well as the instance**, since the library wrote that dict.
The bare word is not matched: a field whose answer is the word *unknown* is ordinary.

**`str(Unknown)` renders `unknown (reason)`.** The reason alone was rejected: it reads as an
answer, which is the class of bug this section is about. The decision was made against a real
prompt in this repository, `record_backend_cassettes.py`'s `graph_summarise`, which f-strings a
`Maybe` field straight into a prompt.

**`Maybe` appends its absence description** where the field's own says nothing about the tag,
at `json_schema_for_model`, which every path goes through. A refusal was rejected: a description
that is merely incomplete is one the library can complete.

**The retry is triggered by a new `Throttled(ModelFacingError)` carrying `retry_after_s`, not by
`retryable`.** Flipping `retryable`'s default to `False` and acting on it was the alternative,
rejected because it changes the recorded meaning of a flag already written into every trajectory
on disk. `retryable` keeps its meaning and is documented as what it is. The shape is field-tested:
dogfood #5's project built its own `Throttled` *"precisely so it can never be caught as absence"*.

`plan.md` §2.2's *"A client that stops re-paying a retry ladder"* was re-decided at the sitting
and kept deferred: its decider, a 429 the library **cannot** classify, is unmet either way, since
Wikipedia publishes `Retry-After`. Its entry now names the tool-side ladder as a second surface.

## 3. Build

3911 tests, up from 3874. No format moved: no trajectory, manifest, results, suspension, shelf or
conversation version changed.

**Surfaces touched.** `nodes.py`, `pipeline.py`, `progress.py`, `context.py`, `errors.py`,
`schema.py`, `cassette.py`, `builtins/http.py`, `__init__.py`; `docs/pipeline.md`, `docs/tools.md`,
`docs/evaluation.md`, `CHANGELOG.md`. New public names: `Throttled` and `retry_after_seconds`.
One public name removed: `warn_absence_undescribed`, which had nothing left to warn about.

**Four things the build found that the design did not know.** The fourth is in §4, found by a reverification cycle rather than by the build.

**1. "All of `CallerFacingError`" was wrong, and the suite said so within a minute.** The sitting
decided the base class on the strength of its own docstring, *"Infrastructure is broken and the
run is invalid. Raised, never passed to the model."* The code contradicts that docstring in one
place: [`_validated_output`](../../src/simple_agents/runtime/calls.py#L440) raises a bare
`CallerFacingError` where a model's response does not match the output schema, which is one
item's problem and exactly what `max_failures` exists for. Widening to the base class ended a
whole run on one item's bad JSON, and six fan-out tests failed. The tuple names the run-level
subclasses instead, as [`_STOPS_THE_RUN`](../../src/simple_agents/nodes/fanout.py#L443), with a comment
saying why the base class is not in it.

**2. `_ends_the_run` and `_STOPS_THE_RUN` are deliberately different, and making them identical
broke the failure budget.** `_Failures.saw` raises a bare `CallerFacingError` while collecting,
and the pool has to stop the items not yet started on it. `_STOPS_THE_RUN` decides what an item
raises *instead of collecting*; `_ends_the_run` decides what stops the items *beside* it, and
anything reaching it has already escaped the item. Narrowing both to one tuple let a batch that
had passed its tolerance run to the end: `test_max_failures_stops_a_batch_that_is_failing_systematically`
saw 5 requests where it wanted 2.

**3. The absence description reached one level of nesting and not two.** Found in the third
reverification cycle, after the tests for one level were green. Pydantic hoists every nested
model into one `$defs` at the top however deep it sits, and the first walk looked for `$defs`
inside each nested schema, which is always empty. A model two levels down kept a description
that said nothing about the tag. The walk collects the models transitively off the annotations
and matches each `$defs` entry to the one that produced it.

**Our own suite carried the finding's first instance.**
`test_a_fan_out_reads_the_conversation_and_adds_nothing` named its prompt function's parameter
`item` and read `item["q"]`, where a fanned-out node is handed the whole input with the fanned key
holding one item. Both items raised `KeyError: 'q'`, `max_failures` swallowed both, and the test
passed because it asserted the fan-out added nothing to the conversation and got nothing for the
wrong reason. This is `BUILD-LOG.md:375-380`'s defect in the library's own tests, and the new rule
is what surfaced it.

**The `graph` Mistral cassette is retired.** `str(Unknown)` changes what
[`graph_summarise`](../../scripts/record_backend_cassettes.py#L466) builds, which moved two of
that recording's keys, and Mistral is out of credits. `handoff.md`'s rule is that the next change
invalidating one needs a new arm, so `graph-gemini` was added to the recording script and
recorded. **Checked before committing to the change**: Gemini takes the same route on both
questions, so every assertion in `TestBranchAndSkip` transferred unchanged. What is lost is a
recording of Mistral answering `unknown` where the notes did answer, which no test asserts on.

**Nothing else was invalidated, verified rather than assumed.** Every cassette in
`tests/cassettes/` was scanned for a field that admits absence and describes only the value,
which is what the `Maybe` append would move: **zero**, including the four Mistral arms that
cannot be re-recorded.

**`scripts/shape_baseline.json` was updated.** `nodes.py` grew 51 lines and `pipeline.py` 45, and
both are already the two largest modules. `plan.md` §2.1's pre-release refactor entry is what owns
that, and it waits on `P3-32` deliberately, so the sizes are recorded rather than decomposed here.

## 4. Verification

**Live against Gemini** (`gemini-3.1-flash-lite`), one run exercising three sections at once: a
fan-out of two questions over a `Maybe[str]` field whose `Field(description=)` replaces the
library's, at `concurrent_items=4` under the default `concurrency=1`.

```
A. concurrency warning: 'This run permits 1 call(s) in flight and ask declares 4, ...'
B. items: [(0, True, Answer(answer='kirkwall')),
           (1, True, Answer(answer=Unknown(type='unknown', reason='...no revenue data...')))]
D. rendered: unknown (The provided text ... does not contain any revenue data for Kirkwall.)
```

Item 1 is the append working end to end: the model was shown a field described only as *"The
retailer's name."* and still returned a correctly tagged absence. Before this change it was shown
that sentence alone, and dogfood #1 measured 13% of rollouts writing the word into the value
branch under exactly that condition.

**Live against Gemini, the fan-out rule**, reproducing `DF5-D25`'s first instance: a prompt
function reading the item under the wrong key, three items, a real backend.

```
A. refused: Node 'sum' fanned out over 3 items and every one of them failed with the same
   KeyError: 'text'
```

**Against a real HTTP server**, not a mock transport: a `http.server` on 127.0.0.1 answering
`429` with `Retry-After: 0` twice and then `200`, so real sockets, real httpx and real headers.

```
B. raw tool call raises: Throttled, retry_after_s=0.0
C. through the library: '<html><body><p>the page ' after 2 requests
```

The library waited the throttle out and the page came back, in one `tool_call` record.

**`graph-gemini` recorded live** against the paid key, and `TestBranchAndSkip` replays it.

**Reverification ran until a cycle found nothing.** The first passes were a read of the code
against what the sitting decided followed by a run. Then Thilina corrected how they were being
run: they had been scoped to a different part of the item each time, *"which defeats the purpose
of repeated cycles"*, since a fix made in one is never re-checked by the next. **A cycle covers
everything**: read the docs, read the code, cross-verify one against the other, test the pieces,
run the whole suite, run it live. The cross-verification and the piece tests were written as a
script so a later cycle cannot quietly cover less than an earlier one, and every finding below
was added to it.

The early three found the two `CallerFacingError` defects in §3, then the two-level nesting
defect over green tests for one level, then the interactions those had not covered: that every
tool path goes through one dispatch point so an `AgentNode`'s model-chosen calls are retried too,
that the append is idempotent across repeated `model_json_schema()` calls and does not leak into
pydantic's own API, and that the throttle check precedes the general `>= 400` refusal in the
redirect loop.

**The full cycles found five more.** Three came only from reading a document against the code
that was supposed to implement it, and one only from reading the diff:

1. **`docs/pipeline.md` §1.5 said a fan-out raises on "a misconfiguration, or anything else
   caller-facing".** The code raises a named tuple, and a bare `CallerFacingError` is still
   collected, which is what a schema violation is. The section names the five instead.
2. **`CHANGELOG.md` listed a cassette miss and an exhausted budget among the failures that
   "was collected as that item's failure and is now raised".** Both were always raised: the
   original tuple held them. Three are new, not five. Corrected there, in `plan.md` §4 and in
   §2 above.
3. **`docs/evaluation.md` §7.4.1 explained what the behaviour was before `0.1.0`.** Nothing is
   released, so a builder reading it has no such version to have relied on, and a builder-facing
   document is written for the release rather than for the state of development. The history
   left; this build log is where it belongs.
4. **A node that ran out of the budget it declared read as a node with a broken prompt.**
   `_fan_out` deliberately keeps a `NodeBudgetExceeded` item outside `max_failures`, saying in a
   comment that *"the items did not fail, the node ran out of what it declared"*, and the new
   rule counted those items like any other failure. A fan-out whose every item was stopped by
   the node's own budget was told its prompt or schema was wrong for all of them. Found by
   reading the diff rather than by any test, since nothing in the suite declares a per-item
   budget tight enough to stop every item. `_RAN_OUT` names the type and the rule skips it,
   `docs/pipeline.md` §1.5 says so, and a test asserts it.
5. **`ctx.call_tool` rebuilt a plain `ModelFacingError` from the message**, so a node body
   catching a kind of tool failure caught nothing, and a recorded failure replayed as the base
   class. **`Throttled` is the first `ModelFacingError` subclass this library has had**, so the
   flattening was invisible until this item created something to flatten. Found live, in cycle 5,
   on the very example `docs/tools.md` §2.1 tells a builder to write. `_ToolOutcome` and the
   flight carry the exception now, `ctx.call_tool` re-raises it, and `encode_tool_failure`
   records the throttle so `decode_tool_response` rebuilds one. Three tests, and the cassette
   gains two keys without a format bump, since an old recording decodes as it always did.

## 5. Doc consequences

- **`docs/pipeline.md` §1.5** gains the two failures that are the node's rather than an item's,
  with the message.
- **`docs/pipeline.md` §1.10** gains what happens where a node declares more overlap than the run
  permits, with the warning.
- **`docs/pipeline.md`**'s absence section: `value_or` reads both shapes, and `str(Unknown)`
  renders the word first. The paragraph saying a `Field(description=...)` **replaces** the
  `Maybe` description now says the library completes it.
- **`docs/tools.md` §1.3** gains `Throttled`, and says what `retryable` is: recorded, and read by
  no library code. **§2.1 gains the fact that `ctx.call_tool` re-raises the failure the tool
  raised**, with the worked `except Throttled` a node body writes, since that section is where a
  builder is told to catch one.
- **A shipped sentence of this item's own named an internal run.** `docs/tools.md` §1.3 read
  *"dogfood #5 met 736 of them and reported no article"*, which is development history in a
  document a builder reads. Found while preparing sitting 8, after the item was committed, and
  corrected to name no run. It is the second instance of `plan.md` §2.1's shipped-comment entry
  and answers that entry's decider; see §6.
- **`CHANGELOG.md`** gains the entry. No format moved, and two changes break a recorded artifact
  without moving one: a prompt interpolating a `Maybe` field, and a schema whose absence field
  described only the value. **The cassette gains two keys on a recorded tool failure**, read with
  a default, so a recording made before this decodes as it always did.

**Shipped statements that stopped being true**, both corrected:

- **`docs/evaluation.md` §7.4.1**, *"A fan-out is the exception. A `ConfigurationError` raised
  inside one item is collected as that item's failure"*. It is no longer, and the section says
  what changed and when.
- **`http_fetch` and `read_page`'s tool descriptions**, *"a failure means to try a different URL
  rather than the same one again"*, which was false for a 429 and is prompt text. Both corrected.
  Only `read_page`'s was corrected at first; a test asserting on `http_fetch`'s caught the other,
  which is `DF5-X17`'s lesson that a fix applied to one surface has to be checked against the
  others.

## 6. Left open

- **A retry policy for a throttled tool is not declarable.** The ladder is three attempts from a
  module constant, so a project that wants more, fewer, or none cannot say so. No project has
  asked; the numbers are in `context.py` beside a comment saying why they are smaller than the
  model clients'. **Destination**: [`plan.md` §2.2](../plan.md#L211) if a project meets it.
- **A node with `over=`, `retry=` and `max_failures=` retries the new refusal.** The refusal
  reaches `except Exception` in the executor like any other node failure, so a declared
  `RetryPolicy` re-runs the whole fan-out, which is definitely-wasted work on a node the library
  has just said is broken for every item. The existing `max_failures` refusal has behaved this way
  since it shipped, so this is consistent rather than new. **Destination**:
  [`plan.md` §2.2](../plan.md#L211), with the question of whether either refusal should be exempt
  from `retry=`.
- **A throttled `robots.txt` reads as a site with no `robots.txt`.**
  [`_read_robots`](../../src/simple_agents/builtins/http.py#L314) returns `None` on any status
  `>= 400`, and a site that is rate limiting will rate limit that request too, so a throttle there
  is read as permission. This predates the item and the docstring already says an unreadable
  `robots.txt` is treated as permitting everything. **Destination**:
  [`plan.md` §2.2](../plan.md#L211).
- **`plan.md` §2.1's shipped-comment entry has its answer.** It waited on *"whether a second
  one has appeared since"*. Two have: `view/record.py` names `dogfood-5-frozen`, written at
  `P3-52`, and this item wrote a third into `docs/tools.md` before catching it. **Three
  instances, and nothing sees any of them**: `prose_check`'s internal-id rule reads `P3-n` and
  `DF5-Inn`, so a run named in prose passes. The entry's own remedy is a rule, and the evidence
  it wanted is now on record. **Destination**: [`plan.md` §2.1](../plan.md#L76), whose entry is
  updated rather than a new one opened.
- **38 citations in `runs/full-test-2026-08-13/inventory/claims-evaluation.md` were repaired** as
  a side effect of running `check_citations --fix` over the tree. They had drifted before this
  item and were not caused by it. **Destination**: nothing, they are fixed.
