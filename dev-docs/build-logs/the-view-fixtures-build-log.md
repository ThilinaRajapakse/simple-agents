# Build log — The view fixtures, and what keeps them current

`plan.md` §1 `P3-58`, the first stage of [`P3-51`](../plan.md#L28), shipped under its own id
per §1's convention. Started and built 2026-08-28. The stage is the sitting's decision 8:
a generator and currency check for `tests/fixtures/view_projects/`, the frozen run named
with its reason, and the `DF5-X20` absence fixture.

## 1. Before any design

- `tests/fixtures/view_projects/` measured at manifest `0.32`/trajectory `0.27` against
  writers at `0.39`/`0.29`, results at `0.25` against `0.29`, with 3,911 tests green over
  the drift. The item record's table held the same numbers.
- Three projects hold runs: `branching` (2 runs, 1 evaluation, its own `record.py`),
  `one-pipeline` (1 run, no recorder), `many-pipelines` (1 run, generating code gone).
  Every run held its cassette inside its own directory.
- `correct_abstention` requires `expected` to be `Unknown` and the scored answer to be one
  ([`outcomes.py`](../../src/simple_agents/evaluation/outcomes.py#L1), the sorting table).
  `branching`'s suite scored `output.get("from")`, which is never absent, so no example
  could reach the outcome: the fixture gap was in the scoring, not only in the data.
- `Pipeline.rerun` cannot regenerate these runs: it refuses a record with no `run_start`,
  and the committed trajectories predate `0.29`.

## 2. Design

- **Each runs-holding project's `record.py` is the spec** (inputs, seeds, evaluation
  parameters, cassette labels), and [`scripts/build_view_fixtures.py`](../../scripts/build_view_fixtures.py#L1)
  drives it in either mode. `one-pipeline` gained one, its inputs and seed read off the
  committed manifest. Cassettes moved from inside run directories to `<project>/cassettes/`,
  one file per record, so a manifest's recorded cassette path stays resolvable after the
  runs are deleted and remade.
- **The committed records are live recordings, and offline replay is verification rather
  than regeneration.** Found by building, and the reason the first design fell: a served
  call spends nothing, so a replay-regenerated evaluation carries `paid_tool_calls: 0` and
  `tool_spend: null` however much the recorded run spent (model cost is a valuation of
  recorded usage and survives; a tool's `declared_cost` is cash and does not). Committing
  replay artifacts would leave the page's money surfaces tested by files that cannot carry
  a spend, which is `DF5-X20`'s shape for the money column. `--record` re-records
  everything live (~0.005 USD); the offline default replays each spec into a scratch copy
  and fails if a call no longer serves or the outcomes differ from the committed results
  file.
- **The absence example is scored through the project's own semantics.** `reply_source`
  maps `from == "escalate"` to `Unknown("escalated to the rota, so no reply went out")`:
  an escalated ticket produced no reply, so the answer there is an absence. `t-nonsense`
  (a gibberish ticket) routes to `escalate` and its `expected` is `Unknown`, giving
  `correct_abstention` without touching `agent.py`; a value example a model misroutes to
  `escalate` becomes `missed`, which is the true reading.
- **The frozen run is option one of the sitting's three**: `many-pipelines`' run stays as
  committed, named in the generator (`FROZEN`) and exempted by name in the currency check,
  because its staleness is the property `code_moved_since` is tested against. The check
  also fails if that run ever carries current formats, so the exemption cannot outlive the
  property.

## 3. Build

What shipped: `scripts/build_view_fixtures.py` (record and verify modes),
`tests/fixtures/view_projects/one-pipeline/record.py`, `branching/record.py` rewritten as
the spec, `t-nonsense` in `branching/evals/examples.jsonl`,
[`tests/test_view_fixtures.py`](../../tests/test_view_fixtures.py#L1) (format currency,
the frozen-run exemption and its inversion, and the `DF5-X20` page-against-report checks),
and all committed records re-recorded live: manifests `0.39`, trajectories `0.29`, results
`0.29`, runs filed under `runs/dev/<date>/` and `runs/eval/<id>/`.

Found while building, beyond the design:

- **`scripts/view_at_stage.py` subtracted the evaluation by the old flat layout only**
  (`runs/eval_*`), so a derived `build` stage kept the whole evaluation once runs were
  filed under `runs/eval/`. It removes both forms now.
- The runner refuses `Cassette.update` for an evaluation and `Cassette.record` over a file
  that already holds a recording; both refusals shaped the modes above rather than being
  worked around.
- The evaluation's worst case moved past its ceiling with the fourth example
  (4 × 2 × `max_cost` 0.2 > `max_spend` 1.5), so the spec's `max_spend` is 2.00.
- Three test files reached runs by the flat `runs/run_*` glob and missed the new layout
  entirely; they read `runs/dev/*/run_*` now. Ten count pins moved for the larger
  evaluation (8 rollouts, 4 examples, `escalate` taken 3 times).

3,923 tests, from 3,911. No format moved.

## 4. Verification

- Live: two full `--record` passes against Gemini (`gemini-3.1-flash-lite`), ~0.004 USD
  each. Both rollouts of `t-nonsense` escalated and scored `correct_abstention`; the report
  reads `correct 5, correct_abstention 2, missed 1`, floor 0 of 4, `answer_directly`
  carries `paid_tool_calls: 1`, `tool_spend: 0.004`.
- Offline: the verify mode replays all three specs from the committed cassettes in a
  scratch copy and matches the committed outcomes; run after the final recording, clean.
- The page: `branching`'s page rendered in headless Chrome and read by eye. The standing
  sentence counts the abstentions in ("scored 7 of 8 rollouts right"), the baseline sits
  beside it, and [`test_view_fixtures.py`](../../tests/test_view_fixtures.py#L125)
  `test_the_page_counts_agree_with_the_record` holds page against report on the same data.
- Full suite, `prose_check`, `shape_check`, `check_docs`, `check_citations`: clean.

## 5. Doc consequences

Nothing in `docs/` and no CHANGELOG entry: fixtures, tests and scripts only. One statement
in the item record stopped being true and is corrected there: regeneration is not "replays
offline against no backend", because replay semantics differ from live on spend; offline
replay is the verification half.

## 6. Left open

- **A replayed run's record says a paid tool spent nothing, while its model calls keep
  their priced cost.** Deliberate on the runner's side (a served call spends nothing) and
  consistent with `max_spend` not being checked on replay; observed here because it decides
  what a fixture can hold, and left as it is. Destination: nothing, recorded for the next
  reader who meets the asymmetry.
- The shell and the measure page, which are `P3-51`'s remaining stages:
  [`plan.md` §1 `P3-51`](../plan.md#L28).
