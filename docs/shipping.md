# Shipping

Shipping is when somebody other than the builder starts using the agent. `docs/procedure.md` stage 6 is when to read this; this document is what the stage rests on.

The library ships the part that makes a live run say it is live, and the part that turns live runs back into something the next version can be built from. Deployment, the server and the scheduler are the project's.

**The `ship` gate does not close behind the project.** `stage = "ship"` stays in the brief, so what fires there runs every later time the suite does. FT-31 reads who answers the agent (§4). FT-37 and FT-38 read a change rather than an arrival: the first fails once the pipeline that produced the reported number is gone, the second once the entries describing the pipeline were last read against something else (`docs/conformance.md` §3). A project keeps building after this point, and re-running `simple-agents check` is what covers it.

---

## 1. A live run says so

```python
env = RunEnvelope(run_dir="runs/", cost_basis=PRICES)

real = env.with_live()                       # an end user is on the other end
result = pipeline.run(question, envelope=real, model=client)
```

`RunEnvelope(live=True)` does the same at construction, for a project whose every run is live. `env.with_live(False)` goes back, and everything else on the envelope is shared, so one configured envelope serves both.

The manifest records `live`, and nothing infers it. A project that never sets it has no live runs as far as every reader is concerned, which is the same rule the tier follows: a claim the library cannot check is one the project makes.

**`live` and `role` are separate.** `role` says what the run was for, `agent` unless the envelope said otherwise (`docs/run-envelope.md` §2.1). `live` says who was on the other end. A live run is a run of the agent, so `RunEnvelope(role="labelling", live=True)` is refused.

**An evaluation's rollouts are never live**, whatever envelope they came from. A rollout runs a seeded example rather than something a person asked for.

**The conformance checks read the runs that are not live.** FT-13 and FT-14 are about what the project built, and a live run belongs to an end user: it carries their material and can be sampled down to no payloads. A project whose every run under `runs/` is live has still recorded everything, so the newest is read and the report says which it was. A project with both gets a note naming the newest live run beside the one the checks read, since what it does now is reported rather than certified (`docs/conformance.md` §4.4).

---

## 2. Reading live runs back

```python
from simple_agents import runs

real = runs("runs/", live=True)
development = runs("runs/", live=False)
```

`run.live` is the same fact on one handle. A run written before the manifest carried the field counts as not live.

This is what the brief's `watching_live` answer is implemented against. Three shapes, and a project picks the one the builder asked for:

```python
recent = [run for run in runs("runs/", live=True) if run.finished][:20]
for run in recent:
    print(run.run_id, run.outputs_of("recommend"))
```

- **A sample read by a person.** The runs above, with what each produced.
- **A judgement from the end user.** What they say lands in `evals/labels.jsonl`, one per judgement, each naming what decided it (`docs/evaluation.md` §1.5). Those are the example set the next version is measured against.
- **A fresh evaluation at an interval**, against the same held-out split, compared on the interval rather than on the point estimate (`docs/evaluation.md` §9).

---

## 3. What a live run keeps

Every run writes a trajectory and a cassette holding the whole prompt and the whole response, under the redaction the envelope declares. The volume decision is `Trajectory` and it is `docs/run-envelope.md` §7:

```python
env = RunEnvelope(run_dir="runs/", trajectory=Trajectory.sampled(0.01))
```

`Trajectory.full()` keeps every payload on every run. `Trajectory.sampled(rate)` keeps them on that share, decided as each run starts rather than nominated afterwards, and the run's cassette goes with them. `Trajectory.sampled(0.0)` keeps neither and gives up replay, re-scoring and any later use of the runs as training data.

Counts, timings, token figures, seeds and cost are written for every run at every rate.

**The material is the end user's now.** Redaction removes credentials, the values `secret_env` names and anything typed `SecretStr`, and nothing else (`docs/run-envelope.md` §6). Material that must not be recorded is declared there rather than answered by turning the record off. This is what the brief's `live_records` answer settles.

**A run that has to be reproducible** is made through `envelope.with_trajectory(Trajectory.full())`, whatever the rate is otherwise.

---

## 4. Who answers the agent now

A consultation reaches whoever the channel says it reaches, and the declaration is on every consultation and on the tool's manifest entry (`docs/tools.md` §4.6.2). What was true while the project was built is usually not true afterwards.

```python
registry.add(consult(ask_in_chat, answered_by="end_user"))
```

| While building | Once shipped |
|---|---|
| `consult(ask_on_stdin, answered_by="builder")`, the author at a terminal | `answered_by="end_user"`, where that terminal is the end user's |
| `consult(answer_from_the_session, answered_by="coding_agent", permission=...)` | Gone. The coding agent is not there |
| `SimulatedEndUser`, a model playing the reader in an evaluation | Gone. It answers rollouts |
| `unattended()`, for smoke runs | Kept where the run is meant to be unattended, and the run answers `Unavailable` |

**FT-31 reads this**, once the project has reached stage `ship`. It fires on `coding_agent`, `simulated`, `canned` and `builder`, and passes on `end_user` and on `nobody`. Where the builder is the person the agent is for, the declaration is `end_user`: `builder` means the author standing in for somebody else.

**A run can replace the channel without the pipeline being rebuilt**, and the manifest records what that run was given:

```python
real = env.with_live().with_end_user(ask_in_chat, answered_by="end_user")
```

