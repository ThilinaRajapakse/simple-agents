# Build log — Absence declared where it is enforced

`plan.md` §1 `P3-46`. Built 2026-08-27. Closes `DF5-I29`.

## 1. Before any design

**What the waiver read, and what it could not.**
[`_absence_waived`](../../src/simple_agents/conformance/checks.py#L1405) required
`allow_unknown is False` on every `llm` or `agent` entry in the results file's `config.nodes`.
The `no-absent-examples` fixture is the item's shape in two nodes: `hunt` is an `agent` pointing
at `verify`, an `llm` pointing at nothing, and both carried `allow_unknown: true`.

**What identifies the answering node, checked before deciding it.** `EvalSuite(answer=...)`
takes a field name or a callable over the output, so **it never names a node**, which is the
item's open question answered: the graph is the only thing that can identify one. Each entry in
`config.nodes` carries `successors`, a container entry carries `nodes` for its children, and a
nested pipeline's ids are dot-prefixed, so the walk is possible from the results file alone.

## 2. Design

**Settled at dogfood #5's sitting 4**: the waiver narrows from every model-calling node to the
node producing the scored answer, and FT-04's message reads the brief's `absence_vs_error`.
Rejected there, with reasons recorded in the item: letting the brief waive the gate outright, and
demoting FT-04 to a question.

**Which node that is, decided in the build.** The pipeline's last unit, meaning one that points
at nothing; where that is a pipeline used as a node, its last unit in turn, to a bounded depth;
and where the last unit calls no model, the model-calling nodes that point at it, since a
`Deterministic` step assembling an answer carries no `allow_unknown` to declare on. A loop whose
every node points somewhere falls back to the last declared unit.

**What the message says when no model produces the answer.** The node name is replaced by "the
node producing the scored answer, which calls no model in this pipeline", and the waiver does not
apply, which is right: a pipeline that reaches no model on the answer path has declared nothing.

**The brief is quoted and decides nothing.** `absence_vs_error`'s answer appears in the failure
message beside the fix. The gate still reads the declaration on the node, because that is what
the run manifest records and what a later reader can check.

## 3. Build

[`_answering_nodes`](../../src/simple_agents/conformance/checks.py#L1419) and its three helpers
do the walk; `_absence_waived` reads it. FT-04's message in
[`docs/failure-taxonomy.md`](../../docs/failure-taxonomy.md#L112) gains two placeholders, `node`
and `said`, which `ft_04` fills from the graph and from the brief. The message text lives in that
document and the check renders it, so nothing here holds a second copy.

**Found by writing the test.** The first walk selected the units nothing else points at, which is
the **entry** node rather than the terminal one, so it named `hunt` on a two-node pipeline whose
answer comes from `verify`. `test_the_failure_names_the_node_and_what_the_builder_said` is what
caught it, before any live run.

**`_answering_nodes` was 51 lines and 20 branches on its first draft**, over both thresholds. It
is four named units now, none of them over, and the duplicated model-calling predicate in
`_serving_models` reuses `_calls_a_model`. `checks.py` itself grew 1,680 to 1,747 recorded lines
and is on the pre-release refactor's worklist; several checks read a recorded graph their own
way, and collecting those is that refactor's job rather than this item's.

**Four tests**: the lookup that may be absent, the reverse direction, the message naming the node
and the brief, and an answer a `Deterministic` node assembles naming what fed it. **3,599 tests
pass.** No format moves.

## 4. Verification

**Live, against Gemini** (`gemini-3.1-flash-lite`), on the item's own shape: an `LLMNode` hunting
for a review quote with `Maybe[str]` and `allow_unknown` left true, feeding an `LLMNode` producing
a two-word verdict with `allow_unknown=False`. The evaluation ran, its results file recorded
`hunt` pointing at `judge` and `judge` pointing at nothing, `_answering_nodes` named `judge`, and
FT-04 waived. **Under the rule this replaces, that project could not have waived it at all.**

**3,599 tests pass.** `prose_check`, `shape_check`, `check_docs` and `check_citations` clean.

**Verified again across eight reverification cycles over `P3-44` to `P3-47` together.** What
they found here: FT-04's message filled its quote slot with "the brief records no answer to
absence_vs_error" where the brief has none, so the sentence read as though the builder had said
it; `docs/procedure.md`'s measure stage still said only "Include examples whose correct answer
is absence", which is the instruction that produced dogfood #5's twenty invented ones, and the
escape this item narrowed was in no line the procedure carries; and the walk was never exercised
over a pipeline used as a node, a loop, an answer no model produced, or a results file whose
entries record no `successors`. All four are tests now.

## 5. Doc consequences

`docs/failure-taxonomy.md` FT-04 gains which node has to declare it and that a step on the way to
the answer declares nothing, and its failure message names the node and quotes the brief. The
passing detail says "the node(s) producing the scored answer" rather than "every model-calling
node". `CHANGELOG.md` records that a pipeline which waived before still waives.

## 6. Left open

**Nothing joins the brief's answer to the declaration.** `absence_vs_error` is quoted in the
failure and no gate fails on the two disagreeing, which was rejected at the sitting: the brief is
prose the coding agent writes. If a project appears where the builder said absence is impossible
and the pipeline declares otherwise with the gate satisfied by invented examples, that is the
evidence for a check. Nothing queued.

**Several units in `checks.py` read a recorded graph, each its own way**: `_serving_models`,
`_planned_from_the_manifest`, `_unseeded`, `_reported_metrics`, `_consultations_in_the_results`
and this item's `_answering_nodes`. Collecting them belongs to the pre-release refactor,
built 2026-08-31 as `P3-63`
([build log](pre-release-refactor-build-log.md#L1)), which gave them `conformance/recorded.py`. *(This entry named six line numbers until the
sixth reverification cycle, and every one of them had rotted by the time it was read back,
which is what `CLAUDE.md`'s rule about naming a citation's subject is for. Bare numbers in
prose are the form `check_citations` cannot see.)*
