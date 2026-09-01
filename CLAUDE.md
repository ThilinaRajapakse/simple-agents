- **Two documentation trees.** `dev-docs/` holds development docs — the design of record, internal. `docs/` holds shipped library documentation — the prompt surface a builder's coding agent reads. Where they overlap, `docs/` is authoritative on detail and `dev-docs/` on rationale; a `dev-docs` section that has been expanded into `docs/` says so and points there.
- Both trees always need to be kept updated to prevent drift. For `dev-docs`, present the user with what you want to change and why, and get their approval before making any changes.
- **DO NOT TUNNEL VISION**
  - Always keep the bigger picture in mind.
  - The library exists to serve a builder and a coding agent building any conceivable agentic system. The dogfoods are experiments run to inform the library, the library does not exist to serve (only) the dogfoods.
- Always ask questions if unsure about anything. It's better to clarify than to make assumptions.
- **Decide on merit, not on precedent.** A rule recorded earlier is evidence about what was known then, not the reason to do something now. We update as we learn.
- **Never bend, work around, or change a settled rule without Thilina's explicit approval.** Surface it and wait. This applies to anything in the do-not-change list, a decision with a stated rationale, or a convention that shipped.
- **When asking, argue from the situation and not from the rule.** Lead with what actually happened and what it costs. Then name the rule, why it exists, and what changes if it moves. "This violates §2.5" is not an argument; "two sessions had to guess at a number the response already carried" is.
- **Cite with a clickable link.** A bare section reference like "§2.6" costs time to hunt down. Use a markdown link with a line anchor, on a path **relative to the file the link is written in**, because that is what a renderer follows. From `CLAUDE.md` at the root that is `[simple-agents.md §2.6](dev-docs/simple-agents.md#L184)`; from inside `dev-docs/` the same target is `[tools.py:718](../src/simple_agents/tools.py#L718)`, and from `dev-docs/build-logs/` it is `../../src/...`. *(This said "repository-relative" until 2026-08-10. The two coincide in `CLAUDE.md` itself, so the rule read as unambiguous and was not: 18 of 21 citations in `dev-docs/` followed it literally and none of them resolved.)*
- **Name what a citation is about, in backticks, beside it.** A line number rots on the next edit above it. `scripts/check_citations.py` re-resolves a named symbol and reports or fixes the drift, and it can check nothing where no name is given. Run it after moving code:

    ```
    uv run python scripts/check_citations.py [--fix]
    ```
- **`dev-docs/` has its own check.** `handoff.md` is a pointer with a line ceiling, nothing cites a queue position, and every `plan.md` §1 row carries a `P3-n` id. It lives in `dev-docs/` rather than `tests/` because a builder reads `tests/`. Run it before presenting written work here:

    ```
    uv run python dev-docs/check_docs.py
    ```
