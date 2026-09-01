# Changelog

Notable changes to Simple Agents, newest first. A change to any on-disk format a project
holds (trajectory, manifest, suspension, shelf, conversation, results file, variant
comparison) is recorded here.

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
