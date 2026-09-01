# A judge the library ships

`plan.md` §1 P3-14's record. **Nothing is built, and the shape is not decided.** What is decided
is that the library ships a judge rather than only the seam, which reverses half of `P3-13`'s
decision 5. Everything in "What has to be decided" is open.

## Where it came from

`P3-12` stage 2's Left open, raised at the 2026-08-18 build and put to Thilina. His first
reading, before the premise was checked:

> "It seems obvious that it should carry the same correction everywhere, no? Reasking the same
> thing 8 times without stating the failure is both useless and wasteful. We don't need to build
> it now, but I would add it to the plan queue at the top since it seems important to fix
> immediately."

**Two of that premise's three parts did not survive being measured**, and the section below is
what replaced them. Put back to him with the measurement and three shapes, he chose the largest
and moved the position:

> "I am leaning towards C to be honest. Put it in the schedule after P3-1. But include that the
> solution is not fully decided in the relevant doc."

Shape **C** is a shipped `ModelJudge`, sibling of
[`ModelReader`](../../src/simple_agents/builtins/consult.py#L362). The two shapes not taken were
**a**, `docs/evaluation.md` §12 gaining the pattern in prose, and **b**, a helper wrapping a
per-item judge function with `ModelReader`'s retry.

## What the problem is

**The re-asking is already closed, and this item is not about it.** Measured 2026-08-18 by
reading and by the test that already covers it:
[`test_a_pass_that_answers_nothing_stops_rather_than_asking_again`](../../tests/test_judgements.py#L322)
asserts `rounds == [3]`, one round and not eight. `JUDGE_ROUNDS = 8` in
[`runner.py`](../../src/simple_agents/evaluation/runner.py#L106) (`DEFAULT_JUDGEMENTS`) is a backstop for a rule that
discovers a **new** judgement each round, and
[`_through_judging`](../../src/simple_agents/evaluation/runner.py#L1620) ends the loop on the
first round that answers none of what it asked. Each round also asks only what is still missing.
`P3-13` closed this, and `build-logs/consultation-reading-build-log.md` §6 carries the correction
to the entry that said otherwise.

**The library never calls the judge model, so there is nothing for it to state a failure back
into.** [`_judged_by`](../../src/simple_agents/evaluation/runner.py#L1588) calls the project's
`using` with the whole worklist and takes back `Label`s. It refuses a non-`Label` and a label
keyed to something nothing asked about, and it accepts a short list without comment. That is
`P3-13`'s decision 5 working as designed: Thilina, 2026-08-18, *"ship the seam and no default
judge, make it easy to set one up, and do not get in the way of whatever technique a project
wants."*

**So what failed on the live run was a project's judging function, and every project writes one.**
`build-logs/recorded-judgement-build-log.md` §4: `Qwen3-1.7B` failed schema validation on some
judge calls and the verification harness dropped them silently, so the pass returned fewer
judgements than it was asked for. The harness was ours. The library saw a short list and correctly
reported which answers were still waiting.

**`ModelReader` is now the library's only worked example of stating a failure back to a model, and
a judge cannot reach it.** `ModelReader` owns its model call, so it can hand the model its own bad
reply and the option list again. A judging pass owns its calls and the library owns none of them.

## What has to be decided

1. **Whether `ModelJudge` takes the worklist or one request.** Decision 5's argument against
   calling a project function per judgement was that it fixes the granularity at one model call
   per answer and makes a panel, a batch and a cheap pre-filter impossible or wasteful. A shipped
   judge going per item reintroduces exactly that; one taking the worklist has to decide the batch
   shape, and a retry over a batch has to say which items it is re-asking.
2. **What the prompt is, and what the project fills in.** `ModelReader` owns its question because
   `options` and `chose` are the library's own concepts. A judge's question is the project's
   criterion text, which the library cannot see the meaning of. So a shipped prompt is a frame
   around text it does not understand, and what that frame may assert is the question.
3. **What a response it cannot read costs.** `ModelReader` ends the run, which is right for one
   consultation in one run. Ending a whole evaluation on one unreadable verdict is heavier: the
   rollouts are paid for and on disk. The alternative is returning fewer labels and letting the
   gate refuse, which is today's behaviour and what wasted the live run.
4. **Whether `P3-13`'s decision 5 is amended or held.** It reads *"ship the seam and no default
   judge"*. Shipping one reverses the second half, so the rationale has to be defeated in writing:
   whether a shipped judge that a project can replace is different in kind from a default judge
   that a project inherits.
5. **Whether the panel is this item or another one.** The shipped example set owes a judge **and**
   a panel ([`items/example-projects.md` §19.9](example-projects.md#L1739)), and a panel is the
   technique decision 5 was most careful not to foreclose.
6. **Whether `_judged_by` should say a list came back short.** It accepts one silently today. Even
   with no shipped judge, a pass that answered 3 of 6 and does not know it is a defect a project
   meets before it meets anything above.

## What it waits on

**`plan.md` §1 P3-1**, on Thilina's ordering decision of 2026-08-18. Nothing structural: it can be
designed the day P3-1 closes, and questions 1 to 6 need no measurement that does not exist.

**What it hands to other records.** Question 5 is shared with
[`items/example-projects.md` §19.9](example-projects.md#L1739), and whichever lands first should
say what it left the other.
