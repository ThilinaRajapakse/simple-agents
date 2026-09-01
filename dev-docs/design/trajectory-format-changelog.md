# Trajectory format — pre-release version history

**Moved here from `docs/trajectory-format.md` §9 at the document review, 2026-07-30.** A
changelog does not belong in a builder-facing document, and these entries in particular are
written for us: each argues its own case and cites internal decisions. No project will ever
hold records written in `0.1` through `0.7`, because nothing was released while they existed.

**From `0.8` onward, a format change is recorded in `CHANGELOG.md` at the repository root**,
like any other breaking change. This file stays as the record of what happened before the
first release, and of *why* each bump was taken. The root changelog says what changed; this
one says what it cost and what it settled.

The shipped document keeps one fact from the old §1.4: every record carries `format_version`,
and the current version is stated in §2. `tests/test_packaging.py` asserts that the document,
its field table and its example records all agree with `simple_agents.FORMAT_VERSION`.


## 0.29 — what the run was given (2026-08-28)

**What it settled.** Every record in the format says what happened during the run. None of them
said what the run was **asked to do**. That is the one input the whole causal chain follows from,
and it was recoverable only by knowing which node ran first and reading its
`node_execution.inputs`, which is written when that node **ends**. `P3-50`'s decision 7, taken by
Thilina on 2026-08-28.

**A seventh record type, `run_start`**, carrying `inputs` and `seed`, written before the first
node. `parent_id` and `ended_at` are `null`: nothing contains a run, and the record describes a
start rather than a span. It is the second root type, beside `node_execution`.

**The argument is the record's completeness, and two counts of crashed runs were rejected as the
basis for it.** The first offered at the sitting was that three of dogfood #5's four
inputs-missing runs were its most expensive to redo; the second was that only 14 unfinished runs
exist across four dogfoods and 6,141 runs. Thilina rejected both as designing for the dogfood, and
he was right in both directions. What decided it: `SuspensionState` already carries `inputs`
because a run that stops has to say what it was doing, and a crash is a suspension nobody got to
write, so the asymmetry had no design reason; the manifest already records four other caller-held
facts (seed, model configuration, budget, cost basis) for the reason that a record is read later
by someone who is not the caller; and a killed process is ordinary deployment rather than an
accident, since an out-of-memory kill, a container eviction, a spot reclaim and a SIGTERM on a
rolling deploy all produce one.

**Why the trajectory and not the manifest.** Measured over 400 runs of dogfood #5: a run's inputs
are a median 31,886 bytes against a mean whole manifest of 9,733, with a p90 of 168,513 and a max
of 500,007. Every check parses manifests whole, `runs()` parses them whole, and
`view/runs_overlay.py` streams trajectories and parses manifests whole precisely because a payload
record can be megabytes. Payloads in the manifest breaks that split. In the trajectory, redaction
and sampling both come free: `PAYLOAD_FIELDS` gained one entry.

**What the duplication costs, measured rather than estimated.** The first node receives the run's
inputs, so those bytes are written twice: a median 4.2% of a trajectory file, 18.5% at p90.
Storing the first node's copy by reference would remove it and was rejected as out of scope, being
`plan.md` §2.2's own entry and about transformed payloads, which is the harder half.

**What the bump cost, counted rather than estimated**: `RecordType` and `PAYLOAD_FIELDS` in
`trajectory.py`, one constructor, one emission site in `Pipeline.run`, and the manifest's counts
and `conformance/checks.py`'s `RECORD_TYPES` both followed automatically because each reads off
`RecordType` rather than repeating it. In the tests, ten assertions that indexed `records[0]` or
assumed every record hangs off a node. **The lesson is the one `0.28` already recorded and it held
again**: a type added to the format reaches every counter for free, and reaches every test that
assumed the first record was a node execution not at all.

## 0.28 — what a node's own code did to a store (2026-08-28)

**What it settled.** A store reached through a tool is a `tool_call` carrying what was asked
for and what came back. The same store reached in a node's own code left `touches=` naming it
and nothing else, so the completeness of `simple-agents view`'s data view turned on which way
a project happened to write the step. `P3-41`'s decision 6, taken by Thilina on 2026-08-28:
record the access, and record the value.

**A sixth record type, `resource_access`**, carrying `node_id`, `resource`, `direction`
(`read` or `write`), `inputs`, `outputs` and `item_index`. Written by
`NodeContext.record_access`, which every node kind reaches.

**Why a sixth type rather than a `tool_call`, which was cheaper.** The same argument `0.14`
made for `delegation`, and one more. A `tool_call` carries a `side_effect_class`, which
`docs/tools.md` §1.4 defines as declared by the author, and nobody declared one here; it
carries `spent`, which `tool_spend()` sums and this never buys; and it would land in
`counts.tool_call`, where a reader counting a node's tool calls would count accesses the node
made in plain code. The direction is not a side-effect class either: `read`/`write` describes
what the node reported doing, and a class describes what a declared tool may do.