- When updating this doc (@CLAUDE.md), keep updates clear, consistent, and concise. Avoid unnecessary repetition and ensure that the information is accurate and up-to-date.
- Do not describe absence using chains of negative constructions. State the positive conclusion directly. Prefer “X is unknown” over “nothing says X.” Prefer “X is undeclared” over “no step has declared X.” Prefer one short declarative sentence over explaining the logical path that led to the conclusion.
- Do not write in an “AI explanatory” style. Avoid constructions like “No X…, no Y…, so nothing…” and “There is no X, which means Y cannot…” If the system lacks information, simply say what is unknown.
- Go step-by-step while building the project. Think, plan, clarify, execute. There may be a lot of decisions to make, and it's important to take the time to consider each one carefully.
- Do not make decisions based on assumptions. Always verify information and seek clarification when needed.
- When asking Thilina to make decisions, provide context and rationale for each option, pros and cons, along with a concrete, human understandable example if possible. Add an "Anything else?" question at the end to catch anything that may have been missed. The anything else is not the place to ask for new decisions, because it carries no context and Thilina cannot decide there. Anything Thilina needs to decide or answer needs to come alongside the context. Don't add anything else questions for the sake of it. If there's nothing else, don't ask for anything else. Don't move genuine questions or decisions there just to populate it.
- Remember that Thilina cannot know all of the library shorthand off the top of his head. You must give him full context.
- For design/decision sittings, always group by decision or question. All information relevant to a decision should be grouped together and come alongside the input you are asking for. You shouldn't make it necessary to scroll up and down to find the context for a decision. If you have multiple decisions, group them by decision and provide context for each one. Try to provide both the technical explanation and the human understandable, plain language explanation.
- If you disagree with Thilina's decision, you are always encouraged to push back and provide your reasoning. More context or examples can help clarify your perspective.
- When thinking about and presenting decisions, don't be restricted by the current implementation or current limitations. Keep in mind that this is a project being built. It is not being used by real users today. Consider the problem space and the best solution, even if it requires changes to the existing codebase.
- Rerecording cassettes or trajectories is basically free at this stage. Mistral is free tier and VLLM is local. Don't use rerecording or invalidation as an excuse to avoid a better design or solution.
- After adding a new feature or completing an item that involves code changes, always run a proper test with an actual pipeline(s) with VLLM and Mistral to ensure that the changes work as expected. Unit tests alone are not enough. **A green suite that never used a real backend proves less than it looks**: item 5 found two bugs in items 3 and 4 within minutes of the first live `AgentNode` run, after 236 tests had passed over both. `scripts/record_backend_cassettes.py` captures a real recording once and replays it for free afterwards.
- **A documented bug is not a measurement.** Item 5's first pass cited an open vLLM issue about `prompt_tokens_details` and drew a conclusion from it; the probe against the running server found the field present and the issue stale. Check the machine, not the tracker.
- **An example that parses and resolves can still be wrong, and nothing executes one.** `scripts/prose_check.py` checks that every fenced Python block in `docs/` and every `::` literal block in a docstring parses, that every name it imports exists, and that every keyword it passes is one the callable takes. What it cannot see is whether the example runs: `docs/pipeline.md` §1.4's accumulator parsed, resolved, and was missing the node that gives the first one a `Join`. Running the example is what closes that, and `tests/test_labelling_pass.py` is what that looks like.
- **The trajectory format is pre-adoption and moves.** A bump is cheap now and stops being cheap at the first release. `dev-docs/design/trajectory-format-changelog.md` records what each cost and why; `CHANGELOG.md` records what a project would have to do.
- When an item is done, that is the design has been agreed, questions settled, decisions made, and the code has been implemented, read the code again and verify that it does what it was meant to do as decided at the sitting. Check if anything was missed, and if something unforeseen had changed or been affected. It's possible that some bugs, issues, or simple unintended consequences will only be clear once the code is written. Then run the actual code to find implementation issues, both with tests and real backends (use free/local) where applicable. Report all of these properly, following the usual format of giving proper context. When issues are found and fixed, another read and verify pass has to be done, and this cycle continues until no new issues are found.
- For session spanning items, provide me a roadmap, so I know what's done, what we are doing, and what's to come and why.
- When discussing something, especially in sittings, don't just give bare pointers and IDs. That means nothing to me. Use the pointers to orient, but also say what they actually are.
- Always check `dev-docs/random-thoughts-questions.md` for any open questions that may be relevant to the current task. If there are any, address them before proceeding.
- **Read the deferred list before proposing, designing or changing anything.** `plan.md` §2.2 is what was considered and put down, and each entry names what would decide whether it is worth owning. A new proposal is often exactly that evidence, and a deferred entry is often why a proposal is smaller than it looks. See if any of them now deserve to be pulled into the current item or promoted to either accepted or scheduled in the plan.

## Where things live in `dev-docs`

**Four files at the root, and they are the four you always start from**: `handoff.md` where a session starts, `plan.md` the only queue, `simple-agents.md` the design of record, `random-thoughts-questions.md` the inbox. Everything else is in one of six directories.

