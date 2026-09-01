# Findings verified directly by the lead pass

These were confirmed by the lead rather than by an area agent, either because an agent flagged
them and the flag needed a reproduction, or because they were found while reading. Area findings
live in the sibling files. Machine-readable results are in `../runs/`.

Severity is the lead's judgement: **blocker** stops a release, **major** misleads a builder about
something that costs money or correctness, **minor** is wrong but bounded, **cosmetic** is prose.

---

## L-1. A tool parameter's `Field(description=...)` never reaches the model, and its constraints are dropped. Major.

**What is claimed**, [tools.md §1.2, line 61](../../../../docs/tools.md#L61):

> A description anywhere in that schema is prompt text: `Field(description=...)` on a parameter,
> or the docstring of a model used as a parameter's type. **The model reads it.** Use it where
> the argument's meaning is not obvious from its name and type

followed by a worked example using `Annotated[int, Field(description="How many to return. Above
10 crowds the turn.")]`, and then:

> Without one, `top_k` reaches the model as a bare integer with a default and nothing saying what
> a good value is.

**What actually happens.** With the description, `top_k` still reaches the model as a bare integer
with a default and nothing saying what a good value is. The `Annotated` metadata is discarded
before the schema is built, so the documented example produces exactly the outcome the
documentation says it avoids.

Running the shipped example's shape:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def search_docs(
    query: Annotated[str, Field(description="The search phrase, in the user's own words.")],
    top_k: Annotated[int, Field(description="How many results to return.", ge=1, le=10)] = 3,
) -> str:
    """Search the documentation."""
```

produces this schema, which is what the backend is sent:

```json
{"properties": {"query": {"title": "Query", "type": "string"},
                "top_k": {"default": 3, "title": "Top K", "type": "integer"}},
 "required": ["query"], "type": "object"}
```

No `description` on either parameter. No `minimum` or `maximum` on `top_k`.

**The constraints are lost from validation as well, not only from the schema.** `ge=1, le=10` is
declared and `top_k=400` is accepted by the tool's own validator. A tool author who expresses a
bound this way has no bound. That is the more serious half: a missing description degrades the
prompt, while a missing constraint means the library validates a call it was told to refuse, and
[tools.md §1.2](../../../../docs/tools.md#L80) says a call that does not satisfy the schema is handed
back to the model for correction.

**Cause**, [tools.py:1069](../../../../src/simple_agents/tools.py#L1069), in `_resolved_hints`:

```python
return get_type_hints(fn)
```

`typing.get_type_hints` strips `Annotated` metadata unless it is given `include_extras=True`, so
`Annotated[int, Field(...)]` arrives at `create_model` as plain `int`. Demonstrated directly:

```
without include_extras: {'top_k': <class 'int'>}
with    include_extras: {'top_k': Annotated[int, FieldInfo(..., description='How many to return.',
                                                           metadata=[Ge(ge=1), Le(le=10)])]}

include_extras=False -> {'default': 5, 'title': 'Top K', 'type': 'integer'}
include_extras=True  -> {'default': 5, 'description': 'How many to return.',
                         'maximum': 10, 'minimum': 1, 'title': 'Top K', 'type': 'integer'}
```

**Proposed patch**, one line, in `../patches/L-1-tool-annotated-metadata.patch`. It is not applied.
It needs a test over the offered schema, and it will change the schema every affected tool sends,
which moves cassette keys for any tool whose parameters carry `Annotated` metadata.

---

## L-5. A resume that is refused destroys the suspended run. Blocker.

**A mistyped node id in `answers=` throws away a suspended run irrecoverably.** The refusal names
the mistake and says what the right id is; by the time it is raised, the state file it would be
used against has already been deleted.

Measured, in order, on one run:

| Step | Result |
|---|---|
| The run stops in node `ask` | `suspension.json` written, `state_exists` is `True` |
| `resume("rloss", answers={"ask_typo": "regular"})` | refused: *"resume(answers=...) names 'ask_typo', and this run did not stop in that node. It stopped in 'ask'."* |
| Directory immediately after the refusal | `manifest.json`, `trajectory.jsonl`, `workspace`. **`suspension.json` is gone.** |
| `resume("rloss", answers={"ask": "regular"})`, the correction the refusal asked for | *"There is no suspended run in ..."* |

**Cause**, [core.py:610](../../../../src/simple_agents/pipeline/core.py#L610). The restore block is
wrapped in `try/except` that calls `release_claim(root)` and re-raises, so a failure there is
recoverable. `discard_claim(root)` is then called, and only afterwards are
`codec.decode(state.inputs, ...)` and `self._answers_for(state, answer, answers)` evaluated, as
arguments to `_drive(...)`. Python evaluates arguments before the call, so every refusal those two
raise happens after the state has been discarded, with nothing to restore it.

```python
        discard_claim(root)
        return self._drive(
            inputs=codec.decode(state.inputs, source=None),   # can raise, state already gone
            ...
            answers=self._answers_for(state, answer, answers),  # can raise, state already gone
        )
