# The passage question answerer

## What this is

An agent that takes a question and a collection of passages, and returns the shortest span that
answers it. Where the collection does not answer the question, it says so instead of guessing.

## Who it is for

The support team who maintain the collection. They are not the builder, and they act on an
answer without reading the passage it came from.

## What it works on

Questions in plain English, against a passage collection the project builds into a
`DocumentIndex`. Passages run to about 120 words. Of the 20 questions read before anything was
written, 3 have no answer anywhere in the collection, which is why absence is a first-class
answer rather than a fallback.

## Where this is going, and where it is not

The smallest version worth having answers span questions and reports absence for the rest. The
finished version cites the passage each answer came from, so an answer can be checked without
reading the whole collection. Not part of this: writing new passages, answering questions that
need two passages combined, and any interface beyond the command line.

## What is still open

Whether a question needing two passages should be answered or reported as absent. The builder
has not decided, and the current behaviour reports absence.
