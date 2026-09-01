# Item 7 checkpoint — the brief for the session that runs it

`archive/plan-history.md` §3.5 asks for a cold-read checkpoint after item 7. This document is what the session
setting it up and analysing it reads. **The cold-read session itself must never see this file,
or anything else in `dev-docs/`.**

Read `handoff.md` first, then `archive/plan-history.md` §3.5, then this.

---

## 1. What is under test, and what is not

A fresh coding-agent session is given only the installed wheel and the six documents in
`docs/`. What is measured is **whether the API was used correctly by something that has never
seen this design work**. A cold agent writing an argument that does not exist is a
documentation bug, and it is cheap now and expensive once six more items sit on top of the
misreading.

**This is not a dogfood.** There is no procedure, no gates, no brief and no conformance suite
at this point, so a session that flounders for want of a procedure is telling us nothing.
Nothing here is logged against Phase 2.

**Not findings, because they are known gaps:** no tool-authoring guide (item 13), no procedure,
brief or gates (items 10 to 12), no eval machinery (item 8), and anything environmental such as
an interpreter that is not the one the library was installed into.

## 2. Why this one is different from the item 5 checkpoint

Item 5's two sessions wrote their own tools. This one meets a tool set it did not write, and a
corpus it cannot fit in one prompt. Both surfaces are new since a session last read them.

**What to read on the tool surface:**

- Is `docs/tools.md` found at all?
- Is `ToolRegistry` used, or is a bare list passed, or is a registry hand-rolled?
- Are the built-in tools found, or does the session write its own `document_search`? Writing
  its own is a documentation finding, not a preference.
- Is the side-effect class chosen thoughtfully or copied from the nearest example?
- Are `ModelHandle` and `Workspace` discovered? The failure mode to watch for is a session
  closing over a path or a client instead, which is the leak session B hit at item 5.
- Is `AgentNode(finish_check=...)` found? Session B wanted exactly this and could not have it.
  If a session that could have it does not find it, the documentation is the reason.
- Does anything about the replay rules confuse it: a filed tool against a re-run one, the
  occurrence count, why a nested model call parents to its tool call?

**What to read on the context surface:**

- Is `docs/context.md` found at all?
- Meeting a corpus that does not fit, does the session reach for the seam (`AppendAll`,
  `over=`, a builder of its own) or hand-roll truncation inside a prompt function? The second
  is FT-17's failure committed by a capable reader, and it is the single most valuable thing
  this checkpoint can produce.
- Does it set `max_input_tokens`, and does it read the window from `GET /v1/models` as
  `docs/context.md` §2.2 says, or invent a number?

**The standing question from item 5, worth asking again:** does the session reach for an
`AgentNode`, and can it say what the model decides that fixed control flow could not? That is
the library's central claim, and the task must not prescribe a shape.

## 3. The corpus: what it has to be, with the arithmetic

**The requirement from `archive/plan-history.md` §3.5 is that the corpus forces a context decision.** The
session must have to choose between fanning out with `LLMNode(over=...)`, packing one prompt,
and writing a builder. A corpus that fits comfortably in one prompt does not force anything,
and the checkpoint then measures the tool surface only.

**Both backends bind at about the same size, which makes the choice backend-independent.**

| | Limit that binds first | In tokens | In words, at roughly 4 characters per token |
|---|---|---|---|
| Mistral free tier | 50,000 tokens per minute, well below the 262,144 window | 50,000 | ~33,000 |
| vLLM, Qwen3-1.7B | `max_model_len` 40,960, a hard refusal | 40,960 | ~27,000 |

So **a corpus above roughly 50,000 words cannot be packed into a single call on either
backend**, and an `AgentNode` accumulating a conversation reaches the limit sooner. Sixty to a
hundred documents of 600 to 1,000 words each lands there. Below about 30,000 words the decision
is not forced and the checkpoint loses half its purpose.

Note which limit binds on Mistral: the rate limit, not the window. A session that packs
everything gets a 429 rather than a `ContextOverflow`, and how it reads that is itself worth
watching, since `docs/model-clients.md` §6 says a per-minute quota is not what retries are for.

## 4. Choosing the dataset

**A public dataset is right here, and `simple-agents.md` §1.6's rule against one does not apply.** That
rule is about the library's own `tests/`, where machinery can only be verified against data
whose correct answer is already known. This is a checkpoint over a project a session builds, so
a real dataset is better than a synthetic one: session B's ten synthetic articles left a
standing question about whether the corpus was simply too easy.

**Do not use SQuAD 2.0.** It is dogfood #1's dataset (`archive/plan-history.md` §4.2), and reusing it here
blurs the two measurements and hands the eventual dogfood session a corpus that has already
been built once.

