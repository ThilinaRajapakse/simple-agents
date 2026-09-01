# Area J: can a coding agent build from the shipped documents alone?

Three coding agents were each given a fresh venv with the built wheel, their own copy of the
fifteen shipped documents, a live Gemini key, and a build task. **Each was forbidden from reading
this repository or the installed package's Python source.** They could read the `.md` documents,
tracebacks, and `--help`.

The prohibition is the measurement. A coding agent that falls back to reading the source is
answering a different question. All three worked within it and recorded the points where they
could not proceed as gaps rather than looking.

| | Task | Result |
|---|---|---|
| **J1** | Two-node pipeline, a hand-written tool, labelled examples, evaluation with intervals, record and replay | **Complete.** Verdict written |
| **J2** | An agent that consults the end user, a typed reply, routing, suspend and resume, then an evaluation of it | **Complete.** Verdict written |
| **J3** | Lexical search, semantic search, reranking, cross-run memory | **Incomplete.** Working code and a full log; the session limit ended it before the verdict |

Their working directories are under
`/tmp/claude-1000/.../scratchpad/docstest/j{1,2,3}/`, each with `DOCS-LOG.md` and, for J1 and J2,
`VERDICT.md`.

---

## The headline: yes, and it took five failed attempts

**J1 built a complete, evaluated agent from the documents alone.** Two nodes, a `Maybe[str]`
schema, budgets on pipeline and node, a run envelope writing manifest, trajectory, cassette and
workspace, 9 labelled examples over 4 sources split dev and held-out, `suite.record` of 15 live
rollouts for $0.0133, then `suite.run` replaying them offline, verified with a placeholder API key
at `hits: 3 / misses: 0` per rollout. It reported accuracy `0.800 [0.400, 1.000]` and
`false_confidence_rate 0.200 [0.000, 0.600]`, all six rates with intervals and the method named.
`suite.rescore` re-scored under a looser matcher with no model call. `simple-agents check` passed
11 of 11, exit 0.

**J2 built a working consulting agent**: six nodes, a consultation offering three fixed options, a
typed `Reply` carrying `chose`, and a four-way route covering the three options, an unmatched
answer and a refusal. All four branches were exercised live and each took the correct edge. All
three resolutions were produced and read back from the trajectory.

J1's own summary of why this worked is worth keeping: **"the library's error messages were
consistently better than the docs at exactly the points where the docs were wrong."**

---

## J-1. `resume(answer=...)` delivers to an `AgentNode` and to nothing else, and the documented example uses the node kind that fails. Major.

**J2 could not resume its consulting agent by the documented call.** `pipeline.resume(run_id,
answer="express")` re-enters the `Deterministic` node holding `consult`, calls the channel again,
and raises `RunSuspended` a second time. `answers={"ask": "express"}` fails identically. The same
consultation inside an `AgentNode` resumes correctly on the first attempt.

**The documentation points the builder at the failing configuration.**
[tools.md §4.6.1](../../../../docs/tools.md) shows the consultation on a `Deterministic` node.
[pipeline.md §1.8](../../../../docs/pipeline.md) says "Every other node runs again from the
beginning, **which is why a `Deterministic` node has nothing to lose**". A `Deterministic` node
holding a pending consultation has the question to lose, and loses it.

**Independently found from the other side.** Area H recorded the same behaviour as `H-08d`: *"a
`Deterministic` node whose tool suspended is never handed the answer: it runs again from the
beginning, calls the tool again, and suspends again. The run cannot be continued."* Two agents,
two directions, one defect.

J2's workaround was to rebuild the pipeline with a channel that returns the answer instead of
raising. It completes and routes correctly, and it costs the trajectory its record pairing: the
answering record carries `answers: null` instead of naming the pending record, so
`trajectory-format.md` §4.3's counting rule reports three consultations for one question.

---

## J-2. `on_reply(field=...)` is documented to work over a dict, does not, and silently takes the wrong branch. Major.

[tools.md §4.6.1](../../../../docs/tools.md) says to "Use `field=` where the node returns a model **or
a dict** rather than the reply itself", and the `on_reply` docstring repeats it.

