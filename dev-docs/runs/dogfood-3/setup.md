# Dogfood #3 — setup, and how to run it

Set up 2026-08-10. **This file lives here and not in the project**, because the project is what
the coding agent reads and this is context it must not have.

The protocol is `runs/dogfood-protocol.md` §1. This file is only what is already done and what to paste.

---

## 1. What is set up

`/home/thilina/Projects/dogfood-3`, following the `dogfood-N` convention.

| | |
|---|---|
| Python | `.venv`, 3.12, made with `uv venv --python 3.12` |
| The library | **installed from the built wheel**, not from the source checkout |
| `pyproject.toml` | declares `simple-agents` with a `[tool.uv.sources]` entry pointing at the wheel, so a fresh `uv run` resolves. `uv.lock` is written |
| The procedure | `simple-agents init` has run: `.agents/skills/simple-agents/` is linked and `AGENTS.md` is written |
| Credential | `.env` holds `MISTRAL_API_KEY`, copied from the library's own, mode 600, gitignored |
| Git | initialised, nothing committed. `.gitignore` covers `.venv`, `.env` and bytecode only |

**Verified before handover.** `simple_agents.docs_path()` resolves to
`runs/dogfood-3/.venv/.../simple_agents/docs` with 11 documents; the linked skill carries the four
stages; `simple-agents check` exits 2 with the missing-tier message; and one live Mistral call
returned `Ready` for 22 input and 2 output tokens.

### 1.1 The wheel, and why this differs from dogfood #2

**Dogfood #2 was installed editable against the source checkout.** Its own `pyproject.toml` says
so and gives the reason: editing the library next door then takes effect without a rebuild.

That is wrong for a run whose whole premise is that the coding agent has the library and its
docs and **no context from this design work**. Under an editable install
`simple_agents.docs_path()` returns `/home/thilina/Projects/simple-agents/docs`, and
`dev-docs/` is one directory up from there: the design of record, every findings file, and
this file. Nothing stops a coding agent following that path.

Dogfood #3 installs the wheel, so the path the library hands out stays inside `site-packages`.

**The wheel goes inside the project**, at `<project>/wheels/`, with `[tool.uv.sources]` naming
it by a project-relative path. *(Amended 2026-08-11. It pointed at
`../simple-agents/dist/simple_agents-0.0.0-py3-none-any.whl` until then, and §1.1.1 is what
that cost.)*

```
[tool.uv.sources]
simple-agents = { path = "wheels/simple_agents-0.0.0-py3-none-any.whl" }
```

**The cost, and it is real: a library change does not reach the project until the wheel is
rebuilt and copied in.** After changing anything in `src/` or `docs/`:

```
cd /home/thilina/Projects/simple-agents && uv build
cd /home/thilina/Projects/dogfood-N && cp \
    /home/thilina/Projects/simple-agents/dist/simple_agents-0.0.0-py3-none-any.whl wheels/
VIRTUAL_ENV= uv sync
```

**`VIRTUAL_ENV=` matters.** With the library's own venv active, `uv pip install` targets that
one whatever directory the command runs in. It happened during this setup and replaced the
library's editable install with the wheel, which would have had `uv run pytest` testing a stale
artifact silently. It was restored with `uv pip install -e .` and the suite re-run.

#### 1.1.1 Why the wheel lives in the project, measured 2026-08-11

**A wheel outside the project makes `uv build` in the library break the dogfood.** `uv.lock`
records a path source with the wheel's sha256. Rebuilding changes the hash, and the next
`uv run` in the project fails on the mismatch and refuses to run anything at all, which every
entry point there goes through. Verified in a throwaway project rather than on the dogfood.

**Nothing about the install mode caused this.** Installing the wheel rather than editable is
what keeps `docs_path()` inside `site-packages`, and that decision is untouched. Where the wheel
sat was never decided: it pointed at `dist/` because that is where `uv build` puts things.

**The two are independent**, so a project holding its own copy gets the same isolation with no
coupling. Dogfood #3 was repointed on 2026-08-11, mid-run, and it was safe because the bytes
were identical: the hash did not move, nothing reinstalled, and the library the run imports did
not change. `dist/` was rebuilt straight afterwards and the project was unaffected.

**Dogfoods #1 and #2 never had this**, for different reasons. #1 had no `uv.lock` at all. #2 was
editable, so `uv run` checked no hash and tracked the source live, which is the leak this
section exists to close.

---

## 2. What this run is testing

**The `brainstorm` stage has never met a builder.** It shipped 2026-08-10, hours before this
setup, and dogfood #3 is the first project to reach it. Everything else here has three runs
behind it.

Worth watching, and none of it should be helped along:

- Whether the coding agent asks `what_it_does` first and **reads the answer** to decide how far
  to open up, which is a scaffold instruction rather than a mechanism.
- Whether `one_real_input` produces an actual file being read, or a description of one.
- Whether `idea.md` gets written as five real sections or as five headings with a line each.
- Whether `understanding_confirmed_at` is ever updated again after `brainstorm`, or set once and
  left, which is the failure FT-29 exists for and which no check can distinguish from a real
  reading.
- Whether six required questions at one stage reads as thorough or as an interrogation.

---

## 3. The prompt

The protocol is to point it at the library and name the task. Nothing about stages, gates or
`idea.md`: finding those is what is being measured.

> Build a book recommendation agent using Simple Agents. The library is already installed in
> this project and `AGENTS.md` says where its procedure is.

**The task is not fixed.** `items/example-projects.md` §17 is the worked candidate, and its §17.9
records what the real Goodreads export turned out to contain. Any task works; the stage under
test does not depend on which.

**If the task is the book one**, the export is at
`/home/thilina/Downloads/goodreads_library_export.csv`: 346 rows, 303 rated, **no `Average
Rating` column**, ratings skewed 203 at 5 star, 74 distinct authors, no review text. Hand it over
when `one_real_input` is asked and not before.

---

## 4. The build log to ask for

Ask for it at the start, in these words, from `runs/dogfood-protocol.md` §1:

> Keep a `BUILD-LOG.md`. Record our interactions verbatim. Put a timestamp on every entry. Write
> `WAITING ON BUILDER` when you start waiting on an answer from me and `RESUMED` when you get
> one. Every figure you report names the file you read it from.

**The format carries no Simple Agents vocabulary**, so the same log can be asked for from a build
that does not use the library. That comparison is Phase 5.

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

Nothing is said to the coding agent about deleting or overwriting an artifact. What a run
destroys is a finding.

---

## 6. Machine facts that cost a session time

| | |
|---|---|
| Free tier | 50 requests and 50,000 tokens per minute, published on every response header |
| Default `python` | a conda 3.7.7 the library refuses to install into. Always `uv venv --python 3.12` |
| vLLM | its own environment at `~/.venvs/vllm`, outside any project. Port 8000 is taken, use 8001. `--gpu-memory-utilization 0.6` fits `Qwen/Qwen3-1.7B` |
| `.env` | nothing reads it automatically. The project has to load it, and `load_env` was dropped as outside the library |

---

## 7. Where the findings go

`dev-docs/findings.md`, following the shape of the other three. `plan.md` §1
item 1 is this run.