**Why the payloads are the node's choice.** The library did not make the call, so it has no
value of its own to record. A step that reads 67,353 rows and keeps 12 records the two counts,
and a step that reads three passages records the passages. Both are the same field under the
same rules: `PAYLOAD_FIELDS` gained an entry, so redaction and sampling reach them.

**What the bump cost, counted rather than estimated**: `RecordType` and `PAYLOAD_FIELDS` in
`trajectory.py`; `per_node._count` and two `NodeMetrics` fields, which is a results-format bump
of its own (`0.24` → `0.25`); `RECORD_TYPES` in `conformance/checks.py` and the manifest's
counts, both of which read the tuple and needed no edit; the five sentences in `docs/` and
`README.md` that said "five record types", one of which `tests/test_readme.py` asserts by the
spelled number; `docs/trajectory-format.md` §1.2's table and a new §4.5; and
`simple-agents.md` §6's callout about not pairing record types with node kinds. Every
conformance fixture was regenerated; no cassette was invalidated.

**What it did not break.** `per_node._owners` walks `parent_id` to the first node record and a
`resource_access` names its node execution as parent, so every existing figure is unmoved. The
manifest gains a `counts.resource_access` key because `counts` is written off `RECORD_TYPES`,
which is what `0.14` set up and is not a manifest format change: `trajectory_format_version`
on the manifest is what says which list the counts follow.

**`touches=` moved with it.** It was on `Deterministic` alone, so an `LLMNode` or `AgentNode`
whose prompt function reaches a store could declare nothing and therefore record nothing.
Additive, and the view already read `touches` off any node.

## 0.26 — which item a call belongs to (2026-08-19)

**What it settled.** A fan-out's items share one `parent_id` and can overlap, so nothing but a
field on the record attributes a call to an item. `0.13` put `item_index` on `model_call` for
that reason and left the other three record types without it, so a forty-item fan-out's tool
calls, consultations and subtasks were one undifferentiated set under the node. `P3-22` stage 1
needs the attribution: the gate it builds fires on a unit of work that spent its budget without
calling anything, and a fan-out item is such a unit.

**`item_index` on `tool_call`, `consultation` and `delegation`.** The item the call was made
for, and `null` outside one. Threaded from the loop that already knows it, which is
`AgentNode._one` under `over=`, and from `NodeContext.item_index` for a `Deterministic` or
`LLMNode` node's own tool calls.

**What it cost.** Nothing recorded before this reads differently. The field is additive and
absent on every record written by an earlier version, and no other format moved. Every
conformance fixture was regenerated; no cassette was invalidated, because a cassette is keyed on
the request rather than on the record.

## 0.24 — what read the answer (2026-08-18)

**What it settled.** `0.23` gave a `consultation` `chose` and `declared_choice` and left the
reader unable to tell what decided `chose`. That mattered the moment a second kind of rule
existed. The sitting is `build-logs/consultation-reading-build-log.md` §2, `P3-12` stage 2.

**`read_by` on `consultation`.** `rule` for the tool's own matching over the text, whether
`consult(match=...)` or the default; `model` for a reader registered with `consult(read=...)`;
`null` where nothing decided it, which is a question offering no options and a consultation
nobody answered.

**A model's reading is a `model_call` record parented to the consultation.** That is where the
model, the tokens and the derived cost are, so `read_by` carries one word and nothing else moved.
The call is charged to the run's budget, unlike `answered_by_model`'s, which is the stand-in's
and stays off the node's figures: a reader ships with the agent and a stand-in is measurement
machinery. `per_node` folds it onto the node that asked, so a `deterministic` node can report a
model call it did not itself make.

**What the build found that the sitting did not.** The design said the reading would be a
`ModelHandle` on the consult tool. Measured, that makes the tool re-executed, and a re-executed
consult tool asks the person again on every replay and every rollout. The reading is a separate
library-owned step instead, run wherever an answer first arrives.

**What it cost.** Nothing recorded before this reads differently. The field is additive and
`null` on every record written by an earlier version, and no other format moved.

## 0.23 — which answerer, and how the answer was read (2026-08-17)

**What it settled.** Two things a `consultation` could not say: which of several people the
question reached, and whether the tool's own rule read the answer the way the channel meant it.
The sitting is `build-logs/end-user-in-an-evaluation-build-log.md` §2.3 and §2.5.

**`reaches` on `consultation`.** Which answerer the tool asks, from `consult(reaches=...)`,
`null` where the pipeline asks one person. `answered_by` is what kind of answerer and this is
which one, so a requester-and-approver pipeline is readable from the record rather than inferred
from tool names.

**`declared_choice` on `consultation`, and it never routed the run.** The option the channel
itself said its answer was, for a channel that can say; `null` for every channel reaching a
person. `chose` stays what the tool's `match=` read and is what a `route=` branched on. The two
differing is a misreading, counted in a results file as
`per_node.consultation_misreadings`. Whole-answer equality, which is the rule where a project
passes none, read an option out of **0 of 24** stand-in answers, so a project whose channel
writes prose reads that count equal to its consultations.

