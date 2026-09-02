# What the procedure reaches

`plan.md` §1 P3-76's record. **Nothing is built.**

## Where it came from

Five candidates from dogfood #6's sitting of 2026-09-02, all about the procedure and the
documents: [`DF6-I12`](../runs/dogfood-6/inventory.md#L62), [`DF6-I13`](../runs/dogfood-6/inventory.md#L63), [`DF6-I17`](../runs/dogfood-6/inventory.md#L67), [`DF6-I18`](../runs/dogfood-6/inventory.md#L68), [`DF6-I16`](../runs/dogfood-6/inventory.md#L66).
Thilina ruled `DF6-I16` at the sitting: the product's design is a section the `ship` gate reads
and the procedure says to put to the builder before building, and no seventh stage.

## What the problem is

- **Research adopts library facilities and the build does not reach them** ([`DF6-D12`](../runs/dogfood-6/findings.md#L312)):
  five adopted, one used, `MemoryStore` unbuilt for the third project running, fetching outside
  the tool layer again.
- **`Pipeline.rerun` was not found** ([`DF6-D13`](../runs/dogfood-6/findings.md#L329)) and a killed import was rebuilt as chunked
  runs with a memory note saying the library has nothing for it.
- **A decision kind marked `not_applicable` is never re-asked** ([`DF6-D17`](../runs/dogfood-6/findings.md#L382)): the catalogue
  went into the code with no `dependency` decision until the builder asked.
- **A `prompt_rule` decision was put to the builder as a summary** ([`DF6-D17`](../runs/dogfood-6/findings.md#L382)); the builder
  asked for the text and found eighteen caps.
- **The product after `ship` has no shape** ([`DF6-D16`](../runs/dogfood-6/findings.md#L368)), for the second project running.

## What has to be decided

- **The adopted-row check**: an `adopted` row naming a library name is read against what the
  code imports and the manifests record; a check or a view region, and what it says.
- **Where `rerun` is named** for a builder who asks for resumability: the procedure's feature
  index names it already, so the question is which sentence the coding agent reads.
- **Re-asking `not_applicable`** at `build`, and whether FT-30 refuses a kind that stayed
  `not_applicable` past a stage where its evidence exists.
- **The prompt text with a `prompt_rule` decision**: the recorded prompt from a run, whole,
  and the procedure saying so.
- **The product design section**: `stored_output`'s wording, FT-34's clause, and whether a
  changed section re-asks the question.

## What it waits on

none
