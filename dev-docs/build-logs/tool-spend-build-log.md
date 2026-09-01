# Tool spend — the DF2-D2 sitting, and the build

**Sitting held 2026-08-09.** DF2-D2 was open from dogfood #2 and `archive/dogfood-absorption.md`
items 6 and 7 stopped at the line it owns. Nine decisions, all Thilina's, all recorded in
§2. Baseline 1344 tests.

---

## 1. What was measured, before any design

All figures from dogfood-2's 18 runs, dogfood-1's and run 2's 1,109 manifests, and two probe
runs against the library as it stands.

### 1.1 The declared figure is 1.35× the true one, not 6×

`runs/dogfood-2/findings.md` DF2-D2 put the true spend "near $0.19". No artifact supports it.

| Source | Live searches | At $0.005 |
|---|---|---|
| `BUILD-LOG.md`, the 11 runs it prices | 199 | $0.995 |
| The 18 trajectories | 263 | **$1.315** |
| Declared across those runs (354 paid calls) | — | $1.770 |

The 246-call subset the finding cites is the record-mode runs before the 22:55Z pin: 191 of
them reached the provider, $0.955 against $1.230 declared.

**Method.** A paid call returning in under 0.2s never reached the network. Not assumed: it
matches the build log's stated live-search count exactly on all 11 runs that state one
(2, 12, 3, 11, 12, 24, 17, 24, 22, 36, 36), and 263 live calls equals the 263 files in
`runs/dogfood-2/cache/search/`.

### 1.2 The artifacts account for 35% of the money

Model spend across the 18 runs is $0.697 and tool spend $1.315, so **tool spend was 1.9× model
spend** and appears in no artifact. On `run_3af779ccfd7d`, the run `check` certifies after
DF2-D4's fix, `totals.cost` reports $0.0995 against $0.180 of true tool spend: **the manifest
reports 36% of what the run cost**, carrying `is_upper_bound: false` and nothing saying it is
partial.

### 1.3 Every dollar of the overstatement is a state where nothing was bought

| | calls | declared |
|---|---|---|
| Reached the provider | 263 | $1.315 |
| Served from the project's cache | 60 | $0.300 |
| Refused, nothing done | 19 | $0.095 |
| Replayed from a cassette | 12 | $0.060 |

`replayed` and `error` are fields the library wrote on the same record. The cache became the
library's at absorption item 7.

### 1.4 The same cache hit is counted correctly and priced wrongly

Two probe runs against the library as it stands, one live call and one cache hit each:

```
read_page  ×2  ->  manifest fetch_policy: {"max_fetches": 10, "fetches": 1}
web_search ×2  ->  two tool_call records, each declared_cost.per_call 0.005
                   totals.cost 0.000315 (model only), max_cost 0.50 bound nothing
```

`docs/tools.md` §4.5 already states the rule for the count: nothing served from the store is
charged against `max_fetches`, because nothing was requested.

### 1.5 `max_cost`'s bounded-figure path has never executed

1,127 manifests across the three dogfoods: **every one declares a `price` basis**,
`is_upper_bound` is false on all of them, `max_cost` was set on 541 runs and fired zero times.
`max_wall_clock` fired 18 times and `max_steps` once. `is_upper_bound` is discarded at the
charge site (`nodes.py:1432` passes `cost.value`) and reaches the manifest only.

---

## 2. The sitting, 2026-08-09

| | Decision |
|---|---|
| **1** | The corrected figures stand. DF2-D2 and §9.1 are rewritten |
| **2** | Stop writing `declared_cost` on a call that bought nothing, shipped independently |
| **3** | A tool reports what it spent, through an injected meter. `re_executed` splits from `handles` |
| **4** | Tool spend is bounded — see 9, which supersedes the separate-ceiling reading |
| **5** | A declared per-call ceiling is checked before the call and the actual recorded after; where no ceiling is declared, allow and record, overshoot bounded by one call, and the manifest says which runs had an exact cap |
| **6** | §2.3's upper-bound enforcement reopens now rather than in its own sitting |
| **7** | The figure appears in the manifest, `report()` and `compare()`, with no interval. No conformance check until a second project has a metered tool |
| **8** | `max_cost` is not enforced against a figure known to be a bound. `report_concurrency` defaults on for `VLLMClient`; a warning at run start; the first bounded call ends the run. The capability-declaration variant was rejected as over-refusal bought with a Protocol change |
| **9** | Tool spend depletes `max_cost`. One axis for all money, viable because 8 makes it exact wherever it fires. The count ceiling `HostPolicy.max_fetches` stays alongside |