| Directory | Holds |
|---|---|
| `items/` | One file per planned item: its record while it is open. |
| `build-logs/` | One file per built item: how it was built and what it found. |
| `runs/` | One directory per run, plus `dogfood-protocol.md`. |
| `design/` | Design of record for one subsystem. |
| `templates/` | The required shape of each record. Copy one to start. |
| `archive/` | Superseded text, verbatim. |

**An item moves; it is never in two places.** Not scheduled → a `plan.md` §1 row plus an `items/` record → a build log → a line in §4 Done. **When an item is built, its `items/` file goes to `build-logs/` if the build log now says everything it said, to `design/` if it is standing design of record, or to `archive/` if it is superseded. It never stays.**

**Naming.** Lowercase and hyphenated. The directory names the genre and the file names the subject, so no genre word in a filename. `build-logs/` is the exception and keeps its `-build-log` suffix, because a build log is cited bare in prose where `memory.md` alone would collide with `items/`. A run directory holds `setup.md`, `findings.md` and `inventory.md` and nothing else. A date appears in a name only when the thing is identified by when it ran; a sequence number only where a series exists. The `itemNN` build-log names are legacy proper nouns with 581 citations behind them, not a scheme to extend.

**A build log carries six sections, and `templates/build-log.md` is the authority on them** — `check_docs.py` reads the required headings out of that file, so changing the standard means editing the template. Any section may be one line, and "Left open: nothing" is a real answer.

**Every pointer in `plan.md` is a markdown link with a line anchor.** A bare backtick filename is not a pointer.

**Restructure a record by transforming its text, never by rewriting it from a reading of it.** Open the original, move what moves, and let the diff show what left. Writing a new file from notes drops whatever the notes omitted, and the loss is invisible: on 2026-08-15 dogfood #4's inventory lost seventeen rows to a bulk rewrite, including a recorded decision the next session then re-derived, and the file came out the same size because new text replaced it. `check_docs.py --since <ref>` reports a record that shrank against a git ref, which catches wholesale loss and not substitution at constant size. Run it after any restructuring, and read the diff for the rest.

**A citation between two records of one run resolves both ways.** A candidate names its evidence and the finding names the candidates it produced. The inventory is the source of truth; `check_docs.py --fix` generates the other side. Citations out of the run stay one-way. *(An id that resolves is not an id that is right: on 2026-08-15 eight candidates cited a real but wrong finding and every one passed a resolution check. The back-reference is what catches that.)*

**How work moves.** The tree above says where a thing lives; this says what you do to move it.

| When | Do | Done when |
|---|---|---|
| A thought arrives unscoped | One dated bullet under `## Unscoped` in the inbox | It has a destination, within 7 days |
| A run finishes | Write the run's `findings.md`, then `inventory.md` from it off `templates/run-inventory.md` | Every finding is a candidate, a learning, a correction or a question |
| Working through an inventory | Give each candidate a destination. **Take the blockers first**: their outcome changes the disposition of everything behind them | No candidate is still `open` |
| A candidate is agreed | `plan.md` §1 with a new `P3-n` and an `items/` record if it needs one, or §2.1 if there is no slot, or §2.2 if we have not decided to own it | The inventory row's status names where it went |
| A sitting is done | **Build what it scheduled before taking the next sitting.** That is what the grouping is for; taking sitting after sitting produces hypothetical plans that collide. The inventory item and the items its sittings schedule alternate in §1 | The next sitting's row says it waits on the built one |
| An item is built | Write the build log off `templates/build-log.md`; move its `items/` file out; add the §4 Done line; set the inventory status to `built` | `check_docs.py` is clean |
| A shipped statement is found false | Apply the correction now, and log it in the run's §2 | Never queued; §2 is a log, not a backlog |

**Four of the five destinations are in `plan.md`, and what separates them is how far we have committed.** §1 is **ordered**: a `P3-n`, a position, and the top row is what happens next. §2.1 is agreed with **no position claimed**, and says what it waits on. §2.2 is **not decided to own at all**, and says what would settle it. `declined` carries a reason. Most candidates land in §2.1 or §2.2, because agreeing to do something is cheap and claiming it is next is not.

