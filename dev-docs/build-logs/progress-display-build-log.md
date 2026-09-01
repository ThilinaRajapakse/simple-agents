# Build log — Progress a builder can see

`plan.md` §1 P3-19. Started 2026-08-18. Written while building, not afterwards.

## 1. Before any design

Dogfood #4's `DF4-N10` asked for progress bars.
[`findings.md` §8.3](../runs/dogfood-4/findings.md#L1153) answered that it is a discoverability
finding rather than a missing feature, because `progress_of` shipped off `DF3-D3` and the project
rebuilt it by hand. **That reading is understated, and the library was read again.**

- **Three channels report progress and one renders.**
  [`describe`](../../src/simple_agents/evaluation/runner.py#L160) returns a line;
  [`progress_of`](../../src/simple_agents/evaluation/progress.py#L204) returns a dict and
  `simple-agents` had no subcommand over it;
  [`NodeEvent`](../../src/simple_agents/pipeline/events.py#L61) had no formatter.
- **The row's own words are wrong about which is which.** It says `on_rollout=` ships data that
  nothing renders, and that is the one channel that does.
- **`P3-16` widened the gap on 2026-08-18.** An `item` event carried `item_index` and no total,
  so a caller watching a fan-out had no denominator and could not derive one: `over=` names a
  field of the node's input, resolved while the run is running. The count is in scope at
  [`announce`](../../src/simple_agents/nodes/fanout.py#L304) and was not put on the event.
- **Nothing repainted.** Every documented example is `print(...)`, so a 165-rollout evaluation
  emits 165 lines.
- **`on_progress` is called from the fan-out's pool threads** and is not lock-guarded, unlike
  [`saw`](../../src/simple_agents/evaluation/runner.py#L259). Anything holding state across
  events needs its own lock.

## 2. Design

Decided at dogfood #4's sitting 2, 2026-08-18, with
[`inventory.md` DF4-I35](../runs/dogfood-4/inventory.md#L447) as the record.

Thilina rejected the first proposal of a hand-written renderer: *"Why not just use tqdm? It looks
good, and it usually just works. I didn't make a rule about not adding dependencies. Especially
not tiny ones like tqdm."* The two-dependency wheel had been presented as a constraint and is a
status quo. `tqdm` 4.70.0 is an 80KB wheel with no required runtime dependency outside Windows
`colorama`.

**Required rather than an extra, on his call**, because an extra means two code paths and a
fallback that has to be written anyway.

**What tqdm does not answer is wiring**, so the library ships the callback rather than the advice.
A builder left to wire it themselves is back to assembling a display out of three channels, which
is what dogfood #4 did by hand and got wrong twice.

## 3. Build

**[`ProgressBar`](../../src/simple_agents/progress.py#L21)**, in a module of its own rather than
in `pipeline.py` or `runner.py`, which `plan.md` §2.1 already records as the two files carrying
subsystems that settled where they were first called. It takes either callback and tells them
apart by whether the object carries a `phase`.

**`NodeEvent.item_total`**, filled from `len(items)` at the fan-out, and `None` on every other
phase. `item_index` is a position in the whole collection, so a resumed fan-out's indices are
where they were.

**`simple-agents watch <run_dir>`**, over `progress_of`, importing nothing of the project.
`--expected`, `--interval` and `--once`.

**What the build found that the design did not know.**

- **An evaluation gets a bar and a run gets a counter.** The rollout count is known before the
  first one starts; the node count is not, because loops and routes decide it while the run is
  running. tqdm takes `total=None` as a counter, so both are the same object.
- **A resumed evaluation has to be set rather than stepped.** `RolloutProgress.finished` counts
  what was read back from disk, so incrementing would start it at zero and end it short.
- **`disable=None` is what suppresses output off a terminal**, measured rather than read: the
  default writes 89 characters to a `StringIO` and `disable=None` writes none.
- **`file=` earns its place beyond testing.** It is how the display is put somewhere other than
  standard error, and it is what lets a test assert on rendered text rather than patching the
  module's `tqdm`.
- **Adding a dependency pruned the `semantic` extra.** `uv sync` without `--extra semantic`
  removed `sentence-transformers`, and one pacing test failed until it was restored.
- **`watch` without `--expected` had to count rather than show a proportion**, found on the
  session's verification pass. It was passing the count so far as the total, so a directory
  holding 12 rollouts read as 12 of 12 and the bar said the evaluation was over. `progress_of`
  already documents that a directory cannot say whether what it holds is all of it. The
  docstring also promised a stop condition that does not exist: without a total the loop
  follows until interrupted.

2670 tests to 2682. Surfaces touched: `progress.py` (new), `pipeline.py`, `nodes.py`, `cli.py`,
`__init__.py`, `pyproject.toml`, `docs/pipeline.md` §1.7, `docs/evaluation.md` §6.6,
`CHANGELOG.md`, `tests/test_progress.py` (new).

## 4. Verification

**Live, 2026-08-18**, both callbacks against both backends. Mistral is out of credits, so the
hosted arm is Gemini.

| What ran | Backend | What the display showed |
|---|---|---|
| A fan-out of 6 items, `concurrent_items=3` | vLLM `Qwen3-1.7B` | `echo: 100%\|##########\| 6/6 [00:02<00:00, 2.28 items/s]`, and `run: 1 nodes [00:03, 3.48s/ nodes, echo]` |
| An evaluation, 4 examples at k=2 | vLLM `Qwen3-1.7B` | `eval_e5598ec17b48: 100%\|##########\| 8/8 [00:01<00:00, 7.77 rollouts/s, 8 false_confidence]` |
| A fan-out of 4 items, `concurrent_items=2` | Gemini `3.1-flash-lite` | `echo: 100%\|##########\| 4/4 [00:01<00:00, 2.15 items/s]` |

**What it shows.** Both callbacks render against a real backend, and the fan-out arms exercise
the threaded `announce` path: 6 items at 3 at a time counted 6 of 6. The item bar carries a
proportion and a rate, which is what `item_total` is for and what the note asked for.

## 5. Doc consequences

- **`docs/pipeline.md` §1.7** leads with `ProgressBar` and says why a run gets a counter. The
  `item` paragraph gains `item_total` and what an index means after a resume.
- **`docs/evaluation.md` §6.6** leads with `ProgressBar` for the inside view and adds
  `simple-agents watch` for the outside one. `describe()` stays, as the one-line form.
- **`CHANGELOG.md`** gains an entry naming the new dependency.
- **No shipped statement stopped being true.** Neither document claimed anything rendered, and
  `docs/index.md`'s count of sixteen documents is unchanged.

## 6. Left open

- **A resumed fan-out's bar ends short of its total.** Items already done are not announced
  again, so a bar counting events reaches `total` minus what was resumed. The evaluation display
  does not have this, because `RolloutProgress.finished` carries the resumed count and the
  fan-out event carries no equivalent. Destination:
  [`plan.md`](../plan.md#L1) §2.2, entered as its own line with what would decide it.
- **Nothing renders a `TokenEvent`.** `on_token` fires thousands of times per node and is a
  different display problem, named in `docs/pipeline.md` §1.9. Destination: `nothing`.
