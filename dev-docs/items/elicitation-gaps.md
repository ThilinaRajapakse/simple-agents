# What elicitation does not ask

`plan.md` §2.1's record for the audit's elicitation and procedure gaps. **Nothing is built and
nothing is scheduled**; accepted 2026-09-01, waiting on the release (`P3-31`).

## Where it came from

Thilina's 2026-08-29 audit of the docs, findings 1 to 4, verbatim except paths rewritten to
repo-relative links. Thilina ruled on 2026-09-01 that these are design work and the release
does not wait on them.

> 1. High — measurement elicitation is behind the evaluation API.
>    The [measure stage](../../docs/procedure.md#L1) asks what doing nothing would score, but
>    does not require implementing `EvalSuite(baseline=...)`, checking `against_baseline`, or
>    handling `baseline_unscored`. The
>    [improvement question](../../src/simple_agents/conformance/elicitation.py#L749) also omits:
>    - `rollout_noise`, `inside_the_noise`, and `moved`
>    - paired `compare`/`compare_variants`
>    - grouping heterogeneous examples with `results.grouped(...)`
>
>    Its instruction to compare "on the interval" is insufficient: the docs explicitly
>    distinguish sample uncertainty from rerun variation in
>    [§4.1](../../docs/evaluation.md#L1), define the executable baseline in §4.2, and warn
>    about pooled cancellation in §8.2.
>
> 2. High — multi-run state is not properly elicited.
>    The procedure requires `design.md` to say "what it holds on to between runs" at
>    [`procedure.md`](../../docs/procedure.md#L212), but provides no decision checklist or
>    route to the relevant docs. There is no shape question distinguishing:
>    - pipeline edges
>    - conversation history
>    - agent memory
>    - product-owned stored artifacts
>
>    This matters because [memory scopes users explicitly](../../docs/memory.md#L1), while
>    [a conversation makes each turn a separate run](../../docs/conversation.md#L1).
>    Elicitation should ask about lifetime, identity/scope, retention and deletion, redaction,
>    compaction, and simultaneous turns.
>
> 3. High — concurrency and backend pacing are reference-only choices.
>    The build procedure points generally to pipeline and model-client documentation at
>    [`procedure.md`](../../docs/procedure.md#L249), but the
>    [backend question](../../src/simple_agents/conformance/elicitation.py#L1) asks only
>    about model, price, credentials, and embeddings.
>    Nothing asks the builder to settle safe values for `concurrency`, `concurrent_nodes`,
>    `concurrent_items`, or `concurrent_tools`, despite their shared-workspace and
>    budget-overshoot implications in [pipeline §1.10](../../docs/pipeline.md#L1). Nor does it
>    ask about provider allowance or `PacedClient`, documented in
>    [model clients §4](../../docs/model-clients.md#L1).
>
> 4. Medium — abandoned-run recovery is not in the shipping procedure.
>    `RunHandle.liveness` and `Pipeline.rerun` are well documented in
>    [run-envelope §8.3](../../docs/run-envelope.md#L1) and
>    [pipeline §1.13](../../docs/pipeline.md#L1). The [ship stage](../../docs/procedure.md#L1),
>    however, never asks who detects abandoned runs or whether recovery is manual or automatic.
>    The procedure should make clear that the project owns the monitor/scheduler and may use
>    `Pipeline.rerun`; the library does not provide a supervisor.

## What the problem is

Four capabilities are documented in their reference documents and absent from the procedure and
elicitation that route a coding agent to them: the baseline evaluation API, the four kinds of
multi-run state, the concurrency and pacing settings, and abandoned-run recovery. A project gets
them only if its coding agent already knows to look.

## What has to be decided

Each finding is a design question, and the sitting takes them one at a time:

- Which of the evaluation API's figures the measure stage requires, against the stage's cost of
  requiring more.
- Whether multi-run state becomes a shape question, and which of the audit's six axes
  (lifetime, identity, retention, deletion, redaction, compaction, simultaneous turns) it asks.
- Whether the backend question gains concurrency and pacing, and what a safe default is where
  the builder does not answer.
- Where the ship stage says the project owns the monitor.

## What it waits on

`P3-31`, the release. These change what the procedure asks of a project, and the release does
not wait on design sittings.
