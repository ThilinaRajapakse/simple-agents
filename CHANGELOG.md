# Changelog

All notable changes to Simple Agents are documented in this file, including every change to
an on-disk format a project holds: trajectory, manifest, suspension, shelf, conversation,
results file and variant comparison.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `DocumentIndex.add`, `.replace` and `.remove`: only the documents given are embedded.
- `NumpyVectors`, the vector store an index builds where numpy is installed. `VectorScan`
  remains the fallback.
- `FaissVectors`, exact or approximate and on the CPU or a GPU, behind a new `ann` extra
  (`pip install 'simple-agents[ann]'`). `docs/retrieval.md` §4.3 has the GPU install.
- `DocumentIndex.load(vectors=...)`, to read a saved index into a named store.
- `simple-agents record answer <key>`, `record decision <name>`, `record set`,
  `record confirmed`, `record read-against` and `record shape`: each writes one entry of
  `brief.toml` stamped from the clock. `record_answer` and `record_decision` do the same from
  Python.
- FT-44: a `recorded_at` ahead of the clock the suite runs on fails. Twenty-seven checks.
- `ctx.run_inputs` on every node context: what `Pipeline.run(inputs)` was given.
- `EvalSuite.run(stores=...)`, with `CopyPerRollout` and `Shared`. `compare_variants` takes it
  too. `docs/evaluation.md` §6.9.
- `contamination(similarity=...)` and `nearest_cross_split(similarity=...)`, for a similarity
  measure the project supplies.
- `Retry(spent_quota_phrases=...)`, for 429 wordings beyond the ones the library ships.

### Changed

- Results file format `0.30`. `config.stores` records each store's isolation.
  `EvalResults.carries("stores")` is false on a file written before it, and a file scored with
  `rescore` records `null`.
- Manifest format `0.40`. Each entry under `tools` gains `retrieval`, which is part of
  `behaviour_fingerprint`, and the manifest gains a `retrieval` array outside it. An
  evaluation whose rollouts were recorded before this refuses to score them beside new ones
  where a tool searches an index. A project with no `DocumentIndex` is unaffected.
- Index file format `2.0`. `DocumentIndex.save` writes the vectors to a binary file beside the
  JSON one (`corpus.index` and `corpus.index.vec`) and records the analyzer. Both files move
  together, and `load` still reads a `1.0` file.
- `EvalSuite.run`, `EvalSuite.record` and `compare_variants` over a pipeline whose steps
  declare a store in `touches=` are refused until `stores=` covers each of them. `Shared("<reason>")` is the declaration for a store no rollout
  writes.
- A slice returns its own last node's output. `pipeline.slice(end="select")` and a `nodes=` set
  ending short of the terminal used to raise `LeftTheSlice`.
- A resume that fails part-way leaves its suspension in place. The nodes the failed attempt
  completed run again on the next resume and write their records twice.
- `Example.text` reads numbers and booleans as well as strings, which moves what
  `contamination` and `nearest_cross_split` report for a project with numeric inputs.
- `contamination` and `nearest_cross_split` warn when every compared pair scored alike.
- Gemini's depleted-prepayment 429 stops the run instead of climbing the retry ladder.
- A rate-limit refusal from a backend that publishes no allowance advises `concurrency=`.
  `PacedClient` warns as it is built when the adapter it wraps declares its backend
  publishes none.

### Fixed

- An index given `vectors=` a store of its own never embedded anything, and its semantic arm
  found nothing with nothing raised. A store handed in empty is filled from the corpus, and one
  holding part of the corpus has the rest embedded.
- `save` dropped the vectors of any store that was not a `VectorScan`, and `load` then
  re-embedded the whole corpus. A store that cannot hand its vectors back is refused at `save`.
- A re-embedding load left the index with no recorded embedding model, switching off the
  refusal of a query embedded by a different model.
- A `DocumentIndex.save` that was refused left the index it saved over unreadable. Both files
  are written beside the real ones and moved into place once every check has passed.
- Loading an index built the whole corpus as Python floats. It is read as a `float32` matrix
  where numpy is installed.
- `VectorScan`'s documented memory figures were a `float32` matrix's. Measured: 307 MB at
  10,000 documents and 3.0 GB at 100,000, at 768 dimensions.
- A brief answer drawn beside the code was cut at 300 characters, mid-word and unmarked. A
  step's docstring and a consultation question now cut at a word.
- A step that decides for itself read as "resolve_show is a decides for itself" wherever the
  view put its kind into a sentence. A sentence takes the noun.
- The note marking a message as sent ran past the right edge of the constants table, and the
  run picker took the build page sideways at more than a few runs.
- A one-click action waited for the server to re-read the whole project before it showed
  anything. It answers the click at once and reconciles behind that.

## [0.1.2] - 2026-09-01

### Fixed

- `simple-agents view --serve` lost the pipeline drawing after its first render. Loading a
  project forgot every module under the project directory, so the library unimported itself
  and the second load read an empty registry. Installed packages now stay imported.
- A malformed `brief.toml` killed a `--serve` request with a traceback instead of reporting the
  problem on the page.
- An `agent.py` that will not import drew an empty frame reading "Registered pipelines: none".
  The frame now names the import failure and the error, and it is the first finding the page
  leads with.
- The view showed only the first 600 characters of a brief answer, a decision, a `research.md`
  section or an `idea.md` section, cut mid-word with no marker, and collapsed the line breaks
  in the questions region. Every one is now carried whole, clamped with a control that shows
  the rest.
- Every remaining cut in the view lands on a word and shows that it cut. A summary surface
  carries the whole of the text in its `title`, and the page it files under holds all of it.

## [0.1.1] - 2026-09-01

### Fixed

- `AGENTS.md` and the procedure now say where the installed docs live:
  `simple_agents.docs_path()` prints the directory.
- New asking rule in the procedure: prose questions are not mixed into an exchange with
  questions put through the session's question mechanism, and an unanswered question is put
  again.

## [0.1.0] - 2026-09-01

First public release.

Formats at release: trajectory `0.29`, manifest `0.39`, suspension `0.5`, shelf `0.1`,
conversation `0.2`, results file `0.29`, variant comparison `0.3`.

`0.1.0.post1` and `0.1.0.post2` corrected the package summary and the README quick start.

[Unreleased]: https://github.com/ThilinaRajapakse/simple-agents/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/ThilinaRajapakse/simple-agents/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/ThilinaRajapakse/simple-agents/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ThilinaRajapakse/simple-agents/releases/tag/v0.1.0