`field=` is an attribute lookup. Over a dict it finds nothing, and a missing reply is
indistinguishable from a refusal, so the route takes the `declined` branch without saying anything.
J2 verified it offline: `route({'reply': reply}, None)` returns `'stop'` for a reply whose `chose`
is `'express'`, while the same reply on a pydantic model returns `'apply'`.

A field annotated `str` has the same silent outcome by a different path: it coerces the `Reply` and
drops `chose`.

**A route that cannot find the reply picks a branch rather than refusing.** That is the failure the
typed consultation answer was built to remove.

---

## J-3. An evaluation of a consulting agent reports a total failure rate. Confirmed from the builder's seat.

J2 ran it: an evaluation whose channel suspends scores every rollout `failed` and reports
`failure_rate 1.000 [0.610, 1.000]`. The same agent with a channel that answers reports
`accuracy 0.917 [0.750, 1.000]` with `consultation_resolutions={'answered': 7, 'unmatched': 2,
'declined': 3}`.

This is `F-1` in `area-f-evaluation.md` seen by a builder rather than by a test. J2 also found that
[evaluation.md §5](../../../../docs/evaluation.md) says only that "An evaluation supplies the
consultation channel" and nothing else anywhere explains how.

**What did hold, and is worth recording**: replaying against a channel that would raise `Suspend`
never reaches the channel. J2 calls that "the one non-obvious promise in the consultation
documentation that held".

---

## J-4. Documented statements J1 found to be false

- **[evaluation.md §6.1](../../../../docs/evaluation.md)** says re-running an evaluation "writes into
  the same directory and the second overwrites the first". The library refuses with
  `ConfigurationError`, in the exact paragraph a reader consults to learn whether re-running is
  safe.
- **[evaluation.md §3](../../../../docs/evaluation.md)** says an empty-denominator metric "reports
  `value` as `None`". `Metric` has no `value` field; `interval` is what is `None`. A reporting loop
  written from §3 and §4 together raises `AttributeError` on the first replay.
- **[procedure.md](../../../../docs/procedure.md) and
  [failure-taxonomy.md](../../../../docs/failure-taxonomy.md)** give the `idea.md` section heading as
  "where this is going and where it is not". FT-29 accepts it only with a comma before `and`, and
  that comma appears in no document. A project following the documents fails the check.
- **[pipeline.md §2.4](../../../../docs/pipeline.md)**'s "refused before the run starts" does not hold
  inside `EvalSuite.run`, which scored 15 configuration failures as a complete six-rate result.
- **[run-envelope.md §3](../../../../docs/run-envelope.md)**'s CI-replay claim needs an API key string
  that nothing documents.
- `Recording` returns a non-zero `spend` with `currency=None`.

---

## J-5. What J3 searched for in the documents and could not find

J3's log is the most useful artifact of the three for the shipped-document review, because it
records search terms rather than conclusions. Nothing in `docs/` answers:

| Looked for | Outcome |
|---|---|
| `Retrieval`, the handle a hand-written retrieval tool must accept | one hit in all of `docs/`, the title of `retrieval.md`. It is exported from `simple_agents` |
| how to write a custom search tool at all | nothing |
| the shape of a `memory_search` result payload | nothing |
| the default model for `SentenceTransformerEmbeddings` | hinted in an error example, never stated |
| the default model for `LocalCrossEncoder` | nothing |
| what `from_directory` uses as a `doc_id` | nothing |
| whether `top_n` caps `top_k` | nothing |
| `call_kind` | only in `retrieval.md` §6, absent from `trajectory-format.md` |
| how to price a locally-run model inside a per-model basis | `DeviceBasis` alone is covered, not mixing |

The tools claim inventory flagged the `Retrieval` omission independently.

---

## What this exercise did not establish

- **Three agents is not a sample.** Each met the documents once, on one task, with one model.
- **J3 has no verdict.** Its code and log survive and its conclusions are not written up.
- **None of them attempted the `brainstorm` stage's full elicitation**, or the conformance gates
  beyond J1's single `simple-agents check`.
- **A coding agent that had read the source would not reproduce this.** The result is about the
  documents as a prompt surface, which is what it was meant to measure, and it says nothing about
  whether the library is easy to use with the source open.
