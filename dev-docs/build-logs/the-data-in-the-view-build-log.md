# Build log — The data in the view

`plan.md` §1 P3-40. Started 2026-08-27, built the same day. Its record was
[`build-logs/the-data-in-the-view-build-log.md`](../build-logs/the-data-in-the-view-build-log.md#L1), whose design belongs
here now; the subsystem's design of record stays in
[`design/view.md`](../design/view.md#L1).

## 1. Before any design

- [`shapes.py`](../../src/simple_agents/shapes.py#L43) `produced_by` already resolves what a
  node produces, including a `Deterministic` node's return annotation, and the view read
  `output_schema` directly, so a fixed step that declared what it returned read as handing on
  plain data.
- [`graph.py`](../../src/simple_agents/graph.py#L692) `_invert` publishes `predecessors`, and
  `_edges_of` counts an `on_error` target as an edge, so what reaches a step is derivable
  without a new mechanism. `back_edges` is the set the drawing needed and did not have.
- [`runs_overlay.py`](../../src/simple_agents/view/runs_overlay.py#L37)
  `_stream_node_executions` filtered lines on the head and then parsed every match in full, so
  the item record's "parses only small records" was not true of the code.
- [`artifacts.py`](../../src/simple_agents/conformance/artifacts.py#L489) `_latest_results`
  and `_declared_results` are the rule the gates use to pick a results file, so the page could
  read the same one rather than inventing a rule.
- [`envelope.py`](../../src/simple_agents/envelope.py#L472) `runs` excludes an evaluation's
  rollouts unless `nested=True`, which the view's own glob already matched.
- `EvalResults.read` refuses a file written at another format version, so the page reads
  results as JSON instead: `dogfood-5-frozen` reports format `0.23` against the current
  `0.24` and would otherwise have lost its whole measure section.

## 2. Design

Four things were open in the item record. What was decided, and why:

- **What of a results file the builder reads, and where.** Both: a `measure` section with
  every figure, its definition, denominator, interval and left-out counts, and per-node
  figures on the step cards. The section carries coverage, the outcome mix, what it cost and
  every results file on record; the cards carry reach, calls, spend, consultations and the
  step's own accuracy.
- **The example-data contract.** One value per step from the newest run, 220 characters a
  field over at most eight fields, with the full length reported beside a clipped one. A
  record over a million characters is reported by its size and never parsed. Labelled with the
  run it came from, so it reads as one run's value and not as a schema. Redaction is applied
  at write time and the card says when a record carried redactions or omissions.
- **Expand-on-click.** The node opens in place with its facts as label-and-value rows: what it
  takes in and hands on, tools, where it goes, limits, the last run, what the evaluation
  measured, and one real value. The rail card keeps the schemas field by field, the recorded
  decisions, the conversation and the composer.
- **The data path.** Its own section rather than an overlay on the drawing: one row per step
  in graph order, because the question it answers is "where does this go" and a path reads
  down a page better than it reads on a graph already carrying branches, loops and error
  edges.

Weighed and not taken:

- **`foreignObject` for the open node.** It gives real text wrapping and needs a measured
  height; measuring inside a scaled `viewBox` is a second layout pass over a value that
  changes with the panel's width. Wrapping at a fixed character count is deterministic and
  the strings are ours.
- **Giving the graph the page's full width when it overflows.** It needs the rail below the
  drawing, and a sticky rail in a spanned grid row scrolls away from the graph it belongs to.
  The drawing scrolls sideways instead, and the panel says so.
- **Recomputing the baseline's interval.** `EvalResults.baseline_metrics()` bootstraps 2,000
  resamples per figure. The page reports the floor as counts, which need no interval, and a
  rate with no interval is what FT-06 refuses.

## 3. Build

Shipped: [`cards.py`](../../src/simple_agents/view/cards.py#L1) and
[`findings.py`](../../src/simple_agents/view/findings.py#L1), split out of `assemble.py`;
[`evaluation.py`](../../src/simple_agents/view/evaluation.py#L657) `read_evaluation`;
`_trace_inputs`, `_containers`, `_link_containers` and `_data_path` in `cards.py`;
`rollout_runs` and the skipped-record accounting in `runs_overlay.py`; `/api/reopen` in
`serve.py`; a rewritten graph in `template.html` with a layered column assignment, container
frames, edge labels and expand-in-place; the `measure` and `datapath` sections. A sixth
fixture, `tests/fixtures/view_projects/branching/`, with its own `record.py`. 3,203 tests.

What the build found that the design did not know:

- **A step the run skipped was reported as a step that ran.** A branch nothing reached emits a
  `node_execution` record carrying `termination: "skipped"` and no output, and the overlay
  counted every record as an execution. The first real run of the new fixture showed
  `answer_directly`, `escalate` and `apologise` each "ran 1×" on a run that took none of them.
  Counted apart now, which is the accounting the evaluation's own per-node figures already
  used.
- **An edge naming a nested pipeline pointed at nothing.** `_declared_with_graph` flattens a
  container into its children, and the container's own id stays in its neighbours'
  successors, so the drawing dropped both edges and rendered the nested steps as a component
  connected to nothing. An edge into a container now enters its first step and its last step
  carries the container's edges out.
- **The rank layout ran away on a cycle.** Ranks were computed over every successor, so
  `critique → draft` pushed both down one row per pass and the graph came out 1,400 pixels
  tall with two boxes in it. Ranks skip a cycle's closing edge, and a layered column
  assignment puts each step under the steps that feed it, which is also what makes a
  container's frame a tight box.
- **The page told the builder to run `simple-agents view —serve`.** JetBrains Mono ligates
  `--`, so every command on the page rendered with an em dash and would not work if copied.
  `font-variant-ligatures: none`.
- **The data path and the system map disagreed about direction.** The path folded a paid
  tool's resource into "writes" while the system map draws it undirected. Both follow one
  rule now, and a resource nothing gives a direction to is a finding that says which of the
  two reasons it is.
- **`_type_name` leaked `fingerprint` into the page's script**, which
  `test_no_library_internals_reach_the_builder` caught. Whether the evaluation describes the
  pipeline being drawn is computed in `assemble` now and reaches the page as `measured_here`.
- **The shape ratchet fired on eleven units.** `assemble.py` crossed the 800-line module
  threshold and nine functions grew. The package was split and the functions decomposed
  rather than the baseline raised: `scripts/shape_baseline.json` lost nine entries and gained
  one, which is `_type_name` under its new path at its old numbers.
- **`prose_check.py`'s reader exemption followed the copy.** The page's builder-facing
  sentences moved from `assemble.py` to `findings.py`, so `ADDRESSES_THE_READER` names that
  file. **The exemption itself was approved by Thilina on 2026-08-27**, having been raised
  and left unsigned at `P3-35`
  ([`the-common-language-build-log.md`](the-common-language-build-log.md#L1) §5).

**A second pass, the same day, on Thilina's rejection of the first.** *"I still don't see
anything about the actual data that the system processes."* He was right and the reading was
mine to correct: what shipped first was 220 characters of one payload written out, which for
a forty-item list is 220 characters of the first item. The data side is **how much**, and it
is computable from the same records:

- **Volume at every step**, from the keys that hold a count: `gather_candidate_pool` reads
  `survey 2,000 · pool 40` out, `judge_candidates` reads `items 40`, and `select` reads
  `rejected 32 · recommendations 8`. Over `dogfood-5-frozen`, that is 2,393 runs of eighteen
  shapes reporting what each of their steps moved, with no pipeline registered at all. This
  is `DF5-N3`'s `in: 67,353 · out: 12` made computed.
- **The shape of a value**, three levels deep, with the keys holding a collection first: a
  record of nineteen fields where two of them are the candidates and the survey is a record
  about those two, and truncating in declaration order is what hid them.
- **The example set**, `evals/examples.jsonl`, which the page had ignored: counts per split,
  absence per split, sources, the fields each example carries, and one worked example that is
  never taken from a held-out split (FT-02).
- **A resource card.** Resources were selectable and had nothing behind them. One now names
  the steps on each side and every tool that reaches it with its own description.

**And the ceiling this was designed around was wrong.** `MAX_RECORD_CHARS` was a million
characters because "a trajectory cannot be parsed, only streamed". Measured 2026-08-27: an
11.3 MB trajectory whose largest record is 2.7 MB parses all eleven of its node executions in
**0.06 seconds**. The prototype's constraint was `json.loads` over a whole file as one object,
not over its lines, and the caution was inherited without the measurement. The ceiling is
40 MB now, and the 2.7 MB record that was reported as "too large to show" is read.

**A third pass, on the builder-perspective read Thilina asked for.** Eight gaps came out of
reading the page as a builder; he took the first four into this item and scheduled the rest as
[`P3-41`](../plan.md#L1).

- **What was said, against what the code does.** Six answers have an exact counterpart in the
  code, and nothing compared them:
  [`claims.py`](../../src/simple_agents/view/claims.py#L212) `read_claims` joins each on a
  step's name and reports both sides. **This is `DF5-D7` caught by the page**: the `mid-build`
  fixture's brief now names `judge_books` as deciding for itself, and the page leads with *"You
  said judge_books decides for itself. In the code, judge_books is a model call. Nothing in the
  code does."* An answer naming no step says so rather than claiming a disagreement, because
  the join cannot read prose.
- **How every step ended.** `termination` was already on every record and only `skipped` was
  read. Each step's card now carries what its executions ended as, a step with more than one
  execution in one run reads as retried, a failure path that fired is named, and runs that did
  not complete are one sentence over the whole record. On `dogfood-5-frozen` that is *"20 runs
  of 2,393 did not complete. 13 unrecorded, 7 error."*
- **What the agent asked a person.** `consultation` records carry the prompt, the options, the
  answer, which option the rule read, who answered and whether the run waited. None of it was
  read. The section shows every question the newest run asked; an answer the channel said was
  one option and the rule read as another is reported, since the branch behind it was never
  taken.
- **What moved since the run before.** `read_runs` now reads the two newest runs of each shape
  rather than one, and compares them step by step: what each handed on, how long it took, and
  whether it ran. Measured on `dogfood-5-frozen`: 18 shapes, both runs each, 0.6 seconds.

The fixture grew a second live run and a consultation to carry all four:
`publish` asks the rota to confirm before the draft leaves, which is what the brief said the
project does. Writing it the obvious way put `reply.chose` on a reply that has none, so all six
evaluation rollouts failed on it; `docs/tools.md` §4.6.1 says to read the reply rather than the
text, and an unattended run holds the draft instead of sending it.

## 4. Verification

- **Live Gemini, twice.** `tests/fixtures/view_projects/branching/record.py` made one real
  `gemini-3.1-flash-lite` run of `triage` ($0.00014, ten steps, the research branch and one
  pass of the revision loop) and one real evaluation over three held-out examples at k=2
  ($0.0010): accuracy 83.3% [50.0%, 100.0%] against a do-nothing floor of 0 of 3,
  `classify` scoring 100% on its own through `node_matches`, `answer_directly` reached by one
  rollout in six and spending $0.004 on its paid tool, `apologise` reached by none. Both are
  committed, with paths relative to the fixture.
- **The evaluation refused to start three times before it ran**, each refusal naming the
  fix: a `spends_money` tool with no `max_spend`, a consultation with no stand-in, and a
  ceiling of 1.2 USD against a `max_spend` of 0.5. The fourth attempt died on the `NotBuilt`
  step a route reached, which is why the fixture's planned step moved to `reindex`.
- **Driven browser sessions**, Playwright over Chrome against the served fixture: opening a
  step in place, writing a comment (asserted in `comments.toml` with its snapshot), taking it
  back and finding it still on the page under "Taken back", putting it back, and reading the
  measure and data-path sections out of the rendered page.
- **A simulated run in flight**: the newest manifest reopened and its trajectory truncated to
  three steps. The banner, the three ticks and the moving step drew correctly, and a step the
  run has not reached no longer says "did not run".
- **Screenshots of all six shapes plus `dogfood-5-frozen`, light and dark.** They found the
  ligature, the rank runaway, the container frame overlapping its neighbours, a value printed
  twice where a step hands on what it was given, group headings with no counts, and the
  uppercase run id.
- **The volumes read against a real project**: `dogfood-5-frozen`'s 2,393 runs, 18 shapes,
  0.4 seconds, every step of every shape carrying what it moved. `resolve_titles` reads
  `rows 1,991` in and `rows 1,991 · resolved 1,554 · unresolved 437 · files 111` out, which
  is the kind of sentence the item existed to produce.
- **Two more live Gemini runs** of the fixture, so the run-to-run comparison and the
  consultation have real records: the newest asked the rota *"The draft from critique is ready.
  Send it?"* and was answered `send it`, and the comparison reads *"critique took 1,516 ms,
  slower than the 825 ms before it"* and *"draft handed on body 344 characters, and body 499
  characters in the run before."*
- **The claim join against a real disagreement**: `dogfood-5-frozen`'s own `DF5-D7` shape,
  reproduced in the `mid-build` fixture and asserted from the page's own sentence.
- vLLM was not started; Mistral is out of credits (`handoff.md`).

## 5. Doc consequences

`docs/view.md` §5 gains taking a thread back and putting it back, §6 gains what each step is
handed, the real value, and the data path, and a new §7 says what the evaluation shows on the
page. `docs/index.md`'s row for it and `docs/evaluation.md`'s "what to reach for" table both
point at that. `CHANGELOG.md` records all of it under "The data in the view".

## 6. Left open

- **A `Deterministic` node's `touches=` carries no direction**, so a step that plainly writes
  a resource is drawn undirected and the page has to say the direction was never declared.
  A direction on the declaration would fix it and is a `nodes.py` API change nobody has
  decided to own. **Closed at `P3-41`, 2026-08-28**, by the record rather than the
  declaration: `ctx.record_access` carries `read` or `write`, so a step that has recorded one
  is on that side and the card says where the answer came from.
  [`what-the-picture-cannot-say-build-log.md`](what-the-picture-cannot-say-build-log.md#L1).
- **A wide graph scrolls sideways.** Five columns of steps do not fit beside the rail on a
  1440-pixel window. The panel says so. Destination: nothing.
- **The sixth fixture fails seven conformance checks**, including FT-04, which is right: its
  held-out split has no example whose correct answer is absent. It is test data for the view
  rather than a model project. Destination: nothing.
- **`prose_check`'s defensive rule fires on data.** "Is that on purpose?" inside a support
  ticket tripped it, and the ticket was reworded. The rule reaches string literals in
  `tests/`, where a fixture's content is not prose. Destination: nothing, unless it happens
  again.
- **The product level is still folded into the others**, unchanged from `P3-35`.
  Destination: nothing, until a project with a real product surface meets the view.
- **Four gaps from the builder-perspective read**: cost as a shape rather than a total, the
  project's own data behind a `touches=` string, no way to open one run, and a drawing whose
  geometry encodes nothing quantitative. Destination:
  [`plan.md` §1](../plan.md#L1), the `P3-41` row.