**What the build found that the sitting did not.** The declaration was first held on the call's
provenance, where a cassette hit never populates one, so the same run reported one misreading
live and none replayed. It is stored with the answer instead, the way `Unavailable` already is,
and `read_answer` rebuilds it: a replay reports what the live run reported. This is
`ConsultTool.read_answer`'s own documented rule about `chose` applying to a second field.

**What it cost.** Nothing recorded before this reads differently; both fields are additive and
`null` on every record written by an earlier version.

## 0.22 — who answered, and nobody to ask (2026-08-15)

**What it settled.** Whether a `consultation` says who supplied the answer. It did not, and
that is why dogfood #4 read 97 `answered` for two days over a channel returning one fixed
string. The sitting is `build-logs/consultation-build-log.md` §2.2.

**Three fields added to `consultation`.** `answered_by` is the channel's declaration, one of
`end_user`, `builder`, `coding_agent`, `simulated`, `canned`, `nobody`. `reason` carries
`Unavailable(reason=...)`. `answered_by_model` carries the model that wrote the answer, with
its tokens and derived cost, for a channel that runs one.

**`resolution` loses `timed_out` and `defaulted` and gains `unavailable`.** The two removed
were declared in `trajectory.py` from the beginning and produced by nothing, and
`docs/trajectory-format.md` §4.3 described a mechanism that did not exist. `Unavailable` with a
reason carries the timeout case in its reason, and one value with a reason beats three values
nothing produces. §1.2 of the sitting.

**Why `answered_by` is a declaration and not an observation, stated in the shipped document.**
The library cannot verify that a person typed anything. What it can record is what the project
said the channel reaches, made once where the channel is registered. A reader who takes it for
a verified fact would draw a stronger conclusion than the record supports, so §4.3 says which
it is.

**What the build found that the sitting did not.** Overriding the channel per run, which is how
an evaluation supplies its stand-in, left the record naming the *registered* answerer rather
than the one that answered. Caught by a test asserting the case the field exists for. The fix
is in `ConsultTool.for_one_call`, and the rule is that the manifest carries the declaration and
the trajectory carries what the run did.

**And a second, from the live run.** `Cost` carries no serialiser and holds slots rather than a
dict, so a record handed the object stored the string its `repr` produces. The consultation
record was the first to put a `Cost` somewhere the writer had not already converted it.
`nodes.py` `_cost_entry` builds the same five keys every other record writes.


## 0.21 — which option the end user's answer was (2026-08-12)

**What it settled.** Whether an answer that was none of the offered options is a refusal. It is
not, and the format now says so.

**Two changes to `consultation`.** `chose` holds the option the answer matched, and `null`
where it matched none or where none were offered. `resolution` gains `unmatched`, which is an
answer that was none of them: the end user said something, `response` holds it, and the run may
route on it. `answered` narrows to an answer that matched, or to any answer where no options
were offered.

**Why a field rather than reading it back off `response` and `options`.** The matching rule is
the project's: `consult(match=...)` replaces the default, which folds case and punctuation. A
reader recomputing the match would need that function, and a trajectory read a year later does
not have it. Recording the outcome makes the record self-contained, which is what every other
derived-looking field here is for.

**Where the derivation actually runs, and the defect that placed it.** Not in the tool. A
`Reply` is a `str` subclass, so a cassette stores the text the end user typed and nothing else,
and a replayed run rebuilds a bare string. Deriving `chose` only inside the tool made a replay
record `answered` where the live run recorded `unmatched` — a replayed evaluation disagreeing
with the run it was recorded from, which is the one thing the cassette exists to prevent. The
derivation runs wherever an answer arrives instead: from the channel, from a resumed run, and
from the cassette. `ConsultTool.read_answer` is that function, and it is required to be
deterministic in the answer and the options because it is called more than once for one answer.
`tests/test_builtin_tools.py::TestConsult::test_a_replayed_answer_records_the_same_thing_the_live_run_did`
fails with `('answered', ...) != ('unmatched', ...)` when it is removed.

**Measured live.** Against Gemini, one `AgentNode` asking three questions: an answer matching an
option, one matching none, and a refusal produced `answered`/`unmatched`/`declined` with
`chose` set only on the first, and a replay of the same cassette reproduced all three exactly.

## 0.20 — state a backend requires back (the Gemini adapter, 2026-08-12)

**What it settled.** Where an opaque value a backend sends with a tool call lives, given that
the same backend refuses the following turn without it.

**One optional key**, `provider`, on each entry of `model_call.outputs.tool_calls`. It holds
what the backend sent with that call, in the backend's own shape, and the adapter returns it
unchanged on the next request. Gemini puts a `thoughtSignature` there; both OpenAI-dialect
adapters send nothing and write no key.

