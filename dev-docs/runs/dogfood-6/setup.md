# Dogfood #6 — setup

How this run was set up, written after it ran rather than before, because it was not set up as
a dogfood. Thilina built `lost-the-plot` for himself against the public package on 2026-09-01
and 2026-09-02, and the record was made afterwards on 2026-09-02 from a frozen copy. The
protocol is [`dogfood-protocol.md` §1](../dogfood-protocol.md#L10); §4 below says where this run
departed from it.

## 1. What is installed

| | |
|---|---|
| Project | `~/Projects/lost-the-plot`, frozen for this record at `~/Projects/lost-the-plot-frozen` from commit `1d92f0b` (2026-09-02 12:33 local, 12 commits) with two uncommitted files, `data/lost-the-plot.db` and `view.html`, copied as they stood. `.venv`, `evals/scratch/` (4.2GB of per-example database copies), `data/cache/` and the Flutter build directories are left out of the copy |
| Python | `.venv`, 3.13, created by `uv` |
| The library | **`simple-llm-agents` from PyPI**, `0.1.1` at brainstorm and `0.1.2` from the `build` stage on (`BUILD-LOG.md:343`). The first project on a released wheel; no `wheels/` directory and no path source |
| The procedure | `simple-agents init` ran: `.claude/skills/simple-agents` links into the installed package and `AGENTS.md` names it. The linked `SKILL.md` is byte-identical to `docs/procedure.md` at `main` on 2026-09-02, so no document moved between the wheel and this tree |
| Credentials | `.env` holds a free and a paid Gemini key, added by the builder mid-`build`. The paid key is prepaid credit and ran out at 06:48 UTC on 2026-09-02; the free key allows about twenty `gemini-3.7-flash` calls a day |
| Local models | `Qwen/Qwen3-Embedding-0.6B` and `Qwen3-Reranker-4B` on the RTX 3090, from `HF_HOME=/deep_learning/.cache/huggingface` |
| Git | Initialised and first committed at the builder's word on 2026-09-02 at `ship`, twelve hours in (`BUILD-LOG.md:923`, `:953`). `data/raw/`, `runs/`, `.env`, `data/cache/` and `evals/scratch/` are ignored |

## 2. The task

A replacement for TV Time, the same task as dogfood #5, chosen by Thilina because he wanted the
app: the service shut down on 2026-07-15 and deleted his history. Half CRUD and half agent by his
own framing, seeded from his real Netflix and Prime exports, with a native app on his phone as
the surface. Tier `evaluated`, all six stages.

Two things distinguish it from dogfood #5 and are what this record reads it for. It is the first
project against the public package, so anything that breaks is what an adopter meets. And the
builder steered: the coding agent's memory file for the project holds eight standing rules he
gave it, every retrieval decision was put to him one at a time, and he read the prompts.

## 3. The prompt

No prompt was written for this run. The builder's opening words are recorded verbatim in the
brief under `entries.what_it_does` (`brief.toml:28-43`): an app like TV Time, agentic instead
of CRUD, tracking as CRUD and discovery and recommendations as the agent, a calendar of upcoming
episodes, a backlog sorted by air date, weekly discovery, recommendations on demand and when the
queue runs low, and "an app on my phone".

## 4. What this run is testing

Written after the fact, so these are the questions the record was read for rather than
questions set before it could be influenced.

1. **Does the released package install and run for a project cold**, including an upgrade
   mid-build?
2. **What does a project with six pipelines do to the checks**, which dogfood #5's seven
   pipelines first strained (`DF5-D4`, `DF5-D5`, `DF5-I13`)?
3. **What does an evaluation over a stateful pipeline meet**: one that writes to a store and
   reads back what it wrote?
4. **Does the product-after-`ship` finding recur** (`DF5-D19`) with a native app?
5. **Which of the library facilities the research stage adopts does the build reach?**
6. **What did the builder have to say himself**, read off the eight rules in the coding
   agent's memory file, and which of them could the library have carried?

The protocol's asymmetry was not applied. Thilina answered what he was asked and also
corrected, redirected and rejected unprompted, so the three categories of
[`dogfood-protocol.md` §1](../dogfood-protocol.md#L18) step 5 are read as what he chose to say
rather than what he was forced to.
