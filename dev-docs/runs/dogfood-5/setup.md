# Dogfood #5 — setup, and how to run it

Set up 2026-08-20, agreed at a sitting the same day. **This file lives here and not in the
project**, because the project is what the coding agent reads and this is context it must not
have.

The protocol is [`dogfood-protocol.md` §1](../dogfood-protocol.md#L10). This file is what is
already done and what to paste.

---

## 1. What is installed

`/home/thilina/Projects/dogfood-5`, following the `dogfood-N` convention.

| | |
|---|---|
| Python | `.venv`, 3.12, made with `uv venv --python 3.12` |
| The library | **installed from the wheel at `wheels/`**, built from `9b8e96c` with the tree clean |
| `pyproject.toml` | declares `simple-agents` with a `[tool.uv.sources]` path entry, so a fresh `uv run` resolves |
| The procedure | `simple-agents init` has run: `.agents/skills/simple-agents/` is linked and `AGENTS.md` is written |
| Credential | `.env` holds `GEMINI_API_KEY` and nothing else, mode 600, gitignored. **The Mistral key is deliberately absent**: it is out of credits, and re-finding what a 402 does bought dogfood #3 nothing |
| Git | initialised, **and the setup is committed** as `4bf6bb5` |

**Verified before handover.** `docs_path()` resolves inside `site-packages` with 18 documents,
`product.md` among them; **zero of them name `questions.jsonl` and two name
`evals/examples.jsonl`**, which is the layout as renamed the morning of this setup; the library
reports 46 elicitation questions, with `used_through` fourteenth at brainstorm and ninth
required, 19 checks and 6 decision kinds; the linked skill names all six stages; and
`simple-agents check` refuses with the missing-tier message.

### 1.1 The wheel was rebuilt first, and why

`docs/` changed heavily on 2026-08-20 (`P3-28`, `P3-30`, the `examples.jsonl` rename) and the
wheel force-includes them, so a wheel from even a day earlier tests last week's documents. It
was rebuilt from `9b8e96c` before anything else and probed as above.

[`dogfood-4/setup.md` §1.2](../dogfood-4/setup.md#L38)'s isolation measurement, that a library
rebuild reaches the run only when `wheels/` is replaced and `uv sync` re-run, is a property of
this layout and holds unchanged. It was not re-measured.

---

## 2. The task

A replacement for TV Time, the TV show tracking app, from Thilina's inbox entry of 2026-08-18,
chosen at the sitting of 2026-08-20. His call there: **it has almost everything dogfood #4 did,
including the same need for a recommender in the absence of user interaction data.** What is
new is that the task is product-shaped by nature rather than by instruction: the value is the
accumulated watch state and the surface it is touched through, which is the shape dogfood #4
failed at and `P3-30` shipped machinery for.

Naming the dead product is how a real builder asks, and it hands the research stage something
concrete to research. "For me" is what makes `used_through` answerable with a real preference
rather than a hypothetical one.

**True at handover and in no artifact**: Thilina expects to answer the surface question with a
UI plus a coexisting natural-language interface, and his viewing history exists only in
whatever he can export or recall. Both reach the run only through elicitation.

### 2.1 The run straddles the release, knowingly

Accepted 2026-08-20. Dogfood #4 took three days, this run starts today, and
[`P3-31`](../../build-logs/going-public-build-log.md#L1) goes public tomorrow-ish. What lands before release
is the front half: cold-start defects in elicitation, research, shape and design, historically
the cheapest to fix and the first an adopter hits. Evaluation- and ship-stage defects land
after the repository is public, which v0.1's own criterion tolerates, being unmet either way.
*(Overtaken 2026-08-25, once the run's inventory was drafted: the whole of it lands before the
repository is public, `P3-32` above `P3-31`. [`inventory.md` `DF5-X5`](inventory.md#L41).)*

---

## 3. The prompt

The protocol is to point it at the library and name the task. Nothing about stages, gates,
decisions or the product concept: finding those is what is being measured.

> Build a replacement for TV Time (the TV show tracking app) for me using Simple Agents. The
> library is already installed in this project and `AGENTS.md` says where its procedure is.

---

## 4. What this run is testing

**Product-first.** `P3-30` (the product) and `P3-28` (the research stage) both shipped on
2026-08-20 and neither has met a cold start.
[`the-product-build-log.md` §6](../../build-logs/the-product-build-log.md#L257) names this run
as where its deciders' evidence can turn up. Worth watching, and none of it should be helped
along:

- **Does the product concept reach the builder?** `used_through`, the `design.md` product
  section with its four interaction kinds, FT-34 reading it. The measure is not whether the
  gates pass; it is whether the run again ends in a bare display over stored output, which is
  [`DF4-N14`](../dogfood-4/inventory.md#L827) verbatim.
- **The research stage, cold.** TMDB, TVDB, Trakt and TVmaze all exist, so there are real
  sources to find and compare. Does the coding agent find them unprompted (`DF4-N3` is what the
  stage shipped for), does FT-36 fire on a blank survey outcome, and does a required entry
  answered `source = "coding_agent"` fail FT-24.
- **[`DF4-Q1`](../dogfood-4/inventory.md#L785), a real answerer at last.** Two runs used
  `consult` and neither reached a person. Thilina is genuinely this product's end user.
- **The state questions, with live deciders.** `DF4-Q2` (is the store-versus-results split
  general), [the memory store's shape](../../plan.md#L148) (`DF4-L8`: the one project that
  specified `MemoryStore` built SQLite around it), and
  [a shipped store for the product's artifact](../../plan.md#L159) (does this run hand-build
  the same four behaviours again). `DF4-Q4`, semantic recall, if the run reaches memory at all.
- **[The scheduler entry](../../plan.md#L172).** New episodes air on a schedule, so this
  product has a real trigger; whether the host's scheduler expresses it well is exactly that
  entry's decider.
- **`DF4-Q5`.** A tracker is counts everywhere: episodes watched, shows tracked, seasons
  finished. Three of three dogfoods that got as far as caring built a count seam by hand.
- **The thin-agency reading.** Most of a tracker is CRUD. A run that reaches for
  `Deterministic` where no model is needed is a finding about whether the docs permit not using
  a model; no run has tested that direction. Thilina's call at the sitting: the task still
  carries dogfood #4's recommender need, cold-start recommendation with no user interaction
  data, so the agentic surface is real.
- **Twelve shipped breaking changes** since dogfood #4's wheel, used fresh from the docs alone,
  and `HostPolicy` with the per-run fetch binding shipped the same day as this setup.

---

## 5. The build log, and why it is again not in the prompt

Dogfood #4's decision, carried forward with the enforcement moved underneath it:
`docs/procedure.md` instructs the coding agent to keep `BUILD-LOG.md`, and since `P3-7`,
**FT-33 reads a log that stopped before the runs did**. The library now enforces its own
instruction, and whether that holds unprompted is worth more than the one figure it risks.

The cost, known in advance: the waiting time is lost again if the log does not appear, and the
timestamps that do appear are composed rather than read.
[The timestamp entry in `plan.md` §2.2](../../plan.md#L303) predicted exactly this for a fifth
run and was left standing at the sitting; its own decider, reconstructing dogfood #4's
per-stage elapsed from its manifests, runs against files already on disk any time after.

**If the log does not appear by the end of stage 2**, the run continues without one and the
finding is recorded. Do not ask for it mid-run.

---

## 6. The rules while it runs

From [`dogfood-protocol.md` §1](../dogfood-protocol.md#L10), and the asymmetry is the sharpest
instrument in the protocol:

1. **Library-prompted elicitation: answer it, fully, and volunteer nothing beyond the question
   asked.** This is the product working, not an intervention.
2. **Unsolicited helping, clarifying, correcting or rescuing: forbidden.** Being forced into it
   is a documentation bug and goes in the log.
3. **Three things go in the log and they are different bugs:** interventions forced, questions
   asked that the library should have answered itself, and **things wanted to volunteer but
   never asked for**, which is a missing elicitation question and the easiest to miss.

What is sharper this time, all decided 2026-08-20:

- **The urge to volunteer will be the strongest it has ever been.** The builder has real
  opinions about his own tracker. Every suppressed urge is a category-3 entry, and category 3
  is the highest-value category the protocol has.
- **Keys are answers, not setup.** TMDB needs a free signup and TVmaze none; nothing is
  pre-seeded, because finding sources and asking for what they need is the research stage under
  test. When asked, Thilina obtains and provides.
- **vLLM likewise.** Not running at handover. It is started only if the coding agent asks for a
  local or free backend and Thilina agrees.
- **Personal viewing data lands in this run's records the day before the `dev-docs` scan
  pass** ([`going-public.md`](../../build-logs/going-public-build-log.md#L1) already flags the
  Goodreads-derived material in earlier runs). Keep real exports out of what this run's records
  commit, or flag them for the scan explicitly.

A decision presented for agreement is elicitation, not an intervention. Nothing is said to the
coding agent about deleting, overwriting or committing; what a run does to its own history is a
finding.

---

## 7. Machine facts that cost a session time

| | |
|---|---|
| Gemini | `GEMINI_API_KEY` in the project's `.env`, paid tier, model `gemini-3.1-flash-lite`; `docs/model-clients/gemini.md` §2 says why the cheaper one cannot be called. Nothing reads `.env` automatically |
| Mistral | **out of credits**, HTTP 402, and its key is not in this project |
| vLLM | **not running at handover**; nothing was serving on 8000-8009 and the GPU had ~21GB free. Its environment is `~/.venvs/vllm`, outside any project; port 8000 is historically taken, use 8001 |
| A reasoning model with no output ceiling | `Qwen3` generates until context runs out and a `Budget` checks between steps, so it bounds nothing. `max_output_tokens` on every node, and preflight one call |
| Default `python` | a conda 3.7.7 the library refuses to install into. Always `uv venv --python 3.12` |

---

## 8. Where the findings go

`dev-docs/runs/dogfood-5/findings.md`, following the shape of the other four, with a `DF5-`
series, and `inventory.md` beside it off `templates/run-inventory.md`.
[`plan.md` §1 P3-31](../../plan.md#L27) is fed first: a defect this run finds lands before the
repository is public. The §2.2 entries whose deciders name this run: the memory store's shape,
the shipped store, the scheduler, and the seeded start.