**Why a per-call field rather than the two cheaper alternatives.** `Reasoning.blocks` exists
for exactly this shape and is per turn, while the signature is per function-call part, so a
turn carrying two calls would need them re-attached by position; the loop also carries only
`reasoning.text` into the conversation, so blocks would have had to start travelling as well.
An adapter-private map from tool-call id to signature needs no format change at all, and breaks
on resume: a second process rebuilds the conversation from `suspension.json` with an empty map
and is answered `400: Function call is missing a thought_signature`. **A value the backend
requires back has to survive being written down**, which is the argument, and it is the same
one `simple-agents.md` §2.5 makes for `Reasoning.blocks` in the first place.

**What the bump cost, counted rather than estimated: nothing was re-recorded.** The key is
absent where the backend sent none, so every conversation an OpenAI-dialect adapter builds is
byte-identical to one built before the field existed and no cassette key over a message list
moved. `ToolCallRequest` gained `to_record` and `from_record`, and the four sites that had each
built the dict by hand now go through them: the assistant turn in `nodes.py`, the `model_call`
record, `encode_model_response`, and the suspension state's `pending` and `remaining`. Beyond
that: `FORMAT_VERSION`, three version assertions in tests, and `docs/trajectory-format.md`
§4.1.4.

**One defect fell out of the same corner and predates this.** `decode_model_response` rebuilt
every token count with `tokens.get(name, 0)`, so a count stored as `Unknown` came back as a
plain mapping and the first sum over the counts raised `TypeError`. No cassette had ever held
one, because vLLM reports an unknown count only without `--enable-prompt-tokens-details`. The
new backend reports one on every call.


## 0.19 — a subtask a model chose (the pipeline-as-a-tool item, 2026-08-10)

**What it settled.** How a pipeline reached by a model call rather than along an edge appears in
a trajectory, and how the n executions it produces under one set of node ids are told apart.

**A fifth record type, `delegation`**, and `node_execution` gains a `parent_id`. Two changes, one
of them additive and one not: a new type is additive, and `parent_id` was hard-coded `null` on a
node record and the shipped document stated that as an invariant.

**Why a fifth type rather than a `tool_call`, which was cheaper.** The whole argument is one
field. A `tool_call` carries a `side_effect_class`, which `docs/tools.md` §1.4 defines as
declared by the author and never inferred, and which is what `simple-agents.md` §4.4's refusal
reads. A pipeline declares none: its effects are its tools', each declared and recorded
separately. Writing `null` there, or deriving a class from the tools inside, puts a value the
FT-19 spine treats as a declaration into a record where nobody declared one. Everything else
about a `tool_call` fitted — `tool_version` could have been the worker's `graph_fingerprint`,
and `spent: null` would have kept `tool_spend()` correct.

**What the bump cost, counted rather than estimated**: `RECORD_TYPES` in
`conformance/checks.py`, `PAYLOAD_FIELDS` in `trajectory.py`, `per_node._count`, five sentences
in `docs/` that said "four record types", `docs/trajectory-format.md` §1.2's table and a new
§4.4, and `simple-agents.md` §6 including the callout that exists to stop a reader pairing record
types with node kinds. That callout needed the most care: a type named after a pipeline makes the
misreading *more* tempting, so it gained a paragraph saying so directly.

**Why `parent_id` on a node record, given that it broke a stated invariant.** With n subtasks
sent to one worker, the n sets of executions share their node ids, because a node id names the
node and a `record_id` names the execution — which is the rule a bounded cycle already follows.
Without a parent, separating them means bracketing `sequence` between consecutive `delegation`
records and knowing that a parent is written after its children. That works, is fragile, and was
documented nowhere. With it, "what ran inside subtask 2" is a query.

**What it did not break.** `per_node._owners` walks `parent_id` up to the first node record, and
a node record is itself one, so the walk stops at step zero and every existing figure is
unmoved. That was checked before the change rather than after.


## 0.18 — what a fan-out carried past itself (the DF2-D1 sitting, 2026-08-09)

**What it settled.** Whether a value that arrived beside a fanned-out sequence has any way to
reach the node after it, given that a fan-out node's output is the outcomes and nothing else.

**A fan-out's `outputs` gain `kept`**, an object keyed by the input key each value came from,
present only where the node declared `keep=`. A record from a node without one is unchanged, so
this is additive in the strong sense: nothing already written reads differently.

**Why the record carries it at all, given that it is a copy.** What `kept` holds is also in the
previous node's `outputs`, so a reader could follow the edge back. Recording it is what makes
the *reading* node's `inputs` hold the value it used, which is the property a value routed
through the workspace breaks (`docs/pipeline.md` §3) and the property this whole sitting is
about. A pointer would have made the fan-out the one edge in the graph a reader has to resolve
by hand.

**What it is worth.** Measured on dogfood #2: three of its four off-graph workspace files cross
one fan-out and are read at the node straight after it, totalling 3,726 bytes. The blanket
alternative, a fan-out passing its whole input through, costs 146,305 bytes on the same run
because the pages it fanned out over travel with it.

