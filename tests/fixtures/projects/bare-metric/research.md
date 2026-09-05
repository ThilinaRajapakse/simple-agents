# What was already known about answering a question from a passage collection

## The parts, and what each has to do

1. **Finding the passages that bear on a question.** The collection is fixed and large enough
   that reading all of it per question is not affordable.
2. **Answering from what was found.** The answer is a span of the passage rather than a
   summary, and the absence of one has to be reportable.
3. **Deciding a question is unanswerable.** The collection does not cover everything the
   support team asks.
4. **Judging whether a span is right.** Someone has to say what a correct answer is before
   anything is measured.

## What was found against each part

| Part | Candidate | What it is | Outcome |
|---|---|---|---|
| Finding passages | a hosted answering service | question in, answer out, priced per call | rejected: the collection is internal and may not leave the network |
| Finding passages | BM25 over the collection | lexical, no model, ships with this library | adopted: lexical search over the notes, registered as catalogue_search |
| Finding passages | embeddings and a reranker | finds a passage worded differently from the question | adopted alongside BM25: `docs/retrieval.md` |
| Answering | one call reading every retrieved passage | the common shape in published work | adopted |
| Answering | one call per passage, then a merge | more calls, and the merge has to resolve disagreement | rejected: cost, and nothing said the merge was better here |
| Deciding absence | a confidence threshold on the answer | needs a calibrated score the backend does not publish | not investigated, because no backend under consideration publishes one |
| Deciding absence | an output schema that admits `unknown` | refuses to construct a schema that cannot say it | adopted: FT-09 |
| Judging | a second model scoring the span | cheap, and it agrees with itself rather than with the team | rejected for the reported number, kept for development |
| Judging | the support team labelling a held-out set | slow, and the only source of a label they would act on | adopted |

## What this turns on, having looked

**Deciding a question is unanswerable.** Every approach found for the other three parts is
established and the choice between them is cost. How to decide absence well is an open
question: the calibrated-score route needs something no candidate backend publishes, and what
was adopted records absence rather than deciding it. The failure mode reported everywhere is a confident
answer to a question the collection does not cover, and this project has no signal for it
beyond the labels.

**Finding passages worded differently from the question** is the second. BM25 alone misses it,
which is why the retrieval half runs both.

## What the builder said about it

Shown the survey and asked whether the hosted service was worth another look:

> "No. Nothing in that collection leaves our network, and that is not negotiable."

Asked what to do about absence, given nothing found solves it:

> "Then measure it. I would rather know it gets absence wrong a fifth of the time than have
> it papered over. Put absent questions in the set."

That is why the held-out split carries questions the collection does not answer, and why the
reported number is read beside the absence rate rather than alone.
