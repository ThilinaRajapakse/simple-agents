# Build log — connecting to an MCP server

`plan.md` §1 P3-38. Started 2026-08-27. Written while building, not afterwards.

## 1. Before any design

**Measured on this machine before anything was argued**, because the dependency question was the
one the whole design read under and every earlier framing of it was recall rather than
measurement.

- **The library reaches no MCP server.** `grep -rin "mcp" src/ docs/` returned nothing.
- **The library is synchronous throughout.** No `asyncio` or `anyio` import anywhere in `src/`;
  concurrency is `ThreadPoolExecutor` in [`concurrency.py`](../../src/simple_agents/concurrency.py#L18), `run_over`.
- **The runtime closure is 12 packages**, by `uv pip compile` against the real dependencies on
  Python 3.12. With `mcp` it is 32; with `mcp-types` alone it is 13.
- **`Tool` is a `@dataclass(slots=True)`** ([`tools.py`](../../src/simple_agents/tools.py#L688), `Tool`) and `ConsultTool` already subclasses it
  with extra fields, so an `MCPTool` had a pattern to follow.
- **`_tool_entry` reads subclass fields with `getattr(tool, ..., None)`** ([`pipeline.py`](../../src/simple_agents/pipeline/recording.py#L147), `_tool_entry`), so a
  new per-tool manifest field costs one line.
- **[`source_version`](../../src/simple_agents/records/manifest.py#L596) covers a closure only for captured data whose text is fixed by
  its value.** A closure over a live connection is versioned by its source alone, identical for
  every tool one server offers. This is why the version had to be declared rather than derived.
- **`EvalSuite` builds one pipeline for every rollout**, stated in [`docs/tools.md` §3.2.1](../../docs/tools.md#L537). This
  is what made a live listing at construction incompatible with the offline requirement.
- **A replayed evaluation is pointed at a cassette file**, not a run directory
  ([`docs/evaluation.md` §6.3.1](../../docs/evaluation.md#L1411)). So the manifest is not reliably reachable from a replay,
  and the recorded listing had to live in the cassette.
- **`CassetteEntry.kind` is a free string** with no format gate on it ([`cassette.py`](../../src/simple_agents/records/cassette.py#L93), `CassetteEntry`),
  so a new kind is additive.
- **The reference server runs here.** `npx -y @modelcontextprotocol/server-everything` over both
  stdio and streamable HTTP, 13 tools, all four hints present. Node 24.19.0, npx 11.17.0.

## 2. Design

Two sittings, both 2026-08-27. The item's own record held the design until it was built; it is
here now.

**Sitting 1: the dependency, the transports, the lifetime.**

- **The `mcp` SDK, as an optional extra.** 20 new packages, including a second HTTP stack
  (`httpx2`), a full ASGI server with no client-only extra, and a compiled `cryptography`. Taken
  anyway on merit: `mcp.client.auth` ships `OAuthClientProvider`, `PKCEParameters` and
  `TokenStorage`, and the case this item exists for is an organisation's own server behind OAuth.
  The SDK has 70 releases, five protocol revisions and a shape change at `2026-07-28`, and
  [`simple-agents.md` §10](../simple-agents.md#L619)'s thin-front-end rule argues for putting that churn behind a boundary
  somebody else maintains. **The first pass cited that rule against taking a dependency, which is
  backwards, and recommended `mcp-types` (one new package) on a footprint argument Thilina
  rejected**: *"I don't really care that much about dependency minimalism. That's something you
  wrote down, because you get overzealous as usual."*
- **The async objection was measured and did not survive.** A correct synchronous bridge is 52
  lines. The naive one, a task per call, listed and called correctly and died on teardown with
  `RuntimeError: Attempted to exit cancel scope in a different task than it was entered in`.
- **Both transports**, stdio and streamable HTTP.
- **The connection is an object the builder constructs and holds**, not per-run. Spawning a stdio
  server costs about 400ms against a 5ms `tools/call`, and [`docs/product.md`](../../docs/product.md#L7) opens on a product
  being a run per request. **This amended [`simple-agents.md` §2.1](../simple-agents.md#L104)** on Thilina's call: *"it might
  be a stupid rule to hold for a library that helps build agentic systems."*

**Sitting 2: the declaration shape, the mapping, drift, and replay.** Sitting 3 was folded in;
the split had been drawn before sitting 1 settled the lifetime, which answered most of it.

- **The shape follows LangGraph and Pydantic AI**, on Thilina's call. **A first pass recommended a
  CLI import command writing a committed TOML file and was rejected**: *"The cli option seems a
  bit clunky and might not be natural to the builder and coding agent."* Both dropped.
  Verified out of their wheels rather than recalled: `pydantic_ai/mcp.py` has `MCPToolset` with a
  live `list_tools()` and `cache_tools=True`, passing the hints through as opaque metadata;
  `langchain_mcp_adapters.client` has `await client.get_tools()`. **Neither carries a side-effect
  class**, so following them settles the shape and says nothing about the declaration.
- **The declaration is `effects=` in Python**, which is the selection and the declaration at once.
- **The proposal from the hints is delivered in the refusal**, which is [`simple-agents.md` §9 item 9](../simple-agents.md#L600),
  failure messages are instructions. That is the import step with no new surface.
- **The mapping**: `readOnlyHint: true` proposes `read_only`; `readOnlyHint: false` with
  `destructiveHint: false` proposes `writes`; with `destructiveHint: true` proposes
  `irreversible`; **no annotations proposes nothing**, because the specification's defaults read
  as `irreversible`, an evaluation refuses every tool in that class, and servers publishing no
  annotations are common. `idempotentHint` and `openWorldHint` are recorded and map to nothing.
  `spends_money` is never proposed: MCP publishes no cost hint.
- **Drift is verified on first connect, recorded, and read by a new `FT-43`.** Part of it was
  already built: a `dependency` decision's `produces` already fails from `ship` on a tool no run
  recorded, so `FT-43` covers what that cannot see.
- **A replay reads the schema from the recording.** The listing is a call, so it is a cassette
  entry like any other.

**What the elicitation already had, and so was not built.** `tool_effects`'s scaffold in
[`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L619) already reads *"List every tool the agent will be given, with the
side-effect class it declares and what one call does. Have the builder confirm each or correct
it."* The confirm-once step the item proposed is that question. No new mechanism was needed.

## 3. Build

**Shipped**: [`mcp.py` `MCPServer`](../../src/simple_agents/mcp.py#L236), and beside it `MCPTool`,
`MCPHints`, `proposed_side_effect_class` and the 52-line `_Session` bridge; `ToolRegistry.add_all`;
`_read_mcp_servers` in [`pipeline.py`](../../src/simple_agents/pipeline/core.py#L2245) and the `mcp` key on `_tool_entry`; the manifest's `mcp`
array; `ft_43` and its taxonomy entry; the `[mcp]` extra.

**Formats**: manifest `0.33` to `0.34`. The trajectory stays at `0.28`: `side_effect_class` is on
every call already and a hint does not vary per call. A new cassette entry kind, `mcp_tools`,
which is additive and needed no version.

**Tests**: 3487 to 3534. `tests/test_mcp.py` is 39, `tests/_mcp_fixture.py` holds the HTTP
server fixture, and four went into `tests/test_conformance.py` for `FT-43`.

**What the build found that the design did not know:**

- **`@dataclass` without `eq=False` makes `MCPServer` unhashable**, so the at-exit weak set
  refused it. A server is a resource and identity equality is what it wants.
- **Two units the shape check was right about.** `ft_43` at 13 branches and `_read_mcp_servers`
  at 13 branches were both split rather than recorded, into `_newest_manifest` /
  `_servers_read` and `_mcp_servers_in` / `_read_one_mcp_server`.
- **`docs/procedure.md` was at exactly 3000 words**, its ceiling, so the pointer to §7 that was
  drafted for it was reverted. [`docs/index.md`](../../docs/index.md#L1)'s row is the discovery path instead, which is
  what that column is for.

## 4. Verification

**Against the reference server, `@modelcontextprotocol/server-everything`, on this machine.** No
model backend is involved: this item adds no model call, so vLLM and Mistral have nothing to say
about it. What had to be exercised live is the protocol, and it was, on both transports.

- **stdio**: 13 tools listed, all four hints present on `echo`
  (`read_only=True destructive=False idempotent=True open_world=False`), a real call answering
  `Echo: hello`, and a schema-violating call raising `ModelFacingError` off the server's
  `isError: true`.
- **A recorded pipeline run replayed against `this-command-does-not-exist`**, producing identical
  output, an identical tool version (`sha256:992850801171`), 2 cassette hits and 0 misses, with
  no process spawned. **This is the offline requirement exercised rather than asserted.**
- **Drift**: a recording edited to look like an older server, then updated against the live one,
  produced all three differences: `added`, `withdrawn` and `description`.
- **A replay whose recording holds no listing** raises `CassetteMiss` naming the re-record.

**Two defects the live run found that a green suite had not.**

- **The HTTP transport was broken and 3531 tests passed over it.** The v2 SDK renamed
  `streamablehttp_client` to `streamable_http_client` and moved headers, authentication and
  timeouts onto an `httpx2` client built by `create_mcp_http_client`. The path had never been
  executed. It is exercised now by `TestOverStreamableHTTP`, and a `triple=` flag that was dead
  went with it.
- **The HTTP fixture passed against a server it had not started.** Bound to the server's default
  port 3001, it connected to one left running by earlier probing, and its own teardown could not
  reap the server because `npx` execs through a process chain. It claims a free port through
  `PORT` and signals the process group now. The tell was the timing: 0.44s for three tests that
  each need a server start, against 1.46s once it started its own.

## 5. Doc consequences

- **[`docs/tools.md` §7](../../docs/tools.md#L1352)** is new: declaring a server's tools, what the hints propose, what a run
  records, how an MCP tool is replayed, and what an unreachable server does.
- **[`docs/run-envelope.md` §2.10](../../docs/run-envelope.md#L313)** is new, for the manifest's `mcp` array, and §2.1 gains its
  row. The stated current version moves to `0.34`.
- **[`docs/failure-taxonomy.md`](../../docs/failure-taxonomy.md#L599)** gains `FT-43` and its index row; the counts move to 43 entries,
  29 `prototype`, 32 artifact.
- **[`docs/conformance.md`](../../docs/conformance.md#L134)** moves from twenty-five checks to twenty-six in five places, gains
  `FT-43`'s row in §3, and its §4 sample report was regenerated from a real run.
- **`README.md`** moves from 42 to 43 entries and twenty-five to twenty-six checks.
- **`CHANGELOG.md`** records the feature, the manifest bump and `FT-43`.
- **`scripts/prose_check.py`**'s `NUMBER_WORDS` gained 26 to 29 and 43 to 44, which is what lets
  the count rule keep reading these sentences.

**No shipped statement stopped being true.** The section is additive throughout.

## 6. Left open

- **A tool the server will only run as a task.** Investigated 2026-08-27 on Thilina's call and
  **declined**: the protocol removed tasks at `2026-07-28`, the TypeScript SDK ships them under
  `experimental/`, the Python SDK carries no client-side support, and 36 of 37 tools across four
  real servers forbid them. A tool declaring `required` fails as a `ModelFacingError`, which is
  the safe failure. **Destination**: [`plan.md` §3](../plan.md#L521), with the evidence and what would reverse it.
- **What a server may ask of the client**, which is what that investigation found instead:
  this library declares no `elicitation`, `sampling` or `roots` capability, and a server that
  gates tools on them hides those tools. The reference server offers 13 to us and 16 to a capable
  client. **Destination**: `P3-43`, [`items/what-a-server-may-ask.md`](../items/what-a-server-may-ask.md#L1).
- **`tools/list_changed` mid-run is recorded and not honoured**, which is what the design decided
  and what the cassette requires. **Destination**: nothing; this is the decision, not a gap.
- **The `spends_money` path has no live exercise.** No MCP server on this machine charges for a
  call, so the declaration is tested and the meter is not. **Destination**: nothing; it is the
  ordinary paid-tool path, which [`docs/tools.md` §1.5](../../docs/tools.md#L149) already covers and other tests exercise.