**What it cost.** One optional key. No cassette was invalidated: the key is computed from the
request, and this changes only what a record carries.

## 0.17 — what a tool call spent (the DF2-D2 sitting, 2026-08-09)

**What it settled.** Whether the money figure on a `tool_call` record says what the call was
worth or what the tool charges, given that they differ on a quarter of the paid calls anyone
has recorded.

**The `tool_call` record gains `spent`**, `null` where the call cost nothing, and
`{currency, amount, source}` where it did. `declared_cost` is unchanged and stays the
declaration in force.

**Why a second field rather than a correction to the first.** `declared_cost` is what the tool
declares and belongs on every call it made, the way `side_effect_class` does; a reader asking
what the tool costs still gets an answer on a call that was replayed. What was missing is a
field a total can be summed over. Zeroing `declared_cost` on a free call would have made a
genuinely free tool and a cached call indistinguishable.

**What it is worth.** Measured on dogfood #2: 354 paid tool calls declaring $1.770, of which
263 reached a vendor and $1.315 was spent. Of the $0.455 difference, $0.155 is calls that
errored or were replayed, both already knowable from fields on the same record, and $0.300 is
cache hits, which reach `spent: null` through the same rule once the library's own `UrlCache`
is the one in front of the tool.

**`source` exists because the meter is coming.** The DF2-D2 sitting settled that a tool reports
what it was charged, so the field has to say whether a figure is the declaration or the tool's
own report. Adding it now costs one key and avoids a second bump.

**What it cost.** One field. No cassette was invalidated: the key is computed from the request,
and this changes only what a record carries.

## 0.16 — what a call spent waiting (dogfood #1 run 2, 2026-08-07)

**What it settled.** Whether a reader of a trajectory can separate the time a call spent working
from the time it spent waiting to be allowed to call.

**The `model_call` record gains `held_back_ms`.** `ModelResponse.held_back_ms` has carried
retry backoff and `PacedClient` pacing since the D2 fix off run 1, and `max_wall_clock` has been
charged the call without it since then. Nothing wrote it down. The record's timestamps bracket
the whole call, waiting included, so a project asking how much of an evaluation was waiting had
the aggregate and no split.

**Why it is one field rather than two.** Backoff and pacing are the same thing to the budget and
to a reader: the call was not being served. Which of them held it back is answerable from
`rate_limit` on the same record, and splitting the field would put the adapter's internals into
the format.

**What it cost.** One field. No cassette was invalidated: the key is computed from the request
the library builds, and this changes only what a record carries.

## 0.15 — trajectory volume in production (item 8b, 2026-08-06)

**What it settled.** How a project bounds what its trajectories accumulate without turning
recording off, and what a record says when a payload was not kept.

Three changes, and only the first is what the item was scheduled for.

**Every record gains `omissions`**, a sibling of `redactions` naming the payload fields this
run dropped. The value written in their place is `{"type": "not_recorded", "reason": ...}`.

**The `{"type": "unknown"}` convention could not carry it**, which `plan.md`'s entry assumed it
could. Run rather than argued: a payload nulled that way is counted by
`per_node.absent_outputs` and decoded by `decode_answer` into an `Unknown`, so it reads as a
node reporting that it did not find the value. That number reaches a project's results file.
`null` was unavailable too, since §3 already gives it two meanings on `outputs`. The build log
§1.8 has the table.

**`model_call.params` loses `tools` and `output_schema` and gains `tools_ref` and
`output_schema_ref`.** The blocks move to the manifest's `schemas` under those references. This
is §6's own rule, that a value the same for every record in a run belongs in the manifest,
applied to a field that had escaped it: measured at 87.9% repetition across 74 recorded calls,
and one distinct value across the seven calls of a six-turn production run.

**The cassette key is untouched.** `ModelRequest.params_for_record` fed both the record and the
key and is now split, with `params_for_key` unchanged. Every committed cassette replays and
none was re-recorded, which the build log §2.1 verified against fourteen readers before the
change was made.

**§1.1 changed, on Thilina's sign-off.** Payloads are written in full and dropped when the run
closes, so the writer does rewrite the file once. The alternative, deciding at write time,
cannot see the run's outcome, and the outcome is what keeps an errored run's payloads.

**What it cost.** 7 existing tests, 37 added, 81 fixture trajectories and 90 fixture manifests
migrated. No cassette re-recorded.


## 0.14 — reasoning output (item 8f, 2026-08-05)

**What it settled.** Where a chain of thought belongs in the record, and what a field for it
has to be able to hold.

`model_call.outputs` gains `reasoning`, an object with `text` and `blocks`. **It went inside
`outputs` rather than beside it**, and that was the cheapest decision in the item: `archive/plan-history.md`
§3.1 item 8b samples `inputs` and `outputs` and nothing else, so putting reasoning anywhere
else would have made 8b's design need amending for the largest payload the record carries. A
trajectory sampled at 1% now drops chains of thought with everything else.