**Asked to write a kickoff prompt for the next session, follow `templates/kickoff.md`.** It is a pointer and an intent, capped at 15 lines: what to read, the task named by id, what is true right now that is in no file, and any constraint with its reason. Everything else is already on disk or a command away. **If the prompt needs to explain something, that is a file missing it** — write it to the record and cite it.

**A new rule in `check_docs.py` comes with a fixture in its `SELF_TESTS`**, which is one deliberate defect and the message it must produce. **The fixtures run on every invocation**, not only under `--self-test`, which runs them alone for working on a rule. This is `simple-agents.md` §1.6's requirement applied to our own machinery: it can only be verified against data whose correct answer is known. Four rules covered the instance that prompted them rather than the rule they were named for, and the suite found two more the day it was written. **The fixture list is also the coverage map**: a convention with no fixture has no check. *(The fixtures ran only on demand until 2026-08-17, and one anchored on a `P3-n` row sat broken through a green 2403-test suite until someone thought to run them. **A fixture anchors on the shape and not on the wording** — `_sub_re`, `_reuse_an_id` and `_move_an_item` resolve a live id or filename out of the tree, because every item that ships retires one.)*

**Run the check before presenting written work here**, and never weaken a rule to make it pass:

    ```
    uv run python dev-docs/check_docs.py
    ```

## Writing for the right reader

Three surfaces, three audiences. Never let one leak into another.

| Surface | Reader | Contains |
|---|---|---|
| `dev-docs/` | Library maintainer | Design of record, rationale, history, alternatives rejected |
| `docs/` | The builder's coding agent | What to do, and why it matters to *their* project |
| Code comments, docstrings, error messages | Builder and coding agent reading the source | What this does, what to pass, what happens if they get it wrong |

### A docstring or comment contains only these

1. What the thing is.
2. What it does, and what the caller supplies.
3. What it returns or modifies.
4. **How to use it, with a code example on anything a builder constructs or calls.**
5. What happens when it is used wrongly, and what to do instead.

Anything else belongs in `dev-docs/`: design rationale, options rejected, the reasoning behind a constant, and debugging history.

**Items 4 and 5 are the ones that get skipped, and they are the ones a coding agent needs most.** It reads a signature and a description and then has to guess the call shape. An example removes the guess. Every public name in `__init__.py` carries one, and so does anything with more than one sensible way to call it.

Write examples as a literal block, which keeps them out of the length limit:

```
    """A model call at a fixed point in fixed control flow.

    Prose stays short. The example carries the rest::

        node = LLMNode(build_prompt, output_schema=Answer)
    """
```

Where two things are easily confused, say which to reach for. `LLMNode`'s docstring ends "A step whose next action depends on what the model returned is an `AgentNode`", and that sentence is worth more than another paragraph describing `LLMNode`.

An error message is an instruction too: name what is wrong, then the specific call that fixes it.

### How to write it

**Third person.** No "you" or "your". "A tool must declare a side-effect class", not "your tool needs one". **`README.md` is the exception, agreed 2026-08-18**: a reference document describes the library to someone who has already chosen it, and the landing page addresses someone who has not. `prose_check.py`'s `ADDRESSES_THE_READER` exempts that one file from that one rule, and `tests/test_prose.py` fires both sides of it.

**State absence positively.** Thilina, 2026-08-28: *"Do not describe absence using chains of
negative constructions. State the positive conclusion directly. Prefer 'X is unknown' over
'nothing says X'. Prefer 'X is undeclared' over 'no step has declared X'. Prefer one short
declarative sentence over explaining the logical path that led to the conclusion."* No
`No X…, no Y…, so nothing…`, and no `There is no X, which means Y cannot…`.

