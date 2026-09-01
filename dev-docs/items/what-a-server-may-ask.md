# What an MCP server may ask of the client

`plan.md` §1 P3-43's record. **Nothing is built.**

| | | |
|---|---|---|
| Sitting 1 | The replay shape, which all three share | next |
| Sitting 2 | The sampling policy, and what a third party may spend | |
| Sitting 3 | Elicitation onto consultation, and roots onto containment | |
| Build | Against `server-everything`'s three capability-gated tools | |

## Where it came from

The investigation `P3-38` ran on 2026-08-27 into whether MCP tasks were worth owning. Tasks were
declined ([`plan.md` §3](../plan.md#L521)) and this is what the investigation found instead. Thilina, on being
shown it: *"Plan it properly with proper investigation. Let's not do half baked support."*

## What the problem is

**A server can ask the client for three things mid-call, and this library answers none of them.**

| Request | What it is | What it already is here |
|---|---|---|
| `elicitation/create` | ask the end user something | a **consultation** (`docs/tools.md` §4.6) |
| `sampling/createMessage` | ask the client's model to generate | a **model call on the run's budget** |
| `roots/list` | which directories the client exposes | containment, as `HostPolicy` is for hosts |

[`mcp.py` `MCPServer`](../../src/simple_agents/mcp.py#L236) constructs its `ClientSession` with no
`sampling_callback`, `elicitation_callback` or `list_roots_callback`. The SDK then installs
defaults that return `ErrorData(INVALID_REQUEST, "... not supported")`, and declares a capability
only where its callback was replaced, so **this library's `initialize` declares none of the
three.** That part is correct: a server is told the truth and a well-behaved one never asks.

**The cost is not a tool that fails. It is a tool that is never offered.** Measured 2026-08-27
against `@modelcontextprotocol/server-everything`, listing twice over one stdio connection:

```
declaring nothing:                      13 tools
declaring sampling+elicitation+roots:   16 tools
offered only to a capable client:  get-roots-list, trigger-elicitation-request,
                                   trigger-sampling-request
```

A server that gates tools on client capability hides them. They are absent from the listing, so
they are absent from the refusal that proposes a declaration, and a builder has no way to learn
they exist.

**And these are the durable feature, where tasks were not.** At protocol revision `2026-07-28`,
`InputRequest = CreateMessageRequest | ListRootsRequest | ElicitRequest`: the three are exactly
what an `InputRequiredResult`'s `input_requests` carries. Tasks were the transitional wrapper
around them and were removed; the three were not.

## What has to be decided

**Sitting 1: the replay shape, which all three share and which is the hard one.**

[`docs/tools.md` §3.2](../../docs/tools.md#L412) draws the current line: a tool taking a handle is re-run on replay,
because everything it does through handles is recorded separately and the records then match; a
stored tool returns its recorded value without running. **An MCP tool that elicits fits neither.**
The elicitation is performed by the server, so it cannot be re-run offline, which rules out the
handle path. But if the tool is merely stored, the replay writes one record where the live run
wrote two, and the consultation is gone from the trajectory.

- Does the cassette entry for an MCP tool call carry the exchanges that happened inside it, so a
  replay re-emits them without reaching anything?
- Or is each exchange its own cassette entry, keyed on the server, the tool and an occurrence?
- What is the key, given that what the server asks may depend on what it was asked?
- **The cassette carries no format version** and `CassetteEntry.kind` is a free string
  ([`cassette.py`](../../src/simple_agents/records/cassette.py#L93), `CassetteEntry`), so either shape is additive. This is why the item
  does not have to precede the release.

**Sitting 2: the sampling policy.** Settled in principle 2026-08-27: **opt-in, bounded, recorded.**
Off unless the project declares it, with its own ceiling, and every call recorded as a `model_call`
parented to the tool call so what the server asked and what it spent are both readable from the
run. The same shape a `spends_money` tool has: the library does not refuse the capability, it
refuses to let it happen unnamed and unbounded. What is left is the mechanism.

- What the declaration looks like, and which model it is given.
- Which axis bounds it: calls, tokens, cost, or its own budget.
- What happens when the ceiling is reached mid-call, given the server is waiting.
- Whether the prompt the server sent is recorded in full, and what redaction reaches it.
- Whether [`simple-agents.md` §9 item 8](../simple-agents.md#L594)'s agency boundary has anything to say. It governs the
  builder's code reaching a model, not a server's, so this looks like new ground rather than an
  amendment; that reading should be checked before anything is built on it.

**Sitting 3: elicitation onto consultation, and roots onto containment.**

- A `consultation` record parented to a `tool_call` is a shape nothing writes today.
- What `answered_by` says when the question was composed by a server rather than by the project.
- What happens when the channel shelves or is unavailable while the server waits: decline the
  elicitation, or cancel the call.
- Whether an elicitation the server composed may reach an end user unreviewed, which is the same
  question `description` raises and which no check reads.
- Roots: a declared list, and whether it is the run's `Workspace` or something the project states
  separately.

## What it waits on

`P3-31`, going public. Nothing here moves a format a project holds on disk, so it does not have to
precede the release, and the release has been held twice already.