**Why the handle refusal did not reach a meter.** `Tool.handles` meant two things at once: the
library fills this parameter, and this tool is not keyed in the cassette so its body re-runs on
replay (`tools.py:300`, `re_executed = bool(self.handles)`). The refusal at `tools.py:278` was
guarding the second and naming the first. `ModelHandle` needs re-execution because a filed tool
writes no nested `model_call` record on replay (`simple-agents.md` §8.2), and `Workspace` needs
it because the files must exist for a later step. A meter needs neither: it writes a run-local
counter, and on replay it should read zero, which is the ruling already made for
`fetch_policy.fetches` in `absorption-items4-7-build-log.md` §3.2.

**Thilina's standing note on proportionality.** A local vLLM server is an unlikely place for
anyone to care about a dollar figure, and an hourly rate on hardware you own is invented. The
compute basis is for a rented device. `max_wall_clock` is the exact bound on a machine you own,
needs no basis and no concurrency, and fired 18 times in the dogfoods where `max_cost` fired
none. This is a documentation consequence rather than a code one.

**Build order.** 1 — the `declared_cost` correction. 2 — `is_upper_bound` at the enforcement
site, the vLLM default, the warning and the refusal. 3 — the meter and the per-call ceiling.
4 — tool spend into `max_cost`, the currency check, the relaxed no-basis refusal. 5 — the
manifest total, `report()`, `compare()`, and the shipped-document consequences.

---

## 3. Step 1 — what a call spent, built 2026-08-09

**Two fields rather than one corrected field.** `declared_cost` stays the price and stays on
every call the tool made, which is what a reader asking what the tool charges needs on a call
that was replayed. `spent` is the bill: `null` where the call cost nothing, and
`{currency, amount, source}` where it did. Zeroing `declared_cost` instead would have made a
genuinely free tool and a cache hit indistinguishable, and nulling it would have collided with
the existing meaning of `null`, which is that the tool declares no price.

**`source` was added now rather than at step 3.** The meter is decided, so the field has to say
whether a figure is the declaration or the tool's report. One key now, against a second format
bump later.

**Where the rule lives.** `_spent_record(tool, replayed=, failed=)` in `nodes.py`, called at the
three sites that emit a `ToolCallRecord`. *Superseded at step 3 by `_Metered`, which holds the
same rule as its declared-price branch and adds the measured one.* The resumed-delivery site
passes `None` outright: the call was made before the run suspended, so this process bought
nothing and the earlier process's record holds what it spent.

**A tool charged for work that then failed is recorded as having spent nothing.** The
declaration cannot know, and the meter is what answers it at step 3. Stated in the docstring
rather than left to be discovered.

### 3.1 Verified against dogfood-2's own trajectories

The shipped rule, applied to the 354 paid calls in 18 runs it was designed from:

```
declared, as before the change : $1.770
spent, under the shipped rule  : $1.615
true                           : $1.315

reached the provider                     263
cache hit (project's, still counted)      60
errored                                   19
replayed                                  12
```

$0.155 of the $0.455 error is gone, which is what §2 decision 2 predicted. The remaining
$0.300 is the project's own cache, invisible from outside the tool body; it closes at step 3,
when a tool can say a call bought nothing.

### 3.2 Doc consequences

| Document | What changed |
|---|---|
| `docs/trajectory-format.md` §4.2 | The `spent` row, what `source` means, and that a total sums `spent` |
| `docs/tools.md` §1.5 | The price against the bill |
| `CHANGELOG.md` | One `Added`, trajectory `0.16` to `0.17` |
| `design/trajectory-format-changelog.md` | `0.17`, and why it is a second field |

### 3.3 Tests

**1344 to 1350.** `tests/test_tool_spend.py`, six: a call that reached the provider, the
declaration surviving on a call that did not, a failed call, a replayed call against a live
one recorded from the same pipeline, a tool with no declared price, and the DF2-D2 arithmetic
in miniature. `tests/test_trajectory_conformance.py`'s symmetric difference caught the new
field before any of them were written, which is what that test is for.

---

## 4. Step 2 — a cost limit against a figure that is a bound

**`is_upper_bound` now reaches the decision.** It was computed in `cost.py`, written to the
manifest, and dropped at `nodes.py`'s charge site, which passed `cost.value`. The run now ends
on the first bounded call where `max_cost` is set, and the message names
`report_concurrency=True`, `max_wall_clock_ms` and `max_cost=None` as the three ways out.

**`VLLMClient.report_concurrency` defaults to `True`.** The sample already ran on a thread
joined inside the call, so it costs one local request and no latency. This removes the bound
for the only self-hosted adapter that ships, which is what makes the refusal rare rather than
routine. The capability-declaration variant §2 decision 8 rejected would have refused every
hand-written adapter for a fact that arrives in a response rather than in a signature.