**`blocks` is filled by no shipped adapter and ships anyway**, on an exception Thilina granted.
Anthropic's thinking block carries a `signature` that has to go back verbatim and a
`redacted_thinking` variant with no text at all; OpenAI's Responses reasoning item carries an
`id` and `encrypted_content`. A string holds none of them, and both are the next adapters in
`plan.md` §2.2. The alternative was a second bump and a second re-recording once one of them
exists. Its shape rests on those providers' published SDK types rather than on a call, which is
recorded in `build-logs/item8f-build-log.md` §1.9 and is to be measured when the adapters land.

`stream` gains `reasoning_chunks`. **`first_chunk_ms` was left measuring content**, on Thilina's
call: changing what it means would make every recording made before this incomparable with
every one made after, and a reasoning model's gap before its first answer token is derivable
from the two figures side by side.

**What it cost.** Every committed cassette was re-recorded, all fifteen. That was not forced by
the format: an entry written before this decodes `reasoning` as `null`, which is what a backend
reporting none produces. It was forced by the *recording configuration*. Every vLLM cassette
had been recorded against a server started without a reasoning parser, so its chains of thought
sat inside `content`, and the fix this item ships is invisible under that setup. Re-recording
under `--reasoning-parser qwen3` is what makes the shipped cassettes exercise the field.

Five figures in `test_adapter_integration.py::TestEvaluation` moved, because a fresh recording
is a fresh set of answers: accuracy `4/9` to `5/9`, recall `1/6` to `2/6`, 20 tool calls to 22,
27 model-call entries to 31. **The properties each test demonstrates survived**, which is the
only reason the numbers were updated rather than the recording rejected: the rollout-variance
test still has variance to show, and now on two examples rather than one.

## 0.13 — streaming (item 8e, 2026-08-04)

**What it settled.** Two things: what a streamed call is worth recording, and that a suspension
is not a failure.

- `model_call.stream`, an object carrying `chunks` and `first_chunk_ms`, `null` on a call that
  did not stream. The alternatives were a bare boolean and nothing at all. **Time to first
  token is the reason streaming is adopted and is derivable from no other field**: `started_at`
  and `ended_at` bracket the whole call. A boolean would have cost the same bump and recorded
  the one thing that was already inferable from the manifest's node entry. `chunks` earns its
  place separately: an entry showing one chunk is a backend or an adapter that buffered, which
  is the "a configured control that never fired" shape this project keeps finding by making the
  thing visible in a file.
- **`error.class` gaining `suspended`**, which is not streaming's and was found tracing the path
  item 8d opened. `_call_model` catches `Exception` and emits a failed-call record before
  re-raising, so a `Suspend` raised from a `ModelClient` was recorded as `caller_facing` while
  item 8d had deliberately decided the opposite for the tool path. Anything counting
  caller-facing failures over a trajectory over-counted every suspension. Nothing was lost, only
  mislabelled: the node record already carried `termination: "suspended"`.
- **A streamed call that stops part-way records what was delivered.** `outputs.content` holds the
  text that reached the end user and `stream.chunks` says how far it got. Those pieces cannot be
  recalled and the resumed run makes the call again from the start, so a record showing `null`
  outputs would describe a call nobody made.

**What it cost.** Three test transcriptions, all of them the conformance check and the manifest
check working: `MODEL_CALL_FIELDS` gaining `stream`, the version assertions, and one manifest
node entry. Cassettes did not need re-recording, because `stream` on an entry is optional and an
older file replays as one piece.

## 0.12 — suspend and resume (item 8d, 2026-08-04)

**What it settled.** A run that stops and continues in another process leaves records that say
so, and a question asked in one process and answered in another is not one record.

- `node_execution.resumed_from`, and `termination` gaining `suspended`. The suspended
  execution has to write a record before the process ends, or a run that is never resumed
  leaves its `model_call` and `tool_call` records pointing at a `node_execution` that was never
  written. That was found by testing for it rather than by design: the sitting had the
  suspended record as an observability nicety, and it is a structural requirement of the
  parent-child invariant.
- `consultation` becoming two records joined by `answers`, and `resolution` gaining `pending`.
  Three shapes were considered. One record written on resume leaves a never-resumed run showing
  no sign that anything was asked. Amending the record in place gives up the append-only
  property that makes a crashed run leave a readable prefix. Two records keep both, at the cost
  of a reader having to count the ones where `answers` is `null`.
- `blocking` was already on the record and had never been anything but `true`. It is `false` on
  both records of a suspended consultation, which is what it was written for.

**What it cost.** Version strings in `docs/trajectory-format.md`, the `NODE_FIELDS` set in
`tests/test_trajectory_conformance.py`, and one assertion in `tests/test_run_envelope.py`. No
cassette needed re-recording: the bump adds fields to records and changes nothing a cassette
key is computed over.

## The versioning policy this replaces

The old §1.4 stated it in the shipped document, which is where it did not belong:

