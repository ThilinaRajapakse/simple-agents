# Build log — What a stored result is stamped with

`plan.md` §1 `P3-45`. Built 2026-08-27. Closes `DF5-I19`.

## 1. Before any design

**The sitting's measurement was reproduced before anything was changed**, and reproducing it
found the condition the sitting's note left out. Two pipelines identical except for which
function `consult()` was built over gave `sha256:f8801334f452c2d4` and
`sha256:66191df0642e96f5`; two closures over one function gave two more. **The channel has to
have readable source**: [`_derived_version`](../../src/simple_agents/builtins/consult.py#L905)
digests it through `inspect.getsource`, so a first attempt at the repro from a heredoc returned
`version: None` for both pipelines and no difference at all. A project whose channel comes from
`functools.partial` already stamps the same either way.

**Where the channel enters the digest.** [`_tool_entry`](../../src/simple_agents/pipeline/recording.py#L147)
records `version`, which for `consult()` is `version or _derived_version(ask, match)`.
[`behaviour_fingerprint`](../../src/simple_agents/pipeline/core.py#L2070) digests the tool entries
after [`_without_derived`](../../src/simple_agents/pipeline/recording.py#L229) strips `derived`, so
`version` is what carries the channel in.

**What else reads that version, checked before touching it.** The cassette key for a consultation,
and [`_verify_against`](../../src/simple_agents/pipeline/core.py#L858)'s resume comparison, which reads
`entry["version"]` out of `_node_entries` rather than out of the fingerprint. Both are separate
paths and `_derived_version`'s own docstring states the cassette one as deliberate: two consult
tools differing only in channel record under different keys.

## 2. Design

**Settled at dogfood #5's sitting 4**: the consultation channel comes out of
`behaviour_fingerprint`, the library does not ship the artifact store, and `docs/shipping.md` §6
gains the artifact with no pipeline behind it.

**The item left the mechanism to the build, and §1 decided it.** Of the two candidates, excluding
the `ConsultTool`'s version from the stamp and giving that tool a declared version of its own,
only the first leaves the cassette and the resume alone. Changing `version` itself would re-key
every recorded consultation and make an edited channel replay as though unchanged, which is a
different decision from the one the sitting took and one its rationale does not reach.

**So the version comes out for the stamp alone**, read off `answered_by`, which is set on a
consultation tool and `null` on every other kind. What an edited channel now misses on: the
cassette, unchanged, so it still asks again; the resume comparison, unchanged, so it is still
refused unless waived; the stamp, no longer.

**`answered_by`, `reaches` and `permission` stay in the digest.** A channel that stops reaching a
person is a change in what the pipeline does, and `env.with_end_user(...)` is the per-run version
of that question and is on the manifest per consultation.

## 3. Build

[`_without_channels`](../../src/simple_agents/pipeline/recording.py#L208) drops `version` from a tool entry
carrying an `answered_by`, and `behaviour_fingerprint` applies it to the tool list alone. Nothing
else changed: `_tool_entry`, the manifest, the cassette key and `_verify_against` are as they were.

**`docs/shipping.md` §6.1 is new**, and the elicitation scaffold for `stored_output` names the
case, since the question is what a project answers before it builds the artifact.

**Four tests**, and the four propositions are the ones a reader would want: two channels stamp
the same, `answered_by` still moves it, the channel still keys the cassette, an ordinary tool's
version still moves it. **3,595 tests pass.**

**The stamp's docstring was at the 20-line ceiling** and gained three lines, so four paragraphs
were rewritten shorter. One duplicated sentence left: `docs/shipping.md` §6 already said why a
pipeline taking the run's client refuses.

## 4. Verification

**Live, against Gemini** (`gemini-3.1-flash-lite`), on the shape dogfood #5 built: a
`Deterministic` node consulting through the channel, then an `LLMNode` answering on what came
back, with `for_session`'s two channels as two pipelines.

- The two stamp the same, `sha256:dc953ef2478e8520`.
- A run through the engaged channel wrote that stamp to its manifest, and **the slate it produced
  reads as current against the unattended pipeline**, which is the defect the sitting measured.
- A consultation recorded through the engaged channel and replayed through the background one
  **misses**, as before, so the cassette still tells two channels apart.

**3,595 tests pass.** `prose_check`, `shape_check`, `check_docs` and `check_citations` clean.

**Verified again across eight reverification cycles over `P3-44` to `P3-47` together.** What
they added here: the claim that a resume still tells two channels apart was read out of
`_verify_against` at the build and is measured now, two pipelines stamping one value refusing
each other's suspended run under `tools.ask_reader`; and `docs/shipping.md` §6.1 was checked to
reach a coding agent through the `stored_output` scaffold at the moment of use, which is what
`DF5-X7` says a facility needs. The stamp change was re-measured live against vLLM as well as
Gemini.

## 5. Doc consequences

`docs/shipping.md` §6 says the channel is out and what still moves the stamp, and its new §6.1 is
the artifact with no pipeline behind it, what such a thing is stamped with, and that
`stored_output` records which artifacts carry which. `behaviour_fingerprint`'s docstring carries
the same in two sentences. The `stored_output` elicitation scaffold names the case.

`CHANGELOG.md` records that every stamp moves once, and what a project storing results does about
it, which is nothing beyond one refresh.

## 6. Left open

**The library ships no artifact store**, decided at the sitting against the §2.2 entry, and the
reason is in the entry: three of dogfood #5's six artifacts had no pipeline behind them, so a
store keyed on the fingerprint covers half, and `P3-6`'s rule that no check opens project storage
means shipping it buys no check either. `plan.md` §4's line for this item is the record; nothing
queued.

**A channel built by `functools.partial` has no derived version**, so two of them stamped the
same before this change and still do. `consult(version=...)` is what a project uses where that
matters, and `_derived_version` says so. Nothing queued.