Criteria, in order of weight:

1. **A genuine absent-data class.** Questions whose answer is not in the corpus, labelled as
   such. Without them `unknown` never legitimately fires, and the `unknown` discipline is one
   of the things worth watching.
2. **Multi-hop questions**, where the second lookup's terms come from the first lookup's
   result. This is what makes an `AgentNode` the right answer rather than a fashionable one,
   and it is how the central claim gets tested.
3. **At least 50,000 words of corpus**, per §3 above.
4. **Short checkable answers**, so scoring needs no judge model.
5. **Not SQuAD 2.0.**

**Recommended: MuSiQue.** Multi-hop by construction, its full variant carries answerable and
unanswerable pairs, the corpus is paragraphs that pool naturally to whatever size is wanted,
and answers are short spans. It satisfies every criterion.

**Alternative: QASPER.** Questions over NLP papers with a real unanswerable class, and the
documents are long, so context pressure comes from document length rather than count. Answers
are sometimes free text, which matters less here than it would in a dogfood.

Verify whichever is chosen against the criteria rather than trusting this recommendation, and
record what was checked. **Two wrinkles to handle at build time**, both learned at item 5:

- **An unanswerable question can become answerable once paragraphs are pooled**, which scores a
  correct answer as false confidence. Verify each unanswerable against the whole pool, or draw
  the pool from unrelated sources.
- **Every public benchmark is contaminated**, so the agent can answer from memory. That is
  survivable here because this checkpoint measures API usage rather than agent quality. Record
  it so nobody later cites the number as evidence the library produces accurate agents.

## 5. Holding the answers

**Expected answers must not be in the working directory while a session runs.** A coding agent
working there will read them, and anything measured afterwards means nothing.

Item 5's arrangement worked and should be repeated: the corpus lives where the session works,
the answers live at `~/checkpoint-answers/`, outside `Projects/` so neither the session nor a
stray search reaches them, and the corpus README describes them as belonging in the working
directory, where they go back once scoring is done.

## 6. Environment

The session gets the installed wheel and nothing else. No repository, no `src/`, no
`dev-docs/`.

```
uv venv --python 3.12            # the default python on this machine is a conda 3.7.7
uv pip install /home/thilina/Projects/simple-agents/dist/simple_agents-0.0.0-py3-none-any.whl
```

Rebuild the wheel first if anything in `docs/` has changed since the last build, or the
installed copy is stale.

`MISTRAL_API_KEY` is in `/home/thilina/Projects/simple-agents/.env` and nothing loads it
automatically. **Whether to tell the session that is a decision to take deliberately**: session
A wrote its own eight-line loader and session B did the same without complaining, and both
count as friction worth measuring rather than as something to pre-empt.

For vLLM, `docs/model-clients.md` §4 has the serve command; on this machine use port 8001 and
`--gpu-memory-utilization 0.6`, and add `--enable-auto-tool-choice --tool-call-parser hermes`
or tools cannot be offered at all.

## 7. Shaping the task

**Give the task without a shape.** Prescribing the node kinds throws away the most valuable
thing the session produces. Item 5's session B was given "build an agent that answers questions
about these articles" and nothing else, and what it did with that was the finding.

Say what the corpus is, what the questions are, and that answers should be checkable. Do not
name a node kind, a tool, or a context builder.

**Answer what the session asks, and volunteer nothing.** Being forced to intervene is itself a
result and goes in the log.

## 8. How to analyse it

The item 5 method, which held up:

- **Reproduce every claim against the source before accepting it.** One of session A's claims
  did not reproduce as stated, and the real failure underneath it was worse than the one
  reported. Two findings came out of the verification rather than out of the report.
- **A report praising the library is not evidence.** It is a coding agent praising a library it
  was told was written for it. The load-bearing content is the friction section and the
  defects.
- **Sort into four columns:** library defects, documentation bugs, known gaps, and noise. The
  documentation column is the one the checkpoint exists to fill.
- **Watch what the session did, not only what it says it would do.** Session B's most valuable
  output was that it read the failure taxonomy in full and then tuned four prompt versions on
  one run each anyway. That is behavioural evidence for why the checks have to be executable,
  and it is worth more than any self-report.
- **Turn anything the session guessed at into an elicitation question**, with a scaffold that
  makes it answerable. `runs/checkpoint-item5/findings.md` §7 is the format, and item 12 reads it.

Write the result as `dev-docs/runs/checkpoint-item7/findings.md`, in the shape of
`runs/checkpoint-item5/findings.md`. Fixes that are mechanical and unambiguous can land as they are
verified; anything that changes the public API or a settled decision is held and put to Thilina
with the argument, as the four held items were at item 5.