| Wrong | Right |
|---|---|
| No step declares the resource, so nothing tells us what it contains or how data flows through it. | Resource not declared by any step. Contents and data flow: unknown. |
| The evaluation carries no figure for this step, so nothing measured says whether it works. | Unmeasured. |
| It does not say what it returns, so nothing here can say what comes out of it. | Return type undeclared. |

`prose_check`'s `negation_cascade` catches the two commonest forms and `tests/test_prose.py`
fires both sides of it. A sentence stating a mechanism and its consequence is not this: "the
number comes from inside the lock, so nothing is out of order" is what the rules ask for.

**No contrastive where a plain statement does the work.** Thilina, 2026-08-18: *"The contrastive is not needed. And in general, I don't like the X-not-Y sentence structure."* "with intervals rather than a single number" is "with a confidence interval on every figure". This is wider than `prose_check`'s `EMPHATIC` rule, which catches `X, not Y.` at a sentence opening and no `rather than` or `instead of` clause at all, so it is read rather than checked.

**Plain and declarative.** Say what is true. Short sentences. A sentence carrying three subordinate clauses gets split. No em-dashes; a comma, a colon, a full stop or brackets reads better.

**Never defend the design.** The reader has not objected to anything. Answering an objection they did not raise wastes their attention and reads as insecurity.

**The one judgement call, and the only rule here a check cannot make.** A `because` clause is right when it tells the reader what will happen to them, and wrong when it justifies the design.

- Right: "An `LLMNode` makes one call, so the model has no subsequent step in which to correct the response."
- Wrong: "Public because the cassette is committed more often than a trajectory is."

### Language not to use

