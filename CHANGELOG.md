# Changelog

All notable changes to Simple Agents are documented in this file, including every change to
an on-disk format a project holds: trajectory, manifest, suspension, shelf, conversation,
comments, results file and variant comparison.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `Job`, declared under `Product(jobs=[...])`: a run that starts without the end user, on a
  schedule, on a change or after another job. The ship page draws it beside the surfaces, the
  operate page reads what each job has done, and FT-34 reads the design's product section
  against it. `docs/product.md` §6.
- `Pipeline.run(trigger=...)`, the declared job's name, recorded on the manifest.
  `runs(trigger=...)`, `simple-agents report --trigger` and `simple-agents check --trigger`
  read those runs back.
- `Prompt`, `Value` and `Section`: a prompt is written as fixed text with named values, so a
  run records what the model was told apart from the data that filled it. `docs/prompts.md`.
- `Prompt.turns`, for messages a run already recorded, and `Prompt.blocks`, for an image or any
  other content a backend takes in place of text. `Prompt.marked` sets what a backend reads off
  a message, such as a cache marker.
- `Value(cap=...)` cuts a value and records what it cut, so a truncated prompt says so.
- FT-46: a prompt that builds its fixed text by interpolation fails, since a step whose
  instruction differs on every example has none that can be read, compared or agreed.
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
- FT-44: a `recorded_at` ahead of the clock the suite runs on fails.
- `ctx.run_inputs` on every node context: what `Pipeline.run(inputs)` was given.
- `EvalSuite.run(stores=...)`, with `CopyPerRollout` and `Shared`. `compare_variants` takes it
  too. `docs/evaluation.md` §6.9.
- `contamination(similarity=...)` and `nearest_cross_split(similarity=...)`, for a similarity
  measure the project supplies.
- `Retry(spent_quota_phrases=...)`, for 429 wordings beyond the ones the library ships.
- `Pipeline.name`, set by `@pipeline_factory` on the pipeline the factory builds. A slice keeps
  the name of the pipeline it came from.
- `runs(pipeline=...)` and `RunHandle.pipeline`, which read the runs of one registered
  pipeline. `simple-agents report --pipeline` and `simple-agents check --pipeline` do the same.
- `RunHandle.scripted`, and `scripted` on a model client: `FakeModelClient` declares it and a
  project's own stand-in can.
- FT-45, an evaluation over a pipeline the project registers nowhere. Twenty-eight checks now
  ship, of forty-five taxonomy entries.
- `simple-agents record decision --from-comment <id>`, which copies what the builder said on
  the view into `considered`, agrees the decision and stamps it.
- A prompts page in `simple-agents view`: every instruction the project sends, as written and
  as one real run sent it, with the pipeline path down the side, each value named with where
  it came from and what a `cap` cut, and an agent loop's later turns from the run.
  `docs/view.md` §6.10.
- Three comment addresses for a prompt: the whole prompt, one value in it, and words selected
  in it. A selection is filed under a digest of the words and keeps them, the run they were
  read in, and the digest the fixed text had.

- The report names the library facilities `research.md`'s survey adopted that no run has
  recorded, from stage `build`. It reads what a row wrote in backticks, and a built-in
  registered under a name of the project's own is read by the version a run recorded. The
  research page marks the same candidates. `docs/conformance.md` §4.4.

### Changed

- The operate page's Now tile for stopped runs is "Waiting", with how many wait on a person
  and how many on a clock under the count; it is marked only where a person is needed. The
  Jobs region splits the same way.
- **Breaking.** From stage `build`, a decision recorded `not_applicable` carries the `stage` it
  was settled at, and that stage is `build` or later (FT-30). Before the code exists the answer
  is a forecast. Re-record each with
  `simple-agents record decision <name> --kind <kind> --status not_applicable --stage build`.
- **Breaking.** From stage `ship`, a `dependency`, `shape`, `constant` or `prompt_rule` decision
  names what it became under `produces` (FT-42). A decision that names nothing can be joined to
  no part of the code.
- **Breaking.** From stage `ship`, a project whose code was read and declares no `Product` fails
  FT-34. Where the code could not be read, the reason is reported and the design is not failed
  for it. `docs/product.md` §2.1.
- The `involvement` question offers two granularities rather than three timings: every decision
  is put to the builder before the thing it decides is built, and what the builder chooses is
  whether they see each as it arises or a batch settled before any code is written. The option
  that put a batch at the stage gate is gone, since the code is written by then.
