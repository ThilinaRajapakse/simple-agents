# Random Stuff

Where Thilina puts thoughts that need addressing but are not scoped yet.

**An entry is temporary and carries the date it was written.** It gets a destination at the next
sitting: scheduled into `plan.md` §1, accepted into §2.1, deferred into §2.2, folded into the
document that owns the subject, or dropped with the reason recorded. Then it leaves this file.
`check_docs.py` reports an entry older than 3 days and fails on one older than 7.

**Entries are not numbered.** A number is an identity, an identity gets cited, and a citation is
what creates the pressure to leave a husk behind after the entry moves. Nothing cites into this
file. *(It was numbered until 2026-08-15, and six items had collected about twenty citations from
twelve files. The count-or-total seam sat here for eight days and five separate records had to name
it, because it had nowhere else to be named.)*

**Thilina's Corner is exempt from the age check.** It is reported, never failed, and an item there
is resolved only when he says so.

---

## Unscoped

**New entries go here**, one bullet each, opening with the date: `- *2026-08-15.* <the thought>`.

- *2026-08-31.* `check_citations` verifies `.py` targets and not `.md` ones: a link to a
  deleted `dev-docs` file sat unflagged in a build log until read by hand. A rule with a
  fixture would close it.
- *2026-08-31.*  resolves example imports from the package root and misses a
  submodule path:  passed clean for a module that no
  longer exists (found at the  reverification, fixed in place). Same shape as the
  -link gap above.
- *2026-08-31.* `prose_check` resolves example imports from the package root and misses a
  submodule path: `from simple_agents.reporting import ...` passed clean for a module that
  no longer exists (found at the `P3-64` reverification, fixed in place). Same shape as the
  `.md`-link gap above.
- *2026-08-31.* A test-suite hygiene pass: outdated and duplicated tests, not speed (4,083
  tests in 180s measured healthy at `P3-63`). Raised at the `P3-63` build report; whether it
  becomes an item behind the release or is declined is Thilina's call.
- *2026-09-01.* A `§`-existence rule beside the `.md`-link one: a `docs/x.md §N` reference
  whose target document has no heading `N` goes unreported. A sweep at `P3-66` checked 358 of
  them by script and found none broken, after fixing by hand the class the checks cannot see
  (twenty-plus stale `runs/<eval_id>/` path shapes from the 2026-08-28 run-filing change).



## Thilina's Corner

**Always read it, but don't edit it without his permission. Ask for clarification when needed,
never make assumptions about anything in Thilina's corner. When items get resolved, ask Thilina if
they should be marked as resolved.**

- *2026-08-28.* Plain language docs/explanations/guides for the builder
- *2026-08-09.* I'm doing a pass on some of the docs and stripping out some of the more flowery, defensive, hedging, and weird language.
  - Made some changes and added a lot of comments to the README.md to fix and think about some of the language and tone issues. We should go through it again after the evaluation item lands and maybe before the doc updates for that item.
  - The README might be pushing the idea that this library is written for coding agents a bit too much. It's not FOR coding agents, it's ALSO for coding agents. This does not mean that you should now go around and change everything in the opposite direction with defensive language, but it's something to keep in mind. If there are places where this message is being pushed, bring them up, and we can discuss it.
  - Stop using this stupid, defensive question and answer format in the docs. Docs disseminate information, not arguments.
  - Builder-facing docs should always be written for when the library is released in mind. Not the current state of development.
  - When you are discussing a change with me, you need to provide context. At the least, I need the original wording, proposed wording, and my comment that triggered it.

## To-do's for Thilina (Don't write here)

- Check what was added to `docs/tools.md`.
