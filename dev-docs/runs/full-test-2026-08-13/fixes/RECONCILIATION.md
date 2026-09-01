# Cross-stream reconciliations

Points where two streams reported something that looked like a contradiction, settled by the lead
against the source rather than by taking either report at face value.

## `held_back_ms`: Stream A measured 7000, Stream D measured 3000. Both are right.

`Retry`'s docstring: "Backoff doubles each attempt up to ``max_backoff_s``, so the defaults wait
1, 2, 4, 8 and ...". The waits are between attempts, so `max_attempts=n` waits `n-1` times:

| `max_attempts` | waits | total |
|---|---|---|
| 3 | 1, 2 | **3000 ms**, which is Stream D's figure |
| 4 | 1, 2, 4 | **7000 ms**, which is Stream A's figure |
| 6 (the default) | 1, 2, 4, 8, 16 | 31000 ms |

Stream A wrote that Stream D's "harness measured something different from what the shipped
`Retry` does". It did not. It measured a different `max_attempts`, which is a legitimate
configuration. No defect, and nothing to fix.

## `docs/run-envelope.md` §2.1 on `held_back_ms`: already correct

Stream A reported all three of the section's claims false after its second change. Reading the
file shows Stream D had already revised it, after Stream A's lines landed and before Stream A
read it. The shipped text now says: "A call that exhausted its retries counts here too, on the
run that its failure ended: the run waited, and the wait is what explains its wall clock." That
matches the implemented behaviour. Stream A read a stale copy. Nothing to fix.

## `nodes.py:2867`, `observe_held_back(record.held_back_ms)`

Stream D hit `AttributeError` on every semantic search during its run, because `Record` is a
`dict` subclass and the line used attribute access. Stream D did not edit the file, which is
correct: it is Stream A's. Stream A fixed it inside the same window. Recorded so the episode is
not mistaken for an open defect.
