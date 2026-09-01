# Absorption items 4 to 7 — the fetch surface — build log

**Kept while building.** Design of record: `archive/dogfood-absorption.md` §4 to §7, approved
2026-08-09, **and amended at the sitting on four points** (§2). The four items compose: 4 is
independent, 5 gives 6 and 7 something to wrap, 6 decides whether a fetch is allowed, 7 sits in
front of the network.

**Status: sitting held 2026-08-09, built. Baseline 1266 tests after item 2 and 3.**

---

## 1. What was measured, before any design

All figures are from dogfood-2's 18 runs and the 155 pages its cache holds.

### 1.1 The library's page tool deletes the thing the page is read for

| | |
|---|---|
| median raw page | **761,608 chars** (~190,000 tokens) |
| pages exceeding the 100,000-char default cut | **144 of 155** |
| cached pages holding a `<table>` | 48 |
| whose first `<table>` falls **past** the cut | **44** |

```
first <table> at 284,590 of 1,485,387 chars   asket.com/en-de/womens-t-shirt-black
first <table> at 455,212 of   471,714 chars   sunspel.com/products/mens-riviera-polo
first <table> at 134,434 of   149,535 chars   faq-uk.uniqlo.com/.../Knowledge/...
```

On 92% of pages that have a size chart, the shipped default removed the chart and charged
~25,000 tokens for the navigation it kept. One run reached 595,548 uncached input tokens.

**And the truncation was silent**: `body[:max_chars]`, no marker, while `simple-agents.md` §2.4
commits to erroring rather than truncating for prompts.

### 1.2 The scoped search was the majority of searches

| tool | calls across 18 runs |
|---|---|
| `search_within_site`, the project's own | **201** |
| `web_search`, the library's | 115 |

The project bypassed the library's tool and called its provider directly with `domains`,
saying so in its docstring.

### 1.3 The project switched the library's containment off to get a growable one

`http_fetch(allow_hosts=...)` freezes at construction. The project passed `allow_hosts=None`
and re-implemented the host check. Two details it paid for live: subdomains (a size guide on
`faq-uk.uniqlo.com` refused against a configured `uniqlo.com`) and `www.` normalisation (an
admission slot spent re-admitting a configured site).

### 1.4 The cache saved 232 of 387 successful reads

Of 503 `read_page` calls: **232 served from the local store**, 155 fetched fresh. 60% of
successful reads made no request.

---

## 2. The sitting, 2026-08-09

Presented with §1 and a proposal per item. Four amendments, all Thilina's, all adopted:

1. **Item 4 gains a generic passthrough as well.** The named `domains` stays, because the model
   chooses it per call and a JSON Schema cannot express `**kwargs`; `provider_options=` carries
   what the builder fixes. On "isn't `domains` one vendor's convention", the answer is that the
   library owns the normalised name and the provider translates, which is what `web_search`
   already does on the way out with `title|name|heading` and `url|link|href`.
2. **Item 5's truncation default is wrong, not just its size.** `max_chars` now defaults to
   `None` and a limit that is set says how much it dropped.
3. **Tables-first was designing for the dogfood.** Stripping script, nav and footers is general;
   the *ordering under truncation* is a judgement. `as_prompt(order=...)` and
   `read_page(order=...)` make it one argument, defaulting to tables first.
4. **Item 7 raised whether memoisation should be general.** It should not, yet: the tool-call
   key carries an occurrence ordinal precisely because tools are impure, and a general memo is
   unsafe for exactly those tools. `UrlCache` is built as a keyed store the tools *use*, so a
   later general seam is a different key function rather than an unpicking.
5. **Q3, the manifest surface, was granted on a new argument.** Item 6 makes an existing
   manifest claim false: the reachable set stops being knowable from the tool declarations once
   a run can add to it. One named field with a fixed schema, not a general tool→manifest
   channel, which would be a junk drawer.

---

## 3. Where building sharpened a decision

### 3.1 The cache sits inside the fetch, after the checks and before the network

Order in `http_fetch`: scope and robots, then the store, then `policy.spend_fetch()`, then the
request. So a stored page is still refused for a host out of scope, and a stored page is not
charged against the ceiling because nothing was requested. Both pinned.

`read_page` learns the age by reading the store before delegating, rather than the fetch tool
injecting a note into the body: a note inside the markup would be reduced away or corrupt it.

### 3.2 A replayed run records zero fetches, and that is correct

Measured: live run records `fetch_policy.fetches: 1`, its replay records `0`. A filed tool is
served from the cassette without running, so the policy is never charged. The alternative would
be a manifest claiming requests a replay did not make.

### 3.3 The occurrence ordinal is what makes a mutable policy replay-sound

Pinned end to end: a refused fetch, an admission, then a successful fetch of the same URL
records two entries under one argument set and replays as `["refused", "fetched"]`. Without the
ordinal the second call would replay the first's refusal.

### 3.4 The docstring length rule bit three times, and was right each time

`http_fetch` and `read_page` both grew past 20 prose lines as parameters accumulated. The fix
each time was to move detail to `docs/tools.md` and leave the docstring saying what the thing
is, what to pass, and what happens when it is wrong.

## 4. What building found that is nobody's design

### 4.1 The JS-shell refusal fired on a test fixture

A cache test's fixture page reduced to 52 characters and `read_page` refused it as a JavaScript
shell. The check was right and the fixture was thin; it was lengthened. Worth recording because
it is the first evidence the threshold does something on a page nobody designed against it.

### 4.2 Verified against the 155 real pages

The library's reducer run over every cached page dogfood-2 holds, none of which it was written
against:

```
pages reduced: 155        pages where a table survived: 48
median raw/reduced ratio: 62x
median reduced chars — library 9,706
```

48 of 48 table-bearing pages keep their table, against 4 of 48 surviving the old truncation. No
crashes on bodies up to 1.5MB.

## 5. Doc consequences

| Document | What changed |
|---|---|
| `docs/tools.md` §4.2, new | The search provider, `domains`, `provider_options` |
| `docs/tools.md` §4.3, new | `read_page`, `order`, `link_words`, and `reduce_html` on its own |
| `docs/tools.md` §4.4, new | `HostPolicy`, admission, the ceiling, and what the manifest records |
| `docs/tools.md` §4.5, new | `UrlCache`, and the four things it does not do |
| `docs/tools.md` §4 table | Rows for `read_page`; `http_fetch` re-described as the raw-body tool |
| `docs/run-envelope.md` §2.1 | The `fetch_policy` field, manifest `0.13` |
| `docs/run-envelope.md` §3 | A cassette is not a cache in front of the network |
| `docs/index.md` | The tools row names the three new subjects |
| `CHANGELOG.md` | Four `Added`, one `Changed` |

`consult` and `extract_to_schema` moved from §4.2/§4.3 to §4.6/§4.7 across items 2, 4 and 5. The
one internal citation of `extract_to_schema` was updated with them.

## 6. Tests

**1266 to 1321**, 55 added across four files: `test_html_reduction.py` (24, over two handcrafted
fixture pages), `test_host_policy.py` (16, including the replay-soundness sequence and the
manifest record), `test_url_cache.py` (14), and 6 in `test_builtin_tools.py` for `domains` and
`provider_options`. One existing test changed: the truncation test now asserts the marker and a
sibling asserts the whole body comes back by default.