**A warning at run start**, before any call, so a builder setting `max_cost` under a compute
basis reads it having spent nothing.

**One test asserted the old default and became two.**
`test_the_field_stays_null_unless_the_flag_is_set` is now
`test_the_server_is_asked_by_default` and `test_turning_the_flag_off_leaves_the_field_null`.

**The docstring length rule bit again**, on `VLLMClient`, and the fix was the same as the three
times item 5 to 7 hit it: the detail moved to `docs/model-clients/vllm.md` §5.

---

## 5. Step 3 — the meter, and splitting `re_executed` from `handles`

**`Tool.re_executed` is now a property of the handle type**, not of having one.
`RE_EXECUTED_HANDLE_TYPES` holds `ModelHandle` and `Workspace`; `SpendMeter` is a handle that
is injected and does not force re-execution. The refusal at `tools.py` keys on `re_executed and
reaches_outside_the_run` rather than `handles and ...`, so a paid tool taking a `ModelHandle`
is refused exactly as before, and a paid tool taking a meter is not.

**`SpendMeter.spend(amount)` is called after the vendor answers.** A tool holding one is
authoritative: reporting nothing means the call cost nothing. That is the only way a cache hit
inside a tool body reaches `spent: null`, and it is the $0.300 residue §3.1 left open.

**A metered tool is still served from the cassette**, pinned by a test that records and
replays the same pipeline. A replayed call reports nothing and spends nothing, which is
`absorption-items4-7-build-log.md` §3.2's rule applied to money.

**`DeclaredCost.max_per_call`** is the most one call can cost, for decision 5's option C. A
ceiling below `per_call` is refused at construction.

---

## 6. Step 4 — one axis for all money

**A paid call the limit cannot afford is refused before it is made, model-facing.** This is
where building changed the design: `BudgetExceeded` would have ended the run, and the shape
with field evidence behind it is `HostPolicy.spend_fetch`'s and dogfood-2's own provider's,
both of which tell the model to answer with what it has. The run continues, and the cap holds
without a run ever being killed for it — which is the whole of Thilina's opening requirement.

**The check is against the ceiling, not the price**, so a tool declaring `max_per_call` cannot
take the run past the limit at all. Without one the run can exceed by whatever a single call
cost beyond `per_call`, which is decision 5's stated fallback.

**Two currencies in one run are refused before it starts.** `DeclaredCost` has refused a
figure with no currency since item 7, on the grounds that it "cannot be summed across tools or
compared against a budget" — a sum that did not exist until now. The message names which tool
declared which.

**`_refuse_unauditable_cost` now fires only where a model call is reachable.** A pipeline of
`Deterministic` nodes whose only spend is a paid tool needs no basis, because the tool reports
what it was charged.

---

## 7. Step 5 — where the figure is read

| Surface | What it carries |
|---|---|
| `manifest.totals` | `tool_spend` (amount, currency, calls, source) and `charged_cost`, beside `cost` |
| `cost.tool_spend(records)` | The derivation, mirroring `total_cost` over the same trajectory |
| `NodeMetrics` | `tool_spend` and `paid_tool_calls`, no interval, since a sum is not a rate |
| `report()` | A `tool spend` column beside a renamed `model cost` column |
| `compare()` | `tool_spend` per arm, so a variant that drops a paid tool shows the difference |

Manifest `0.13` to `0.14`, results file `0.5` to `0.6`, variant comparison `0.1` to `0.2`.

**`docs/trajectory-format.md` §6 said something that had become false.** "No record carries a
cost figure" is still true of `model_call` and is not true of `spent`. The section now says
both, and why: what a vendor charged is not a function of anything the run observed, so there
is no basis to re-derive it from and the alternative is not recording it.

**The sample report in `docs/evaluation.md` §8.1 was updated by hand**, which is `CLAUDE.md`'s
standing entry about examples nothing executes. **It is now pinned**, by
`tests/test_sample_report.py`: the block is read out of the shipped document, two `NodeMetrics`
are built to match it, and the header, both node rows and the lines indented under a node are
compared whole, spacing included. Verified by deleting the new column from the document, which
fails the `hunt` row. This is the first shipped example the suite executes.

### 7.1 Verified end to end

A metered search over a cache, three calls, one limit:

```
provider reached: 2 of 3 calls
   declared 0.005   spent {'currency': 'USD', 'amount': 0.005, 'source': 'measured'}
   declared 0.005   spent None
   declared 0.005   spent {'currency': 'USD', 'amount': 0.005, 'source': 'measured'}
totals.cost         0.00042
totals.tool_spend   {'amount': 0.01, 'currency': 'USD', 'calls': 2, 'source': 'measured'}
totals.charged_cost 0.01042
```

