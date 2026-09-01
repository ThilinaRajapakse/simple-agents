# Build log — a design decision the coding agent proposes rather than makes

`archive/plan-history.md` §1.11 is the brief, built 2026-08-11. `runs/dogfood-3/findings.md` `DF3-D8` is the
evidence and §1.11 is the brief.

**1737 tests**, up from 1721. **Eleven conformance checks**, up from ten. **33 elicitation
questions**, up from 30.

---

## 1. What shipped

- **Six decision kinds**, `simple_agents.conformance.DECISION_KINDS`: `dependency`, `shape`,
  `constant`, `prompt_rule`, `presentation`, `measurement`. Each carries the question to put to
  the builder, what falls under it, and a worked example taken from dogfood #3.
- **`[decisions]` in the brief**, one entry per decision, with `kind`, `status`, `chose`,
  `considered`, `because`. Statuses are `proposed`, `agreed`, `changed`, `not_applicable`.
- **FT-30**, at tier `prototype`: no decision may be `proposed`, and every kind has an entry.
- **Three elicitation questions**, all required. `how_far` at `brainstorm` asks how finished
  this has to be, giving the builder what each stage produces so they can answer it, and
  settles the tier. `involvement` follows it. `presentation` is at `shape`. 33 in all.
- **`simple-agents questions --decisions`**, and `--json`.
- **`docs/procedure.md`** gains a section on what to settle and keep settling, the design
  discussion moved to stage 3 where the pipeline is written, FT-30 at every gate, and a
  `BUILD-LOG.md` line. Reorganised to fit its original word budget, §3.

---

## 2. The four questions §1.11 said a design has to answer

*Amended 2026-08-11 after Thilina's review: the glossary is updated, the procedure is
reorganised rather than the budget raised, and the build-log line is in.*

**Where the record lives: the brief, not `idea.md`.** §1.11 leaned the other way, on the
grounds that `idea.md` grew a section per stage in dogfood #3 and is the artifact that worked.
The lean did not survive contact with the third question. A gate has to read a per-decision
status, and `idea.md` is prose: parsing `status = "proposed"` out of markdown means either
inventing a markup convention or accepting that the check cannot see it. `brief.toml` is TOML,
`conformance/brief.py` already parses it, and the builder already reviews it.

**This widens what the brief is.** The glossary called it "the structured file recording
elicited answers". A decision the coding agent made is not an elicited answer until the builder
sees it, and then it is one. **`CLAUDE.md`'s glossary was updated on Thilina's ruling**: the
brief records what passed between the coding agent and the builder, `entries` for elicited
answers and `decisions` for what the coding agent chose and had them settle.

**What the gate checks, and what it cannot.** It reads that an entry exists per kind and that
none is `proposed`. It cannot read whether the record is complete, because a decision the
coding agent did not notice making is one it did not write down, and it cannot tell agreement
from a rubber stamp. Both are stated in FT-30's own text and in `docs/conformance.md` §4, which
now names three limits rather than two.

**The kinds are typed, not prose.** §1.11's lean, kept: `kind = "dependency"` is what makes
"which kinds have no entry" a question a gate can ask, and that question is the one that catches
a decision nobody thought about rather than one somebody deferred.

**The dial moves the timing.** `involvement`'s scaffold offers three levels and says in the same
breath that it sets *when* the six kinds are put to the builder, not *whether*. All six are
recorded and settled at every level. A test holds that sentence, because it is the part that
would quietly erode.

---

## 3. What the build found

**A kind with no entry had to be a failure, not a silence.** The first cut only checked for
`proposed` entries, which passes a brief with no `[decisions]` table at all: a project that
never thought about any of it looked identical to one with nothing to decide. `not_applicable`
exists so those are different states, and it is the same argument the brief already makes for
`deferred` against a blank.

**The word budget on `docs/procedure.md` was raised and then put back.** It sat at 1354 against
1355, and the first cut of this item took it to 1556, so the cap went to 1580. On Thilina's
ruling the file was reorganised instead: what the skill restated of `docs/pipeline.md`,
`docs/tools.md`, `docs/evaluation.md` and `docs/conformance.md` came out, which is exactly what
the budget exists to prevent, and **1352 words now carry three instructions the file did not
have before** under the original 1355 cap. The budget was right and the first attempt was lazy.

---

## 4. The measurement

**Dogfood #3 passed 10 of 10. Against this library it fails 2 of 11**, and the two are exactly
what its findings were about:

```
FAIL  FT-24  Elicitation skipped                        brief.toml
FAIL  FT-30  Design decisions the builder never saw     brief.toml
```

FT-24 fires because `involvement` and `presentation` are now required and that brief answers
neither. FT-30 fires because the project recorded no decisions at all, having made every one of
them alone. **Nine checks still pass**, including every measurement check over the evaluation
`DF3-D1` showed could not detect its own effect, which is the part FT-30 does not reach and the
`measurement` kind is aimed at.

---

## 5. What is left open

- **`DF3-D1` closes with this only if the `measurement` kind does its job.** The kind asks what
  an agent that did nothing would score. Nothing checks the answer, and nothing can: the library
  cannot compute a project's chance rate. What it now refuses is the answer being absent.
  Whether asking is enough is what dogfood #4 measures.
- ~~The build log in the procedure~~ **built**, in the reorganisation above. One line under the
  layout, and a test holds it.
- **No live run exercises FT-30**, because it reads a static file and nothing about it involves
  a model. The dogfood #3 check above is the closest thing to a live test it has.
