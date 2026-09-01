# Absorption items 8 and 9 — `load_env` (dropped) and grounding — build log

**Kept while building.** Design of record: `archive/dogfood-absorption.md` §8 and §9, approved
2026-08-09. **Item 8 was dropped at the sitting**; item 9 shipped with one design reversal.

**Status: sitting held 2026-08-09. Baseline 1321 tests after items 4 to 7.**

---

## 1. Item 8, `load_env` — dropped as outside the library

**What was proposed.** `simple_agents.load_env(path=".env") -> tuple[str, ...]`, twenty lines
of stdlib parsing, returning the names it set so that
`Redaction(secret_env=load_env())` composes.

**The evidence for it.** Three hand-rolled loaders, and dogfood-1 wrote the same one twice in
one project (`agent.py:237` and `verify_unanswerable.py:57`, byte-identical). Dogfood-1 run 2
wrote none and put a shell incantation in an error message instead.

**Thilina's ruling: outside the scope of the library.** The absorption doc's own generality
check said as much and then argued itself out of it on the `secret_env` composition; the ruling
is that the composition does not make env parsing agent machinery.

**What follows.** `archive/dogfood-absorption.md` §8 needs its disposition changed from approved to
dropped, with this reason, which is a `dev-docs` edit to propose. Nothing was built and no
shipped document mentions it.

---

## 2. Item 9 — what was measured

### 2.1 Both dogfoods wrote the same two pieces of plumbing

Dogfood-2 `agent.py:897`, a `finish_check`, checks `evidence_url` against a set built from
`ctx.tool_calls` filtered by name and `ok`. Dogfood-1 run 2 `agent.py:246`, a `Deterministic`
verifier, checks the cited passage exists, the quote is in it, and the answer span is in it, all
through a local `_comparable()`.

### 2.2 The normalisation that shipped is not the one the projects wrote

Run 2's `_comparable` strips **every** non-alphanumeric character, defended in its docstring by
a real case: passages write `O 2`, the model writes `O₂`, and "a check that rejects a genuine
citation over a subscript is worse than no check".

Tested against run 2's own eval set, 30 questions with a value expected, each with its gold
passage:

| normalisation | answers found in their passage |
|---|---|
| as written | **30/30** |
| NFKC + casefold | 30/30 |
| + separators to one space | 30/30 |
| + separators removed | 30/30 |

**Normalisation buys nothing measurable on the data it was written for**, and the `O₂` case does
not occur in the 30. What the aggressive rule costs is measurable:

```
'therapist' in 'the rapist was named'   collapsed=False   stripped=True
'3040'      in 'cost 30, 40 and 50'     collapsed=False   stripped=True
```

A grounding check exists to stop an ungrounded claim being accepted, so a rule whose failure
direction is *accepting text the source does not contain* is the wrong one. **Separators
collapse to one space and are not removed.** Approved.

---

## 3. Where building sharpened a decision

### 3.1 A smoke test caught a false claim in the new docstring

The first draft said the helper made `"O₂"` match `"O 2"`. It does not, and cannot: `O₂` folds
to `o2` with no separator, while `O 2` keeps one. The claim was wrong the moment the safe rule
was chosen, and running the docstring's own example is what found it.

The docstring now states both directions, because a reader deciding whether to use the helper
needs the case it refuses as much as the ones it accepts. Every claim it makes is pinned by a
parametrised test.

### 3.2 `url_was_read` takes no tool name

Dogfood-2 hardcoded `call.name == "read_page"`. The shipped helper scans every successful call
for an argument that parses as an absolute http address. A project using both `read_page` and
`http_fetch` would otherwise get a false negative, and the question is whether the run fetched
the page rather than which tool did. A query string mentioning a site does not parse as an
address and does not count; pinned.

### 3.3 `urls_read` returns the addresses as the model wrote them

`url_was_read` compares canonically, so a `www.` or a trailing slash does not matter. The
refusal message needs the opposite: what the model actually passed, so it can recognise its own
call. Two functions, two shapes, both needed by dogfood-2's message.

## 4. What building found that is nobody's design

**Two flaky tests in `test_runs.py`, one root cause.** Both asserted an order between runs
sharing a `started_at`, which nothing determines: the tiebreak is file mtime, which ties at the
filesystem's resolution. Found by the suite failing once in about six runs and passing on
re-run. Fixed by giving the fixtures distinct times, which is what the ordering contract is
about. The second one was found only because the first had taught what to look for.

## 5. Doc consequences

| Document | What changed |
|---|---|
| `docs/tools.md` §5.3, new | The grounding check, both helpers, and what the normalisation refuses |
| `CHANGELOG.md` | One `Added` |

## 6. Tests

**1321 to 1344**, 23 added in `test_grounding.py`: the normalisation table including the two
cases it must refuse, the address table, six over `ctx.tool_calls`, and one end-to-end that
drives a real `AgentNode` through refuse-then-accept so that what a finish check receives is
what the loop hands it.