- `docs/procedure.md`'s `build` stage names `Pipeline.rerun` for a run whose process was killed,
  beside `Pipeline.resume` for one that stopped to ask, and says to put a `prompt_rule` decision
  with the prompt rather than a summary. Its `ship` stage says to design the product surface
  with the builder before building it.
- **Breaking.** A prompt function returns a `Prompt`. A string or a list of message dicts is
  refused with a `ConfigurationError` naming the call that replaces it: in a node's prompt, in
  `ModelHandle.complete`, and in a consultation reader's `Reading.complete`. Text a project has
  already assembled goes through as the fixed text, `Prompt.user(text)`; text that arrived from
  outside the project goes in as a value, since a brace in it would read as a gap.
- `simple-agents comments` prints the words a thread about a prompt quotes and the run they
  were read in, and `--json` carries all four snapshot fields.
- `docs/trajectory-format.md` §6 said prompt text was not in the format, which stopped being
  true at `0.30`: a call built from a prompt carries its fixed text in `inputs.assembly`.
  What the manifest holds and the record does not is the prompt's version.
- Comments format `2`. A thread may carry `quoted`, `quoted_chars`, `run` and `instruction`,
  which is what a thread about words in a prompt keeps so it still reads after the wording is
  rewritten. Every field is optional and a `1` file reads unchanged.
- Trajectory format `0.30`. A `model_call` carries `inputs.assembly`: the fixed text of each
  message, the values that filled it, what any of them cut, `instruction` digesting everything
  fixed about the prompt, and `templates` for the distinct pieces it was built from. Absent on a call whose messages are a conversation, which is every turn of an agent
  loop after the first.
- Manifest format `0.43`. A run records `trigger`, the name of the declared job that started
  it, and `null` on a run somebody asked for.
- Manifest format `0.42`. Each entry in `prompts` carries `text`, which is `written` or
  `interpolated`; `observed`, the distinct instructions that step's calls were built from and
  how often; and `distinct`, how many there were. A prompt's
  recorded version now covers the module-level strings the prompt function passes as fixed
  text, so editing a prompt held in a constant moves the version and
  `Pipeline.behaviour_fingerprint`.
- Manifest format `0.41`. A run records `pipeline`, the registered name of the pipeline it is,
  and `scripted`, whether its model answered from a script. `pipeline` is `null` for a pipeline
  built outside a `@pipeline_factory`, and a run of a slice records the name of the pipeline it
  came from.
- Results file format `0.31`. `config.pipeline` records which registered pipeline was measured.
  `EvalResults.carries("pipeline")` is false on a file written before it.
- `runs("runs/eval/<eval_id>")` needed `nested=True` to list an evaluation's rollouts, which
  `docs/run-envelope.md` §8 now shows. Without it the call returned nothing.
- **`runs()` leaves out runs whose model answered from a script**, and so do
  `simple-agents report`, `simple-agents check` and `node_metrics`. `scripted=None` includes
  them, and `--scripted` does on the commands. A project that wrote `FakeModelClient` runs into
  `runs/` sees its totals change, and one whose every run is scripted is told that rather than
  that it has no run.
- **Every check that reads one run reads the newest run of the pipeline the results file
  measured**, rather than whichever pipeline ran last. FT-13, FT-14, FT-15, FT-32, FT-33 and
  FT-43 all read it. A background pipeline calls no model, so FT-14 used to report that the
  run named no model to pin and a project whose agent floated its model was told nothing.
  `--run` still names a run directly, and the report's header names the pipeline whose
  newest run it read.
- FT-25 reads the newest run of each pipeline rather than the newest run, and passes where any
  of them registers a consultation tool that reaches a node.
- FT-37 and FT-38 read the newest run of the pipeline the results file measured. On a project
  running a background pass every morning, both used to fire on every morning. Where the
  pipeline is named and no run of it is on disk, both report blocked; where the runs predate
  manifest `0.41`, both read the newest run of any pipeline and say so.
- FT-42 and FT-41 read every run whatever its role and whatever answered its model: a name a
  run recorded is a name the project built, and a run that stopped to ask a person stopped.
  FT-42 names the roles that recorded each name. A
  decision about a corpus names the nodes of the pipeline that builds it, and those were
  reported as names the project never built.
- The view's constants marks a number the newest run of every pipeline no longer records as
  gone, dates it, and offers no agreement on it.
- `simple-agents view` counts a run whose model answered from a script like any other: the page
  is a census of what ran rather than a figure about the agent.
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
