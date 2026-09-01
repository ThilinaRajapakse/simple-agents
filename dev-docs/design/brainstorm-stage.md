# A `brainstorm` stage before `shape`

Status: **decided 2026-08-10, not built.** Design of record for the change; the build log will
supersede it on the points where building teaches something different.

Every decision below carries its rationale, and §9 records how each open question closed. The
survey that led here is in the working notes and is not part of the design.

---

## 1. What changes

A fourth stage, `brainstorm`, before `shape`. It ends at a gate like the others. It produces:

- **Brief entries** for six required and five optional questions, none of which exist today.
- **`idea.md`**, a prose account of what the project is, maintained rather than written once.

Everything else about the procedure is unchanged.

---

## 2. The problem

**All five `shape` questions presuppose the project already exists as a concept.** `ground_truth`
asks "for one input, what is the correct answer", which assumes the shape of an input is known.
`answer_form` asks what form a correct answer takes. `agency_boundary` asks which decisions the
agent makes while running. None of them is answerable by a builder who has an idea rather than a
specification, and nothing in the library carries them from one to the other.

### 2.1 Evidence

From the session that produced this proposal, where the builder arrived with "a book
recommendation agent" and the coding agent was the one designing:

| What happened | What was missing |
|---|---|
| Six dogfood candidates proposed and all six rejected as "too technical, or too industry focused" | Nobody had established who the artifact was for |
| A research-grade evaluation designed (contrarian splits, disjoint pairing, cluster bootstrap) for what was actually a demonstration. Two rounds of work discarded | Nobody had established what the project was for, so "credible measurement" was assumed to be the goal |
| The first design rested on an `Average Rating` column the builder's real export does not contain, found by reading the file after the design existed | Nobody had obtained one real input and read it |

Three failures, one cause. The library asks nothing about purpose, audience, or whether the
input exists.

### 2.2 The question was also raised independently

`random-thoughts-questions.md`, Thilina's Corner: *"Does elicitation need a pre-build stage?
Where the builder actually figures out what they want to build and how."* Recorded separately
from the session in §2.1, and answered by this document.

### 2.3 The same gap in the dogfood record

Dogfood #2 ended on the builder's verdict that the market does not publish the data the agent
needed. That is an `abandon_condition` discovered after the work rather than stated before it.

---

## 3. The decisions

All Thilina's, 2026-08-10, at the sitting this document records.

1. **The stage is called `brainstorm`.** The bare noun, alongside `shape`, `build`, `measure`.
   The name is a behavioural instruction to the coding agent: this stage is divergent where the
   other three are convergent. `intent` and `frame` were considered; `frame` collides with
   `shape` as a near-synonym, which the glossary rule makes a bug.
2. **Over-asking is not a constraint at this stage.** `runs/dogfood-protocol.md` §1 names the failure as
   elicitation firing where documentation should have sufficed, meaning questions the library
   could have answered itself. At this stage that category is close to empty: what the builder
   wants, who it is for, and what data exists are things the library cannot know.
3. **The account of the project is its own file, not a brief entry.** Brief entries are answers
   to specific questions; this is the synthesis, and the relationship is the one `handoff.md` has
   to the build logs. A multi-paragraph synthesis inside a TOML string is written once and never
   opened, and an artifact that is not read is bureaucracy.
4. **It is confirmed at every later gate, not graded and not diffed.** The brief records the
   stage at which it was last confirmed current. Advancing a stage requires updating that field,
   which forces a read rather than a rewrite.
5. **The depth of the stage adapts to how developed the builder's idea is.** More questions where
   the idea is vague, fewer where it is settled, and the same artifact either way.
6. **Existing projects breaking is accepted, not mitigated.** The three dogfood projects will
   fail FT-24 until they carry the new entries. They are dogfoods.
7. **Faithful recording is trusted, not enforced.** A brief entry holds what the coding agent
   wrote down, and no check can tell a verbatim answer from a rephrasing. The scaffolds ask for
   verbatim where it matters; nothing verifies it. This is `simple-agents.md` §3.2's ceiling and
   belongs in `docs/conformance.md` beside the rest of it.
8. **The stage records where the project is going, not only what it is now.** Paired with the
   smallest version worth having, so the project is bounded from both ends. This is the answer
   most likely to change, which is what makes it the clearest case for FT-29 in §7.2.

---

## 4. The stage

```
brainstorm   what the builder is trying to build, who for, and on what
shape        what the agent is for, what counts as an answer, where agency sits
build        the pipeline exists and has run once inside the run envelope
measure      the labeled set, the split, the scoring rule, and the evaluation
```

