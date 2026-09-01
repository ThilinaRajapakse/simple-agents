# Area C: tools

124 checks ran against the tool contract, the thirteen built-in modules, the registry, the
side-effect classes, `HostPolicy`, `UrlCache`, `SpendMeter` and `max_cost`, the finish check,
the grounding helpers, the cassette key, and `consult` with its typed `Reply`. 118 passed and 6
failed; nothing was skipped, including the one public-internet fetch, which reached
`example.com`. Four suites are offline and two spend money: five live runs against
`gemini-3.1-flash-lite` cost $0.0511 and confirmed that a real backend accepts the tool schemas
the library sends, including `$defs`/`$ref`, `enum` and `anyOf`, and that a real model's tool
calls round-trip through the loop, the cassette key and the trajectory. Raw rows are in
`../runs/area-c-tools-{contract,builtins,policy,consult,replay,live}.jsonl`; the scripts that
produced them are in the session scratchpad under `qa/area_c_*.py`.

## Findings

### 1. `Annotated[..., Field(...)]` on a tool parameter is discarded (major)

**Claimed.** [docs/tools.md §1.1 L61](../../../../docs/tools.md#L61): "A description anywhere in
that schema is prompt text: `Field(description=...)` on a parameter, or the docstring of a
model used as a parameter's type. The model reads it." The section then gives a worked example
with `top_k: Annotated[int, Field(description="How many to return. Above 10 crowds the turn.")]`
and closes: "Without one, `top_k` reaches the model as a bare integer with a default and
nothing saying what a good value is."

**What happens.** `top_k` reaches the model as a bare integer with a default and nothing saying
what a good value is. [`_resolved_hints`, tools.py:1069](../../../../src/simple_agents/tools.py#L1069)
calls `get_type_hints(fn)` without `include_extras=True`, so every `Annotated` metadata item is
stripped before `create_model` sees the annotation. The description never reaches the schema,
and neither does any constraint: `Annotated[int, Field(ge=1, le=10)]` accepts `top_k=400`
without a `ModelFacingError`.

The docstring of a pydantic model used as a parameter's type does reach the schema, so the
second half of the sentence holds.

**This is shipped in the built-in set.** [`web_search`,
websearch.py:100](../../../src/simple_agents/builtins/websearch.py#L100) declares `domains`
with exactly this pattern. The model is offered
`{"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}], "default": null,
"title": "Domains"}` and is never told the entries are bare hosts such as `example.com`, which
is the one thing the parameter needs said.

**Reproduction.**

```python
from typing import Annotated
from pydantic import Field
from simple_agents import SideEffectClass, tool

@tool(side_effect_class=SideEffectClass.READ_ONLY)
def look_up(query: str,
            top_k: Annotated[int, Field(description="How many to return.", ge=1, le=10)] = 5):
    """Search the catalogue."""

look_up.parameters["properties"]["top_k"]   # {'default': 5, 'title': 'Top K', 'type': 'integer'}
look_up.call({"top_k": 400})                # accepted
```

**Severity: major.** A documented prompt-surface feature silently does nothing, and the failure
is invisible: the tool builds, the contract test passes, and the model behaves worse for a
reason nothing in the run records. `scripts/prose_check.py` parses the fenced example and
resolves its names, so it passes too. Evidence: `TOOL-005` in
`../runs/area-c-tools-contract.jsonl`.

### 2. `contains_normalised` does not fold accents, and splits accented words (major)

**Claimed.** [`contains_normalised`, grounding.py:50](../../../../src/simple_agents/grounding.py#L50):
"Both sides go through `normalise_text`, so `"O₂"` matches `"O2"`, a curly quote matches a
straight one, and `"Beyoncé"` matches `"Beyonce"`." [docs/tools.md §5.3
L813](../../../../docs/tools.md#L813) repeats it: "It folds case, accents and punctuation".

**What happens.** `contains_normalised("Beyoncé sang", "Beyonce")` is `False`.
[`normalise_text`, grounding.py:27](../../../../src/simple_agents/grounding.py#L27) applies NFKC,
which composes rather than decomposes, and then
[`_SEPARATORS`, grounding.py:24](../../../../src/simple_agents/grounding.py#L24) replaces every
character outside `[0-9a-z]` with a space. An accented letter is therefore not folded to its
base letter; it is treated as a separator, which is the case the same docstring warns about two
sentences later ("Words are not joined across a separator").

```
normalise_text("Beyoncé")  -> 'beyonc'      normalise_text("Beyonce") -> 'beyonce'
normalise_text("café")     -> 'caf'         normalise_text("naïve")   -> 'na ve'
normalise_text("Müller")   -> 'm ller'
```

The result is also asymmetric, which is worse than a plain miss:

```python
contains_normalised("The café is closed", "cafe")   # False
contains_normalised("The cafe is closed", "café")   # True
```

The O₂ and curly-quote examples do hold: NFKC maps `₂` to `2` and `“` to `"`.

**Where it costs.** This backs the grounding check `docs/tools.md` §5.3 is written around. A
model quoting an accented span without the accent, which is the common direction, produces a
refusal of an answer that is grounded. The same function backs
[`_matched`, consult.py:583](../../../../src/simple_agents/builtins/consult.py#L583), so an option
written `café` is not matched by the answer `cafe` and the reply is routed as `unmatched`.

**Severity: major.** A grounding check that refuses correct answers sends debugging to the
prompt, which is the failure mode `docs/tools.md` §1.2 names for a drifted description.
Evidence: `GROUND-002` in `../runs/area-c-tools-policy.jsonl`.

### 3. A `consult` answer is never delivered to a resumed `Deterministic` node (major)

**Claimed.** [docs/tools.md §4.6 L704](../../../../docs/tools.md#L704): "Raising `Suspend` writes
down where the run got to and ends the process; the answer arrives later and `Pipeline.resume`
continues from the same point, with the agent's conversation and its spend intact." And
[L719](../../../../docs/tools.md#L719): "The answer is a second `consultation` record naming the
first." The `on_reply` example directly above, at
[L686](../../../../docs/tools.md#L686), puts `consult` on a `Deterministic` node.

**What happens.** On a `Deterministic` node the resume re-runs the node function from the top,
`ctx.call_tool("consult", ...)` calls the channel again, the channel raises `Suspend` again,
and the run suspends a second time. The answer passed to `resume(answer=...)` is never
delivered. The trajectory ends up holding two `pending` consultation records for one question
and no record with `answers` set, so a run written the documented way can never complete.

[`_FixedPointCaller`, nodes.py](../../../../src/simple_agents/runtime/tooling.py#L30) has no
resume-state path: it dispatches every declared call afresh. The `AgentNode` loop does have
one, and the same test on an `AgentNode` passes, so the defect is confined to the fixed-point
caller.

**Reproduction.**

```python
def by_email(question, options):
    raise Suspend(waiting_for=question, options=options)

def ask(inputs, ctx):
    return ctx.call_tool("consult", question="Apply the change?", options=["yes", "no"])

pipe = Pipeline([Deterministic(ask, tools=[consult(by_email)], node_id="ask")], budget=...)
try:
    pipe.run({}, envelope=env)
except RunSuspended as stop:
    pipe.resume(stop.run_id, answer="Yes.", envelope=env)   # RunSuspended again, same run
```

**Severity: major.** The two shipped examples in §4.6 and §4.6.1 combine into a flow that
cannot finish, and every existing test of consult-and-resume uses an `AgentNode`, so nothing
catches it. Evidence: `CONS-017` failing and `CONS-018` passing in
`../runs/area-c-tools-consult.jsonl`.

### 4. `Reply`'s own example is the case the default matcher rejects (major)

**Claimed.** [`Reply`, consult.py:57](../../../../src/simple_agents/builtins/consult.py#L57):

```
reply = ctx.call_tool("consult", question="Ship it?", options=["yes", "no"])
reply.chose        # 'yes'
reply               # 'Yes, go ahead'
```

**What happens.** `_matched("Yes, go ahead", ["yes", "no"], None)` returns `None`. The default
rule compares the whole normalised answer against the whole normalised option, so `"Yes."`
matches and `"Yes, go ahead"` does not. Under the docstring's own values the reply is
`unmatched`, and an `on_reply` route sends it to the `amend` branch rather than `apply`; under
`exhaustive=True` it ends the run.

**A live model produced exactly this.** In `LIVE-004` an `AgentNode` on Gemini asked the end
user to confirm an irreversible order change, offering `["yes", "no"]`. The channel answered
"Yes, go ahead." and the trajectory recorded `resolution: "unmatched"`, `chose: null`. That is
a clear approval landing in the amendment branch.

**Reproduction.**

```python
from simple_agents.builtins.consult import _matched
_matched("Yes, go ahead", ["yes", "no"], None)   # None
_matched("yes please", ["yes", "no"], None)      # None
_matched("Yes.", ["yes", "no"], None)            # 'yes'
```

**Severity: major.** The rule itself is defensible and `match=` exists for projects that want
more, but the example a coding agent reads first states the opposite of what ships, and the
common shape of a real answer falls on the wrong side of it. Either the example or the rule has
to move. Evidence: `LIVE-004` and `LIVE-006` in `../runs/area-c-tools-live.jsonl`.

### 5. A URL naming an explicit port is out of scope on a host that is in scope (minor)

**Claimed.** [docs/tools.md §4.4 L586](../../../../docs/tools.md#L586): "A subdomain of a host in
scope is in scope, so `help.example.com` is reachable under `example.com`, and a leading `www.`
is ignored on both sides." Nothing says a port removes a host from scope.

**What happens.** [`_allowed`, http.py:150](../../../../src/simple_agents/builtins/http.py#L150)
takes `urlparse(url).netloc`, which carries the port, and compares it against the configured
bare hosts. [`in_scope`, tools.py:521](../../../../src/simple_agents/tools.py#L521)
matches on the whole string, so `docs.example.com:8443` is not `docs.example.com` and is not a
subdomain of it. `allow_hosts` behaves the same way. The refusal reads as a contradiction,
naming the same host on both sides:

```
This agent may not fetch from 'docs.example.com:8443'. Permitted hosts: docs.example.com.
```

**Reproduction.**

```python
policy = HostPolicy(["docs.example.com"])
policy.in_scope("docs.example.com")        # True
policy.in_scope("docs.example.com:8443")   # False
http_fetch(policy=policy).fn(url="https://docs.example.com:8443/page")   # refused
```

**Severity: minor.** Most addresses carry no explicit port, so this bites a project reading a
site on a non-default port or a local service under `allow_private=True`. A configured host
written with its port works, which is the workaround, but nothing documents it. Evidence:
`POL-008` in `../runs/area-c-tools-policy.jsonl`.

### 6. `HostPolicy.admit` accepts a whole URL and spends an admission on it (minor)

**Claimed.** [`admit`, tools.py:532](../../../../src/simple_agents/tools.py#L532)
anticipates the mistake in its refusal for an empty host: "Pass a bare host such as
`'brand.example'`, taken from the URL rather than the whole URL." [docs/tools.md §4.4
L593](../../../../docs/tools.md#L593) shows a bare host.

**What happens.** `admit("https://brand.example/listing", reason=...)` succeeds. The whole URL
is stored as a host, `in_scope("brand.example")` stays `False`, and one of the run's
`max_admitted` slots is spent on an entry that can never match. The manifest then records an
admission that reads as though the host was reached.

**Reproduction.**

```python
policy = HostPolicy(["docs.example.com"], max_admitted=1)
policy.admit("https://brand.example/listing", reason="named on the listing")
policy.in_scope("brand.example")   # False
policy.to_record()["admitted"]     # [{'host': 'https://brand.example/listing', ...}]
policy.admit("brand.example", reason="the host this time")   # ConfigurationError: cap reached
```

**Severity: minor.** The value is checked for emptiness and for nothing else, and the failure
is silent until the next admission is refused for a cap the project did not knowingly spend.
Evidence: `POL-009` in `../runs/area-c-tools-policy.jsonl`.

### 7. `fetch_policy[].declared_by` is `null` for the pipeline the run started with (cosmetic)

[docs/tools.md §4.4 L610](../../../../docs/tools.md#L610) says `fetch_policy` is "an array, one
entry per pipeline that declared a policy, each naming the pipeline it came from under
`declared_by`". The top-level pipeline's entry carries `declared_by: null`, which
`manifest.py:86` states plainly and `docs/tools.md` does not. A reader of the shipped docs
looking for the name will not find one. Evidence: `POL-006` and `POL-007` in
`../runs/area-c-tools-policy.jsonl`.

## Everything else in this area passed

Stated once each rather than listed per check.

- **The contract.** Schema derivation from the signature, required against defaulted
  parameters, refusal of an unannotated parameter, of `*args`/`**kwargs`, and of an annotation
  naming a type declared inside a function. `parameters=` bypass, with the argument names still
  checked and an undeliverable property refused at build. The invented-argument refusal matches
  the documented sentence verbatim. `**kwargs` absorbs and is not checked. `description=`
  replaces the docstring; an empty description is refused. `side_effect_class` has no default
  and refuses a string. `DeclaredCost` refuses a figure with no currency and an inverted
  ceiling; `SPENDS_MONEY` with no per-call cost is refused; `SpendMeter.spend` refuses a
  negative amount. Handles are filled and left out of the schema; `ModelHandle` and `Workspace`
  make a tool re-run and `SpendMeter` does not; `SPENDS_MONEY`/`IRREVERSIBLE` on a re-run tool
  is refused; a workspace path escaping the root is refused model-facing and writes nothing.
  `version=` is kept, and an unset one is derived from the source and moves with the body.
- **The registry.** Refuses a non-`Tool`, a duplicate name, and `finish`; `get` of an
  unregistered name names what is registered; two registries share no namespace; a
  pipeline-level registry records an unused tool with `offered: false`; a registry passed to a
  nested pipeline is read at the top. `ctx.call_tool` records the class, version and declared
  cost; a `ModelFacingError` raises out of it; any other exception ends the run; an undeclared
  name is refused; a `ModelHandle` tool is refused on a `Deterministic` node.
- **The thirteen built-in modules.** `now`, `document_search` (including stopwords,
  `from_directory`, and an empty result rather than a raise), the three workspace tools,
  `remember`/`recall`/`memory_search` (including the refusal when the envelope declares no
  store, and the key listing on a miss), `reduce_html` (tables, `ld+json`, prose, dropped
  chrome, same-host link filtering, `order`, `max_chars`, and never raising), `http_fetch`
  (private-address refusal, relative URL, 404, robots.txt, five-hop redirect ceiling with every
  hop re-checked, `allow_hosts`, `max_chars`), `read_page` (parts under headings, the
  JavaScript-page refusal, every `http_fetch` keyword passed on), `web_search` (normalisation,
  dropping a result with no url, the `domains` capability check, `provider_options`, a provider
  that raises), `extract_to_schema` (the `unknown` requirement, the nested model call parented
  to the tool call, `re_executed`, an unparseable response failing model-facing), and the
  `ranking`/`rerank` surfaces at the depth `docs/tools.md` covers them.
- **Side-effect classes.** `reaches_outside_the_run` is true for `SPENDS_MONEY` and
  `IRREVERSIBLE` only; the class is on every `tool_call` record and in the manifest; a tool
  whose `DeclaredCost` names a second currency is refused before the run starts, and
  `meter.spend(currency=...)` naming one is refused at the call.
- **`HostPolicy`.** Subdomains and `www.`, the refusal of a policy with no hosts and of
  `max_fetches<=0`, admission and the cap, the refusal naming the reachable set, `max_fetches`
  counting requests for the whole run, and the manifest entry per declaring pipeline including
  a nested one.
- **`UrlCache`.** Serving a page across runs with its age stated, not charging `max_fetches`,
  the host checks still applying to a stored address, storing the body so a reduction change
  does not discard it, expiry on age with no eviction, `max_age_days<=0` refused, and a search
  keyed on `domains` so a scoped search is never served a whole-web result.
- **The finish check and `SpendMeter`.** A refusal reaching the model as a failed `finish`,
  `ctx.tool_calls` carrying the turn being finished, `ctx.finish_attempts` carrying the
  refusals, three identical refusals stopping the node at `termination: "finish_rejected"` with
  no output, a schema-invalid payload coming back for correction, `spent` recorded `measured`
  where the tool reports and absent where it does not, `max_cost` refusing an unaffordable call
  model-facing before it is made, and the check being against `max_per_call`.
- **`consult` and `Reply`.** Sixteen of eighteen checks: the `str` subclass and its fields, the
  four resolutions, the `consultation` record rather than a `tool_call`, cassette replay
  re-deriving `chose` from the stored text so a replay records `unmatched` where the live run
  did, `match=` and its refusal of an invented option, `on_reply` refusing a missing branch, an
  empty map and `exhaustive=True` alongside a branch, all four routes, the manifest entry
  including the waiver, an unmapped option ending the run by name, `field=`, and the pending
  record written when a channel suspends.
- **Grounding.** `same_url` and `urls_read`/`url_was_read`, including a failed call not
  counting and a query string not being mistaken for a page.
- **The cassette key.** The occurrence count per node, a description edit not changing the key,
  a version change missing with the re-record command named, and an edited body doing the same
  through the derived version. A replayed and a failed paid call both carry `declared_cost` and
  no `spent`.
- **Live, against Gemini.** The registry's wire schemas were accepted, including `$defs`/`$ref`
  for a pydantic-typed parameter, a `Literal` rendered as `enum`, and `anyOf` for an optional
  list. No handle parameter reached the request. The model chose tools, its arguments validated
  against the derived schema, the finish check saw them, a recorded run replayed to identical
  tool calls and output with the network removed, and a paid tool the model called recorded
  both its declaration and its measured spend.

## What I could not test, and why

- **`document_search` with embeddings, and the `Retrieval` handle.** `docs/tools.md` §4.1 hands
  the semantic path to `docs/retrieval.md`, which is another area's surface. The `ranking` and
  `rerank` modules were exercised only at the depth §4.1 states: which retrievers a strategy
  declares, `VectorScan`'s search and its pairing refusal, and `ModelRerank`'s order parsing.
  Fusion arithmetic, hybrid ordering, cross-encoder reranking and the cost of the model calls a
  search makes are untested here.
- **`web_search` against a real vendor.** The library ships no provider and this project holds
  no search key, so every `web_search` check ran against a provider function written in the
  test. Normalisation, the `domains` capability check and caching are covered; what a real
  API's result shape does to `_normalise` is not.
- **`http_fetch` against sites with awkward behaviour.** Redirects, robots.txt, 404s and the
  hop ceiling ran against a local server. One live fetch of `example.com` confirmed the tool
  reaches the public internet under a real allow-list. Nothing tested a site with a large
  `robots.txt`, a redirect loop across hosts, or a slow response against `timeout_s`.
- **`min_interval_s` pacing.** Verified only that the argument is accepted and passed on.
  Measuring the wait would have made the suite slow for a claim that is one `time.sleep`.
- **Concurrent tool calls sharing a turn.** `docs/tools.md` §3.1 says overlapping calls take
  their numbers from their positions before any is made, and points at `docs/pipeline.md`
  §1.12. That is area A's surface and `tests/test_concurrency.py` covers it; I tested the
  sequential occurrence count only.
- **`extract_to_schema` against a live model.** It ran against a scripted client through a real
  `AgentNode`, which exercises the `ModelHandle` path and the nested record. Whether a real
  model returns JSON the schema validates is a prompt question, not a contract one, and I spent
  the live budget on the tool-schema round-trip instead.
- **A second recording of the live cassette.** `LIVE-003` recorded once and replayed once. It
  does not show that a second live run against the same prompt produces the same calls, which
  no claim asserts and a sampled model would not satisfy.

## What I might have missed

- **Coverage of the built-ins is by claim, not by argument space.** Each tool was checked
  against what `docs/tools.md` §4 says about it and against its own docstring. A tool with an
  argument combination nobody wrote down, such as `read_page(order=("links",))` or
  `web_search(max_results=0)`, was not swept.
- **The `Field(description=...)` defect may reach further than the two places I checked.** I
  confirmed it in the derivation and in `web_search`. Any other shipped or project tool using
  `Annotated` loses the same metadata, and I did not grep the whole tree for the pattern.
- **The accent defect's blast radius.** I traced `normalise_text` to `contains_normalised` and
  to `consult`'s matcher. It is exported from the package, so other callers may exist that I
  did not follow.
- **The consult resume defect might not be confined to `Deterministic`.** I established the
  `AgentNode` path works for one suspension in one node. A delegated pipeline suspending inside
  a nested `Deterministic` node, or two nodes suspending in one run and being resumed with
  `answers=`, was not tried.
- **Trajectory shape.** I read the fields each claim names. Whether the records validate
  against the conformance schema in full is `tests/test_trajectory_conformance.py`'s job and I
  did not re-run it against my runs.
- **`side_effect_class` and evaluation.** §1.4 says an evaluation refuses to start when it can
  reach a `spends_money` or `irreversible` tool unless replaying. I checked the class is
  declared, refused and recorded everywhere the tool surface touches it; the refusal at
  evaluation start is `docs/evaluation.md` §7.2 and belongs to another area.