```

**Why this is a blocker rather than a nuisance.** A suspended run holds work that has already been
paid for and a person who has already been asked a question. `docs/pipeline.md` §1.11 documents
resuming as the ordinary continuation of a designed interaction, and the glossary is explicit that
consultation is "a designed interaction, not a fault path". A typo in the continuation call is the
single most likely mistake a builder makes there, and it is unrecoverable. The better the refusal
message is, the worse the outcome, because it invites a corrected retry that cannot succeed.

The area H pass records the same shape from three other directions: a version mismatch
(`H-06b`), an unreadable value tag (`H-03e`), and a refused resume generally (`H-03b`). They are
one defect with one cause.

**Fix direction.** Discard the claim after everything that can refuse has run, or restore it in an
`except` around the `_drive` call the way the restore block already does. Not patched here because
the correct placement interacts with what `_drive` itself may raise partway through a resumed run,
and getting that wrong would leave a claim held forever instead.

---

## L-2. `consult()` produces a tool with no version, where every decorated tool derives one. Minor, with a replay consequence.

`@tool` sets `version=version or derived_version(fn)`
([tools.py:1288](../../../../src/simple_agents/tools.py#L1288)). `consult()` builds its `ConsultTool`
directly and passes `version=version`, which defaults to `None`, so no version is derived.

```python
from simple_agents.builtins.consult import consult
t = consult(ask=lambda q, options=None: "yes")
assert t.version is None      # holds today
```

The consequence is on the cassette key, which carries the tool version: a consultation records
under a null version while every other tool records under a derived one. Two consult tools with
different `ask` channels and different `match` functions are therefore indistinguishable in a
recording. Whether that matters depends on whether a project is expected to swap the channel
between a recording and a replay, which is a design question rather than an obvious defect.

---

## L-3. A `web_search` answered from its cache is charged the full declared price. Major.

`docs/tools.md` §1.5 states that a call a cache answered pays nothing, and §4.5 recommends the
composition `web_search(provider, declared_cost=..., cache=cache)`.

`web_search` is declared `SPENDS_MONEY` and requires a `declared_cost`. Its function returns
early on a cache hit
([websearch.py:33](../../../../src/simple_agents/builtins/websearch.py#L33)) and **takes no
`SpendMeter`**, so it has no route by which to report that the call spent nothing. `declared_cost`
is what stands, and it stands on every hit.

Measured: two identical queries through a `UrlCache`, one provider call, and the tool's accepted
parameters contain no `meter`.

The effect is that a cache, whose purpose is to stop paying for a search made before, reduces the
real spend and not the recorded spend. `max_cost` bounds what tools spend, so a run using the
documented composition stops earlier than it needs to, and `totals.tool_spend` overstates.

---

## L-4. `contains_normalised` does not fold accents. Minor.

Flagged by the tools area and confirmed: `contains_normalised("Beyoncé sang", "Beyonce")` is
`False`. The grounding helper is documented as folding case, accents and punctuation. Case folding
works; accent folding does not. A project checking whether an answer is grounded in a fetched page
gets a false negative on any accented name, which is a class of name that appears constantly in
the sourced-answer tasks the helper exists for.

Area C's findings file carries the fuller reproduction.

---

## Flags investigated and dismissed

Recorded so the next reader does not spend time on them again.

- **`max_steps` charged after the call for a plain `LLMNode`.** A chain of six `LLMNode` under
  `max_steps=3` makes exactly 3 calls, and a fan-out with `over=` honours the limit at every
  concurrency. The real defect is narrower and is A-1 in `area-a-pipeline-graph.md`.
- **A cassette recorded under concurrency cannot be replayed.** It replays at the concurrency it
  was recorded at, at `concurrency=1`, and against a client pointed at a dead address with an
  invalid key, which is what proves it serves from the file rather than the backend.
- **`Cassette.record()` and `Cassette.replay()` do not exist.** They do. An early probe searched
  for the wrong method names.
- **`RunResult.cost` disagrees with the manifest.** It does not. `RunResult.cost` is a mapping
  rather than an object, and its contents match `totals.cost` exactly.
