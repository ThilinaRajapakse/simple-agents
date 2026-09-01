"""The versioned record formats: what a run writes that a project holds on disk.

Every module here defines a file format a project keeps and our format changes can break:
the trajectory, the manifest, the cassette, a suspension, the shelf, a conversation, and the
comments file. `CHANGELOG.md` records every change that moves one. The results-file format
lives with its writer in `evaluation/results.py`.
"""