`STAGES` gains an entry at the front. `FIRST_STAGE` becomes `brainstorm`, so a project with no
declared stage and no artifacts is held to the brainstorm questions rather than to the shape
questions, which is the correct default for a project that has just started.

`reached()` is unchanged in logic. It infers `build` from a run directory and `measure` from a
results file; neither inference is affected by a stage before both.

---

## 5. The questions

Eleven. Six required, five optional. Text is drafted to the shipped-prose rules: third person,
plain, no second person, no em-dashes.

### 5.1 Required

**`what_it_does`**
> In two or three sentences, what does the agent do, and who is it for?

*Scaffold.* Ask it open, and write the answer down verbatim before rephrasing it. Read what comes
back for three things: what the agent receives, what it produces, and who receives that. An
answer carrying all three is a developed idea, and the work is to record it and confirm the
reading back. An answer missing any of them is where the optional questions apply, because the
builder is exploring rather than specifying and a design settled now is settled against a guess.

**`purpose`**
> Is this something the builder will use, something they will show other people, or something
> other people will depend on?

*Scaffold.* Offer the three and take one. Each sets a different bar. A tool the builder uses
answers to one person who recognises its mistakes. Something shown is finished when a reader can
follow what it did. Something others depend on answers to people who cannot recognise its
mistakes. The answer decides the tier the project claims, and whether a wide interval is a
finding or a problem.

**`one_real_input`**
> What does the agent receive, and can one real example of it be produced now?

*Scaffold.* Obtain one and read it before any node is designed. Record what it holds rather than
what it is assumed to hold: the fields present, the fields absent, and the range of values. A
field assumed present and missing from the real file is found here rather than after the pipeline
is written.

**`end_user`**
> Who uses the finished agent, and is that the builder?

*Scaffold.* Where the builder is the only user, record that. The answer decides how much the
output has to explain itself, and whether consultation reaches somebody other than the person who
built it.

**`smallest_worthwhile`**
> What is the smallest version that would still be worth having?

*Scaffold.* Ask it beside `finished_version` and record both together, since a floor and a
destination are easier to state against each other than alone. Record it as something the project
could stop at: it is what the first working version aims at, and it is the fallback where a later
stage shows the full version is not reachable.

**`finished_version`**
> What does this look like when it is finished, and what does it do then that the first working
> version will not?

*Scaffold.* Ask for what the end user gets rather than for a list of capabilities. It is the
answer most likely to change as the project is built, and recording it is what makes that change
visible at a later gate rather than a drift nobody names.

### 5.2 Optional, and when they apply

These are the brainstorming set. `what_it_does`'s scaffold says when they apply: an opening
answer that does not name an input, an output and a recipient.

**`existing_solution`**
> What does the builder do about this today, and what is wrong with it?

*Scaffold.* The current approach is what the agent has to beat, and it is often not automation at
all. Record it. An agent slower and less accurate than what already happens has no reason to
exist.

**`success_story`**
> Describe one time the finished agent works well, from the first thing it receives to the last
> thing it produces.

*Scaffold.* Have the builder narrate it. A walkthrough surfaces steps a description of the goal
leaves out, and it names the intermediate values the pipeline will have to carry.

**`alternatives`**
> What are two other versions of this idea?

*Scaffold.* Ask for versions differing in what the agent does rather than in how it is built. The
point is to find whether the first statement was the idea or the first thing that came to mind.

**`not_building`**
> What has the builder decided this will not do?

*Scaffold.* Record the exclusions in the builder's words. An exclusion recorded now is a refusal
the coding agent can point at later, rather than a scope decision it makes alone.

**`abandon_condition`**
> What would show that this is not worth continuing?

*Scaffold.* Ask for a condition that could be observed, such as a source that turns out not to
publish the data, or a figure the agent cannot beat. Recorded now it is a decision the builder
already made. Discovered later it is a decision made under sunk cost.

---

## 6. `idea.md`

Five sections. Drafted so the file reads as a document rather than a form, which was the
condition for it being a file at all.

| Section | Holds |
|---|---|
| **What this is** | A few sentences. The agent, what it receives, what it produces |
| **Who it is for** | The end user, and whether that is the builder |
| **What it works on** | The real input, and what reading one actually showed |
| **Where this is going, and where it is not** | The smallest version worth having, the finished version envisioned, and the stated exclusions |
| **What is still open** | Questions carried forward, and what would settle each |

The fourth section bounds the project from both ends and holds the exclusions between them, which
keeps the file at five sections rather than six and keeps the three scope answers together where
they are read against each other.

