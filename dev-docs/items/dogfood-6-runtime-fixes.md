# Dogfood #6's runtime fixes

`plan.md` §1 P3-74's record. **Nothing is built.**

## Where it came from

Six candidates from dogfood #6's sitting of 2026-09-02, each cheap and each in the runtime or
the evaluation: [`DF6-I01`](../runs/dogfood-6/inventory.md#L51), [`DF6-I02`](../runs/dogfood-6/inventory.md#L52), [`DF6-I03`](../runs/dogfood-6/inventory.md#L53), [`DF6-I10`](../runs/dogfood-6/inventory.md#L60),
[`DF6-I15`](../runs/dogfood-6/inventory.md#L65), [`DF6-I19`](../runs/dogfood-6/inventory.md#L69).

## What the problem is

- **A slice's own end node routes to a cut successor** ([`DF6-D1`](../runs/dogfood-6/findings.md#L114)): `slice(end=)` and a
  `nodes=` set ending short of the terminal raise `LeftTheSlice` on every run, reproduced on
  three `Deterministic` nodes; the docs' example cannot run.
- **An evaluation over a pipeline that reads back what it writes** ([`DF6-D2`](../runs/dogfood-6/findings.md#L139)): twenty-three
  rollouts on one database copy blocked each other's picks, and the documented rule sends writes
  under the workspace, which this pipeline could not use.
- **A node after a model node cannot read the run's inputs** ([`DF6-D3`](../runs/dogfood-6/findings.md#L160)); the project keeps
  a module dict keyed by `run_id`.
- **A depleted prepaid balance is retried as a burst limit** ([`DF6-D10`](../runs/dogfood-6/findings.md#L277)): `QUOTA_PHRASES`
  holds one Mistral phrase, and the advice names `PacedClient` on a backend that publishes no
  allowance.
- **A failure inside a resumed run leaves no suspension to claim** ([`DF6-D15`](../runs/dogfood-6/findings.md#L356)).
- **`nearest_cross_split` returns every pair at 1.0** on identifier inputs and says nothing
  ([`DF6-D5`](../runs/dogfood-6/findings.md#L188)).

## What has to be decided

- **The slice terminal**: a cut successor out of the slice's end node is the end, and a run
  that reaches it returns that node's output. Whether a route that selects only cut arms from a
  non-terminal node still leaves.
- **The evaluation's isolation**, **ruled by Thilina 2026-09-02** as both halves put to him:
  `EvalSuite.run(store_for=...)`, a copy per rollout the suite makes and deletes and records;
  and a refusal where a node declares a store write (`touches=`) and no isolation is given.
  The docs carry the recipe either way. What is left to decide is the parameter's name and
  what the results file records about the isolation.
- **Run inputs on `NodeContext`**, or a pipeline-level `keep=`.
- **Quota phrases per backend**, and advice that names `PacedClient` only where the backend
  publishes an allowance.
- **What a failed resume does**: put the claim back, or re-suspend at the failure.
- **`nearest_cross_split`** says when every text is identical, or compares what it can.

## What it waits on

none
