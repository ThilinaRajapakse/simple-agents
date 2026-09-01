# Dogfood #4 — setup, and how to run it

Set up 2026-08-11, straight after the dogfood #3 sitting closed. **This file lives here and not
in the project**, because the project is what the coding agent reads and this is context it must
not have.

The protocol is `runs/dogfood-protocol.md` §1. This file is what is already done and what to paste.

---

## 1. What is set up

`/home/thilina/Projects/dogfood-4`, following the `dogfood-N` convention.

| | |
|---|---|
| Python | `.venv`, 3.12, made with `uv venv --python 3.12` |
| The library | **installed from the wheel at `wheels/`**, built from `9dbe71b` |
| `pyproject.toml` | declares `simple-agents` with a `[tool.uv.sources]` path entry, so a fresh `uv run` resolves |
| The procedure | `simple-agents init` has run: `.agents/skills/simple-agents/` is linked and `AGENTS.md` is written |
| Credential | `.env` holds `MISTRAL_API_KEY`, mode 600, gitignored. **Mistral is out of credits**, so the local vLLM server is the only live backend |
| Git | initialised, **and the setup is committed** as `e2fa029` |

**Verified before handover.** `docs_path()` resolves inside `site-packages` with 15 documents;
the linked skill carries the four stages; the library reports 33 elicitation questions, 11
checks and 6 decision kinds; and `simple-agents check` refuses with the missing-tier message.

### 1.1 The baseline commit, which dogfood #3 did not have

Dogfood #3 was initialised and never committed, so `git log` was empty and the build order could
not be read off it. Three deleted evaluations were recovered from unreachable objects in its
object store, which was luck rather than method (`runs/dogfood-3/findings.md` §1.1).

**This project starts from a commit**, so what the run adds is a diff against a known point.
Nothing is said to the coding agent about committing, for the same reason nothing is said about
deleting: what a run does to its own history is a finding.

### 1.2 The wheel is inside the project, and the isolation was measured

`runs/dogfood-3/setup.md` §1.1.1 is the convention. It was checked here rather than assumed, because
a deterministic build makes the obvious check vacuous: rebuilding an unchanged tree produces a
byte-identical wheel and proves nothing.

**Measured 2026-08-11.** A line was appended to `docs/index.md`, `uv build` run in the library,
and the project inspected:

| | |
|---|---|
| `dist/` wheel | `ccb0f88…` — moved |
| `runs/dogfood-4/wheels/` wheel | `7e35779…` — unmoved |
| Did the change reach the project? | **No.** The probe text was absent from the project's copy of `index.md` |

The probe was reverted and the library rebuilt, so `dist/` and the project's wheel are the same
bytes again. **A library change reaches this run only when the wheel is replaced and
`uv sync` re-run**, which is the property to keep while it runs.

---

## 2. What this run is testing

**Everything dogfood #3 produced, and nothing else has exercised any of it.** That run's
findings are all closed or narrowed, and every repair is a claim about a coding agent's
behaviour that no coding agent has met.

Worth watching, and none of it should be helped along:

- **Does FT-30 change what the builder is shown?** The gate refuses while a decision is
  `proposed`. What it cannot see is a decision the coding agent never noticed making, which is
  the failure it exists for. **The measure is not whether the gate passes; it is whether the
  builder still finds a decision in the code that they never saw.**
- **Does `how_far` get asked before the design, and does its answer hold?** A builder who says
  `build` and is then walked through `measure` was not listened to.
- **Does `involvement` do anything at all?** It sets when decisions are surfaced, not whether.
  A coding agent that ignores the answer and batches everything regardless is the failure.
- **`DF3-D1` is the open one.** The `measurement` kind asks what an agent that did nothing would
  score. Nothing checks the answer and nothing can. **If this run again reaches a green gate
  with a measurement that cannot move, the elicitation answer was not enough** and the ceiling
  needs a different instrument.