**Where the answer arrives later**, the channel raises `Suspend` and the run stops with its state on disk. `Pipeline.resume` continues it when the answer comes back (`docs/pipeline.md` §1.8). **Where an answer may come later but the run cannot wait**, the channel returns `Shelved`, the run finishes, and a later run uses the answer (`docs/product.md` §4). **Where there is nobody to ask**, `unattended()` returns `Unavailable`, the model is told once, and the agent reports what it could not settle (`docs/tools.md` §4.6.3).

---

## 5. Memory across a person's runs

A memory store is declared once and read under a scope, and a scope usually identifies one person:

```python
env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/"))
result = pipeline.run(question, envelope=env, model=client, memory_scope=f"user-{user_id}")
```

Each end user gets their own memory, and nothing one wrote is readable from another's runs. What goes in it is what the agent learns and writes; what the end user tells the product is the project's data model. `docs/memory.md` is the whole of it, including what redaction reaches on the way in.

---

## 6. What the end user reads, once it outlives the run

A run returns a value, and the end user reads it. Where they read something the project keeps instead, that artifact outlives the run that wrote it: a queue, a table, an index, a file the agent appends to. A later version of the pipeline does not go back and rewrite what an earlier version left there, so what is being read can hold results from every version that has ever run.

Nothing in the library sees this. An evaluation cannot: a rollout starts from an example the project seeded and reads nothing the agent wrote before. `simple-agents check` cannot: FT-13 and FT-14 read a run directory, FT-01 to FT-07 read a results file, and neither is the artifact. A project can report a sound measurement, pass every check, and be showing results a measured pipeline did not produce. FT-37 reads the same stamp for the reported number and is a different question: it says whether the figure describes the current pipeline, and says nothing about what is in the store.

**Write which pipeline produced a result beside the result.**

```python
stamp = pipeline.behaviour_fingerprint(model=client)

answer = pipeline.run(question, envelope=env, model=client)
store.write(answer, produced_by=stamp)
```

`Pipeline.behaviour_fingerprint()` covers the shape, every prompt's version, every `Deterministic` node's function version, the sampling parameters, every tool's version and declared cost, the model each node calls, and the budgets. An edited prompt moves it, and so do an edited tool body and an edited `Deterministic` node. A version the project declared and did not move does not, which is what declaring one is for: pass `version=` where a node or a tool reads data that changes underneath it, and change it when the data changes (`docs/evaluation.md` §6.7). `Pipeline.graph_fingerprint()` is shape alone and does not, so a project stamping with that one finds a stored result and a current one indistinguishable after a prompt change. Each run's manifest carries the same value under `behaviour_fingerprint`, so stored results and the runs that produced them join on it.

**A consultation channel is not in it.** A product that asks whoever is on the site and shelves the question when the site is unattended builds two channels over one pipeline, and both are the same pipeline. `answered_by`, `reaches` and `permission` are in, so a channel that stops reaching a person moves the stamp; which function does the asking does not. The channel is still what a consultation's cassette entry is keyed on and still what a resume compares, where two channels are two things to record and to continue under.

### 6.1 An artifact with no pipeline behind it

Some of what the end user reads is built by plain code: a page assembled from stored rows, a calendar, an announcement. Nothing there calls a model, so `behaviour_fingerprint` has nothing to describe, and stamping it with one reports the artifact as produced by a pipeline that never touched it.

Such an artifact still goes stale, and what decides it is the project's: the version of the data it was built from, the constants the ordering uses, what the end user has done since, and for anything dated, the date. Stamp it with a digest of those, and keep the two apart by name:

```python
CALENDAR_INPUTS = f"calendar-{catalogue.version}-{today.isoformat()}"
store.write(page, produced_by=CALENDAR_INPUTS)
```

The staleness query and the refresh are the same two halves as above. `stored_output` records which artifacts carry a pipeline's stamp and which carry the project's own, since a reader cannot tell from the value.

**Pass the client the run is passed.** A node that declares no model of its own calls whatever `Pipeline.run(model=...)` was given, so swapping a development model for the production one changes what every stored row holds. A pipeline whose model-calling nodes all declare their own client needs no argument here; one with a node that takes the run's refuses rather than returning a value that would not move when the model changed.

**A stamp needs something that refreshes what it identifies.** Selecting the results a current pipeline did not produce is a query; re-running them is what makes the answer to that query shrink.

```python
for old in store.produced_by_anything_other_than(stamp):
    store.write(pipeline.run(old.question, envelope=env, model=client), produced_by=stamp)
```

A step that selects work usually skips what it has already done, and a result written by an older pipeline is something it has already done. Whichever way that step reads, it decides whether a stale result is ever revisited.

`stored_output` in the brief records the artifact, what writes it, the stamp and the refresh. Where the end user reads a run's return value and the project keeps nothing between runs, the answer says so in a line. The artifact is designed earlier, at the design stage's product section, and `docs/product.md` §5 carries the rule that keeps an evaluation's rollouts from writing into it.

---

## 7. What live runs are worth afterwards

The runs a person made are the material the next version is built from, in three ways, cheapest first:

1. **Reading them.** What the agent actually gets asked is rarely what the example set holds, and the gap is what the next round of examples is drawn from.
2. **Labelling them.** A judgement in `evals/labels.jsonl` turns a live run into an example with a correct answer (`docs/evaluation.md` §1.5). A pass where a model writes or checks a label goes through the envelope with `role="labelling"` so it is not read as a run of the agent.
3. **Training on them.** A trajectory records the full input and output of every call, which is what makes a successful live run usable as a training example later.

A project keeping no payloads keeps none of these three. `live_records` is where that is decided.
