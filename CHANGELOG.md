# Changelog

Notable changes to Simple Agents, newest first. A change to any on-disk format a project
holds (trajectory, manifest, suspension, shelf, conversation, results file, variant
comparison) is recorded here.

## Unreleased

### Added

- `simple-agents record answer <key>` and `simple-agents record decision <name>` write an
  entry into `brief.toml` stamped from the clock, replacing a table already there and leaving
  the rest of the file as it was; `record_answer` and `record_decision` do the same from
  Python. The first project on the public package wrote twenty of thirty-three stamps by hand
  in local time with a UTC suffix.
- FT-44, a stamp the clock did not write: a `recorded_at` ahead of the clock the suite runs
  on fails. Twenty-seven checks.

### Fixed

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