- **Is the `BUILD-LOG.md` line enough?** It is one line in the procedure and nothing checks it.
  §4 is why it is not also asked for in the prompt this time.
- **Does the decision record read as bureaucracy?** Six kinds on top of 33 questions is the most
  a project has ever been asked for, and `involvement` is the only thing that shrinks it.

---

## 3. The prompt

The protocol is to point it at the library and name the task. Nothing about stages, gates,
decisions or `idea.md`: finding those is what is being measured.

> Build a book recommendation agent using Simple Agents. The library is already installed in
> this project and `AGENTS.md` says where its procedure is.

### 3.1 The task is dogfood #3's again, and what that costs

**Thilina's call, 2026-08-11.** The same task, run against a library that has moved.

**What it buys.** The task is held constant, so what differs between the two runs is the
library. Dogfood #3's record says precisely what that build decided alone; if this one surfaces
those same decisions, the change is visible without a second confound about task difficulty.

**What it costs, and it is real: the builder knows the answers.** Which catalogue is right, that
twelve was defending nothing, that the held-out-author measure could not detect anything. That
knowledge sits on the wrong side of §4.1's asymmetry.

**Which makes the rule below the whole measurement rather than an inconvenience.** Answer what
is asked, fully. Volunteer nothing. **The urge to volunteer is the finding**: every time it
appears and the coding agent has not asked, FT-30 and the six kinds did not reach that decision,
and that goes in the log as `runs/dogfood-protocol.md` §1 step 5's third category. Dogfood #3 filled that
category with six entries. **The number this run is really producing is how many it fills.**

---

## 4. The build log, and why it is not in the prompt

`runs/dogfood-protocol.md` §1 has always asked for one in the prompt, in fixed words. **This time it is not
asked for.** `docs/procedure.md` now tells the coding agent to keep a `BUILD-LOG.md`, and
whether it does so unprompted is a thing to measure rather than to arrange.

**The cost if it does not**, and it is known in advance: §4.1's waiting time is gone again, as
it was for dogfood #3. That is one figure against one measurement of whether a shipped
instruction is followed, and the instruction is the library's own.

**If the log does not appear by the end of stage 2**, the run continues without one and the
finding is recorded. Do not ask for it mid-run.

---

## 5. The three rules while it runs

From `runs/dogfood-protocol.md` §1, and the asymmetry is the sharpest instrument in the protocol:

1. **Library-prompted elicitation: answer it, fully, and volunteer nothing beyond the question
   asked.** This is the product working, not an intervention.
2. **Unsolicited helping, clarifying, correcting or rescuing: forbidden.** Being forced into it
   is a documentation bug and goes in the log.
3. **Three things go in the log and they are different bugs:** interventions forced, questions
   asked that the library should have answered itself, and **things wanted to volunteer but
   never asked for**, which is a missing elicitation question and the easiest to miss.

**A decision presented for agreement is elicitation, not an intervention.** Answering "no, use
the other one" is the mechanism under test working. Reaching for it before being asked is not.

Nothing is said to the coding agent about deleting or overwriting an artifact. What a run
destroys is a finding.

---

## 6. Machine facts that cost a session time

| | |
|---|---|
| Mistral | **out of credits.** A run against it returns HTTP 402, which is what killed 25 of dogfood #3's rollouts |
| vLLM | its own environment at `~/.venvs/vllm`, outside any project. A Qwen3-30B-A3B with tool calling was serving on **8002** during this setup; 8001 and 8004 held embedding and reranking models |
| GPU | one RTX 3090, 24GB, and the three servers above filled it. Check what is running before starting a fourth |
| Default `python` | a conda 3.7.7 the library refuses to install into. Always `uv venv --python 3.12` |
| `.env` | nothing reads it automatically. The project has to load it |

---

## 7. Where the findings go

`dev-docs/findings.md`, following the shape of the other four, with a `DF4-`
series. `plan.md` §1 P3-1 is the work off this run.