That is DF2-D2's shape with every part of it answered: the cache hit costs nothing, the total
exists, and one figure covers the model and the tools.

## 8. Tests and checks

**1344 to 1369.** `tests/test_tool_spend.py` holds 19 across five classes and
`tests/test_sample_report.py` 5; the rest are adjustments to format-version pins and the two
vLLM concurrency tests. `prose_check` clean, and the wheel builds.

**`prose_check` caught its own new file.** The first docstring cited `plan.md`, which a test
file may not do: it is in the shipped tree and its reader has no access to `dev-docs`.

---

## 9. Two defects found afterwards, 2026-08-10

Both raised by Thilina reading the shipped code, both from this sitting, both reproduced
before being touched. Neither came from the ground-truth sitting that ran between: that one
changed `conformance/`, `envelope.py`, `manifest.py` and one line of `pipeline.py`, and left
`nodes.py` and `cost.py` alone.

### 9.1 A reported currency escaped the one-currency rule

**Step 4 made `max_cost` bound one number, and the check that keeps that number meaningful
looks at declarations only.** `Pipeline._refuse_mixed_currencies` reads each tool's
`declared_cost.currency` and the basis. `SpendMeter` was built at step 5 precisely to supersede
a declaration, and `_Metered._record` took whatever `spend(amount, currency=...)` passed.

Measured: a `SPENDS_MONEY` tool declaring USD, reporting `meter.spend(100.0, currency="JPY")`
under a USD `PriceBasis`.

```
totals.tool_spend   : {"amount": 100.0, "currency": "JPY", "calls": 1, "source": "measured"}
totals.cost         : {"value": 0.0, "currency": "USD", ...}
totals.charged_cost : 100.0        <- 100 JPY and 0 USD, added
warnings raised     : none
```

The budget then depletes against it, and says so in the currency it is not in: a second call to
the same tool was refused with *"This run's cost limit leaves 0.000000 USD"*.

**Two currencies from two tools are worse**, and this was not in the report. `tool_spend`
accumulates with `currency = currency or spent.get("currency")`, so the first currency seen
labels the sum: 100 JPY and 7 EUR come back as **`{"amount": 107.0, "currency": "JPY"}`**.
`charged_cost` carries no currency field at all, so the number the limit depletes is unitless
by construction.

`cost.py` stated the opposite as fact: "Two currencies in one trajectory are refused before the
run, so the total has one."

**What shipped.** The refusal moves to where the value enters. `_Metered._record` checks a
reported currency against the run's basis, then against an earlier spend in the same call, then
against the tool's own declaration, and names which one it disagreed with. Reporting no
currency is unchanged and is the ordinary case. Alternatives considered: removing the
`currency` parameter, which removes the class of bug but is an API removal on something a day
old; and refusing at construction whenever a `SPENDS_MONEY` tool takes a meter, which bans the
correct usage.

### 9.2 The bounded-cost refusal left a manifest contradicting its trajectory

Step 2's refusal ran ahead of the manifest's own accounting: `_refuse_bounded_cost` sat above
`observe_model`, `observe_tokens` and `run.charge`. Measured, on a compute basis with
`max_cost` and no reported concurrency:

| | |
|---|---|
| trajectory `model_call` records | 1, with `input_uncached: 10, output: 5` |
| manifest `counts.model_call` | 1 |
| manifest `models.observed` | `[]` |
| manifest `totals.tokens` | all four zero |

A reader auditing what that run spent got zero for a run whose trajectory holds the call.
Narrow path, and it breaks record-by-construction, which is the property the envelope exists
for.

**What shipped.** The refusal moves below the three `observe_*` calls and stays above
`run.charge`. Recording the call and enforcing a limit against it are different things, and
only the second was ever the objection. The run still ends with `outcome: error`, and
`totals.cost` is derived from the records at close, so the bound is now reported rather than
lost.

**Not silent, as it turned out.** A `SimpleAgentsWarning` fires at construction when `max_cost`
is set under a compute basis. It warns about the possibility; the manifest was corrupted anyway
when the refusal fired.

### 9.3 Tests

Six: one that a refused run records the call it made, and five over the currency rule — the
basis, the declaration, a second currency inside one call, the matching currency accepted, and
no currency still taking the declared one. **1417 to 1423.** `docs/tools.md` §1.5,
`docs/run-envelope.md` §4.3 and §4.4, and the `cost.py` sentence that said the opposite.
