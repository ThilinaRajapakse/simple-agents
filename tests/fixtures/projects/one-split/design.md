# How the passage question answerer is built

## What it does, step by step

It reads the question and searches the passage collection for the five passages closest to it.
It then reads those passages and returns the shortest span in them that answers the question,
or reports that the collection does not answer it. Nothing else happens: one question in, one
span or one absence out.

## What it holds on to between runs

Nothing. The passage collection is fixed and ships with the project, and every run rebuilds the
index from it. A question asked twice gets the same answer for that reason, and an answer the
support team disagreed with is not remembered anywhere.

## The product

The terminal. One interaction: running the answer script with a question starts a run, and the
printed span is that run's return value, read once. Nothing reads an artifact, because none
outlives the run, and nothing records a judgement.

## What the builder said about it

Shown the two steps and asked whether searching before answering was what they pictured:

> "Yes, and I would rather it looked at five passages than one. If the wording is different
> from the passage it still needs to find it."

Asked whether an answer needing two passages combined should be attempted or reported absent:

> "Report it as absent for now. I would rather be told than guess."

That is why `top_k` is 5 rather than 1, and why the finished version reports absence for a
question no single passage answers.