> While the format is pre-adoption, breaking changes are permitted. Each one bumps the version
> and gets an entry in §9. Once real projects depend on the format, changes become additive by
> default and a breaking change requires the same explicit written argument as any other
> settled decision.

That is still the policy. What is load-bearing is that a record is always self-describing and
that a breaking change is visible and deliberate rather than silent: a reader who finds a
trajectory on disk can tell from any single line which version wrote it, and therefore how to
interpret it. Freezing the schema outright would only lock in decisions made before anything
had been built against them.

## The table

| Version | Date | Change |
|---|---|---|
| `0.1` | 2026-07-26 | Initial. Pre-adoption: breaking changes permitted with a version bump and an entry here. |
| `0.2` | 2026-07-26 | Dual-backend model seam. `model_call` gains `backend`, `model_revision`, `concurrent_requests`. Cost gains a `compute` basis alongside `price`, with concurrency-aware attribution. Cache fields marked provider-conditional. **Breaking:** three new required fields on `model_call`. First use of the pre-adoption clause, and deliberate. |
| `0.3` | 2026-07-26 | Cassette replay. `model_call` gains `replayed`, which `tool_call` already carried: without it a trajectory cannot distinguish a call that was recorded live from one that was served from a cassette, and FT-21 reads exactly that. **Breaking:** one new required field on `model_call`. |
| `0.4` | 2026-07-26 | The token split when a backend does not report one. The three input counts are disjoint, and where only the prompt size is available it goes in `input_uncached` with the two cache counts `unknown`. **Breaking in interpretation, not in shape:** no field is added or removed, but `input_uncached` in a `0.3` record cannot be read as "processed at full price" without knowing which convention wrote it, which is what the version now says. Measured against Mistral and against vLLM with and without `--enable-prompt-tokens-details`. |
| `0.5` | 2026-07-27 | The context builder. `model_call` gains `context`: which builder produced the messages, what it left out, and the basis of any pre-flight estimate. FT-17 requires a truncation policy to record a truncation event, and before this there was nowhere to record one. **Breaking:** one new required field on `model_call`. |
| `0.6` | 2026-07-27 | Model calls made inside a tool. `parent_id` is redefined from "the `node` record this belongs to" to "the record this happened inside", so a `model_call` made by a tool hangs off that `tool_call` and its tokens are attributable to the call that caused them. `tool_call` gains `re_executed`, without which a replayed run cannot be told from a live one for a tool the cassette does not store. A tool call's cassette key also gains an occurrence count, which changes no field but invalidated every cassette holding tool calls. **Breaking:** one new required field on `tool_call`, and a changed meaning for `parent_id`. |
| `0.7` | 2026-07-28 | `model_call` gains `rate_limit` and `provider`. A backend that publishes its remaining per-minute allowance was reporting it on every response and the library was discarding it, so a project pacing a batch had to estimate a figure it had already been given. `provider` carries what the library does not read itself, so a builder needing something the seam does not name is not blocked on the seam growing a field for it. **Breaking:** two new required fields on `model_call`. |
| `0.8` | 2026-07-30 | Naming, at the document review. The `node` record type becomes `node_execution` and `seq` becomes `sequence`. **Breaking:** a reader matching `record_type == "node"` or sorting on `seq` reads neither. See "The `node_execution` rename" below. |
| `0.9` | 2026-08-03 | `model_call` gains `recorded_duration_ms`, carrying how long the live call took on a call served from a cassette. Compute-basis cost is `duration × rate`, and a replayed call returns in microseconds, so **any offline evaluation of a self-hosted agent under a compute basis reported a cost near zero with nothing marking it**. Found at the context-document review, asking whether a documented limitation was a decision. It was an omission. **Breaking:** one new field on `model_call`; a cassette recorded before it reports cost unknown rather than near zero. |
| `0.10` | 2026-08-03 | The `context` object's `builder` becomes `context_builder`, matching the manifest. See below. |
| `0.11` | 2026-08-04 | The graph, at item 8c. `node_execution` gains `route` and `loop`, `termination` gains `skipped` and `max_iterations`, `outputs` is `null` on a skip, and `inputs` gains two tagged shapes for a join and for a node reached through an error edge. A fan-out's `outputs` becomes one entry per input item. **Breaking:** four ways, listed in `CHANGELOG.md`. See "`0.11`: what the graph cost the record" below. |
| `0.29` | 2026-08-28 | What the run was given. A seventh record type, `run_start`, carrying the run's `inputs` and `seed`, written before the first node. Every other record is written when the thing it describes finishes, so a run whose process was killed inside its first node recorded what it was given nowhere. **Breaking:** a seventh record type, which a reader validating `record_type` against a fixed list refuses. |

## The `node_execution` rename, and why the counter-argument lost

Thilina asked why the collision between the `node` record type and "node" the pipeline element
was called deliberate in the shipped document, and observed that the passage existed to justify
it. It did, and it contained no rationale.

