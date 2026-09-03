# Changelog

Notable changes to Simple Agents, newest first. A change to any on-disk format a project
holds (trajectory, manifest, suspension, shelf, conversation, results file, variant
comparison) is recorded here.

## Unreleased

### Added

- `DocumentIndex.add`, `.replace` and `.remove`: a corpus that changes is updated rather than
  rebuilt, and only the documents given are embedded. An add inside a running pipeline takes
  the `Retrieval` handle, so its embedding calls are recorded and replayed like any other.
- `NumpyVectors`, the vector store an index now builds where numpy is installed. Exact, and
  the same order `VectorScan` returns: 3.5 ms against 60 ms on 10,000 documents at 768
  dimensions, and 7.1 ms against 590 ms on 100,000, in a tenth of the memory. `VectorScan`
  stays as the fallback where numpy is unavailable.
- `FaissVectors`, behind a new `ann` extra (`pip install 'simple-agents[ann]'`): an exact or
  an approximate index, on the CPU or on a GPU. `docs/retrieval.md` §4.3 has the GPU install,
  which is a separate FAISS distribution.
- `DocumentIndex.load(vectors=...)`, so a saved index is read into the store the project
  wants rather than the default one.
- `simple-agents record answer <key>` and `simple-agents record decision <name>` write an
  entry into `brief.toml` stamped from the clock, replacing a table already there and leaving
  the rest of the file as it was; `record_answer` and `record_decision` do the same from
  Python. The first project on the public package wrote twenty of thirty-three stamps by hand
  in local time with a UTC suffix. The keys above the tables go through the same command:
  `record set`, `record confirmed <idea|research|design> --at`, `record read-against` off the
  newest run's stamp, and `record shape <pipeline>` off the registered pipeline's.
- FT-44, a stamp the clock did not write: a `recorded_at` ahead of the clock the suite runs
  on fails. Twenty-seven checks.

### Changed

- **Manifest format `0.40`.** Each entry under `tools` gains `retrieval`, which is how the
  index that tool searches ranks: the ranking, the fusion, the reranker, the store and
  whether it is exact, the analyzer, and the model that embedded the corpus. It is part of
  `behaviour_fingerprint`, so a stored result says which store produced it and an evaluation
  reports a changed store rather than comparing figures across one. The manifest also gains a
  `retrieval` array counting each index when the run ends, which is outside the fingerprint:
  a corpus that grew has not changed how the pipeline behaves.
  **An evaluation whose rollouts were recorded before this refuses to score them beside new
  ones where a tool searches an index**, naming `tools.<name>.retrieval` as the field that
  moved. A project with no `DocumentIndex` is unaffected: the key is `null` there, and an
  absent key and a `null` one compare equal.
- **Index file format `2.0`.** `DocumentIndex.save` writes the vectors to a binary file
  beside the JSON one (`corpus.index` and `corpus.index.vec`) rather than base64 inside it,
  and records the analyzer that cut the text into words. Both files move together. `load`
  still reads a `1.0` file, so a saved corpus does not have to be embedded again.

### Fixed

- **An index given `vectors=` a store of its own never embedded anything.** The documented
  way to supply a store returned an index whose semantic arm found nothing, with nothing
  raised. A store handed in empty is now filled from the corpus, one handed in full is used
  as it is, and one holding part of the corpus has the rest embedded.
- **`save` dropped the vectors of any store that was not a `VectorScan`**, writing a file that
  looked saved, and `load` then re-embedded the whole corpus. A store that cannot hand its
  vectors back is refused at `save`, naming the two methods to add.
- **A re-embedding load left the index with no recorded embedding model**, which switched off
  the refusal of a query embedded by a different model for the life of that index.
- **`VectorScan`'s documented memory figures were a `float32` matrix's**, understating what a
  list of Python floats holds by a factor of ten. Measured: 307 MB at 10,000 documents and
  3.0 GB at 100,000, at 768 dimensions.
- **A `DocumentIndex.save` that was refused left the index it saved over unreadable.** The
  vectors were written before the checks and the documents after them. Both files are now
  written beside the real ones and moved into place once every check has passed.
- **Loading an index built the whole corpus as Python floats**, about nine times the size of
  the file: 30 MB on disk became 269 MB in memory for 7,308 vectors at 1,024 dimensions. It is
  read as a `float32` matrix where numpy is installed, and that load is half the time.
- A brief answer drawn beside the code was cut at 300 characters, mid-word and unmarked, in
  the seams and in the rows where the brief and the code disagree. The cap was a named
  constant and survived the sweep that removed the rest. A step's docstring and a
  consultation question now cut at a word.
- A step that decides for itself read as "resolve_show is a decides for itself" wherever the
  page put its kind into a sentence: the rows where the brief and the code disagree, the
  findings, a step's comment label, and the line saying a step changed kind. The card label
  is unchanged; a sentence takes the noun.
- The note marking a message as sent ran past the right edge of the constants table at every
  window width. The run picker, up to 24 chips in a row that could not wrap, took the whole
  build page sideways.
- A one-click action waited for the server to re-read the whole project before it showed
  anything, which is over two seconds on a project with runs. It answers the click at once
  and reconciles behind that.

## 0.1.2 (2026-09-01)

### Fixed

- `simple-agents view --serve` lost the pipeline drawing after its first render. Loading a
  project forgot every module under the project directory, and a virtual environment usually
  sits there, so the library unimported itself: the second load read an empty registry and
  reported no problem. Installed packages now stay imported.
- A malformed `brief.toml` killed a `--serve` request with a traceback instead of reporting
  the problem on the page. Same cause: the re-imported library gave `ConfigurationError` a
  second identity, so the handler stopped matching it.
- An `agent.py` that will not import drew an empty frame reading "Registered pipelines:
  none", which named the wrong cause, and filed the real reason on the `ship` page. The frame
  now names the import failure and the error, and it is the first finding the page leads with.
- The view showed only the first 600 characters of a brief answer, a decision, a
  `research.md` section or an `idea.md` section, cut mid-word with no marker, and collapsed
  the line breaks in the questions region. Every one is now carried whole, with its own
  paragraphs and indents, clamped with a control that shows the rest.
- Every remaining cut in the view lands on a word and shows that it cut. A summary surface
  (the masthead, a step's rail, a table cell, a tooltip) carries the whole of the text in its
  `title`, and the page it files under holds all of it.

## 0.1.1 (2026-09-01)

### Fixed

- `AGENTS.md` and the procedure now say where the installed docs live:
  `simple_agents.docs_path()` prints the directory.
- New asking rule in the procedure: prose questions are not mixed into an exchange with
  questions put through the session's question mechanism, and an unanswered question is put
  again.

## 0.1.0 (2026-09-01)

First public release.

Formats at release: trajectory `0.29`, manifest `0.39`, suspension `0.5`, shelf `0.1`,
conversation `0.2`, results file `0.29`, variant comparison `0.3`.

`0.1.0.post1` and `0.1.0.post2` corrected the package summary and the README quick start.