The last section is what makes it maintained rather than written once, and it is where a
`deferred` brief entry gets its prose counterpart.

**Authority.** The brief is authoritative on answers; `idea.md` is authoritative on the
narrative and on what is still open. This is the rule `CLAUDE.md` already uses between `docs/`
and `dev-docs/`, applied one level down.

---

## 7. The gate

`simple-agents check` at `brainstorm` reports:

1. **FT-24**, extended: the six required brainstorm entries are answered or deferred.
2. **A new check**: `idea.md` exists and its five sections are present and non-empty.
3. **FT-29, new**: the brief's `understanding_confirmed_at` names the project's current stage.

### 7.1 The staleness field

```toml
stage = "build"
tier = "prototype"
understanding_confirmed_at = "build"
```

Advancing a stage requires updating it. A git checkout resets file mtimes, so mtime would fire
spuriously and get disabled; a brief field is robust and is where the rest of the project's
claims already live.

### 7.2 FT-29, drafted

**The project's account of itself was written once and never revisited.**

*Detection surface:* `understanding_confirmed_at` names a stage earlier than the one the project
is at.

*Why it matters:* what a project is for changes as it is built, and the account written on the
first day is the one every later session reads first. A stale account sends the next session, and
the next coding agent, at the wrong problem.

*Next action:* re-read `idea.md`, update what has changed, and set
`understanding_confirmed_at` to the current stage.

### 7.3 What the gate does not do

It checks presence and non-emptiness, not quality. A coding agent can bump
`understanding_confirmed_at` without reading anything, and no check can tell. This is
`simple-agents.md` §3.2's ceiling, unchanged: the mechanism makes the omission visible, not the
negligence. It should be stated in `docs/conformance.md` rather than implied.

---

## 8. What this touches

| File | Change | Risk |
|---|---|---|
| `conformance/stages.py` | One tuple entry, docstring | Low |
| `conformance/elicitation.py` | Ten questions | Low |
| `conformance/brief.py` | `understanding_confirmed_at` | Low |
| `conformance/checks.py`, `artifacts.py` | Read `idea.md`, the two new checks | Medium |
| `docs/procedure.md` | A stage section, and `idea.md` in the layout. **This file is the skill**, force-included into the wheel | **Medium. Six tests in `tests/test_procedure.py` pin every command, stage, path and citation** |
| `docs/conformance.md` | Stage table, check list, the §7.3 ceiling | Low |
| `docs/failure-taxonomy.md` | FT-29, taking it to 29 entries | Low, and both `dev-docs` counts need updating with it |
| `simple-agents.md` §2.8 | The amendment, with this document's §2 as its rationale | Needs approval |
| `archive/plan-history.md` §3.1 | An item | Needs approval |
| `CHANGELOG.md` | Unreleased | Low |

**Breaking for existing projects, and accepted.** `up_to` is cumulative, so every brief declaring
`shape` or later is held to the six new required entries and fails FT-24 until they are added.
The three dogfood projects break. That is not a cost to manage: they are dogfoods, and the
CHANGELOG is where a real project reads what to do.

**Collision with the DF2-D1 session: low.** That work is in the graph and the executor. This is
elicitation, stages and conformance. `docs/procedure.md` is the only file both could reach, and
only if that session edits it.

---

## 9. Open questions

1. ~~**Is the filename right?**~~ **Resolved by Thilina, 2026-08-10: `idea.md`.** `project.md` was
   the first draft and named the container rather than the content. `sketch.md`, `concept.md` and
   `pitch.md` were weighed: a sketch names a form that changes, a concept reads as something
   written once, and a pitch is aimed at someone being persuaded rather than at the builder and
   their coding agent six weeks later. `idea.md` names the one thing that stays true for the life
   of the project, and it is the first file a builder opens.
2. ~~**Does `brainstorm` need its own tier behaviour?**~~ **Resolved by Thilina, 2026-08-10: the
   checks apply at every tier, including `prototype`.** A project that claims nothing still has
   to say what it is. So the brainstorm gate is one of the few things `prototype` cannot turn
   off, alongside FT-13, FT-14 and FT-24, and `docs/conformance.md` §1.1 gains it.
3. ~~**Should `what_it_does` record the builder's verbatim answer?**~~ **Resolved by Thilina,
   2026-08-10: asked, not enforced.** The scaffold asks for verbatim; no check can tell a
   verbatim answer from a rephrasing, and the coding agent is trusted to record faithfully. See
   decision 7 in §3.