The argument for renaming is consistency: `model_call` records a model call, `tool_call` records
a tool call, `consultation` records a consultation. Each names the *event*. `node` named the
thing the event happened to. `node_execution` names the event.

The counter-argument offered was that `node` reads correctly in the field it sits in
(`record_type`), that queries stay shorter, and that the rename costs a version bump plus ten
test files. He called that lazy, and he was right: it is inertia, and a breaking change in a
library that nothing depends on yet is cheap by definition. **A cost of change is not an
argument about which name is correct.**

`step` was considered and rejected: it already means one model call, which is what `max_steps`
counts.

**What it cost, measured:** six places in `src/`, 33 across nine test files, two example records
and one table in the shipped document, and a manifest bump to `0.4` because `counts` is keyed by
record type. No cassette needed re-recording, since a cassette holds responses rather than
trajectory records.

## `0.10`: `builder` becomes `context_builder`

Taken at the `docs/context.md` sitting, 2026-08-03. The manifest recorded
`nodes[].context_builder` and the record recorded `context.builder`, for the same object. He
was asked whether to fix the prose alone or the field too, and took both: **the cost of a
pre-release rename is a constant and an inconsistency is permanent.**

The counter-argument offered was that `context.builder` is unambiguous at its only reading
site, since the object it sits in already says which builder is meant. That is true and it is
the same shape of argument the `node_execution` rename lost on: it describes the cost of not
changing, not which name is correct. `record["context"]["context_builder"]` stutters slightly
and was raised as such; he took it anyway, for one grep across both artifacts.

**What it cost, measured:** one write site in `nodes.py`, five test assertions across two test
files, the version constant, and three lines of `docs/trajectory-format.md` plus its example
records. **No cassette was re-recorded**, because a cassette stores requests and responses
rather than trajectory records. Worth carrying into the next bump: a rename inside a record is
cheap in a way a change to a request is not, and the two get costed as though they were the
same thing.

## `seq` → `sequence`, and a claim that did not survive checking

The first recommendation was to keep `seq`, on the argument that it is an established
convention in log and telemetry records. Thilina agreed conditionally: only if that were
truly established.

Checking it: the *concept* is universal, the *spelling* splits by format type. Wire and
internal log formats abbreviate (TCP's header field, journald's `__SEQNUM`, Elasticsearch's
`_seq_no`). CloudEvents, which is the nearest analogue here in that it is an event-record
document format carried as JSON, spells it `sequence`. OpenTelemetry has no equivalent field
at all.

So the claim held for the idea and only partly for the abbreviation, which is not strong
enough to defend a name a reader found unclear. With `0.8` already breaking for
`node_execution`, spelling it cost nothing extra and avoided a second break later.
`RunContext.next_seq()` was renamed `next_sequence()` in the same pass, since leaving it would
keep the abbreviation in the Python API, which is where the original question pointed.


## `0.11`: what the graph cost the record

Item 8c. The full list of changes is in `CHANGELOG.md`; what follows is what each one settled.

**`route` exists so the executed path is read rather than inferred.** Which nodes ran is
visible from which records exist, but which node handed its output to which is not, and with a
route selecting among several successors that is the question a reader has. The declared graph
is in the manifest and the taken edges are in the trajectory, so the two together separate what
was possible from what happened.

**`loop` replaced `visit`, which item 8c had asked about.** As a bare integer it does not earn
its place: outside a cycle it is always 1, and inside one it has two readings, the executions of
this node in this run and the iteration since the cycle was last entered. Only the second is
undecidable from the file, because the counter resets per entry. The object carries the loop it
belongs to, the iteration, the bound, and whether the bound was reached.

**`termination` could not take `max_iterations` unconditionally, which is the one place item 8c
did not hold.** It says the final iteration's record carries that value. True for a
`Deterministic` or `LLMNode` closing a cycle, whose `termination` was `null`; false for an
`AgentNode`, which always sets its own and would lose `finish` to an overwrite. The node's own
reason wins where it has one, and `loop.exhausted` is the signal on every kind.

**The two tagged `inputs` shapes exist because a bare mapping is ambiguous.** A join's input is
a mapping keyed by source node, and so is the output of any `Deterministic` node that returns a
dict. Tagging is one key and removes the guess.

**A join distinguishes "did not fire" from "answered absence" by a flag, not by the value.**
Item 8c settles that a join delivers `Unknown` on an edge that did not fire, which collides with
`unknown` being a first-class value a node can return. The delivered value is still an
`Unknown`, as it says, and `absent` is what names the edges that did not fire.

**The fan-out record caught up with an API change from `0.10`.** `FanOutResult.values` was
removed then for returning a list of successes that mispairs against the input sequence, and the
record kept exactly that shape: a `values` list without indices beside a `failures` list with
them. Raised by Thilina while reading the `0.11` field table. It is now one entry per input item
in input order, each carrying `value` or `error`. **The lesson is that a fix applied to one
surface has to be checked against the other two**, since the same reasoning applied to the
record the whole time and nothing surfaced it.