| Kind | Example of the failure | Write instead |
|---|---|---|
| Defensive | "This is not bureaucracy. It is what makes evaluation possible at all." | "A tool must declare a side-effect class so the agent can be evaluated." |
| Aphorism | "**A clean pass is not proof of absence.**" | "These rules match known credential formats and declared values. Other secrets are not detected." |
| Superlative, intensifier | "the most precise rule available", "almost never", "essentially every", "exactly the point where" | State the rule. The reader can judge it. |
| Emphatic X-not-Y | "Five fields, not one." | "`input_uncached`, `input_cache_read` and `input_cache_write` are separate counts." |
| Narrative about people failing | "before anyone remembers to clean it", "one tool call away from being committed" | Describe the mechanism. |
| Rhetorical flourish | "the only thing standing between the model and a misuse of the tool" | "`description` is prompt text read by the model." |
| Telling the reader it matters | "Note what is absent", "the whole point is", "deliberately", "on purpose" | Tell them the thing. |
| Jokes, cute examples | `secret_santa` as an example field name | A name that would actually appear. |
| "Nobody does…" | "A design nobody has agreed to", "Nobody opens a window; the reply lands in the outbox" | State the condition: "An unconfirmed design", "The reply is saved to the outbox as a draft". |
| Clauses strung together with commas | "A question put off is counted where it is answered, so a deferral reads as a deferral rather than as an omission." | Split it: "A deferred question is counted when it is eventually answered, so it shows up as deferred rather than missing." (Thilina's rewrite, 2026-08-29.) |

### Examples that are right, from this codebase

Read these before writing new ones.

- **`pipeline.py`, `node_kinds`.** One line. "Count of nodes by kind, keyed by `node_kind`." Nothing further is owed.
- **`budget.py`, `to_record`.** What it produces, then the one fact a caller needs: "All four keys always present; `null` means unbounded on that axis."
- **`context.py`, `next_sequence`.** States behaviour, then what the reader must not do: "Trajectories are ordered by `sequence`, not by timestamp. Concurrent tool calls can share a millisecond, and the clock can be adjusted mid-run."
- **`errors.py`, `ConfigurationError`.** Abstract statement made concrete by a list: "a loop with no budget, an output schema with no `unknown` branch, a tool with no declared side-effect class."
- **`trajectory.py`, `ToolCallRecord`.** A consequence for the reader, with no design rationale: "Re-declaring a tool later does not change what an old trajectory says."
- **`tools.py`, `Tool`.** Longer, and every sentence earns it: what `description` is for, and which exception to raise for which class of failure.

### Enforcement

`scripts/prose_check.py` enforces the rest: em-dashes, second person, references to `dev-docs`/`plan.md`/`handoff.md`/`simple-agents.md` from shipped files, superlatives, defensive constructions, aphorisms, and over-long docstrings. It also checks that references resolve: a `docs/*.md` path must name a file that exists, and an `FT-nn` citation must name an entry in the taxonomy. And it checks the examples: every fenced Python block in `docs/` and every `::` literal block in a docstring has to parse, every name it imports from the library has to exist, and every keyword it passes to a library callable has to be one that callable takes. Nothing is executed, so an example that parses and resolves and is still wrong passes — running it is what finds that. Its failure messages carry the guidance, so it is read at the point of violation rather than remembered from here.

It runs in `pytest` and directly:

```
uv run python scripts/prose_check.py [path ...]
```

**Run it before presenting written work.** Never weaken a rule to make the check pass. `dev-docs/` and this file are not checked, since recording rationale is what they are for.

**The rules are a guideline, and the exception is Thilina's to grant.** A longer explanation is sometimes the right one, and the check cannot tell. A legitimate use is marked `# prose-ok: <reason>` with the reason stated, and **a marker is added only with Thilina's sign-off**: surface the text and the reason and wait, rather than committing it and mentioning it afterwards. Before asking, check whether the violation can be removed instead. The first candidate at item 6 disappeared once a verbatim error body moved from a comment into the fixture that already held it, which was the better fix in any case.

## Glossary

These terms are fixed. Use them exactly; do not introduce synonyms. The docs are a prompt surface, so an ambiguous term is a bug.

**Roles**

| Term | Meaning |
|---|---|
| **Library maintainer** | Thilina, and any coding agent working on Simple Agents itself. |
| **Builder** | The person using Simple Agents to build their idea. The trust audience of `simple-agents.md` §1.5. |
| **Coding agent** | The AI coding assistant the builder uses to implement their idea with Simple Agents. The library's primary reader. |
| **End user** | A human using the agent the builder produced. May be the builder themselves, or a customer of theirs. |

**Artifacts**

| Term | Meaning |
|---|---|
| **Simple Agents** | The library. Always plural, always the library — never the thing built with it. |
| **The project** | What the builder and coding agent produce together: agent code, evals, the brief, trajectories, manifest. The conformance suite runs against *this*. |
| **The agent** | The runnable agent inside the project. One component of it, not a synonym for it. |
| **The product** | What the end user uses: the surface they meet the agent through, and any artifact the project keeps for them to read. The agent runs inside it; every project has one. |
| **The brief** | The structured file recording what passed between the coding agent and the builder: **elicited answers** under `entries`, and the **decisions** the coding agent made and put to them for agreement under `decisions`. Machine-parseable (YAML/TOML) with prose values, so gates can read it and the coding agent can too. |

**Interactions**

| Term | Direction | When | Recorded in |
|---|---|---|---|
| **Elicitation** | Coding agent → builder | Build time, in the coding-agent conversation | The brief |
| **Consultation** | Agent → end user | Run time, via tool call | The trajectory |

Rules that follow from the split:

- **The library never asks the builder anything directly.** It supplies the questions and the gates; the coding agent always does the asking. This is why elicitation is a documentation problem, not a UI problem.
- **Elicitation is staged, not a single upfront questionnaire.** The general shape is settled early with as much detail as is feasible; differentiating decisions may be deferred to a later stage. Each stage carries its own required set, and its gate refuses to advance while a required answer is missing.
- **Every brief entry is `answered`, `deferred` (naming the stage it is deferred to), or `unanswered`.** Gates fail only on `unanswered` for questions required at the current stage. Deferral must be recorded, never left blank — otherwise postponed is indistinguishable from forgotten.
- **Consultation is a designed interaction, not a fault path.** The builder plans for it. It is not an error, an escalation, or a fallback.
