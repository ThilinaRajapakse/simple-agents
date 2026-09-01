# Changelog

Notable changes to Simple Agents, newest first.

Seven artifacts carry their own format version, and a change to any of them is recorded here
because a project holds files written in it: the **trajectory format**, on every trajectory
record; the **manifest format**, on every manifest; the **suspension file**, written by a run
that stopped; the **shelf file**, written by a run that left a question outstanding; the
**conversation file**, written by a run that is a turn of one; the **results file**, written by
an evaluation; and the **variant comparison**, written by a sweep over two versions of a
pipeline.

## Unreleased

Nothing is released yet, so no project holds records written by an earlier version. The
current formats are trajectory `0.29`, manifest `0.39`, suspension `0.5`, shelf `0.1`,
conversation `0.2`, results file `0.29`, and variant comparison `0.3`.

### The pre-release refactor inside the files, 2026-08-31

No format moves. The public surface is unchanged: everything importable from
`simple_agents` and `simple_agents.evaluation` stays where it was.

- **A node that fails or suspends inside a delegated pipeline now records the delegation as
  its `parent_id`.** A successful execution already did; an errored one recorded `null`, so a
  reader grouping a subtask's records lost its failed nodes. Trajectory format unchanged: the
  field existed and now carries the value the format describes.
- **A results file's `config` block carries the same keys in a different order.** The keys an
  evaluation declares are now written by one code path whether the rollouts were run or
  rescored, so a key added to one can no longer be missing from the other. JSON object order
  is not meaningful; a reader by key sees no change.
- Deep imports moved with the refactor: `progress_of` and `RolloutProgress` live in
  `simple_agents.evaluation.progress`, and `prompt_differences` in
  `simple_agents.evaluation.prompts_sent`. **Breaking** only for an import from
  `simple_agents.evaluation.runner`; the package-level names are unchanged.

### The pages read as a builder, 2026-08-29

No format moves. A read of every page on every fixture project, in a browser at laptop and
desktop widths and against the served page, found these.

**The rail sits beside the drawing on any screen 1280 pixels wide or wider**, and scrolls
within its own column. It moved under the drawing below 1720 pixels, which is every laptop
and most desktops, and left the right half of the page empty. Where the drawing itself needs
the whole width, it says so and the rail's two panels sit side by side under it. On the
build page, Progress now sits above the drawing; on a page with nothing to draw, the drawing,
the step card and the page's own empty note collapse into one sentence and the writing panel
follows the content.

**Buttons that did nothing.** *Answer it* on the brainstorm page, *Show me* on four of the
checks, *Walk this rollout* on a rollout the served page fetched, and *Open* on an abandoned
run each landed nowhere; each lands on the thing it names now. On the still page a one-click
(Agree, This is right, The code is wrong) filled a draft the panel never showed; it shows the
words and copies them with the address.

**A one-click already sent reads as sent.** Agreeing added a to-do to the band and kept the
button, so a second click posted a duplicate. The button is replaced by a note that the
sentence was sent and is with the coding agent, while the thread is open. A comment the builder spoke on last is with the
coding agent and is listed as worth knowing; one the coding agent answered is what waits on
the builder, and its button lands on the step the thread is on.

**Wrong numbers and words.** The rung sentence said *rises* where the figure fell.
"27 decisions remain for this stage" counted every stage's questions under one stage's name,
and the region it pointed at held six; the count is of questions, split by the stage that
asks, and the button lands on the page that asks first. A comparison row over two different
example sets said 0.0% beside a dumbbell that moved, with the reason in a hover; the row
says why under itself, and each undecided row carries its own reason. The trend drew a
sweep's arms as the project's behaviour changing. The idea's fifth box read *Unanswered* for
a question a later stage asks. *Seams · 4 to settle* counted rows; it counts the unsettled.
`$0.2`, "1 decision remain", "should decides", "This stage does not ask it", and three
sentences in the library's words rather than the builder's.

**The words.** Thilina, on the pages as built: *"Write this like a human."* Every sentence
on the page, in the findings, in the question texts and in the fixture briefs was rewritten
plainly: "Nobody …" constructions name the state instead (*unconfirmed*, *unanswered*,
*unattended*), clause chains are split into sentences, and "What this turns on" is *The
deciding factor*. `prose_check` gained a `nobody` rule and the same sweep went over the
shipped documents, the docstrings and the tests; FT-39 is *An unanswered comment*. The
`measured` fixture's prompts carried the construction and were re-recorded live, and
`shipped` was re-derived from it.

**The drawing.** Two routes to one step drew the same arm twice with its count on top of
itself; arms leaving straight down spread their labels; the failure label sits on its own
edge; a system-map subtitle fits its box; the dots on a step are in the key; the example
grid's *expects* column wraps rather than clipping every row to the same first clause.

### Four defects the six pages found in each other, 2026-08-29

No format moves.

**The checks board counts passing out of what ran.** A check waiting on an artifact the
project has not produced yet is not a failure, and counting it as one read a project at its
first stage as a project in trouble: 6 of 21, where 10 of the 15 were waiting on an evaluation
and a run that do not exist yet. It reads `6 of 11 pass · 10 could not run · 5 not at this
stage`, and a waiting row says what it waits on.

**The constants and the prompt rules are gathered across a project's own runs**, newest value
first, rather than off the newest run alone. A project with more than one pipeline runs
whichever it was asked for, so the newest run describes one of them: a project whose background
pass ran last showed that pipeline's one number and none of the agent's. FT-42 reads the record
the same way for the same reason.

**A store in the drawing's gutter no longer writes its name over its access count.** The name
takes the room the count leaves and the whole of it is on the element.

**A rollout is offered a walk only where pressing it opens one.** A still page carries the
newest run of each shape and the rollouts that came out wrong; every other rollout's button did
nothing, and now says so, while the served page fetches it on demand.

### The view before there is code, 2026-08-29

No format moves. The `brainstorm` and `research` pages are drawn (`docs/view.md` §6.9).

**The idea is five boxes**: who uses it, the entry point, the agent, what it receives and what
the end user gets, each filled from its answer or **drawn dashed where unanswered**.
That is the ghost a project is made of before there is code, and on day zero all five are
ghosts.

**The staging of the elicitation is visible.** A stage's questions read in four states rather
than the brief's three: an unanswered question this stage asks is open, and one a
later stage asks has not been put yet. Both read as unanswered in the record and only one of
them is anybody's business today. The six stages carry answered-of-asked, so a deferral is
distinguishable from an omission.

**`research.md`'s survey is drawn**, one column a part, each candidate with what became of it,
and every `dependency` decision joined to the candidates its own words reach.

**`idea.md` is read back on the page**, with one click that records the builder confirming it.

### The operate page, 2026-08-29

No format moves: every record it draws was already on disk and the page read none of them.

**`simple-agents view` gains a seventh page, "Operate"**, which appears once the project has a
live run (`docs/view.md` §6.8). It reads six things the page had never read: the suspensions a
run stopped at, the questions a background run shelved, whether a run with no outcome is still
going, the conversations runs are turns of, what each day's live runs cost, and the tool calls
that ended throttled.

**The run record moved to it, split by what each run was for**: real traffic, made while
building, and an evaluation's rollouts. It stays on the `ship` page for a project with no live
run, which has no operate page to move it to.

**A throttle the library waited out leaves no record**, so the history counts a call whose
attempts were spent rather than every throttle a run met.

### The product, declared, and the ship page, 2026-08-29

No format moves: the product is read from the code, and nothing writes it into a run record.

**A project declares what the end user meets.** `Product`, `Surface` and `product_factory` are
new (`docs/product.md` §2.1). Nothing in a run reaches the surface: a web handler calls
`pipeline.run`, so introspection sees the pipeline and never what called it. That is the
situation resources were in before a tool declared what it touches. Each surface names its
kind (one of the four in §2), the pipeline it reaches, the consultation channel an answer
travels through, or the resource it shows.

**`simple-agents view`'s `ship` page is redrawn around it**: the conformance checks as a
board, with each failure's next action and a link to where it shows; the product drawn and
joined to the pipelines, the channels and the stores it names, with the surface's own numbers;
retention in the builder's own answers; and the brief against the code as a tick list. The
run's walk moved to the `build` page (`docs/view.md` §6.6).

**FT-34 reads the declaration against `design.md`.** Where a project declares a `Product`, the
product section has to name every surface it declares; a surface it never names is an
interaction the builder was not shown. **A project declaring no product is unaffected.**

**Loading a project twice now finds it twice.** `simple-agents view` imports `agent.py` and
forgot only that module, so a `@pipeline_factory` or `@product_factory` in a module beside it
registered on the first load and on no later one: a module Python has imported does not run
again. The project's own modules are dropped after each load. This showed up as a page and a
gate reading the same project in one process and disagreeing about what it declares.

### The build page, 2026-08-29

No format moves. `simple-agents view`'s `build` page is redrawn around its own question: is it
being built as agreed, and what changed.

**Progress is one chip a step**, in four states, with the counts and whether each pipeline is
still the agreed shape.

**Every number the code carries is drawn against the decision that names it.** The manifest has
recorded module-level constants since `0.33` and the brief has recorded `constant` decisions;
nothing joined them, so a number the coding agent picked alone read like one the builder
settled. Unconfirmed numbers are marked and one click asks for the decision. **Prompt rules**
does the same for `prompt_rule` decisions against the prompts a run recorded.

**Where the brief and the code disagree, the page offers both ways out**: the answer is wrong,
or the code is wrong. Each is a comment the coding agent acts on.

**The last run moved from the `ship` page to the `build` page and is drawn as a strip**: what
the run was given, the steps it took in order, and the steps it never reached; selecting one
opens its record. An evaluation's rollout is no longer offered in that picker, since a rollout
is opened from the measure page's grid.

**`tool_effects` now counts a `WRITES` tool.** The question asks what the agent may do that
reaches outside the run: "spend money, write somewhere permanent, or take an action that cannot
be undone". The comparison against the code counted only `SPENDS_MONEY` and `IRREVERSIBLE`, so
a builder whose answer named the step that writes their store was told their answer and the
code disagreed. A project whose answer names its writers stops being reported as wrong.

### The shape page, 2026-08-29

No format moves. `simple-agents view`'s `shape` page is redrawn around the question it exists
for: is this the agent that was asked for.

**The story sits beside the drawing.** One row a step, in the order the code declares them,
carrying what the step is for in the words the project already wrote and the seams it holds.
Pointing at a row lights that step and its edges in the drawing; the arrow keys walk it. What
a step is for is read from its `NotBuilt` marker or the first line of its docstring, so
nothing is written down twice.

**Two regions are new**: **Seams**, the four answers the `shape` gate settles beside the steps
the code actually has, and **Shared state**, every resource with the steps on each side of it.

**Agreement is one click.** An unconfirmed design carries **Agree** and **Something is
wrong**, and a proposed decision carries **Agree**. Each lands as a thread in `comments.toml`
at the address of the thing agreed to; the coding agent records `shape_confirmed` or moves the
decision, as it always did. Nothing on the page writes the brief.

**The data path moved from the `shape` page to the `build` page.** Its rows carry how much
went through each step, which only a run fills in.

### A variant arm keeps the suite's floor, 2026-08-29

No format moves. `compare_variants` built each variant's suite without the baseline's
`baseline=` and `judgements=`, so a variant's results file carried no do-nothing floor and
every written comparison listed `baseline: [declared, None]` under `changed` as if the floor
were something the variant took away. A variant arm now carries both, its results file reports
the floor under every figure, and a comparison names only what differed between the two
pipelines. A sweep written before this reads as it did; re-running it writes the floor.

### The results visualiser, 2026-08-28

No format moves. Two additions a project meets.

**An evaluation keeps `progress.json` beside its rollouts while it runs.** Under
`runs/eval/<eval_id>/`, replaced whole after every rollout lands: the total the runner
declared, how many have finished, the outcomes scored so far, what they cost, and the runner's
own estimate of the time left. `simple-agents view --serve` reads it to follow an evaluation
live; nothing else reads it and a project may ignore it.

**`compare_variants` takes `max_spend`.** A suite whose pipeline reaches a `spends_money` tool
was refused by every arm of a sweep, because each arm's run requires the ceiling and the sweep
had no way to pass one. It is passed through to the baseline and to every variant.

### Four surfaces that read as working, 2026-08-28

No format moves. Four changes to behaviour, each one a surface that looked like it was working.

**A fan-out refuses where every item failed the same way.** Over two items or more, where every
failure carries one exception type and one message, the node raises rather than collecting: the
failure is not about the items, so the node produced nothing and the step after it would read an
empty result as a measured shortfall. Separate from `max_failures`, which says how many items may
fail and is untouched. A project whose failures each name their own item is unaffected, since the
messages differ. `docs/pipeline.md` §1.5.

**A failure saying the run is invalid ends the run from inside a fan-out item too.** A
`ConfigurationError`, a `StreamUsageMissing` and a `LeftTheSlice` were collected as that item's
failure and are now raised, joining the cassette miss and the exhausted budget that always were.
**An evaluation over a fanned-out node whose configuration is wrong stops on the first rollout**
rather than running k×n of them. A response that does not match the node's `output_schema` stays
collected, since one item's bad JSON is one item's problem. `docs/evaluation.md` §7.4.1.

**A fan-out's progress bar shows failures and counts a resumed set from where it left off.** A
failed item counted as a finished one, so a bar reached its total over nothing but failures, and a
resumed fan-out ended short by whatever it had already done. `NodeEvent` carries
`item_already_done`.

**A run warns where its `concurrency` cuts a node's `concurrent_items`.** The effective width is
the smaller of the two, so a node declaring 8 under the default `concurrency=1` ran one item at a
time and read as a slow model. Silent while replaying. `docs/pipeline.md` §1.10.

**`value_or` replaces the encoded absence as well as the object.** A `Maybe` field that has been
through `model_dump()` or a stored artifact arrives as `{"type": "unknown", "reason": ...}`, which
`value_or` passed through as a value. The bare word `"unknown"` is still a value and is not
replaced.

**`str(Unknown)` renders `unknown (reason)`.** It was `type='unknown' reason='...'`, so an
absence rendered into a template, a log line or a prompt built with an f-string reached whoever
read it as that. `repr` is unchanged. **A project whose prompts interpolate a `Maybe` field builds
a different prompt now**, so a cassette recorded over one of those misses and needs re-recording.

**A `Maybe` field is always told how to send an absence.** A `Field(description=...)` replaced the
description `Maybe` carries rather than adding to it, and a union around the union such as
`Maybe[str] | None` dropped it, so the model saw a union of a value and an object with no
discriminator described. The library now appends the sentence naming the tag where the description
omits it. **A schema with such a field digests differently**, so a run suspended before this
change refuses to resume after it and a cassette over one of those needs re-recording. A
description that already names the tag is unchanged, and so is a bare `Maybe[T]`. The warning that
used to fire at node construction is gone, having nothing left to warn about.

**`ctx.call_tool` re-raises the failure the tool raised.** It rebuilt a plain
`ModelFacingError` from the message, so a node body catching a kind of tool failure caught
nothing; a recorded failure replays as the same kind too. `Throttled` is the first subclass, so
this was invisible before it. `docs/tools.md` §2.1.

**A throttled source is waited out rather than reported as absence.** `Throttled` is a new
`ModelFacingError` carrying `retry_after_s`: the library waits and calls the tool again, three
attempts, honouring what the source asked for. `http_fetch` and `read_page` raise it on 408, 429
and 503, where they used to tell the model that requesting the URL again would answer the same
way. `retryable` on a `ModelFacingError` is unchanged and is documented as what it is: recorded,
and read by no library code. `retry_after_seconds` is exported. `docs/tools.md` §1.3.

### Evaluating back to front, 2026-08-28

**`Pipeline.slice` returns part of a pipeline as a pipeline.** The tail from a node, the head up
to one, the span between two, or a named set for a branching graph two bounds cannot describe. It
runs, writes a trajectory and a manifest, and is evaluated like any other pipeline, so a project
scores the last step alone on ideal inputs, then the last two, and the rung where the number falls
is the step that lost it. `docs/evaluation.md` §5.6 and `docs/pipeline.md` §1.14.

**An edge whose other end is outside a slice stays declared.** A node that took a `Join` still
receives one, with the arm that was cut in `Join.absent`, which is what it receives in the whole
pipeline whenever the route went the other way. A route may still select an arm the slice does not
hold, and the run ends there rather than going down a surviving arm: `Pipeline.run` raises
`LeftTheSlice`, the manifest records `outcome` as `stopped_early` and `stopped_early` as
`left_the_slice`, and the node's record carries the same `termination`.

**Manifest format `0.38` to `0.39`: a `slice` block.** The source pipeline's `graph_fingerprint`
under `of`, the node set, the bounds, the ids dropped, and one entry per cut edge. `null` on a run
of a whole pipeline. Two evaluations of two rungs of one pipeline are joined on `of`.

**Results file `0.28` to `0.29`: per-node ratios, and `config.slice`.** A `ProjectRatio` may be
declared in `node_metrics`, where it was refused at the declaration before, so a figure counting
what a step handled rather than scoring what it produced can be localised. Each rollout's two
totals are written to `rollouts[].nodes[].ratios`. `config.slice` carries the same block the
manifest does. Additive: a `0.28` file holds neither.

**`ExampleSet.entering` builds what a rung is run on**, taking each example's `inputs` from the
label for the node that was cut off, since the ideal input to a step is the correct output of the
step before it. An example with no label for it is left out, and a first node with two
predecessors gets a `Join` of their labels.

**`EvalResults.read` reads a results file from `0.28`, rather than the current version alone.**
The format is additive by default and re-making a file costs k rollouts of real spend, so a
version mismatch no longer destroys one a project holds. `EvalResults.format_version` says what
was read and `carries` says whether a named figure was written in it, so a figure the file
predates reports as underivable rather than as absent. `docs/evaluation.md` §8.

**A ratio is compared on its recorded totals wherever it is compared.** `compare()` paired one
on per-rollout scores, where a ratio records nothing, so it reported every one as having nothing
to pair with every example on both sides; `against_baseline` did the same against the floor. And
a ratio's scoring rule could move between two evaluations unseen, because the comparison read a
`version` key that a `ProjectRatio` does not write, so a figure that tripled compared as though
both sides were scored the same way. All three are fixed, and the sentence withholding a verdict
now names which half of the ratio moved.

**`simple-agents report runs/` counts runs made by a slice on their own line.** A rung runs under
the role the agent does and keeps its node ids, so the roles line could not separate it and its
per-node figures sat in the table beside the agent's.

**`simple-agents check` reports a project whose every figure is end to end.** FT-08 gains a note
at tier `evaluated`, where no node carries a figure of its own. A labelled node, a per-node figure
or a slice evaluation clears it, and a slice clears it while it was taken of the pipeline the
project has now. It reports and never fails.
### The floor a do-nothing agent sets, 2026-08-28

**`EvalSuite(baseline=...)` returning `None` is refused.** `None` is what a rollout produces when
the pipeline returned nothing, so a floor built from it reported an agent that did nothing as one
that failed: `failure_rate` read a floor of 100% for an agent that cannot fail, and every figure
over rollouts that asserted a value left it out. An agent that never answers says so, with
`Unknown(reason='did nothing')`. **Breaking:** a suite declaring such a baseline now refuses where
it used to run. The baseline is asked once per example **before the first rollout**, so this and a
baseline that raises both cost no rollouts; the message for a raising baseline no longer points at
`rescore`, since nothing has run.

**Results file `0.27` to `0.28`: `baseline_unscored`.** The project figures no baseline answer
reached, because the figure's `over` decides a non-asserting rollout without calling the
project's own function. A do-nothing baseline asserts nothing on every example, so a figure
measuring what the agent refrained from reported a floor describing the declaration rather than
the answers: 0.0 for a `ProjectMetric`, and no floor line at all for a `ProjectRatio`, whose two
totals are both zero. `report()` says so where the floor would be and names `over=Over.ALL`.
Additive: a reader of an earlier file sees the key absent. `docs/evaluation.md` §4.2.

**The floor is over the examples that ran, not over the split.** An evaluation that scored part
of a split reported a floor over the whole of it: a `rescore` of 4 rollouts of a 10-example
split printed `n=4` on the figure and `doing nothing, over 10 example(s)` under it, two
populations at two interval widths, deciding "not separated from it" against the wrong one, and
`against_baseline` paired examples the agent never answered. The report's own INCOMPLETE line
says every figure is over what ran, and the floor is one of those figures. **Breaking for a
part-scored evaluation**, whose floor and `against_baseline` deltas both move; a complete one is
unchanged, since there the two populations are the same.

**The view counted a right report of absence as wrong.** `simple-agents view` held its own
list of right outcomes naming `correct_absent` and `right_abstention`, and the outcomes are
`correct` and `correct_abstention`. Three rollouts whose report said accuracy 100% showed as
1 of 3 on the page, and a floor of two right abstentions as 0 of 3; an example that abstained
rightly was listed among those that went wrong. It reads `Outcome.succeeded` now. No format
moves, and a project regenerates the page by running the gate.

### What a run says it cost, and what it says it is doing, 2026-08-28

**Trajectory format `0.28` to `0.29`: a `run_start` record.** One per run, written before the
first node, carrying the inputs `Pipeline.run` was passed and the seed it derived every other
seed from. Every other record is written when the thing it describes finishes, so a run whose
process ended inside its first node recorded what it was given nowhere. **Breaking:** a seventh
record type, which a reader validating `record_type` against a fixed list refuses. `inputs` is a
payload, so it is redacted and sampled like any other. `docs/trajectory-format.md` §1.3.

**Manifest format `0.37` to `0.38`, and results file `0.26` to `0.27`: `totals.cost` carries what
was measured.** `measured` is what the calls that could be priced came to, with `priced_calls` and
`unpriced_calls` saying how much of the run it covers. `value` stays `null` where any call was
unmeasured, because an unmeasured token count is not zero, so the floor is beside the total rather
than in place of it. **Breaking in the results file:** `totals.cost.measured` was a sum over
nodes, and one unpriced call made a whole node unpriced; it is a sum over calls now, so the same
key holds a different and larger figure. `unpriced_nodes` still names the nodes. Measured on one
evaluation: `null` and `measured: null` where 940 of 994 calls had priced $5.5024 between them.
`docs/run-envelope.md` §4.2.

**A 429 against a spent allowance raises `Suspend` instead of retrying.** Where the backend's
message says the allowance resets on a scale a retry window cannot reach, the first refusal stops
the run rather than climbing the backoff ladder. Measured: 54 calls of one evaluation each waited
the full 31-second ladder against a monthly spending cap, 28 minutes in total. **Behaviour
change:** an evaluation meeting such a refusal now stops at the first one, with `suspension.json`
on disk, where it used to grind through every rollout. `docs/model-clients.md` §4.

**`Retry-After` is capped at `max_backoff_s`.** It replaced the backoff at whatever length the
backend named, and a budget is checked between steps rather than inside a call, so a header naming
an hour held one call for an hour with nothing able to interrupt it.

**`RunHandle.liveness` says whether a run with no outcome is still going**, as `running`,
`abandoned` or `unknown`, with `last_activity_at` beside it. Derived rather than recorded, because
a killed process writes nothing. `simple-agents report` counts an abandoned run on its outcome
line and `simple-agents check` counts one apart from a run that had not finished.
`docs/run-envelope.md` §8.3.

**`Pipeline.rerun(run_dir, envelope=...)` runs again what a dead run was given**, reading its
inputs and seed off its `run_start` record and serving its recorded calls from its own cassette,
so only what never finished is paid for. `docs/pipeline.md` §1.13.

**`simple-agents report` prints a device-basis figure with its unit.** A run priced in
device-seconds carries no currency, so it was summed under an empty unit and printed as a bare
number beside the money.

### A figure that is not a mean over examples, 2026-08-28

**`ProjectRatio` reports a ratio of two totals**, for a figure where the thing being counted is
not the rollout: picks inside an answer, pages a run read, pairs a judge decided. The project
declares a `numerator` and a `denominator`, each taking a `Scoring` and returning that rollout's
contribution; the library sums both over the figure's population and divides. The interval
resamples examples and sums both sides inside each resample, so k rollouts of one example travel
together as they do for every other figure. `ratio_ci` and `paired_ratio_ci` are the two
calculations, and both are public.

**A figure that is a count over one run reports its total and no interval**, declared with
`no_interval` holding the reason. It prints in a form that cannot be read as a measurement and a
comparison withholds its verdict on it. Declaring a `denominator` stays the better answer wherever
there is one, and a `ProjectRatio` with neither is refused.

**FT-06 reads a declaration rather than a string.** A figure with no interval passes by reporting
no value at all, which an empty denominator does, or by declaring `no_interval`. A reported value
carrying a free-text `reason` no longer passes, so the check is stricter than it was while
admitting the count.

**A figure over pairs, where there is no correct answer.** `Pair`, `paired_figure`,
`pairs_from_arms` and `unjudged_pairs`. A project forms the pairs and the library holds no opinion
about what a verdict says: both counting rules are given the pair and the verdict, and read
`this_is` and `that_is` to tell which side was picked. `pairs_from_arms` builds the one pairing the
library holds both sides of, two versions of a pipeline over one example set, and randomises the
order under a seed because a judge shown one arm first prefers it. Verdicts are read, never made
here, so the figure is computed with no network.

**Four answer shapes the survey enumerated, settled.** Written against what ships rather than read
off it. **B2**, several right answers not worth the same, is expressible: a two-criterion `Criteria`
grades the half-right answer 0.5 and `partially_correct_rate` reads it. **G2**, agreement across
the agent's own rollouts with no label, is expressible through the pair seam, which was not designed
for it: the k rollouts of one example are pairs. **F2**, a rubric with named axes, needed one
thing, and `Scoring` now carries the `verdict` inside a `ProjectMetric`, so conditions grouped by a
naming convention roll up per axis. **H1**, a label that is the spread of what annotators said,
needed one thing, and `read_every_label` returns every label under an id where `read_labels` takes
the last. Nothing was lost before it: the file always kept every line.

**A written comparison carries `comparison_format_version`, and everything it computed.**
`criteria` and `groups` were computed and dropped on write, so every per-criterion movement and
every grouped cell was missing from the file while `docs/evaluation.md` called it the full record.

**Variant comparison `0.2` → `0.3`: `behaviour_fingerprint` per arm.** `graph_fingerprint` cannot
see a reworded prompt, a moved temperature or a swapped model, so two arms differing only in a
prompt recorded the same value, which is the blind spot FT-37 closes for a headline.

**Results file `0.25` → `0.26`.** `Metric.denominator` is renamed **`population`**, which is what
it holds: the sentence naming which rollouts the figure covers, such as `"rollouts of examples
where a value exists"`. The freed name `denominator` now holds a number, beside `numerator` and
`estimated`. Each rollout carries `ratios`, its contribution to each ratio figure.

Each figure also carries `over`, the value that decided which rollouts it covers, beside the
`population` sentence that says the same in words.

**What this costs a project:** re-run the evaluation. A results file written at `0.25` is refused
by `EvalResults.read`, as every earlier format is. Code reading `metric.denominator` for the
sentence reads `metric.population`; code reading it for a number is new. A sweep written at
variant `0.2` is read by nothing in the library and can be kept or re-run. A project reporting only
means over examples needs no other change.

### The brief says when, 2026-08-27

**`recorded_at` on every answered entry and every decision**, an ISO 8601 timestamp with a time
zone, written by the coding agent off the system clock. The brief carried `asked_at` and `stage`,
both holding one of the six stage names, and no clock anywhere, so "when was this decided" was
unanswerable and "has something changed since that requires going back to it" had nothing to
anchor against.

**What this costs a project:** every answered entry and every decision in `brief.toml` needs the
key added, and a brief without it is refused when it is read, naming the entry and the line to
write. **The refusal names the first one it meets**, the way every other required brief key
behaves, so add them across the file in one pass rather than re-running between each. A
`deferred` or `unanswered` entry may carry one and is not held to it. A re-asked question moves
it with `asked_at`.

**What is validated is that it is a timestamp.** A value that does not parse is refused, and so
is one naming no zone, since two written on different machines cannot be put in order otherwise.
Nothing in the library writes a brief, so nothing checks the clock the value came from.
`docs/conformance.md` §2.1.

### FT-04's waiver narrows to the node that answers, 2026-08-27

**A project whose answer has no absent state can say so, even where a step on the way to it
does.** FT-04 stood down only where every model-calling node declared `allow_unknown=False`, so
a pipeline whose lookup can genuinely find nothing could not make the declaration at all.
**Measured on dogfood #5**: the shipped pipeline had eight model-calling nodes, two of which
could be absent; the waiver went unused in all 2,669 manifests, and the coding agent wrote twenty
invented absence examples instead, four of which landed in the held-out split and every one of
which scored `false_confidence`.

**Which node has to declare it** comes from the recorded graph: the pipeline's last unit, and
where that is a pipeline used as a node, its last unit in turn. Where the last unit calls no
model, the model-calling nodes that feed it. **What this costs a project:** a pipeline that
declared `allow_unknown=False` everywhere still waives; one that could not declare it before can
now, on one node.

**FT-04's failure message names that node and quotes the brief.** A coding agent that already
asked the builder what a wrong answer costs was told the abstract fix; it now reads
`allow_unknown=False` on `<node>` and the builder's own `absence_vs_error` answer beside it.
`docs/failure-taxonomy.md` FT-04.

### A stored result is not stamped with who was watching, 2026-08-27

**The consultation channel comes out of `behaviour_fingerprint`.** A product that asks whoever
is on the site and shelves the question when the site is unattended builds two channels over one pipeline,
and the two stamped differently. **Measured on dogfood #5**: every slate the product built from
a click reported itself stale the instant it was written, against the same pipeline running
unattended, and offered to rebuild what had just been rebuilt. Both halves were individually
correct, so no check could see it.

**What this costs a project:** every `behaviour_fingerprint` moves once. A project storing
results beside the stamp finds all of them stale on the next comparison and refreshes them, and
nothing is wrong with what is stored. `answered_by`, `reaches` and `permission` stay in, so a
channel that stops reaching a person still moves it.

**The channel still keys the cassette and is still compared on a resume.** Two channels are two
things to record and to continue under, which is a different question from what produced a
stored result. `docs/shipping.md` §6.

**`docs/shipping.md` §6.1 is new: an artifact with no pipeline behind it.** A page assembled by
plain code calls no model, so `behaviour_fingerprint` has nothing to describe and stamping one
with it reports the artifact as produced by a pipeline that never touched it. Three of dogfood
#5's six stored artifacts were this. What such an artifact is stamped with is a digest of what
actually decides it, and `stored_output` records which artifacts carry which.

### Which conversation a run is a turn of is `conversation_id`, 2026-08-28

**`Pipeline.run(thread=...)` is `Pipeline.run(conversation_id=...)`.** A bare `thread` on a
method whose neighbours are `concurrency=` and a `stop_when` documented with
`threading.Event()` reads as the thread the run executes on. The same argument is what settled
`memory_scope=` over a bare `scope=` the day before, and this applies it to the keyword that
shipped with conversations.

**What this costs a project:** rename the keyword at every `run()` call that names a
conversation. A run passing `thread=` now raises `TypeError`, so nothing fails quietly.

**`ConversationStore.threads()` is `conversation_ids()`**, which is what it returns, and
`ROLLOUT_THREAD` is `ROLLOUT_CONVERSATION`. `Thread` and `ThreadView` keep their names: the
handle a tool takes is `Conversation` and the object on disk is `Thread`, which is the shape
`Memory` and `ScopedMemory` already have.

**Manifest format `0.36` to `0.37`: `conversation.thread` is `conversation.id`.**
`Pipeline.resume` reads both, so a run suspended mid-conversation before this continues into the
conversation it stopped in rather than finishing outside it.

**Conversation format `0.1` to `0.2`**: the header record of a conversation file is
`{"record": "conversation", ..., "conversation_id": ...}` rather than `{"record": "thread",
..., "thread": ...}`. **What this costs a project:** `conversation_ids()` reads the new key, so a
store written at `0.1` lists nothing. Everything else about those files is unchanged and every
conversation in one is still read in full, by id, by the runs that continue it and by
`store.thread(...)`.

### Whose memory a run reads is an argument to the run, 2026-08-27

**`MemoryStore` takes a directory and nothing else, and the scope moves to the run.** The
constructor fused where the store lives, which is project configuration set once, with whose
memory it is, which changes per request, so a request handler had to rebuild the envelope for
every incoming request. **What a project on disk has to do:** drop `scope=` from every
`MemoryStore(...)`, and pass `memory_scope=` to `Pipeline.run`, `Pipeline.resume` and
`Pipeline.answer_shelved` wherever the pipeline reaches a memory tool. A run with a store and no
scope is refused before it starts, naming the argument, so nothing fails silently and nothing on
disk has to move: entries keep living under the same digest of the same scope.

```python
env = RunEnvelope(run_dir="runs/", memory=MemoryStore("memory/"))
result = pipeline.run(question, envelope=env, model=client, memory_scope=f"user-{user_id}")
```

**`Pipeline.resume` takes it too, and refuses another end user's.** The manifest records the
scope as a digest rather than as the value, so a resume is told the scope again rather than
reading it back. One whose digest differs from the scope the run started under is refused, which
a reply filed against the wrong run would otherwise turn into a write into somebody else's
memory. `docs/memory.md` §1.1.

**`MemoryStore.scoped(scope)` is how one end user's memory is read outside a run**, and returns
a `ScopedMemory` carrying what `MemoryStore` carried before: `get`, `keys`, `entries`, `put`,
`forget` and the count. Every rollout of an evaluation names the scope `rollout`, since each
already has a store to itself.

**No format moves.** The manifest's `memory` block holds the same three fields and the digest is
of the same string.

**What the documents now say a store is for.** `docs/memory.md` and `docs/product.md` §3 state
that the store holds what the agent learns and writes, and that what the end user tells the
product is the project's data model reaching the run as inputs. `docs/product.md` §3's earlier
sentence, that a request handler scopes the store to its user, read as *per-person state goes in
the memory store* and sent two projects to name the store in their design and build their own.

**`docs/product.md` §3 says the library reads no `.env`.** A model client is constructed with
what the process already holds, and a surface that never loaded the environment its scripts load
answers every request with the failure that client raises.

**`docs/tools.md` §3.3 says what a run loses when a node body does its own I/O**, and
`docs/failure-taxonomy.md` §10 carries it as something the suite cannot check. A `Deterministic`
body is Python: a fetch it makes directly is invisible to the fetch policy, absent from the
cassette so a replay makes it again and an evaluation makes it k×n times, and undeclared by any
side-effect class.

### Manifest format `0.35` to `0.36`: a `conversation` object, 2026-08-27

Recorded here after the fact. The conversation work of the same date bumped the manifest a
second time and this file recorded only the first. The `conversation` object carries the thread,
the turn, `carried_in` and the node that read it, and is `null` on a run that is not a turn of
one (`docs/run-envelope.md` §2.1). A manifest written at `0.35` carries none.

### Runs are filed by what they are, 2026-08-27

**A run's directory says what the run is.** A run an end user made goes under `runs/live/`,
one made while building under `runs/dev/`, an evaluation's rollouts under
`runs/eval/<eval_id>/`, and a run declaring a `role` under `runs/<role>/`. Each of the first,
second and fourth is inside a directory named for the UTC date. A project that listed `runs/`
and got every run it had ever made now gets four names.

**Nothing reads a run back by its location any more.** Every reader walks the tree and
identifies each run from its manifest, so **a project holding runs written under the old flat
layout keeps working and nothing has to be moved**. `find_run(run_dir, run_id)` is how a run is
located by id, and `Pipeline.resume` uses it, so a run suspended before this change resumes
where it sits.

**`Pipeline.shelved` and `Pipeline.suspensions` read the whole tree.** They read one directory
level before this, so a project that organised its runs into folders of its own got an empty
question inbox and an empty suspension inbox with nothing raised.

**Manifest format `0.34` to `0.35`: an `evaluation` object.** `eval_id`, `example` and
`rollout` on a run an evaluation made, and `null` on a run of the agent
(`docs/run-envelope.md` §2.1). A rollout did not record that it was one, and what separated
it from a run made while building was that its directory sat one level further down. A manifest written at `0.34` carries none, and those are read by their depth as before.

**`RunEnvelope(role=...)` refuses `live`, `dev` and `eval`**, which are the directories the
library files runs into itself.

**`evaluation_dir(run_dir, eval_id)` and `rollouts_under(eval_dir)` are new**, and are how an
evaluation's directory and its rollouts are found. `suite.rescore(run_dir=...)` takes the path
`evaluation_dir` returns.

### Connecting to an MCP server, 2026-08-27

**A project can give its agent the tools an MCP server offers**, with the side-effect class
each one has to carry declared in the project rather than taken from the server's hints
(`docs/tools.md` §7). Needs the optional extra, `pip install 'simple-agents[mcp]'`.

**Manifest format `0.33` to `0.34`: an `mcp` array.** One entry per MCP server a run declared
tools from, holding whether the run read the server or replayed a recording of it, the `drift`
between what the server offers now and what a recording holds, and the tools it offers that the
project did not declare (`docs/run-envelope.md` §2.10). Each tool's own entry under `tools`
gains an `mcp` object carrying the server, its four hints, the class those proposed and the
class the project declared. Both are `null` on a run that declared no MCP server, and a
manifest written at `0.33` is read as one, so nothing a project holds stops being readable.

**A new taxonomy entry, FT-43: the MCP server changed under the project.** It reads the newest
run's `drift` and fails where a server the project declared tools from now offers something
else. A description and a schema are what the model is shown, and both come from a server the
project does not control.

**`ToolRegistry.add_all` registers several tools at once**, for a factory that builds them.

### Found while verifying dogfood #5's sittings, 2026-08-27

**`on_reply`'s docstring said three branches where four are required.** `shelved` was added when
consultation met a product and the prose did not follow, so a reader was told three and then
refused by an error naming four. The error messages and `docs/tools.md` were already right.

**The view joins a step to its decision through `produces`**, where the decision records one,
and falls back to matching the step's name in the decision's wording. A brief that follows the
convention keeps identifiers out of that prose, so every well-formed project read as though no
decision named any step. **What this costs a project:** nothing; a decision recording no
`produces` joins as it did before. `docs/view.md` §12.

### What a decision produced, 2026-08-27

**A decision names what it became, under `produces`.** `dependency`, `shape`, `constant` and
`prompt_rule` decisions carry it; `presentation` and `measurement` do not, and a brief recording
one on either is refused. It names the tools of a dependency, the nodes of a shape, the numbers
of a constant, and the nodes whose prompts carry the rule of a prompt rule. **What this costs a
project:** nothing recorded before this is invalid, since a decision without `produces` is read
as naming nothing. `docs/conformance.md` §2.2.

**A twenty-fifth check, FT-42: a decision names something the project never built.** It reads
every name under `produces` against the node ids, tool names and constants of every run under
`runs/` whose role is `agent`, and fails from stage `ship`. Read across every run rather than
the newest, because a project with more than one pipeline runs whichever it was asked for.
**What this costs a project:** one whose decisions carry no `produces` passes, before and after.
A name only a `constant` decision records is left out where the runs predate manifest `0.33`,
and the pass says so, so a project that upgrades and has not re-run is not failed for numbers
it has. `docs/failure-taxonomy.md` FT-42.

**The report prints the other direction and never fails on it**: what the runs recorded that no
decision names, per kind, each name carrying the day of the newest run that recorded it where
that is earlier than the newest run read. Which of a project's numbers are the builder's to
decide is a judgement the library does not make. `docs/conformance.md` §4.4.

**Manifest format `0.32` to `0.33`: a `constants` array.** Every module-level number the
project's own code defines, as `module`, `name` and the value the run started with. The node
callables are the way in and the project's own modules they import are walked from there; an
installed package stops the walk. **It is outside `behaviour_fingerprint`**, so editing a
constant does not move the stamp and no stored result goes stale on one. **What this costs a
project:** a run written by an earlier version records no constants, and the report says the
array was not read rather than reading the project as one that defines no number.
`docs/run-envelope.md` §2.9.

### The build is a conversation, 2026-08-27

**A twenty-fourth check, FT-41: a run stopped to ask, and nothing continued it.** A
consultation that raises `Suspend` ends the run with its state on disk, and `Pipeline.resume`
is what picks it up. The check reads every manifest under `runs/` and fails from stage `ship`
where a suspension is still open and no run was ever resumed. **What this costs a project:** one
that stops runs and never resumes them passes today and fails at `ship` after this. A project
whose channels return `Shelved` or `Unavailable` never suspends and is unaffected.
`docs/failure-taxonomy.md` FT-41.

**Five elicitation questions have new `ask` text**: `answer_form`, `absence_vs_error`,
`judged_steps`, `budget` and `unevaluated_effects`. Each now names what has to be in front of
the builder before it is asked. The `brief.toml` keys are unchanged, so a recorded answer stays
valid. **What this costs a project:** a document quoting the old wording is out of date.

**FT-25's pass note reads the newest results file** as well as the run, and says where no
rollout asked through a registered consultation tool. Still a note on a pass; the check's
failure condition is unchanged.

**`docs/procedure.md`** gains the four rules for how a question is put, at "What to settle
first" so they govern every stage; the statement at `shape` that an evaluation puts no question
to a person, since a rollout is refused over a channel that reaches one; and the stage 4 step
that runs the consultation for real and continues the run.

### What the picture cannot say, 2026-08-28

**A node can record what its own code did to a store.** `ctx.record_access(resource,
direction, inputs=..., outputs=...)` writes what a step asked for and what came back, so a
resource reached in plain code is on the record the way one reached through a tool already
was. The direction is `read` or `write`, which `touches=` never said. The resource has to be
one the node declared, and what the payloads hold is the node's choice, so a step that read
67,353 rows and kept 12 records the two counts rather than the rows. `docs/pipeline.md` §3.

**Trajectory format `0.27` → `0.28`: a sixth record type, `resource_access`.** Additive.
Nothing recorded before this reads differently, and a reader that switches on `record_type`
meets a value it has not seen. A manifest's `counts` gains a `resource_access` key, which
follows the record types and is not a manifest format change.
`docs/trajectory-format.md` §4.5.

**`touches=` is on all three node kinds.** It was on `Deterministic` alone, and an `LLMNode`
or `AgentNode` whose prompt function reads a store had no way to declare it and so no way to
record the access.

**Results file `0.24` → `0.25`: `resource_reads` and `resource_writes` per node**, counting
what each node's own code reached, by resource name. **Breaking**: `EvalResults.read` refuses
a file written at `0.24`, so re-run the evaluation to produce one this version reads. Every
figure that existed is unchanged. `docs/evaluation.md` §5.

**`brief.toml` gains `shape_confirmed`**, a table of one `graph_fingerprint` per pipeline
holding the shape the builder was last shown. No gate reads it; the view uses it to say
whether the drawing has moved since it was agreed. `docs/conformance.md` §3.

**`simple-agents report <run> --walk`** prints one run step by step: what each step was
handed, what it handed on, and every model call, tool call, recorded access and question
under it. **The served view answers `/run/<id>`** with the same walk for any run on disk.

**The view draws what it knows rather than writing it.** A glyph per node kind, an outline
that says built, planned or changed, an edge whose width is how often it was taken, and a bar
in each step carrying what it cost, how long it took, model calls or items handled. Two
controls say what the drawing is over (the project's own runs or an evaluation's rollouts,
never both) and what the bar shows. A key names only the symbols that drawing uses.
`docs/view.md` §6.1.

**Every run is read rather than the newest one**, for what each step cost in the basis its
runs declared, how often each edge was taken, and every access to each store. Measured over
2,393 runs and 2.54 GB: 4.3 seconds, in a page that takes 6.5 to build for that project.
Cost per fan-out item is exact, since `over=` declares
the unit. `docs/view.md` §6.2.

**A store is explorable.** Selecting one shows every access on record with what was asked and
what came back, a tool call and a recorded access alike, the tools that reach it with their
signatures and their code, and where the data goes from there. What an evaluation's rollouts
reached is counted apart. `docs/view.md` §10.

**Every function the project declares is on the page**: its signature, the fields of what it
returns, its docstring, its file and line, and its body. Source goes through the run's
redaction rules before it reaches the file. `docs/view.md` §6.

### The data in the view, 2026-08-27

**The page says what each step is handed, rather than that it is whatever came before.** The
answer is derived from the steps whose edges reach it: one edge names the step and the schema
it carries, several name a `Join` with a key per edge, an error edge names the `NodeFailure`,
and a step nothing reaches takes what the run is given. A step that produces a value its
function annotates now shows that too, so a `Deterministic` node no longer reads as handing
on plain data when it declares what it returns.

**Every step says how much data went through it**, counted from the newest run's own records:
the keys that hold a count and how many they held, so a step reads `survey 2,000 · pool 40` in
and `items 40` out. A record of scalars is named by its longest text, and a `Join` counts the
edges that fired and says how many did not. Beside it the page carries the shape of what
arrived and what left, and one real value clipped to 220 characters a field.

**The data the project is measured on is a section.** `evals/examples.jsonl` is read for how
many examples there are, how they split, how many have absence as their right answer, how many
sources they came from, and what fields they carry, with one worked example that never comes
from a held-out split, because printing one spends it (FT-02).

**The brief is checked against the code.** Six answers have an exact counterpart in the shape
`agent.py` declares, and the page reads each against it: `agency_boundary` against the steps
that are an `AgentNode`, `consultation` against the steps that can ask a person,
`what_goes_wrong` against the steps declaring a failure path, `budget`, `tool_effects` and
`judged_steps` the same way. An answer naming a step the code says is something else leads the
page. The join is on a step's name, so an answer describing a step in other words reads as
naming none, and the page says that rather than claiming a disagreement.

**What a run did wrong is read.** Every step's card carries what its executions ended as, so a
step that ran out of model calls, failed, or was never reached each read differently; a step
with more than one execution in one run reads as retried; a failure path that fired is named;
and runs that did not complete are counted over the whole record by cause.

**What the agent asked a person is a section.** Every question the newest run put to someone,
with what was offered, what came back, which option the rule read it as, and who answered. An
answer the channel said was one option and the rule read as another is reported, because the
branch behind that question was never taken.

**What moved since the run before.** The last two runs of each pipeline, compared step by step:
what each handed on, how long it took, and whether it ran at all.

**A resource shows what can be known about it**: the steps that read, write or touch it, and
every tool that names it with its own description, its side-effect class and its callers.

**A step the run skipped is no longer reported as a step that ran.** A branch nothing reached
emits a record carrying `termination: "skipped"`, and the view counted those as executions.
They are counted apart, which is the accounting an evaluation's per-node figures already use.

**The page shows what the evaluation measured.** It reads the results file the gates read,
keeps every figure's definition, denominator, interval and left-out counts, puts per-node
figures on the steps, and says what was never reached, never scored, or never measured at all.
Where the suite declared a `baseline=`, what the agent got right is shown beside what doing
nothing got right. A results file measured over a graph the code no longer has says so, and so
does a brief naming an older results file than the newest on disk.

**Where the data goes**, as its own section: one row per step in graph order, what enters,
what each step is handed and hands on, the resources it reads and writes, and what leaves.

**The graph draws the hard shapes.** A step opens in place with **more +** for its facts
without leaving the picture; a pipeline used as a node is drawn as a frame around the steps
inside it, with the edges into and out of it reaching them; a cycle's closing edge is drawn
and never ranked, so a revision loop no longer pushes the steps below it down the page.

**A comment taken back can be put back.** `withdrawn` threads stay on the page under **Taken
back**, and the served page's `/api/reopen` makes one open again.

### The common language, 2026-08-26

**A step can be declared before it is built.** `NotBuilt("what it will do")` stands in a
node's callable slot, so a pipeline's shape can be written, drawn and agreed before the code
behind each step exists. A planned node refuses to execute and the rest of the pipeline runs;
`simple-agents view` draws it dashed with its own words on the card, and FT-40 fails a `ship`
gate while one remains.

**A tool or a `Deterministic` node can name what it touches.** `touches="catalogue"` declares
the resource, the same string wherever it is touched, and what flows between pipelines becomes
something the view computes instead of something a reader guesses.

**Manifest `0.31` to `0.32`.** Each node entry gains `planned` and `touches`, and each tool
entry gains `touches`. Both read as absent from older manifests, and nothing else moved.

**The view serves, and the builder talks back through it.** `simple-agents view --serve`
runs the page live on 127.0.0.1: it follows the project as the code and records change, and
everything on it is selectable and speakable: a comment on any element, an answer typed on an
open question, an amendment on an answer or decision already recorded. Each lands as a thread
in `comments.toml` (format `1`) with a snapshot of what the builder was looking at (`about`,
`stage`, `shape`, `when`); the coding agent reads threads with `simple-agents comments`,
replies with `append_reply`, and closes with `set_status(..., "addressed")`. An answer or
amendment never writes the brief by itself: the coding agent records it, so the brief stays
what passed between them. FT-39 reports open threads at every gate, and
`comments_block_gates = true` in the brief makes them refuse instead.

**A project names its pipelines.** `@pipeline_factory("recommend")` on the function that
builds one registers it, which is how `simple-agents view` finds and draws a project's
pipelines without running them.

### What an agent may do alone, 2026-08-26

**A tool may read the node's own input, through `NodeInput`.** A handle is a parameter the
library fills and the model never sees, and there are now seven. Six name something the
library owns and are written as the parameter's type. This one names what the node was handed
on its edges, and is written as annotation metadata, since the type of that value belongs to
the project:

```python
@tool(side_effect_class=SideEffectClass.READ_ONLY)
def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[str]:
    """Rank this node's shortlist against a query. Returns the titles that match."""
    return [row["title"] for row in pool if query.lower() in row["title"].lower()]
```

`NodeInput("pool")` is the value under that key and `NodeInput` with no key is the whole
input. A key the node's input does not carry raises `ConfigurationError` where the tool is
called, naming the keys it was handed. Under `over=`, the tool names the `over=` key and gets
the item. All three node kinds fill it, for a tool the node calls itself and for one the model
chose.

**A tool taking one is re-run on a replay rather than served from the cassette.** The node's
input is not in the call's key, so a stored answer would be served to a rollout that was handed
something else. That puts `NodeInput` under the same rule the other re-run handles are under:
`spends_money` and `irreversible` are refused on a tool that takes one.

**Before this, an `AgentNode` whose tools needed the node's input could not be one.** The
value was neither in the tool's key nor in a handle, and closing over it reaches whatever the
closure was built with, which an evaluation building one pipeline for every rollout makes
wrong k×n times with nothing raised. `docs/pipeline.md` §2.3 now says which of the two shapes
to reach for, the bounded cycle or the loop an `AgentNode` owns.

**`anything_else` is asked at every stage, and the brief entry carries `asked_at`.** Every
other question is the library's; this one is the builder's, and its answer is what nothing
asked about. FT-24 refuses while `asked_at` names an earlier stage than the project is at,
which is what the three `*_confirmed_at` keys do for a document applied to a question. The
answer accumulates under the stage it was given at, *nothing* is an answer, and a deferral is
refused because there is no later stage to defer it to. **A brief on disk gains one entry**,
and until it does the gate fails at whatever stage the project is at.

**`agency_boundary` is asked as a want.** It asks what the builder would like the agent to
work out for itself, written down in their own words before any node kind is named, and the
reading back into `Deterministic`, `LLMNode` and `AgentNode` follows it. It is put together
with `consultation`, which is the same subject from the other side, and it is now an answer
about what is wanted, so a `shape` decision names it under `from` and the report says when
none does.

### What the checks read: two gates on a change, and a header line, 2026-08-25

**A results file records `behaviour_fingerprint`.** What produced the numbers, at the width a
manifest records it. `graph_fingerprint` is beside it and is the shape alone, so an edited
prompt, a changed temperature or a swapped model leaves that one identical. `suite.rescore`
copies the value off the rollouts, since re-scoring runs nothing. **Results file `0.23` to
`0.24`**, so `EvalResults.read` and `compare` refuse a file written before this and it is
re-made by re-running the evaluation or by `suite.rescore` over its rollouts. `simple-agents
check` reads an older file either way.

**FT-37 fails a reported number produced by a pipeline the project no longer has**, from stage
`ship`, and is a note before it. A results file written by an earlier version carries no stamp
and reports `blocked`, naming what to re-run.

**FT-38 fails a brief that was never read against the code again**, from stage `ship`. The note
naming the entries due when `confirmed_against` and the newest run disagree is unchanged before
that stage and stops there, so the report carries the comparison once.

**Neither of those closes.** `stage = "ship"` stays in the brief, so both run every later time
the suite does. Every other check reads a project arriving somewhere; these two read the
pipeline moving underneath what an artifact already says about it.

**The report's header names the run the run-reading checks read, by its nodes.** A batch pass
that goes through the envelope with no `role` writes into `runs/` beside the agent's runs, and
the newest of them is what those checks read. `Report` gains a `reading` field, and the JSON
carries it.

**FT-03 reports `n/a` rather than `pass` where no contamination threshold was set.** No
contamination check ran and none was made, and the report line says that rather than passing.

**Two more notes**, neither of which fails anything: the rollouts a results file describes are
not the ones in the evaluation's directory, joined by the evaluation's identity rather than by
the recorded paths; and, from stage `ship`, what the live runs did, since every check but FT-31
reads a run that is not live.

**FT-35's pass line names `simple-agents report runs/`** where it read fewer runs than the
directory holds.

**A variant sweep's arms declare `role="variant"`.** Every arm but the baseline, so no check
reads an arm as a run of the agent and `runs("runs/", role="variant")` reads a sweep back. The
baseline keeps `agent`: it is the pipeline the project has, run over the example set. A project
whose last activity was a sweep had FT-13, FT-14 and FT-15 certify one rollout of one arm.

**`compare_variants` refuses an envelope declaring `live=True`.** A sweep's rollouts run the
example set, and every arm but the baseline is a pipeline the project does not have, so neither
is a run an end user made. Refused before the baseline runs rather than on the first arm.

### Consultation: a third way to end, an identity, and a shelf, 2026-08-25

**A consult channel takes three arguments.** `(question, options, about)`, where `about` is a
short stable name for what the question concerns. Every channel a project wrote takes the third
argument now, including one passed to `RunEnvelope(end_user=...)` or `suite.run(end_user=...)`.

**A channel may return `Shelved(reason=...)`.** The third way a consultation ends without an
answer, beside raising `Suspend` and returning `Unavailable`: the question is on record and an
answer may come later, the run finishes now, and a later run uses the answer. It records
`resolution: "shelved"` and never silences a later question. `docs/tools.md` §4.6.3.

**`on_reply` requires a `shelved=` branch.** Every route built with `unmatched=`, `declined=`
and `unavailable=` needs the fourth, and `exhaustive=True` waives all four.

**The once-per-run rule is the model's alone.** A consultation reached through
`ctx.call_tool` from a `Deterministic` or `LLMNode` body always reaches the channel. It was
answered from the run's memo before, so a node asking one question per item of a list had every
question after the first answered without the channel seeing it.

**`Suspend` derives from `BaseException`.** An `except Exception` around a call no longer
swallows it, and a run that finishes after one was raised is refused. A project catching
`Exception` around `ctx.call_tool` loses the suspension it used to swallow, which is the point.

**Trajectory format `0.27`.** A `consultation` record gains `about`, `asked`, `answered_at` and
`answers_run_id`, and `resolution` gains `shelved`. All four fields are additive and absent on
every record written by an earlier version.

**Shelf format `0.1`.** A run that shelved a question writes `shelved.json` beside its manifest.
`Pipeline.shelved(run_dir)` lists what is outstanding and `Pipeline.answer_shelved(...)` files
an answer against one and runs the work it triggers. `docs/product.md` §4.

**An evaluation is refused over a channel that reaches a person.** `suite.run` and
`suite.record` stop before the first rollout where a consult tool's `answered_by` is
`end_user`, `builder` or `coding_agent`. Pass `end_user=` to say who answers: a stand-in, or
that channel handed back. A replay is exempt. `consult` is still `read_only`.

### The example set is `evals/examples.jsonl`, 2026-08-20

**`evals/questions.jsonl` is `evals/examples.jsonl`.** The file holds examples and
`ExampleSet` reads it; the old name came from the first question-answering project. A project
on disk renames the file, and every path in the documents and the layout moved with it.

### The product, 2026-08-20

**"The product" is a named part of the project**: what the end user uses, the surface they
meet the agent through and any artifact the project keeps for them to read. `docs/product.md`
is the seventeenth document: the three product shapes, the four kinds of interaction, a run
per request behind a surface, a run that waits for its end user, the artifact that
accumulates, and what triggers runs.

- **`used_through` is required at `brainstorm`**: what the end user opens, and what makes a
  run happen. A project on disk fails FT-24 until it answers.
- **`design.md` has four sections.** The product section classifies every end-user
  interaction as starting a run, answering a waiting run, reading the artifact, or recording
  a judgement. FT-34 reads it, so a three-section `design.md` fails until it gains one.
- The procedure's stages 1, 3 and 4 point at the document, and stage 4 builds the product
  beside the pipeline.

### A fetch policy each run binds its own copy of, 2026-08-20

**`HostPolicy` is a declaration now, and every run counts on its own copy**, so two runs
served by one process no longer share one tally of fetches and admissions.

- **`admit` and `spend_fetch` move to the run's copy.** A route or a `Deterministic` function
  reaches it at `ctx.fetch_policy`, and a project tool reaches it by annotating a parameter
  with `HostPolicy`, which the run fills and the model never sees. Calling either on the
  declaration itself raises, naming both routes. Code that called `policy.admit(...)` on a
  module-level object changes to one of the two.
- **`HostPolicy` is the sixth handle type**, beside `SpendMeter` among the ones that do not
  make a tool re-run on replay: a replayed fetch is served, never made again.
- **The manifest's `fetch_policy` counts are the run's own.** The shape is unchanged.
- **A tool taking a `HostPolicy` parameter with no declaration anywhere is refused** at
  `Pipeline` construction, naming `policy=` on the tool factory and `Pipeline(fetch_policy=)`.
- **`http_fetch` and `read_page` re-derive their versions**, since their bodies now use the
  run's copy, so a cassette holding a fetch call from an earlier version misses.

### A generated run id carries eight random characters, 2026-08-20

`run_20260820T101502Z_a3f92c1d`: the UTC second, then eight characters where there were four.
Runs a product serves concurrently start inside one second routinely, and at four characters a
collision silently merged two runs into one directory, one trajectory and one manifest.
Nothing parses the id, and ids from earlier runs are read as they are.

### The research stage, 2026-08-20

**A sixth stage, `research`, between `brainstorm` and `shape`.** A project that has declared
any stage from `research` on gains five required brief entries and a new artifact, so a gate
fails until it has them.

- **`research.md`, and FT-36.** Four sections: the parts, and what each has to do; what was
  found against each part; what this turns on, having looked; and what the builder said about
  it. The second is a table with one row per candidate and an `Outcome` column, and FT-36 fails
  on a blank cell, on a missing section, on a last section quoting nobody, and on a
  `research_confirmed_at` older than the stage the project is at.
- **Five questions**: `parts`, `approaches`, `available_material`, `what_goes_wrong` and
  `what_this_turns_on`. The first is a decomposition answered before anything is looked up, and
  the rest are asked against each part in turn.
- **A brief entry carries `source`.** `builder`, `research`, `document` or `coding_agent`, and
  it defaults to `builder`. A required question answered `source = "coding_agent"` fails FT-24
  the same as one left unanswered, so a coding agent that filled something in has a way to say
  so instead of recording it as the builder's.
- **`simple-agents report runs/` prints each tool's registration against its use**, and
  `--json` carries it under `tools`. A node's `tools` column counts the calls it made and never
  says to what, so a tool a project built and stopped reaching was visible nowhere.
- **`ExampleSet.nearest_cross_split(n=)`** returns the closest cross-split pairs with both
  examples' text, whatever their similarity. `contamination(threshold=)` returns nothing on a
  clean set, and the `too_similar` question now asks the builder to judge pairs rather than to
  name a threshold.
- **A `dependency` decision naming no research is a line in the report**, alongside the answers
  no shape or presentation decision rests on.
- **The stage count moved from five to six** in `docs/procedure.md`, `docs/conformance.md` and
  every refusal that lists the stages. A brief declaring a stage is unaffected; one deferring an
  entry to a stage now has six to choose from.

### What a figure is reported against, 2026-08-20

**Results file `0.22` to `0.23`.** Five stages, one bump.

- **Every figure can be reported grouped by a property of the example.** `results.grouped(key)`,
  `results.report(group_by=key)` and `compare(before, after, group_by=key)`, where the key is a
  field of the example or one of its `metadata` keys. A headline is a mean over whatever mix the
  split holds, so a change that improved one kind of example and damaged another reports no
  change at all where the prevalence cancels them. The cells are computed from the rollouts the
  file already holds, so a grouping can be chosen after the evaluation ran.
- **An example's `metadata` reaches the results file**, which the field's own documentation had
  said and nothing did. So does `label`, the answer key where it is a single value, so grouping
  by the right answer needs no declaration. A metadata value over `METADATA_CEILING` (64 KiB
  encoded) is named in `metadata_omitted` rather than written, and the example itself is
  unchanged.
- **`Metric.rollout_noise`: how far a figure moves when the same examples are run again.** The
  interval resamples examples and says nothing about this, and it costs nothing: the k rollouts
  of each example already carry it. `report()` prints it as `rerun ±x`.
- **`compare()` withholds `moved` where the difference is inside that noise.** A difference whose
  interval excludes zero but which is no larger than what one configuration produces twice is
  `None` with a reason, rather than reported as a real move. A difference whose interval already
  includes zero is still `False`.
- **`EvalSuite(baseline=...)`: what an agent that did nothing would have scored.** A constant
  answerer scored by the same `matches` and the same conditions over the split that actually ran,
  reported under every figure by `report()` and paired against the agent by `against_baseline()`.
  It calls no model. A floor written into a metric's `definition` instead goes stale when the
  split is rebalanced, and is then read as cleared when it is not.
- **A record that answered part of its key and left a `required` condition alone counts as an
  answer given.** `abstention_rate` is over rollouts that reported absence, and one that named
  a vendor and left the PO number empty reported no absence; `precision_when_asserting` is over
  rollouts that asserted anything, and that record asserted something. It scores 0.0 there, so
  a figure that read the outcome alone was reporting a precision the answers did not support.
  `Verdict.asserted` is the new field and `RolloutOutcome.asserted` reads it. A record silent on
  every condition is unchanged, and so is one whose silence met a condition declaring
  `expects_absence`, which now leaves `precision_when_asserting` rather than counting as an
  assertion.

### A gate on a loop that spent its budget without acting, 2026-08-19

**FT-35**, and it is the first check to read more than one run. **Manifest `0.30` to `0.31`,
results file `0.21` to `0.22`.**

- **`simple-agents check` fails a node with a unit of work that produced no output and never
  called a tool, consulted or delegated.** A unit is one execution or one fan-out item. It
  reads the `unfinished` block of every run's manifest, so it opens no trajectory.
- **The runs it reads are the ones the pipeline as it stands has made**, by the
  `behaviour_fingerprint` each run recorded. A prompt, tool, budget or model that changed moves
  that, so runs made before a fix leave the pool once the fix has run, and none has to be
  deleted for the gate to pass. `--since`, `--last`, `--role` and `--live` on
  `simple-agents check` narrow it further and reach no other check.
- **`AgentNode(..., allow_unfinished=True)`** waives it for one node, recorded in the manifest's
  node entry beside `allow_unknown`. It changes nothing the node does.
- **`unfinished` gains `model_calls_without_tool_calls`**, what the units that never acted
  spent, and `NodeMetrics` gains `unfinished_model_calls_without_tool_calls` beside it. A run
  written before this is reported as unread rather than counted as clean.

### What every run did, without writing code, 2026-08-19

- **`simple-agents report <path>`** reads a directory of runs, one run, an evaluation's
  rollouts, or a results file, and prints what each node did with what it spent. `--json` is the
  same as data, and `--role`, `--live`, `--since` and `--last` narrow which runs are read. The
  first line names how many runs were read of how many are there.
- **`results.report()` carries what each node produced nothing with**, under the node it belongs
  to, and its per-node table's `runs` column is now `execs`, which is what it always held.
- **`runs()` takes `since=` and `last=`**, the filters `node_metrics` already had.
- **`basis_from_manifest`** rebuilds the cost basis a run recorded, so a reader with the runs
  and not the envelope prices them the way the run did.
- **`simple-agents check` prints what the runs produced nothing with** as a note, which is the
  wider figure FT-35 does not gate on.

### `tools_that_never_succeeded` is over every run read, 2026-08-19

The count was written per run rather than accumulated, so over an evaluation's rollouts a tool
that failed in one and worked in the next was still named, with whichever rollout was read last
deciding the number beside it. Found reading the figure back over 3,293 runs.

### A node or a subtask the run stopped inside is counted once, 2026-08-19

A run that suspends writes a record when it stops and another when it is resumed, and
`docs/trajectory-format.md` says both describe one logical execution. `per_node` followed that
rule for consultations and not for the other two, so a resumed run reported twice the executions
it had and twice the subtasks it sent. Found while adding a figure beside `delegations`.

- **`NodeMetrics.executions` and `NodeMetrics.delegations` count the records where
  `resumed_from` is `null`.** A figure read per execution, such as calls per execution, was
  halved by this on any run that suspended.

### Where else a run's spend bought nothing, 2026-08-19

Three more per-node figures, completing what a run can say about spend that produced nothing.
**Results file `0.20` to `0.21`.**

- **`empty_responses`** counts model calls that came back with no content and no tool call. A
  reasoning model that spends its whole output ceiling on the chain of thought answers this
  way, and so does one cut off before it wrote anything. Reasoning is not content. An embedding
  or a rerank is not one of these: it records what came back in its own shape and has no
  content field to be missing.
- **`delegations_out_of_budget`** counts the subtasks that ran the delegated pipeline out of its
  own budget, so the model got a report of failure rather than an answer. Read beside
  `delegations`.
- **`tools_that_never_succeeded`** names the tools a node called where every call failed, with
  how many calls each took. A tool that failed and later worked is absent.

### A fan-out's identical tool calls belong to their own items, 2026-08-19

Two items of a fan-out overlap, so two of them making one call with the same arguments took
their cassette occurrences in whichever order they arrived. A replay that interleaved
differently handed each item the other's answer. Measured with a tool answering differently
each time: recorded `value-1` to the first item and `value-2` to the second, replayed the other
way round.

- **The occurrence is counted within the fan-out item as well as the node**, and the item is
  part of the tool call's cassette key. It needs a fan-out with overlapping items, an identical
  call from more than one of them, and a tool whose answer varies.
- **A call made outside a fan-out keys exactly as it did**, so no existing recording is
  invalidated: the item is absent from the hashed material where there is none. Every tool call
  in the committed cassettes was rekeyed under the new function and none moved.

### A schema shown to a model, and which item a call underneath a node belongs to, 2026-08-19

- **A non-pydantic `output_schema` is refused at construction.** It was accepted in silence: the
  model was offered a `finish` whose parameters were `{"type": "object", "properties": {}}`, so
  it was told the call takes no arguments, and whatever it sent back became the answer without
  being validated. `LLMNode`, `AgentNode` and `extract_to_schema` refuse it now, naming the
  pydantic model to declare. `Deterministic(output_schema=...)` still takes a dataclass or a
  `TypedDict`, since nothing there is shown to a model and it was already validated.
- **A consultation reader's model call carries its fan-out item**, so two items' readings no
  longer share a call counter. The seed each was sent depended on which item asked first, and
  that seed is in the cassette key: **a recording of a fan-out whose items consult with a
  `read=` reader has to be re-recorded.**
- **A search's embedding and rerank calls carry their item too**, so what one item of a fan-out
  spent is readable. Their cassette keys are content-based and no recording is affected.

### What a rate is over, and what leaves it, 2026-08-19

A rollout is inside a rate's denominator when what it returned is attributable to the agent.
That is the rule `no_response` already followed, and it decides two cases that shipped as
counts beside the figures rather than as anything the figures read.

- **A question to a channel that was meant to answer it takes the rollout out of every rate.**
  The agent asked correctly and the answer never arrived, so a rate over it measures the
  answerer. A question to a channel declaring `nobody`, which `unattended()` does, leaves the
  rollout in: behaving well with no one to ask is what such a project is measured on.
- **A fan-out item the backend never reached takes it out too**, which is `no_response` at item
  granularity.
- **`Metric.no_response` is now `Metric.left_out`**, keyed by cause, and `Metric` gained
  `including_left_out`: the same figure with those rollouts counted as they scored. The report
  prints it under the headline, so the narrower number cannot be read without the wider one. A
  `no_response` rollout is in neither, having produced no answer to count.
- **`RolloutOutcome.left_out`** names why a rollout is outside. **Results file `0.19` to
  `0.20`.**

### What a run spent and produced nothing with, 2026-08-19

An `AgentNode` produces its output from a `finish` call, so an execution that stops on a budget
axis returns `None` to the node after it, the run completes, and no error is recorded. Nothing
reported it. Measured over one project's 3,293 runs: 289 executions ended that way and spent
24.4% of every model call it made, and 189 of those made no tool call, no consultation and no
delegation at all.

- **Four figures per node**, in a results file and on `NodeMetrics`: `unfinished_executions`,
  `unfinished_items` for a fan-out's items, `unfinished_without_tool_calls` for the units that
  never acted, and `unfinished_model_calls` for what they spent. **Results file `0.18` to
  `0.19`.**
- **`node_metrics(run_dir)`** reads them, and everything else a node did, out of any directory
  of runs, filtered by `role`, `live`, `since` and `last`. The computation existed and was
  reachable only inside an evaluation.
- **Each run's manifest carries its own**, under `unfinished`, read off the trajectory when the
  run ends, so aggregating many runs opens one small file each. **Manifest `0.29` to `0.30`.**
- **Trajectory format `0.25` to `0.26`.** `tool_call`, `consultation` and `delegation` carry
  `item_index`, the fan-out item the call was made for, and `null` outside one. A fan-out's
  items share one `parent_id` and can overlap, so nothing else attributed a call to an item:
  a project could tell which item made which model call and not which item called which tool.
  Additive, and a record written by an earlier version carries no such field.
- **A model call a tool makes inside a fan-out carries its item.** It carried none, so two
  items' nested calls shared one counter and **the seed each was sent depended on which item
  reached the tool first**, which `docs/trajectory-format.md` §4.1 says cannot happen. A
  cassette entry is keyed on the request and the seed is in it, so **a recording of a fan-out
  whose tool makes model calls has to be re-recorded**.

### A version is taken when the thing is declared, and FT-15 has a check, 2026-08-19

A prompt's version covers what its function closed over, which is what separates two routes one
factory built. It was recomputed every time the manifest was read, so a prompt or route holding
state across its own calls changed version while the run ran, and `behaviour_fingerprint` is the
value a project joins its stored results on: the stamp written before a node ran and the stamp
written after did not match.

- **A version is taken once, when the node is declared**, for a prompt, a route, a finish check
  and a `Deterministic` node's function. Later mutation of what the function captured does not
  move it. Nothing about the recorded shape changes.
- **FT-15 has a registered check**, the seventeenth: every prompt in the manifest records a
  version, and one whose source could not be read fails. Its taxonomy entry now states what a
  check can read, and its surface is `artifact` rather than `static + artifact`.
- **A tool's version covers what its function closed over.** Two tools one factory built over
  different configuration shared a version, and the version is in the cassette key, so a call
  recorded against one was served as the other's answer. The capture is read when the tool is
  declared, so state a run accumulates does not move it. **Every recorded call by a tool built
  from a factory misses until its cassette is re-recorded**, and `document_search` is such a tool.

### What an evaluation is filed under, and what the prompts show, 2026-08-19

An evaluation writes into a directory named after what decides what was measured, so two that
measured different things cannot land in one. Three things decided it and did not name it: an
edited tool body, an edited `Deterministic` node body, and data a node reads. Re-running was then
refused as a used directory, which names the wrong cause, and `resume_from` read the earlier
rollouts as this evaluation's and reported one figure over two versions. An edited `Deterministic`
body also moved `behaviour_fingerprint` not at all, so a stored result could not be told from one
a different pipeline produced. **Manifest `0.28` to `0.29`.**

- **A `Deterministic` node's function is versioned**, in `fn` on its manifest node entry, the way
  a prompt is. `Deterministic(read_library, version="characterised-2026-08")` declares one; left
  unset it is a hash of the source. It is in `behaviour_fingerprint` and in the evaluation
  directory's name.
- **A tool's version reaches the evaluation directory's name.** The name was built from tool
  names alone, so two pipelines differing in a tool body resolved to one directory. `rescore` and
  `resume_from` now refuse rollouts an edited tool produced.
- **`Pipeline.manifest_tools()`** returns the `tools` array the manifest writes, beside
  `manifest_nodes`, `manifest_containers` and `manifest_prompts`.
- **A declared version records the source hash beside it**, under `derived`, on a prompt, a tool
  and a `Deterministic` node. Only the declared version decides identity, so a cosmetic edit under
  one still moves no figure. `resume_from` and `rescore` warn where a declaration stayed put and
  the source under it moved (FT-15).
- **`prompt_differences(run_dir, against=None)`** reads the prompts back out of the trajectories
  and reports where one example was sent more than one. Inside an evaluation that is a prompt
  something other than the example decided; across two it is the change no declaration covers,
  such as a store rebuilt underneath an unchanged pipeline. It reports and never fails: a tool
  holding state across rollouts produces a difference legitimately.

### A run and an evaluation have a progress display, 2026-08-18

Three channels reported what was running and one of them rendered: `RolloutProgress.describe()`
returned a line, while `on_progress=` and `progress_of` handed back an event and a dict. Nothing
repainted, so watching a long evaluation meant printing one line per rollout.

- **`ProgressBar` takes either callback.** `pipeline.run(on_progress=ProgressBar())` and
  `suite.run(on_rollout=ProgressBar())`. An evaluation gets a proportion and a time remaining; a
  run gets a counter, because loops and routes decide how many nodes run while it is running; a
  fan-out inside a run gets its own bar. Nothing is written where the stream is not a terminal.
- **`NodeEvent.item_total`** says how many items a fan-out has, so an `item` event carries a
  denominator. It is `None` on every other phase.
- **`simple-agents watch <run_dir>`** follows an evaluation from another terminal, over
  `progress_of`, importing nothing of the project.
- **`tqdm` is a new dependency**, alongside `httpx` and `pydantic`.

### The stamp on a stored result covers the model and the tools, 2026-08-18

`Pipeline.behaviour_fingerprint()` is what a project writes beside a result it keeps, so a row an
older pipeline produced can be found and re-run. Three things that decide what a pipeline
produces were outside it, and each is recorded in the run manifest: the client passed to
`Pipeline.run(model=...)`, every tool's version and declared cost, and a consultation reader's
model and prompt. A project that swapped a development model for the production one, or edited a
tool, stamped both versions with one value. **Manifest `0.27` to `0.28`.**

- **`behaviour_fingerprint(model=client)` takes the client the run is passed**, and covers it
  where any node calls it rather than declaring its own. A pipeline whose model-calling nodes all
  declare their own needs no argument. One with a node that takes the run's raises rather than
  returning a value that would not move when the model changed.
- **The tool entries are in the digest**, so an edited tool body moves the stamp.
- **`graph_fingerprint` is unchanged.** It answers whether stored state can still be walked, and
  none of this bears on that.
- **`simple-agents check` now reports the brief's pipeline answers as due after a model swap.**
  `confirmed_against` holds this value, and `backend` is one of the questions it dates.

### An adapter cannot silently drop the state a backend requires back, 2026-08-18

A backend may send a value with each tool call and refuse the following request without it, such
as Gemini's thought signature. It travels on `ToolCallRequest.provider`, and the OpenAI dialect
has no field for it.

- **`messages_to_wire` refuses a tool call carrying `provider`** rather than translating the turn
  without it. An adapter for such a backend translates the conversation itself; the shipped
  Gemini client already does, and neither shipped OpenAI-dialect client can reach the refusal
  because neither backend sends state of the kind.
- **`docs/model-clients.md` §7 says what an adapter owes in both directions.**

### An evaluation can see a fan-out item that never reached the backend, 2026-08-18

A fan-out collects a failed item rather than raising, and at the default `max_failures` it never
raises at all, so a rollout whose items were rate-limited or refused completed and was scored on
whatever the rest produced. The classification that separates a backend that did not answer from
an agent that produced no answer is only reached by a run that raised. **Results file `0.17` to
`0.18`.**

- **`RolloutOutcome.unreached_items` counts the items that died on a call the backend never
  answered**, by the rule a whole run is classified on: the item's last model call recorded an
  error and returned no content. An item that failed on a reply it was given, such as one that did
  not validate, is not counted. Nothing is reclassified; the count is what makes it visible.
- **A failed model call records the fan-out item it was for.** A call that returned already did,
  and the record a reader goes to for a failed item is the failed one.
- **`NodeEvent` gains an `item` phase and an `item_index`.** A fan-out hands its whole result to
  the next node when the last item is done, so a project writing each item as it lands had nothing
  to write on. It is a phase of its own, so a caller counting `completed` events counts nodes.

### Every node kind fans out, and a model call at a fixed point can use a tool, 2026-08-18

`over=` was on `LLMNode` alone, so an agentic step once per item of a list could not be one node,
and `LLMNode` took no `tools=`, so a fixed model call that also needed a tool had to be split
across two nodes or promoted to an `AgentNode`. **Trajectory `0.24` to `0.25`, manifest `0.26` to
`0.27`, suspension `0.4` to `0.5`.**

- **`over=`, `keep=`, `max_failures=` and `concurrent_items=` are on all three node kinds.** One
  item is one model call for an `LLMNode`, one agent loop for an `AgentNode`, and one call of the
  function for a `Deterministic` node. Every kind returns a `FanOutResult` and collects a failed
  item rather than ending the run.
- **`ItemOutcome` carries `termination`.** An item of an `AgentNode` fan-out that stopped on
  `max_steps` is a success carrying whatever it had, and the record beside it says so.
- **A fanned-out `AgentNode` declares `budget_per_item=` beside `budget=`.** `budget=` bounds
  every item together and `budget_per_item=` bounds one item. `budget_per_item=` on a node with no
  `over=` is refused; a fan-out with neither is refused; a fan-out with one of the two is
  constructed with a warning naming the axis left open, and the manifest's new
  `node_budget_per_item` records it. An item that never ran because the node's total was gone is
  collected as a failed item saying so.
- **`LLMNode` takes `tools=`.** The prompt function reaches them through `ctx.call_tool`, which is
  what a `Deterministic` node already did. A tool taking a `ModelHandle` is refused, as it is
  there.
- **A model call records which fan-out item it belongs to.** `item_index` is on every `model_call`
  record and on every cassette entry, and a call's seed derives from it and from the call's
  position within that item. An `AgentNode` numbered its calls in the order they were made, so a
  fan-out whose items overlapped seeded them by how the threads interleaved and a re-run missed
  the cassette. **Every fan-out's seeds move**, so a cassette holding one is re-recorded.
- **A retried fan-out asks again rather than re-sending.** Numbering a call by its item's index
  meant both attempts sent one seed, so they were one cassette entry: the recording held the
  failure that caused the retry and a replay served it again. A retried node that does not fan
  out has always had a fresh number for each attempt.
- **A fan-out stopped part-way through keeps what each item was holding.** The suspension file
  carries the finished items and the state of the ones still running, so a resume continues them
  rather than running them again and re-making the calls they had made. One suspension asks one
  question: the lowest item that stopped is answered, and the rest ask on the next resume.
- **`ctx.call_tool` takes the tool's name positionally.** A tool with a parameter called `name`
  could not be called through it.

### A model reads what the end user answered, 2026-08-18

`options` on a consultation decide how an answer is read, and the rule that read them compared
the whole answer against the whole option. That reads no option out of a sentence: measured over
24 answers written by `SimulatedEndUser`, it read 0, so every consultation routed to `unmatched`
and the branches under `chose` were never taken. **Trajectory `0.23` to `0.24`.**

- **`consult(read=...)` reads an answer with a model.** `ModelReader(model=cheap)` is the
  shipped one, and it takes the client that reads answers rather than the one the agent runs on.
  It returns the option the answer meant, or `None` where it meant none, which is what an answer
  stating a condition is. `match=` and `read=` are two rules for one job, so a tool takes one.
- **The reading is one recorded call.** It is made once per answer, wherever that answer first
  arrives, emitted as a `model_call` whose parent is the `consultation`, charged to the run's
  budget, and served from the cassette on a replay, so k rollouts pay for one reading. The cost
  is the agent's: a reader ships with it, unlike the stand-in that plays an end user.
- **`read_by` on a `consultation`** says what decided `chose`: `rule`, `model`, or `null` where
  nothing did.
- **The reader is not part of the tool's `version`**, so an edited prompt misses on the
  reading's own model call and leaves every recorded answer where it is. What the run used is on
  the tool's manifest entry, as the model and a digest of the prompt.
- **`instructions` is the prompt and `attempts` bounds the retry.** A model naming something
  that is not an option is told what was wrong and given the list again. A reader that has used
  its attempts ends the run, and the consultation is recorded carrying the answer, a `chose` of
  `null` and the failure.
- **A `Deterministic` node can carry this one model call.** Its function is still handed no
  client and a tool it calls may still take no `ModelHandle`. A node that asks a person and
  branches on the answer is routed by how that answer is read either way.

**What a project has to do:** nothing, unless it registers `consult(read=...)`. `read_by` is
`null` on every record written by an earlier version.

### A condition a model or a person decides, 2026-08-18

Some conditions on an answer cannot be decided by code, and nothing recorded a decision a model
or a person made about one. A judge written into a scoring rule would have called a model on
every rescore and in CI, which no offline evaluation can do. **Results file `0.16` to `0.17`.**

- **`Judged()` is registered in place of a check** for a condition code cannot decide. The
  condition's text is the question and the answer is the material. `Scoring.judgement(question,
  over=...)` is the same seam for a figure that is not a condition on the answer key.
- **A judgement is made first and read at scoring time.** `suite.judge(run_dir=..., using=...)`
  hands a pass the whole worklist and takes back a `Label` for each; `run(..., judge=...)` does
  the rollouts, the judging and the scoring in one call; `suite.unjudged(...)` is the worklist
  for a person. **No scoring rule ever calls a model** (`docs/evaluation.md` §12).
- **A judgement is keyed on what was judged**, a digest of the example, the question and the
  material. The k rollouts of one example that produced the same answer are judged once, and an
  answer that changed has no judgement rather than an older answer's.
- **Two files.** `evals/judgements.jsonl` is the store, appended to and never rewritten.
  `runs/eval_<id>/judgements.jsonl` is what one evaluation used, so `rescore` reproduces the
  numbers that evaluation reported however the store has moved since.
- **The results file records what a figure rested on**: `config.criteria[id]` gains `decided`,
  the deciders and their counts, the judging runs and a digest, and `config.judgements` carries
  the same over every judgement any figure used. `compare()` withholds its verdict when either
  moved, as it does for a moved `matches`.
- **Scoring refuses between the rollouts and the numbers** where a judgement is missing, naming
  every answer waiting and the calls that judge and score them. The rollouts are already
  recorded, so nothing that was paid for is lost.

**What a project has to do:** nothing to its code, unless it registers `Judged()`. As with
every results-file bump, `EvalResults.read` refuses a file written by an earlier version, so a
comparison against one needs that evaluation re-scored: `suite.rescore(run_dir=...)` produces a
`0.17` file from rollouts already on disk without running anything.

### A condition the answer said nothing about, 2026-08-17

An answer key that is a list of conditions could say a condition was met or unmet, and an unmet
one covered two different results: the answer got it wrong, and the answer said nothing there.
Inside a record those are the two failures FT-10 exists to separate, so an agent that left a
field empty was measured as one that invented a value for it. **Results file `0.15` to `0.16`.**

- **A criterion's check may return `Unknown`**, meaning the answer asserted nothing about that
  condition. `True` and `False` keep their meanings, and `matches` still takes neither.
- **An absent condition is unmet**: no credit, and its weight stays in the denominator, so
  leaving a condition alone does not raise the grade.
- **An answer that met none of its key by saying nothing is `missed`**, not `false_confidence`,
  so a field left empty is not measured as a field invented. One that met part of its key, by a
  value or by a silence a condition declared `expects_absence` for, is `partially_correct`.
  `required` decides that an answer is not partly right; what it asserted decides which failure
  it was.
- **`verdict.parts` holds `True`, `False` or `None`**, with `verdict.wrong` and `verdict.absent`
  beside it. A results file written at `0.15` is refused by its version, so re-run the
  evaluation rather than reading the old file.
- **`node_matches` refuses a return that is not a bool**, as `matches` already did. It coerced
  with `bool()` before, so a check written for `criteria=` and reused there recorded the node as
  having answered wrongly instead of naming the mistake.
- **`results.criteria[id].absent`** counts how many rollouts inside the figure said nothing about
  that condition, and `report()` prints it.
- **`Criterion(expects_absence=True)`** declares that the right answer to a condition is that
  the value is not there, and silence meets it. Absence on both sides is read by the library
  per condition as it already was for a whole answer, so one registered check serves the
  example whose document states the field and the example whose document does not. **FT-04
  reads it**, so a project whose absent cases are single empty fields satisfies that gate with
  the examples it has. Adding the field changes the encoded form of every criterion, so an
  example set carrying one has a new `content_hash`.
- **`s.criterion_id`** names the condition a check is deciding, for one function registered
  under several.

### The end user an evaluation answers with, 2026-08-17

A stand-in was given a description of a person and nothing else, so an example whose right
answer depends on a value that person holds was unreachable in every rollout: measured against
`gemini-3.1-flash-lite`, a cost centre absent from the description was supplied 0 times in 5 and
one written into the description 5 times in 5. **Trajectory `0.22` to `0.23`, manifest `0.25` to
`0.26`, results file `0.14` to `0.15`.**

- **`Example.end_user` takes an `EndUser`**, carrying the description and `knows`, a `Fact` per
  thing that person holds. A `Fact` carries what they know in words, the same thing as `value`
  for a scoring rule to compare against, and `disclose`.
- **`disclose` is `volunteer`, `on_ask` or `hidden`.** A `hidden` fact is never put in front of
  the model and reaches a run through the answer key, which reads it off `s.example`.
- **A plain string still works and still stores as a plain string**, so no existing example
  set's `content_hash` moves. **`example.end_user` is an `EndUser` after construction**
  whichever form it was given, which breaks code comparing that field to a string.
- **The stand-in answers each question with what it already answered in that rollout in front of
  it**, and is told that record is complete. Asked to confirm a choice the person never made, one
  that could not see its own replies agreed 3 times in 3 and one that could refused 3 times in 3.
- **The seed for an answer derives from the question** rather than from how many came before it,
  so two runs at one seed answer one question the same way whatever order they arrived in. The
  counter it replaces was also incremented without a lock.
- **`SimulatedEndUser(instructions=...)`** replaces the prompt, for an answerer who is not a
  person, and is part of the evaluation's identity. The reply format and the rule about what was
  already said are appended by the library.
- **`consult(reaches=...)`** names which answerer a tool asks, and `EvalSuite.run(end_user={...})`
  and `RunEnvelope(end_user={...})` take one per name. The manifest tool entry and every
  consultation record carry it.
- **`declared_choice` on a consultation** is the option the channel itself said its answer was,
  and never routes the run. `per_node.consultation_misreadings` counts where it and the tool's own
  rule disagree, which is what reports a `match=` rule that reads none of the answers a run
  produces.
- **`RolloutOutcome.unanswered_consultations`** counts the questions the end user declined or was
  not there for. No outcome is reclassified.
- **A consult tool may be listed in `concurrent_tools`** where its channel declares
  `may_suspend = False`, which `SimulatedEndUser` and `unattended()` do. The refusal it replaces
  was made when the node was built, before the channel that answers is known.

### What elicitation asks about the answer, 2026-08-17

Four answer keys shipped and no question a builder is asked reached them. **Stage `shape` asks
eight questions rather than six, all required, so a project fails FT-24 until it answers the two
that are new.** No format moved.

- **`judged_steps`** asks whether any step inside the run has its own right answer, which is what
  `Example.expected_by_node` and `EvalSuite(node_matches=...)` are for. Naming none is an answer.
- **`judged_path`** asks whether it matters how the agent reached an answer, which is a criterion
  whose check reads `s.trajectory`.
- **`answer_form` is the answer key question**, offering one value, any of several, a collection, a
  quantity within a tolerance, or a set of conditions. `presentation` keeps the output form, and
  the two are different answers.
- **`ground_truth`** asks which answers the builder would accept rather than what the answer is.
- **`absence_vs_error`** weighs a wrong answer against a missing one and against one that is partly
  right, which is the outcome `Criteria` and multi-value `Contains` made reachable.
- **A scaffold may reach one answer through several exchanges**, stated in the `Question`
  docstring, in `docs/procedure.md` and in what `simple-agents questions` prints. The brief records
  one answer per question whatever it took to get there.

### An answer key that says what it is, 2026-08-17

An example's `expected` took one value, a comparison returned one boolean, and an answer that was
partly right was recorded as a confident wrong value. **Results file `0.13` to `0.14`.**

- **Four answer keys.** `AnyOf`, `Contains`, `WithinTolerance` and `Criteria` sit in the `expected`
  position and encode as tagged objects, so an example file holds them and `content_hash` covers
  them. A key says what the right answer is and never how to compare two values.
- **`Criteria` is a list of conditions**, each judged yes or no, each carrying a weight and whether
  it is required. The criterion is data in the example file and its check is code registered on the
  suite under the criterion's id, so one check serves every example naming it and its version is
  recorded beside `matches`.
- **`Outcome.PARTIALLY_CORRECT`**, for an answer meeting part of its key. A rollout carries the
  verdict that decided it: the grade, the counts, and each condition's own result. An answer that
  missed a required condition is `false_confidence` whatever else it met.
- **Eight rates rather than six**, adding `graded_accuracy` and `partially_correct_rate`.
  `false_confidence_rate` no longer counts a partly right answer, and `precision_when_asserting`
  holds one in its denominator and not its numerator.
- **A figure per criterion**, in `results.criteria` and in `comparison.criteria`, with its own
  interval and its own n.
- **Every scoring rule takes one `Scoring`.** `matches`, `node_matches`, a criterion's check and
  `ProjectMetric.score` all receive the answer, the value being compared against, the example, and
  where the run was recorded. **This replaces `matches(predicted, expected)` and
  `score(predicted, expected, rollout)`**: a two-argument matcher and a three-argument score both
  have to be rewritten as `lambda s: ...`, reading `s.answer`, `s.expected`, `s.example` and
  `s.trajectory`.

### The design the builder agreed to, 2026-08-16

The question set is a floor rather than the script, and how the agent will be built is an artifact
rather than a conversation. **Sixteen checks, 34 taxonomy entries.**

- **`design.md`**, written at stage `shape` beside `idea.md`. Three sections: what it does step by
  step, what it holds on to between runs, and what the builder said about it. The first two go to
  the builder before the code is written, and what comes back goes under the third in their own
  words.
- **FT-34** reads it from stage `shape`: the three sections are there and filled, the third carries
  a quotation, and the brief's `design_confirmed_at` names the stage the project is at. **A
  quotation is a shape, not a fact**: this reads whether something is quoted, never whose words are
  in it.
- **A `shape` or `presentation` decision records `from`**, naming the brief entries it was derived
  from, and the report prints the complement: the answers about what the builder wants that no such
  decision names. `docs/conformance.md` §3.4.
- `docs/procedure.md` says the library supplies a floor rather than the script.

### The brief against the code, 2026-08-16

Three checks that read a brief answer against what a run recorded, and a note that fires when the
pipeline moves rather than when a gate is reached.

- **FT-25's check is registered.** The entry has specified one since the first draft and
  `checks.py` never carried it, so an elicited consultation capability could leave the graph with
  the brief entry still recording the builder's answer. Where the `consultation` answer names
  something to ask, a consultation tool must be registered and given to a node. An answer opening
  on a negation says there is nothing to ask and passes.
- **FT-32, the brief describing a pipeline that no longer exists.** Every side-effect class the
  run's manifest declares appears in the `tool_effects` answer. Tool names are not read: a builder
  describes a tool in their own words.
- **FT-33, the build log stopped before the work did.** Where a project keeps a `BUILD-LOG.md`, it
  was written no earlier than its newest run started. A project keeping none passes.
- **`confirmed_against` in the brief**, holding the `behaviour_fingerprint` its entries were last
  read against. Where the newest run recorded a different one, the report names the entries that
  describe the pipeline and are due for re-reading. It reports rather than fails.
  `docs/conformance.md` §3.4.

### What the end user reads, 2026-08-16

What a project keeps for the end user outlives the run that wrote it, and no later version of
the pipeline goes back and rewrites it. **Manifest `0.24` to `0.25`.**

- **`Pipeline.behaviour_fingerprint()`** covers everything that decides what a pipeline
  produces: the shape, every prompt's version, sampling, tools, the declared model and the
  budgets. A project writes it beside each stored result, so a result an older pipeline
  wrote is a query rather than a guess. `Pipeline.graph_fingerprint()` is shape alone and
  does not move on a prompt edit, which is what a project stamping with it could not see.
- **The manifest records it**, under `behaviour_fingerprint`, so stored results and the runs
  that produced them join on one value.
- **A `ship` question, `stored_output`**: what the end user reads, what writes it, and where
  it accumulates, what refreshes a result the current pipeline did not produce.
  `docs/shipping.md` §6 is the whole of it, and `docs/failure-taxonomy.md` §10 records that
  no check opens the artifact.

### The `ship` stage, 2026-08-15

A fifth stage, after `measure`, for the point where somebody other than the builder starts using
the agent. `docs/shipping.md` is the new document and `docs/procedure.md` stage 5 is when to read
it. **Manifest `0.23` to `0.24`.**

- **A run says whether an end user was on the other end.** `RunEnvelope(live=True)`, or
  `env.with_live()` from an envelope configured once, and `runs("runs/", live=True)` reads them
  back. The manifest records `live`, and nothing infers it. A run of anything other than the
  agent cannot be live, so `RunEnvelope(role="labelling", live=True)` is refused, and an
  evaluation's rollouts are never live whatever envelope they came from.
- **The conformance checks read the runs that are not live.** Where every run under `runs/` is
  live the newest is read anyway, and the report says which it was.
- **The tier decides which stages a project has.** `prototype` has `brainstorm`, `shape`, `build`
  and `ship`; `evaluated` and `trained` add `measure`. **A brief declaring `stage = "measure"` at
  tier `prototype` is now refused**, and so is an entry `deferred_to` a stage that tier never
  reaches. A results file no longer moves a `prototype` project to `measure`, so the elicitation
  gate stops asking for the measurement questions in the same report that says the measurement
  checks do not apply.
- **Four questions at `ship`**, three of them required: `someone_there`, `live_records` and
  `watching_live`, with `unevaluated_effects` optional. `simple-agents questions --stage ship
  --tier prototype` prints a project's own set, and `--tier` drops the stages that tier does not
  have.
- **FT-31, `Shipped on a development channel`.** It reads the consultation channel's
  `answered_by` off the run's manifest, and off a live run's consultations where the project has
  one, and fails a shipped project on `coding_agent`, `simulated`, `canned` and `builder`.
  `end_user` and `nobody` pass. **It is the first check gated on a stage rather than on a tier**:
  a taxonomy entry may now carry `· Stage: ship` on its surface line, and reports `--` until the
  project reaches it.
- **The manifest records the channel a run was given.** `end_user` holds the `answered_by` of a
  channel supplied through `RunEnvelope(end_user=...)`, and is `null` where the run used the one
  the pipeline registered. The `tools` entries still carry what the pipeline declared.
- The report's last line no longer names the tier, since a check can now be inapplicable for two
  reasons and each check's own line says which.

### Dogfood #4's cheap fixes, 2026-08-15

Four surfaces that read as working and were not. No format moved.

- **A node the run routed around no longer fails FT-07.** It records `seed: null` because it did
  not execute, and `termination` of `skipped` is what says so. Reading it as an unseeded node left
  a project two ways to pass and the cheap one was to stop routing around the node, which cost
  1,584 model calls in a single evaluation arm.
- **`LLMNode(over=..., retry=...)` with no `max_failures` is refused.** A failed item is collected
  rather than raised, and a retry re-executes a node only when the node raises, so the retry could
  never fire. Pass `max_failures=0` to make the first failed item raise, or drop `retry=` and read
  the failures off the result.
- **A `consult` tool's version no longer covers the library's own function.** It is derived from
  the project's channel and matcher alone, so upgrading the library no longer makes every recorded
  consultation miss. A channel with no readable source, such as one built by `functools.partial`,
  now derives no version rather than one hashed from library source; pass `version=` to declare
  one.
- **`progress_of` and `RolloutProgress` are exported from `simple_agents`**, and
  `docs/evaluation.md`'s "What to reach for" table has a row for watching an evaluation from
  another terminal. They were importable and in no `__all__`, so nothing reading the surface found
  them.

### Who answers a consultation, 2026-08-15

A consultation recorded what happened to a question and never who answered it, so 97 questions
answered by a fixed string and 97 answered by people produced the same records and the same
rates. And a run with nobody at the other end had no answer but a refusal, which reads as an
end user who would not say.

#### Who answered

- **A `consult` channel declares `answered_by`**, one of `end_user`, `builder`, `coding_agent`,
  `simulated`, `canned` or `nobody`, and a channel that declares none is refused. It is recorded
  on every `consultation` and on the tool's manifest entry. `docs/tools.md` §4.6.2.
- **A channel declaring `coding_agent` also declares `permission`**, the builder's own words
  agreeing that the coding agent may answer as the end user on an unattended run. It is recorded
  in the manifest.
- **`per_node.consultation_answered_by`** counts them beside `consultation_resolutions`, so
  `answered: 97` in a results file carries `canned: 97` next to it.
- Trajectory format **0.22**: `consultation` gains `answered_by`, `reason` and
  `answered_by_model`. Manifest **0.23**: a tool entry gains `answered_by` and `permission`.
  Results file **0.13**: a node gains `consultation_answered_by`.

#### Nobody to ask

- **A channel returns `Unavailable(reason=...)` where there is no one to ask**, recorded as
  `resolution: "unavailable"` with the reason beside it. It is a different event from
  `declined`: declining is a choice and being unavailable is the absence of one.
- **`unattended()` is a shipped channel that returns nothing else**, for smoke runs, sweeps and
  fake runs. The model is told once and every later question to that tool is answered from that
  without the channel being reached again, and each one is still recorded.
- **`on_reply` requires an `unavailable` branch**, waivable with `exhaustive=True` alongside the
  other two.
- Trajectory format **0.22**: `resolution` loses `timed_out` and `defaulted`, which nothing
  produced, and gains `unavailable`. A project reading the enum drops the two.

#### Who a run asks, and who an evaluation asks

- **`RunEnvelope(end_user=...)` and `env.with_end_user(channel, answered_by=...)`** replace the
  registered channel for one kind of run without the pipeline being rebuilt. The manifest keeps
  the registered declaration and each consultation records what actually answered.
- **`ask_on_stdin` ships**, a channel that prints the question and reads the answer. It declares
  no answerer of its own, since a terminal is the builder's while a project is being built and
  the end user's once it ships.
- **`EvalSuite.run(end_user=SimulatedEndUser(model=...))` answers an evaluation's consultations
  with a model playing the end user**, described by `Example.end_user`. Each rollout gets its
  own, seeded from the rollout's seed; the answers are stored in the cassette with the rest of
  the run; the calls go to their own model and stay out of the node's own counts, with what each
  one spent on the consultation record. `EvalSuite.record` takes the same argument.
  `docs/evaluation.md` §5.4.
- **An example with no `end_user` description is refused** before the first rollout, where the
  pipeline can consult and a stand-in was given.
- **Which model played the end user is part of the evaluation's identity**, so two evaluations
  differing only in that write to different directories.

### The full-test checkpoint of 2026-08-13

A pre-release QA pass inventoried every claim in the fifteen shipped documents and tested them
with real pipelines against real backends. What it found is below, grouped by what a project
would notice.

#### Secrets, and replaying a run that had one

- **A tool declares `redact_result=True` where its result carries a credential.** The result is
  redacted before the model reads it, so what the run used and what the cassette stored are one
  string and the recording replays. Without it the model read the value, the file held a marker,
  and every model call built on that result missed on replay. Keying on the redacted form cannot
  close this: a pattern replaces a substring and a field name replaces a whole value, so the two
  sides never produce the same string.
- **`Redaction.at_boundary` decides which rules apply there**, and defaults to every rule that
  matches a credential: `("secret_env", "sensitive_keys", "builtin")`. It takes rule kinds,
  individual rule names, or both. A name that is neither a kind nor a declared rule is refused at
  construction.
- **A rule outside `at_boundary` redacts the trajectory record and leaves the value in the
  cassette**, for a declaring tool alone. That is what a replay costs: the cassette holds what
  the model was given, because a recording holding anything else serves a different string back
  and the call after it misses. A project's own `patterns={"employee_id": ...}` therefore keeps
  an employee id out of the trajectory, lets an agent that has to act on one read it, and leaves
  it in that tool's cassette entry. Naming the rule in `at_boundary` removes it from all three.
- Manifest format **0.22**: `redaction` gains `at_boundary`, so what the model was shown of a
  tool result is on file with the rules that were in force.

#### Stopping and resuming

- **A stop names the node by the id every other surface uses.** `stop.stops[i]["node_id"]` for a
  node inside a pipeline used as a node was the bare leaf, `ask`, while the trajectory, the
  manifest and per-node metrics all said `research.ask`. Two nested pipelines each holding a node
  of that name produced indistinguishable stops. Both `stop.stops` and the `answers=` a resume
  takes now use the qualified id.

#### What a run reports it spent

- **A tool that reports a price it was told says so.** `SpendMeter.spend` takes `source=`, which
  defaults to `measured` and is what the record says the figure is. The shipped `web_search` takes
  a meter so a cache hit can report nothing, and the amount it reports is its `declared_cost`, so
  its live calls now record `source: "declared"` rather than claiming a measurement.
- **`totals.tool_spend.currency` comes from the tool spend.** It was taken from the accumulated
  model `Cost`, so a pipeline of `Deterministic` nodes calling a paid tool reported an amount with
  no unit. `Recording.currency` falls back to the run's cost currency for the same reason: `spend`
  is model calls and paid tool calls together, so it has a unit whenever either was priced.
- The results file is `eval_format_version` **0.12**: each node's entry gains
  `tool_spend_currency`.

#### Failing once rather than k x n times

- **A node reached without a model client raises `ConfigurationError`.** It was a bare
  `CallerFacingError`, the parent class, which an evaluation classifies as an agent failure
  rather than as a fault that fails every rollout the same way. `Pipeline.run` refuses this
  before the first node starts, so an evaluation met the pre-run refusal rather than this one;
  the node-level message is the fallback for a node executed on its own.

#### Budgets

- **`max_steps` is exact on every path.** A node in a declared `concurrent_nodes` group ran
  whether or not a step remained, at every concurrency, because the budget was consulted between
  batches and never inside one: eight arms made eight calls under `max_steps=1`. An embedding or a
  rerank inside a search was charged after the call, so a node that searched was unbounded when
  nothing ran after it. The step is now reserved before the call is dispatched and held until it
  is charged, under the run's lock, so two calls that overlap cannot both claim the last one.
  **A branching pipeline under a tight `max_steps` now stops partway through its arms rather than
  completing them.**

#### Resuming a run that stopped

- **A refused resume no longer destroys the suspended run.** `resume()` discarded its claim before
  the checks that can refuse had run, so a typo in `answers=`, one `answer=` for a run that stopped
  in several nodes, or a state file this version cannot read deleted the run the refusal named.
  The checks now run while the claim can still be put back.
- **`resume(answer=...)` reaches every node kind.** A `Deterministic` node holding `consult` called
  the channel again and suspended again, so a run written the documented way could never finish.
  A node inside a pipeline used as a node was handed nothing and recorded the consultation
  `declined`; the answer now reaches it.
- **A run that stopped in several nodes records all of them** in the manifest's `suspensions`,
  each with its own `waiting_for`, and a resume closes every open entry.

#### Evaluation

- **`eval_id` now separates evaluations that measured different things.** It digests the sampling
  parameters, tools, `allow_unknown`, context builder, route, finish check, fan-out and budgets of
  every node, and the budgets of the pipeline and of every pipeline used as a node, on top of the
  shape, prompts, examples, seed, split, k and model it digested before. Two pipelines differing
  only in a temperature, a tool or a budget wrote into one directory and now write into two, so
  `compare_variants` runs a sampling-only arm, `resume_from` refuses rollouts from another
  configuration, and `rescore` does too, naming the fields that differ. `graph_fingerprint` is
  unchanged: it stays a digest of shape, which is what a resume needs.
- **A rollout the backend never answered is `no_response` rather than `failed`.** A model call that
  raised before returning a response, or a replay holding no answer for a call the run made. Those
  rollouts leave every rate's denominator, and each metric carries `no_response`, the count it left
  out, printed beside every figure in `report()`. A suite running against a model id a provider has
  retired reported `failure_rate` 1.0 with complete intervals, and now reports `undefined` with the
  count.
- **A suspension propagates out of an evaluation.** `RunSuspended` reaches the caller from
  `suite.run` and `suite.record`, rather than being scored as a failed rollout.
- **A configuration error ends the evaluation on the first rollout** instead of being recorded
  k x n times.
- **`resume_from` runs on the default recording path.** The evaluation's own cassette is continued
  rather than recorded over, which the documented call in `docs/evaluation.md` §6.5 was refused for.
- **`compare_variants` names the arm** when a sweep resolves to a directory that already holds
  rollouts, with how many arms have already been paid for.
- The results file is `eval_format_version` **0.11**: `Outcome` gains `no_response` and each metric
  gains `no_response`. Re-run an evaluation to produce a file this version reads.
- **The whole evaluation surface is exported from `simple_agents`.** `EvalSuite`, `Example`,
  `ExampleSet`, `compare`, `compare_variants`, `ablate`, `EvalResults` and the rest were reachable
  only from `simple_agents.evaluation`, so a coding agent reading the package saw no evaluation at
  all.

#### Retrieval and tools

- **A default English stopword list ships**, and `stopwords=` replaces it, `stopwords=()` disables
  it. Without one, BM25 gave nearly every document a vote through words like `the`, and rank-based
  fusion cannot tell a strong score from a weak one, so the default ranking returned the answer to
  a paraphrased question in its top five once in six times where semantic search alone returned it
  five times. Measured again over MS MARCO and Natural Questions before the list was chosen.
- **`ranking=` is required wherever `embeddings=` is passed.** Passing an embedding client is a
  capability declaration and silently chose a ranking as well. The refusal names the four rankings
  and what each is for.
- **A tool parameter's `Field(description=...)` reaches the model, and its constraints are
  enforced.** `Annotated[int, Field(description=..., ge=1, le=10)]` was discarded before the schema
  was built, so the model saw a bare integer and `top_k=400` passed validation.
- **A `web_search` answered from its cache is not charged.** It is declared `SPENDS_MONEY` and took
  no meter, so a cache hit recorded the full declared price and `max_cost` stopped a run early.
- **`contains_normalised` folds accents.** A grounding check on an accented name returned a false
  negative.
- **`consult()` derives a version from its source**, the way a decorated tool does. Its cassette
  key carried a null version, so two consult tools with different channels were indistinguishable
  in a recording.
- **`on_reply(field=...)` finds the reply on a mapping, or refuses.** Over a dict it found nothing
  and took the `declined` branch without saying so.

#### Adapters, cost and the manifest

- **A `Retry-After` header decides the wait** whether it is longer or shorter than the backoff, and
  an HTTP-date is read as well as delta-seconds.
- **A call that exhausted its retries carries what it waited**, read with
  `simple_agents.models.held_back_ms_of`. A run ended by a rate limit reported none of the time it
  spent waiting.
- **`PacedClient.waits` counts the calls that were held back**, not the sleeps.
- **`OpenAIEmbeddings` records an unmeasured cache count as `unknown`** rather than `0`, and a call
  batched into several requests sums every token class rather than only the uncached one.
- **`totals.charged_cost` no longer adds device-seconds to money.** Under a `DeviceBasis` it is the
  run's tool spend, and under a basis pricing some models in each unit it is `null`.
- **`Manifest.restore` restores every record type's count.** A resumed run understated
  `counts.delegation` and `counts.records`.
- **A cassette miss caused by a redacted value re-entering a request says so.**

#### The command line and the conformance suite

- **`simple-agents init` writes a pointer to the path the skill actually went to.** The note was
  one constant, so `--claude` and `--to` registered the skill in one place and told the coding agent
  to read it from another. It also wrote no pointer at all when AGENTS.md contained the string
  `simple-agents` anywhere, which the README's own install line supplies. A second `init` now exits
  1 rather than 0 while refusing.
- **`simple-agents questions --stage` knows about `brainstorm`**, which ships 13 questions of which
  8 are required.
- **FT-04's message names the results file**, which is what the check reads.
- **FT-29 accepts the `idea.md` heading the documents actually write.** It required a comma that
  appears in no document, so a project following `docs/procedure.md` failed the check.
- **Five counts that disagreed with the list printed beside them** are pinned to what they count,
  including FT-13's "the four are" beside five record types and the README's 28 taxonomy entries
  beside 30.

#### Refusals gained

- **A `Join` in a pipeline's node list is refused at construction**, naming what a `Join` is, rather
  than failing at run time with `AttributeError`.
- **`Cost.plus` reports a sum across two units as unknown**, naming both.

#### Drawing and documentation

- **`to_mermaid()` labels a node declaring `suspend_before`.**
- **An embedding made from a `Deterministic` node is parented to the tool call** that made it, so a
  trajectory says which search spent which tokens.
- Roughly forty statements across the shipped documents were corrected against what the library
  does. The largest groups: `docs/pipeline.md` on what the `graph_fingerprint` covers,
  `docs/trajectory-format.md` and `docs/run-envelope.md` disagreeing on whether
  `max_wall_clock_ms` is charged for waiting, the tool-call cassette key, `docs/evaluation.md`
  §8.1's sample report printing an interval the library cannot produce, and `docs/retrieval.md` on
  `top_n` and on which embedding adapters resolve their own revision.

### Added

- **Work in a run can overlap, where it is declared to.** Nothing overlaps until something says
  it may, and `Pipeline.run(concurrency=N)` is the most calls the run may have in flight:

  ```python
  pipeline = Pipeline(
      [plan, read_specs, fetch_reviews, report],
      budget=budget,
      concurrent_nodes=[["read_specs", "fetch_reviews"]],
  )
  pipeline.run(inputs, envelope=env, model=client, concurrency=8)
  ```

  Three things can be declared: `concurrent_nodes` on the pipeline, as groups where two nodes
  overlap when a group lists both; `concurrent_items=8` on an `LLMNode` with `over=`; and
  `concurrent_tools=[search, fetch]` on an `AgentNode`, for the calls the model asks for in one
  turn. A `WRITES` tool is refused there, because a run has one workspace directory and every
  node is handed the same one. `docs/pipeline.md` §1.10.

- **A stop drains.** Work already running finishes, is recorded and is charged; work not yet
  started does not start. One rule for a budget axis exhausted, a node stopping to ask someone,
  and a node raising. `max_steps` is exact under it, because a step is taken before its call.
  `docs/pipeline.md` §1.11.

- **A run can stop in more than one node at once**, and is continued with `answers` keyed by
  node. `RunSuspended.stops` says which nodes stopped and what each is waiting for.
  **Suspension format `0.3` to `0.4`**: a suspended run is a tree rather than a stack, since a
  level where two arms stopped has two ways down from it.

- **`DeviceBasis` reports what a self-hosted run used, with no rate.** For a device the project
  already owns, where no hour is billed to anyone:

  ```python
  DeviceBasis(device="RTX-3090", device_count=1)
  ```

  A call is charged `duration × device_count ÷ concurrent_requests`, reported in
  `device_seconds`. That is a unit rather than a currency, so it fixes no currency for the run
  and `max_cost` is refused against it, naming `max_wall_clock_ms`. `docs/run-envelope.md` §4.1.

- **`EvalSuite.run(run_concurrency=...)`** is what each rollout's own run may overlap. An
  evaluation issues `concurrency × run_concurrency` calls at once and paces for that.
  `docs/evaluation.md` §6.2.

- **`FakeModelClient(answer=...)`** answers from the request rather than from a queue, which is
  what a run whose calls overlap needs. A scripted list called from two places at once is
  refused rather than answering the wrong call.

### Changed

- **`max_wall_clock_ms` is elapsed time while the run is executing**, not the sum of what each
  call took. A run whose calls overlap is charged the time that passed. Time spent waiting to be
  allowed to call now counts, so a run held behind a quota for forty seconds is charged those
  forty seconds; time spent suspended still counts for nothing. The per-node `wall_clock_ms`
  figures in the trajectory are unchanged, so a run's total is less than their sum once calls
  overlap. `docs/pipeline.md` §5.

- **A tool call's cassette key carries the node it was made in**, and its occurrence counts
  within that node rather than across the run. One node's recorded calls now survive an edit to
  another's. **Every cassette holding tool calls needs its keys recomputed**, which
  `scripts/rekey_tool_calls.py` does from what the file already holds, with no backend call.
  `docs/tools.md` §3.1.

- **The manifest records `concurrency`**, the most calls the run could have in flight. Manifest
  format is unchanged: the key is additive.

### Fixed

- **The manifest lost counts when several threads wrote into it.** `count_record`,
  `observe_model`, `observe_tokens`, `count_cassette` and `observe_held_back` each read a number
  and wrote it back with nothing guarding the pair, so a run reported fewer calls and fewer
  tokens than it made. Token totals feed cost, so the figure was low with nothing raised. This
  was reachable before concurrency shipped, through an evaluation's rollouts.

- **A trajectory could be written out of `sequence` order.** The number was taken when a record
  was built and the file was written afterwards, so two records written from different threads
  could be numbered in one order and land in the other. The number is now taken inside the lock
  that orders the file, so `docs/trajectory-format.md`'s "read line by line is already in order"
  holds however many threads are writing.

- **An ablation dropped the pipeline's concurrency groups.** Every other constructor argument
  travelled to an arm and `concurrent_nodes` did not, so an arm ran one after another what the
  baseline ran at the same time, which is a second difference in a comparison meant to hold
  one. Groups now travel, narrowed to the nodes the arm still has, and a group left with fewer
  than two members is dropped. `compare_variants` also takes `run_concurrency`.

- **The unpaced-wait warning recommended a wrapper that does nothing on some backends.** It
  named `PacedClient` whatever the response said. A backend that publishes no rate-limit
  allowance has nothing to pace against, so wrapping it leaves every call as it was; measured
  against Gemini's free tier, the wrapped arm paced zero times and answered fewer items than the
  unwrapped one. The warning now reads the response and names `concurrency=` and
  `concurrent_items=` where there is no allowance to pace against.

- **`VectorScan` could file a vector under another document's identifier.** The identifiers and
  the vectors are one table in two lists and were extended separately, so two writers
  interleaving mispaired them: retrieval returned the right scores against the wrong sources.
  Both `add` and `search` now hold the table. A store supplied by the project is the project's
  to make safe.

- **Two nodes embedding at once each loaded the model.** The lazy build in
  `SentenceTransformerEmbeddings` and `LocalCrossEncoder` had no guard, and two copies of one
  model on one device is how a load that fits runs out of memory.

- **Two writers of one key shared a scratch file**, in `MemoryStore.write` and in
  `UrlCache.put`. Both staged into a path derived from the key alone, so two writes of one key
  could interleave and leave a partial entry. The scratch name now carries the writer.

- **A consultation answer says which option it was.** `consult` returns a `Reply`, a string
  carrying `chose`, and `on_reply` routes on it:

  ```python
  from simple_agents.builtins import consult, on_reply

  Deterministic(
      ask_before_applying,
      tools=[consult(channel)],
      successors=["apply", "amend", "stop"],
      route=on_reply({"yes": "apply", "no": "stop"}, unmatched="amend", declined="stop"),
  )
  ```

  `options` decides how an answer is read and does not constrain what the end user may say. An
  answer matching none of them keeps its text with `chose` set to `None`, recorded as
  `resolution: "unmatched"`, which is distinct from `declined`. `on_reply` requires a branch
  for both unless the offered options are the only outcomes, waived with `exhaustive=True` and
  recorded in the manifest. Pass `match=` to `consult` for a matching rule of the project's
  own. `docs/tools.md` §4.6.1.

### Fixed

- **A function built by a factory is versioned by what it closed over, not by its source
  alone.** `source_version` hashed the source of the returned function, which is the same text
  for every call to the factory, so two routes sending a run to different nodes recorded one
  version and an edit to the mapping was traced to nothing (FT-15). What a closure captured now
  counts too. **What a project does:** nothing, unless it builds a prompt, route, matcher or
  metric with a factory, in which case that entry's `version` in the manifest changes once and
  is stable after. Only captured data whose text its value fixes is counted, so a function
  closing over a client or another function is versioned by its source as before, and a version
  does not move between processes.

### Changed

- **Trajectory format `0.20` to `0.21`.** A `consultation` record gains `chose`, and
  `resolution` gains `unmatched`. **What a project does:** nothing, for a project that reads
  neither. A reader switching on `resolution` gains a case, and one that treated every answer
  as matching its options should read `chose` instead of comparing the text.
- **Manifest format `0.20` to `0.21`.** A node entry gains `consultation_route`, holding what a
  route built by `on_reply` maps and whether it waived its branches. It is `null` for every
  other route. **What a project does:** nothing.

- **A third model client, `GeminiClient`.** A hosted backend beside Mistral, over the
  provider's own API:

  ```python
  from simple_agents import GeminiClient, PriceBasis

  client = GeminiClient(model="gemini-3.1-flash-lite",
                        model_revision="3.1-flash-lite-05-2026")
  ```

  **The price basis needs `input_cache_write_per_mtok=0.0`.** This backend reports no
  cache-write count, so that class is `unknown` on every call, and an unmeasured count with no
  declared rate leaves a call unpriced. A rate of `0.0` prices it exactly, because no value of
  that count changes the total. Without it every Gemini call reports `null` cost and `max_cost`
  never fires. `docs/model-clients/gemini.md` has the rates, the caching, the absence of any
  published rate-limit allowance, and what else this backend does not report.

  **It does not sit on the OpenAI-compatible endpoint that provider also serves.** That
  endpoint refuses `seed`, which every run and every cassette key carries, and reports thinking
  tokens in neither `prompt_tokens` nor `completion_tokens` while billing them: one measured
  call reported 327 output tokens against a charge for 1,446.

### Changed

- **Trajectory format `0.20`.** A tool call on a `model_call` record may carry `provider`,
  holding what the backend sent with that call and requires back on the next request. The key
  is absent where the backend sent none, so a record written by either OpenAI-dialect adapter
  is unchanged and every cassette recorded before this still replays. Gemini refuses the turn
  after a tool call whose thought signature is missing, so an `AgentNode` against it needs the
  value to survive being written down and read back.

  **A project reading `outputs.tool_calls`** gains an optional key on each entry and needs no
  change. **A project holding a hand-written adapter** fills `ToolCallRequest.provider` only if
  its backend sends such state.

- **A token count reported as `unknown` no longer makes a call unpriceable when its rate is
  declared `0.0`.** The count is still recorded as unmeasured, and the price is exact because
  no value of it changes the total. Every other unmeasured count leaves the call unpriced, as
  before (`docs/run-envelope.md` §4.2).

### Fixed

- **An adapter given `http_client=` sent no credentials.** `HTTPBackend` applied its headers
  only to the client it built itself, so a client supplied for a proxy or a custom transport
  went out unauthenticated. Headers are now sent on every request whichever client is used.

- **A cassette could not replay a call whose token count was unmeasured.** An `unknown` count
  was stored correctly and decoded as a plain mapping, so the first sum over the counts raised
  a `TypeError`. It comes back as an `Unknown` now.

### Added

- **A decision the coding agent made, put to the builder before it becomes a fact.** Six kinds
  cover what a build decides on its own: `dependency`, `shape`, `constant`, `prompt_rule`,
  `presentation` and `measurement`. Each is recorded under `[decisions]` in the brief with what
  was chosen, what else was considered, why, and what the builder said:

  ```toml
  [decisions.book_source]
  kind = "dependency"
  status = "agreed"
  chose = "Open Library, with Google Books where a key is configured"
  considered = ["Open Library alone", "a web search over publisher pages"]
  because = "the export carries no descriptions, so something has to supply them"
  ```

  **FT-30 refuses a gate while any decision is `proposed`**, or while one of the six kinds has
  no entry at all; a kind a project has nothing of is `not_applicable`, written out rather than
  left absent. `simple-agents questions --decisions` prints the six. Eleven conformance checks.

  **Three elicitation questions**, 33 in all. `how_far` asks how finished this has to be,
  telling the builder what each stage produces so they can answer, and settles the tier.
  `involvement` sets how much of the rest they are shown and when. `presentation` at `shape` is
  what the output schema is built to serve. Dogfood #3 passed ten of ten having chosen its external catalogue,
  its pipeline, a constant, a prompt rule, a page and its whole measurement alone.

- **An evaluation that stopped part way can be resumed.** `suite.run(resume_from=...)` scores
  the rollouts already on disk without running them and runs only the ones missing:

  ```python
  suite.run(envelope=env, model=client, split="held_out", k=3, seed=41,
            resume_from="runs/eval_a1226bc495df")
  ```

  The directory has to be this evaluation's own, checked by name against the `eval_id` these
  arguments produce, and a rollout that never finished is run again rather than resumed from.
  A dogfood run lost 17 rollouts and $3.23 to a killed evaluation with no way back in.

- **An evaluation can be watched while it runs.** `on_rollout=` is called as each rollout
  finishes, with a `RolloutProgress` carrying what is done, what it cost and what is left.
  `progress_of(run_dir, expected=...)` reads the same from a directory, from another process,
  with nothing of the project imported:

  ```python
  from simple_agents.evaluation import progress_of

  progress_of("runs/eval_a1226bc495df", expected=33)
  # {'finished': 12, 'running': 2, 'done': False, 'remaining_s': 3220.4, ...}
  ```

- **`totals.cost` reports what was measured beside what was not.** `cost.value` is still `null`
  where any node's cost could not be measured; `cost.measured` is what the rest cost and
  `cost.unpriced_nodes` names the ones left out. Results file `0.10`.

- **Per-node `consultation_resolutions`** says how the questions a node asked the end user
  ended, so an evaluation whose channel answered nothing is separable from one measured against
  a person. Results file `0.10`.

- **The conformance report says when the run it read and the results file it read describe
  different measurements.** It fails nothing; both artifacts are real and neither said anything
  about the other.

### Changed

- **An argument the model invents is refused and handed back for correction**, rather than
  reaching the function and raising `TypeError`, which was treated as caller-facing and ended
  the run. This holds however the tool's schema was declared. A function taking `**kwargs`
  receives everything as before and is not checked, which is how a tool absorbs an unexpected
  argument and reports that it ignored it. A declared `parameters=` schema offering a property
  the function cannot receive is now refused when the tool is built.

  The schema sent to the backend is unchanged, and carries no `additionalProperties`.

- **`EvalResults.write` refuses a path that already holds a results file**, as
  `Cassette.record` already did, and called with no path names the file after the evaluation
  under `evals/results/`. Pass `overwrite=True` to replace one. Dogfood #3's baseline was lost
  to a deterministic filename and could not be rebuilt.

- **A search can find a document phrased differently from the query.** `DocumentIndex` takes an
  embedding client and then searches by meaning as well as by words. `document_search` is the
  same tool with the same name, so nothing in a project's tool list changes:

  ```python
  from simple_agents.adapters import SentenceTransformerEmbeddings

  index = DocumentIndex.from_texts(corpus, embeddings=SentenceTransformerEmbeddings())
  registry.add(document_search(index))
  ```

  `pip install 'simple-agents[semantic]'` for a model that runs in the process and needs no
  endpoint. `OpenAIEmbeddings(base_url=..., model=...)` and `MistralEmbeddings()` need no extra.

  **Every part of the ranking is settable**, with the defaults stated as defaults:
  `ranking=` takes `Lexical()`, `Semantic()` or `Hybrid(fuse=..., depth=...)`; `fuse=` takes
  `RRF(k=...)`, `Interleave()` or `WeightedScore(lexical=...)`; `rerank=` takes
  `CrossEncoderRerank(client, top_n=...)` or `ModelRerank(top_n=...)`; and `vectors=` takes a
  project's own `VectorStore` where the default in-memory scan is not enough. Where the defaults
  came from, and what they cost, is `docs/retrieval.md`.

  **`DocumentIndex.save` and `.load`** write the corpus and its vectors to one file, so a corpus
  is embedded once rather than on every process start.

  **`memory_search(embeddings=...)`** does the same over the agent's own memory. Each fact is
  embedded once and the vector is stored beside it, so a search embeds the query alone.

  **An embedding or a rerank is a model call**: a `model_call` record parented to the tool call,
  charged to the run's budget, keyed into the cassette, and read by FT-14. A search that makes
  one is re-run during a replay and its model calls are served, the way a tool taking a
  `ModelHandle` already was. A purely lexical search is unchanged and is still stored as one
  cassette entry.

  **Declare a cost basis per model.** An embedding model is one to two orders of magnitude
  cheaper per token than a chat model, so a single `PriceBasis` prices embedding calls at chat
  rates. A `by_model` basis naming no rate for the embedding model leaves those calls unpriced.

- **`EmbeddingClient` and `RerankClient`**, two protocols beside `ModelClient`, each with two
  methods. `ModelClient` takes messages and returns content, so neither is that protocol with a
  field unused. `docs/retrieval.md` §8 is what an adapter owes its caller.

### Changed

- **FT-14 reads `models.observed`.** A model reached from a tool rather than declared by a node
  was invisible to the check, so a corpus embedded by an unpinned model passed it. Any identity
  that served a call is now read, and reported against `calls it served` where no node names it.

- **Every run records, into its own directory.** `RunEnvelope.cassette` defaults to
  `Cassette.into_run()`, which writes `<run_dir>/<run_id>/cassette.jsonl` beside the manifest
  and the trajectory. It was `Cassette.off()`, which made a recording something a project had
  to ask for before it knew it would want one.

  ```python
  RunEnvelope(run_dir="runs/")                            # records
  RunEnvelope(run_dir="runs/", cassette=Cassette.off())   # records nothing
  ```

  **A run's recording is kept or dropped with its trajectory payloads**, on the one decision
  `Trajectory.keeps(run_id)` makes. A run whose payloads are sampled out has the file deleted
  as it closes, so `Trajectory.sampled(0.0)` keeps both off disk and a project that samples
  does not keep the same prompts and responses in a second file. A cassette the project named a
  path for is not touched, and a run that errored keeps both whatever the rate.

  **The manifest goes to `0.20`**, gaining `cassette.dropped`: `null` while the file is on
  disk, and the reason where the run deleted it. `cassette.recorded` still counts what the run
  recorded before that.

  **An evaluation is unchanged**: its rollouts share one file at
  `<run_dir>/<eval_id>/cassette.jsonl`, which is what lets the k rollouts of an example share a
  recorded tool answer (FT-20). `record=False` now turns recording off for the rollouts as
  well, where before it left them to record one file each.

  `Cassette.record(path)` still refuses a file that already holds a recording. The default
  cannot, because a resumed run writes into the directory its first half wrote, so a default
  recording appends the way the trajectory beside it does.

  A recording with no file raises rather than storing nothing, so a run driven with an
  unresolved default fails instead of finishing with an empty recording.

- **`suite.record` refuses the default cassette**, naming a path to pass. The runs a replayed
  evaluation is served from have to be in one file, and the default would put each in its own.

- **One elicitation question, `keep_payloads`, required at `build`.** It tells the builder that
  every run keeps what was sent to the model and what came back, and asks whether this agent's
  runs should. 30 questions. `reproduce` keeps its question and its scaffold now describes what
  sampling changes, since a recording is no longer something to remember to make.

### Added

- **`EvalSuite.rescore`: score rollouts that already ran, without running anything.** Reads each
  rollout back from its run directory, so a metric that raised, a `matches` that was wrong, or a
  metric added afterwards is applied to rollouts already paid for.

  ```python
  results = suite.rescore(run_dir="runs/eval_a1226bc495df", split="held_out")
  ```

  The answer is the output of the pipeline's terminal node, rebuilt through the schema that node
  declares, so `answer` reads it as it did live whether it names a field or is a function. A
  pipeline with two nodes that have no successor is refused at construction, so which node that
  is never depends on which path ran.

  **A re-score against a different pipeline is refused**, naming both graph fingerprints: a
  number scored from rollouts of another shape describes code that never ran (FT-15).

  **A partial set is scored and says so.** `config.incomplete` carries how many of the split's
  rollouts were found, and `report()` prints an `INCOMPLETE` line above every figure.
  `config.scored_from` is `"run_directory"` rather than `"rollouts"`.
  `docs/evaluation.md` §6.4.

- **An evaluation may run a `spends_money` tool, under a ceiling it declares.**
  `EvalSuite.run(max_spend=...)` is the most the evaluation may cost, model calls and paid tool
  calls together. `irreversible` is still refused outright: an action that cannot be undone is
  not bounded by declaring how many of them are acceptable.

  ```python
  results = suite.run(
      envelope=env, model=client, split="held_out", k=5, seed=41, max_spend=0.50
  )
  ```

  **It is checked before the first rollout and never binds part-way through one.** No rollout
  can pass the pipeline's `max_cost`, so `examples × k × max_cost` bounds the evaluation, and a
  `max_spend` under that figure is refused with both figures named. A budget with
  `max_cost=None` is refused for the same reason.

  Two limits are stated in the refusal rather than left to be found: a rollout can pass
  `max_cost` by one model call, whose cost is known only after it returns, and by whatever a
  tool meters above its own `DeclaredCost`. `docs/evaluation.md` §7.2.

- **`EvalSuite.record`: the recording an evaluation replays.** One live run per rollout, at the
  seed that rollout will use, into one cassette. It returns a `Recording` saying what it cost
  and the seed to pass to `run`.

  ```python
  made = suite.record(envelope=env.with_cassette(Cassette.record(path)),
                      model=client, split="held_out", k=5, max_spend=0.50)
  results = suite.run(envelope=env.with_cassette(Cassette.replay(made.cassette)),
                      model=client, split="held_out", k=5, seed=made.seed)
  ```

  A call already on file is served rather than made again, so the k rollouts of one example that
  make the same tool call buy one answer between them. Model calls carry the seed and are each
  made live, so the variance across rollouts is the real one. `docs/evaluation.md` §6.3.

- **A replay whose recording was made at other seeds is refused.** A model call is recorded
  under the seed it was sent with, and a rollout's seed derives from the evaluation's seed, the
  example's id and the rollout index. Without the refusal such an evaluation completes and
  reports accuracy 0.0 beside failure_rate 1.0, with nothing saying the recording was the
  reason. A pipeline making no model call is not checked, since a tool call's key carries no
  seed. `docs/evaluation.md` §7.7.

- **Memory: a store the agent reads and writes across runs.** Declared on the envelope, reached
  through tool calls and nothing else, and scoped to one end user. `docs/memory.md`.

  ```python
  env = RunEnvelope(run_dir="runs/",
                    memory=MemoryStore("memory/", scope=f"user-{user_id}"))
  registry = ToolRegistry([remember(), recall(), memory_search()])
  ```

  **There is no `ctx.memory`.** A node reaches the store through a tool call, so what it read is
  in a `tool_call` record parented to that node and what it did with it is in the next node's
  `inputs`. A value read from a store no record names cannot be explained from the trajectory.

  `scope` is required and has no default: a store with no scope is one memory for every end user.
  The manifest records the directory, a digest of the scope and the entry count, never the scope
  itself.

  **A write is a put rather than an append.** A tool taking a `Memory` is re-run during a replay
  rather than served from the cassette, so writing twice under one key has to leave what writing
  once leaves. A fact with no natural key goes under one derived from what it says.

  **A value is redacted before it is stored**, under the run's rules, and each entry records what
  they replaced and which rules were in force. The store outlives every run, so a rule added
  later does not reach what is already in it.

- **Three built-in tools over it**: `remember`, `recall` and `memory_search`. Search is lexical,
  the same BM25 `document_search` uses. A search that matches nothing over a store that holds
  something returns `keys`, so a miss on wording is recoverable with one `recall`.

- **`Example.memory`**, what the agent already remembers when an example starts. Each rollout
  gets its own store holding exactly this. Rollouts run concurrently, so a shared store would let
  one rollout answer out of another's write and the same evaluation at the same seed would report
  a different number each time.

### Changed

- **An evaluation records its rollouts, and that is the default.** `EvalSuite.run` writes
  `<run_dir>/<eval_id>/cassette.jsonl` unless the envelope names a cassette of its own, so the
  runs an evaluation paid for can be scored again or replayed rather than bought twice. Every
  call is redacted before it is written, under the same rules and the same path as a trajectory
  record.

  `record=False` turns it off, for a run whose responses must not reach disk at all; that run
  cannot be replayed or re-scored. `docs/evaluation.md` §6.3.

  **`config.cassette` now reports the mode the rollouts ran under** rather than the one the
  caller's envelope declared, which said `off` on a run that had recorded.

- **A project metric is scored as each rollout lands, not after all of them.** A metric's
  `score` is called once per rollout, and one that cannot read what the agent produced ended the
  evaluation after every rollout had been paid for. It now fails on the first rollout it cannot
  score, and an evaluation running rollouts concurrently cancels the ones not yet started, so at
  most `concurrency` are lost rather than all of them. Measured on 18 rollouts against a local
  model: 4 paid for instead of 18.

- **Results file `0.8` to `0.9`**: `config.incomplete` says when a number is over fewer rollouts
  than the split holds, `config.scored_from` distinguishes a run from a re-score, and
  `config.seed_source` says whether the recorded seed is the evaluation's or one rollout's. `n`
  is the examples the number is over, which is not the whole split on a partial set.

- **The FT-20 refusal no longer claims a call count it does not have.** It said an evaluation
  "would execute it up to `examples × k` times". That figure counts rollouts, and one rollout
  calls a paid tool as often as the agent reaches for it: 24 was measured against an arithmetic
  predicting one. The message now says rollouts, and says each may call the tool more than once.
  `DeclaredCost` is documented as the price of a call rather than as the arithmetic for what an
  evaluation costs.

- **Results file `0.7` to `0.8`**: `config.max_spend` records the ceiling a number was measured
  under, and is `null` where none was declared. Superseded by `0.9` above.

- **The manifest gains `memory` and goes to `0.19`.** `null` on a run whose envelope declared no
  store.

- **The manifest's `counts` reports every record type**, including the ones a run wrote none of.
  It listed four names and the format has had five since `0.19`, so a run that delegated reported
  no `delegation` count at all. The list is now derived from the format's own `RecordType`.

- **An evaluation refuses a recording that answers one tool call two ways.** A tool call is keyed
  on its name, version, arguments and occurrence within the run, so two rollouts making the
  identical call share a key, which is what lets one recorded answer serve all k of them (FT-20).
  Where the recording holds more than one response under that key, the tool is not a function of
  its key, and replay would serve the first rollout's answer to every rollout with nothing saying
  it had. Model calls are not read this way: a backend answering one request two ways is what the
  manifest's `diverged` count reports.

- **A model can hand a subtask to a whole pipeline**, declared as `AgentNode(delegates=[...])`
  with a `Delegation`. A `Pipeline` given a `node_id` is a node in another pipeline, which is
  the case where the builder fixes the decomposition; this is the case where the model chooses
  it, and it is what an orchestrator-workers shape needs. `docs/pipeline.md` §2.5.

  ```python
  orchestrate = AgentNode(
      plan_the_work,
      tools=[read_page],
      delegates=[Delegation(research, description="Research one question.")],
      output_schema=Report,
      budget=Budget(max_steps=20, max_tokens=200_000, max_cost=None,
                    max_wall_clock_ms=600_000),
  )
  ```

  **The delegate is declared rather than hidden in a tool body**, which is what makes every
  pre-flight check see it. A tool whose body runs a sub-pipeline is invisible to the eval
  runner's refusal, so a `spends_money` tool inside it executes once per rollout with nothing
  having declared it; a delegate's tools are read the way any other node's are (FT-19, FT-20).
  They are also in the manifest's `nodes`, in `_calling_nodes`, and in the mixed-currency and
  unserved-model refusals.

  **What bounds it.** A delegate's spend counts against the calling node's budget, because one
  step is one model call wherever it was made, so `max_steps` bounds how many subtasks the
  model can send. `max_calls` is required only on a delegate that makes no model call, which is
  the hole `Loop(max_iterations=)` exists for. The delegate's own budget running out is
  returned to the model as an observation; the run's budget running out still ends the run.

  **The trajectory gains a fifth record type, `delegation`**, which is why the trajectory
  format is `0.19`. It carries the subtask the model chose, which invocation it was, and the
  worker's `graph_fingerprint`. A pipeline declares no side-effect class and no cost, so it is
  not a `tool_call`: what it spent is on the records its own nodes and tools wrote.

  **`node_execution` records gained a `parent_id`**, naming the `delegation` they ran inside
  and `null` for a node the pipeline reached along an edge. Node ids repeat across subtasks,
  because a node id names the node and a `record_id` names the execution, so the parent is what
  separates one subtask's executions from the next. `docs/trajectory-format.md` §4.4.

  **A run can stop and continue inside a delegate**, so a `consult` in a worker suspends the
  whole run and the resumed run finishes that subtask first. This is why the suspension format
  is `0.3`: the state used to carry one `node_state` for the run, and a delegation puts two
  agent nodes mid-execution at once. Each frame now carries what its own node held, so `frames`
  is the whole stack. **A run suspended under `0.2` cannot be resumed** and is refused by name.

- **The manifest records the pipelines used as nodes**, under `containers`, which is why the
  manifest format is `0.18`. One entry per nested pipeline: its `budget`, its edges in the graph
  that holds it, and `nodes` naming its direct children. `nodes` stays leaves alone, because a
  pipeline used as a node emits no `node_execution` record. `docs/run-envelope.md` §2.5.

  Reading the two arrays together is what gives the whole graph. `nodes` on its own has an edge
  naming a container that is in no entry, and every leaf that ends a container reading as if it
  ended the run, which is a shape `Pipeline` refuses to construct.

  **`graph_fingerprint` covers those entries**, so a suspended run no longer resumes against a
  pipeline whose sub-pipeline was rewired or gained an error edge. Budgets stay outside it, the
  same as a leaf's `node_budget`.

  **A results file records them too**, under `config.containers`, which is why the results format
  is `0.7`. `compare()` diffs the whole config, so a sub-pipeline rewired or rebudgeted between
  two evaluations now has somewhere for a moved number to be traced to (FT-15).

  **Every edge target is written under the id the node it names records under.** `on_error` and
  `loop.then` inside a nested pipeline used to be recorded bare, naming an id no entry held,
  while `successors` beside them was prefixed.

- **`ablate()` says which variants it did not generate**, as `Ablations.skipped`, a mapping from
  the variant's name to why. A node with no arm is distinguishable from a node whose arm measured
  nothing, and the reason is what a builder writing that variant by hand needs.
  `docs/evaluation.md` §10.2. The return value is still a `Mapping[str, Pipeline]`, so passing it
  to `compare_variants` is unchanged.

- **A model per node.** `LLMNode(..., model=client)` and `AgentNode(..., model=client)` declare
  the client that node calls. `Pipeline.run(model=client)` serves every node that declares none,
  so a pipeline whose nodes share one model is unchanged. A cheap model for a reduction step and
  a strong one for the answer are now one pipeline, and so are two backends in one run.
  `docs/pipeline.md` §2.4.

  Resolution has two levels, the node's own client then the run's. A pipeline used as a node
  declares none for the nodes inside it.

  **The manifest gains `nodes[].model`**, what each node declared and `null` where it takes the
  run's client, which is why the manifest format is `0.17`. `models.configured` is unchanged and
  holds the run's client. No trajectory format change: every `model_call` record already carried
  the backend, the requested model, the revision and the model that served it.

  **A node that can call a model and has no client from either source is refused before the run
  starts.** It used to raise when that node was reached, after the nodes before it had spent.

- **A cost basis per model.** `RunEnvelope(cost_basis=...)` takes a mapping keyed by the model
  identifier alongside the single basis it already took, so a run calling a hosted model and a
  self-hosted one prices each on its own terms and totals in one currency. The manifest records
  `kind` of `by_model` with the bases under `bases`. A call to a model the mapping does not name
  prices as `null` with a reason. `docs/run-envelope.md` §4.1.

  **Two runs are now refused before the first call**: one basis where the run calls both a
  hosted and a self-hosted backend, and one `PriceBasis` where the run calls more than one
  model. Both would have reported a cost derived from the wrong rates with nothing saying so.
  One `ComputeBasis` over several self-hosted models is not refused, because a device rate
  belongs to the deployment rather than to the model.

### Changed

- **A `node_id` containing a dot is refused.** A pipeline used as a node prefixes its own nodes
  with its id and a dot, so `research.hunt` already means `hunt` inside `research`, and a dotted
  id at the top level was indistinguishable from it. Per-node metrics, the trajectory, the
  manifest and ablation all key on that id. `docs/pipeline.md` §1.1.

- **A pipeline's `tools=` registry and `fetch_policy=` are read at every level of nesting.** A
  registry given to a nested pipeline reached neither the manifest's `tools` array nor the
  refusal of a run declaring money in more than one currency, so the same tool was refused when
  the top pipeline declared it and accepted one level down.

  **`fetch_policy` in the manifest is an array** rather than one object, each entry naming the
  pipeline that declared it under `declared_by`, which is `null` for the pipeline the run was
  started with. A nested pipeline could be given one and it was dropped.

- **FT-14 checks every model that could serve a call**, rather than the run's configured pin
  alone, and reports one failure per unpinned identifier naming the nodes it serves. Its failure
  message gains a `<where>` placeholder. A project pinning the run's client and leaving one
  node's model floating used to pass. `docs/conformance.md` §3.3.

- **Streaming is refused per node.** A node declaring `stream=True` whose own client cannot
  stream is now named in the refusal, along with the client its calls go to. The check read the
  run's client before, which said nothing about a node calling its own.

- **A variant may differ in one node's model.** `nodes[].model` is part of what decides whether
  a node's calls replay off the baseline cassette, so a node whose model changed is planned as
  `live`. `ablate()` carries a node's client into the `LLMNode` it flattens an `AgentNode` into,
  which without this would have measured the loop coming out and the model changing at once.
  An evaluation's id covers the per-node models, so two sweeps differing only there no longer
  write into one directory. `docs/evaluation.md` §10.

- **Every distinct client an evaluation can call is paced**, rather than the run's alone.

- **A `brainstorm` stage before `shape`, and `idea.md`.** The procedure is four stages. The
  eighteen questions that shipped before this all presuppose the project already exists as a
  specification: `ground_truth` asks what the correct answer is for one input, which assumes the
  shape of an input is known. `brainstorm` is where the builder settles what to build. Eleven
  questions, six required (`what_it_does`, `purpose`, `end_user`, `one_real_input`,
  `smallest_worthwhile`, `finished_version`) and five that apply when the idea is still open
  (`existing_solution`, `success_story`, `alternatives`, `not_building`, `abandon_condition`).
  `simple-agents questions --stage brainstorm` prints them.

  The stage produces **`idea.md`** at the project root, the project's own account of itself in
  five sections: what this is, who it is for, what it works on, where this is going and where it
  is not, and what is still open. The brief is authoritative on answers and this file on the
  narrative. **`understanding_confirmed_at`** in `brief.toml` names the stage at which it was
  last confirmed to still describe the project, and advancing a stage means reading it again and
  writing the new stage there.

  **What a project has to do.** `STAGES` gains an entry at the front, so a brief that declares
  `shape` or later is now held to the six new required entries and fails FT-24 until they are
  added, and a brief declaring no stage reads as `brainstorm` rather than `shape`. Add the
  entries, write `idea.md`, and add `understanding_confirmed_at` naming the stage the project is
  at. **New check, FT-29**, at tier `prototype`: it fires when `idea.md` is missing, when one of
  its sections is empty, or when the confirmation names an earlier stage than the project is at.
  It reads whether the sections are present, never whether what they say is true.

- **A run says what it was for: `RunEnvelope(role=...)`.** A labelling pass, a model judging
  another model's answers and an ablation arm are all model calls a project makes for itself,
  and running each through the envelope is what gives it a manifest, a cost and a model pin.
  They are not runs of the agent. `role` defaults to `agent` and takes any non-empty string;
  `env.with_role("labelling")` copies an envelope that was configured once. Every conformance
  check that reads a run now reads the newest run whose role is `agent`, so a project that
  followed `docs/evaluation.md` §1.4 and wrote its labelling pass into `runs/` no longer has
  FT-13 and FT-14 report on the labelling run. A project whose only runs declare another role
  fails FT-13, and the reason counts what it found by role. `runs("runs/", role="labelling")`
  reads them back and `RunHandle.role` reports it. A resumed run keeps the role its manifest
  records rather than taking it from the envelope the resume was given, so a labelling pass
  that stopped to wait for a person is still a labelling pass when it continues. Manifest
  `0.15` to `0.16`, where the manifest gains `role`; a manifest written without one reads as
  `agent`. `docs/run-envelope.md` §2.1.

- **`Label`, `read_labels` and `write_labels`: a judgement, and where it is kept.** A label
  records what was decided about one thing, why, and who or what decided it. `decided_by` is
  required, and `run_id` names the run where a model made the call, so the model, the prompt
  and the exchange stay recoverable from the label. They live in `evals/labels.jsonl`, one JSON
  object per line, and `read_labels` keys them by id with the last line winning, so re-labelling
  appends rather than edits. No conformance check reads the file: whether a label is right is
  not checkable and the library does not imply otherwise. `docs/evaluation.md` §1.5.

- **`docs/evaluation.md` §1.4 now fans out over the candidates.** The one-node `Pipeline` it
  showed ran once per candidate, so `max_cost` bounded one candidate rather than the pass and
  60 candidates cost 60 run directories. `over=` makes one call per item inside one run, which
  gives the pass one budget, one manifest and one cost figure.

- **`LLMNode(over=..., keep=[...])` carries an input key past a fan-out.** A fan-out node
  returns the outcomes and nothing else, so a value that arrived beside the sequence reached no
  later node on any edge. `keep=` names input keys that travel on with the outcomes, arriving as
  `FanOutResult.kept`. A key that is not in the input raises `CallerFacingError` naming the keys
  that are, rather than being dropped. Naming the key the node fans out over is refused at
  construction. Trajectory `0.17` to `0.18`, where a fan-out's `outputs` gain `kept`, present
  only on a node that declared `keep=`. Manifest `0.14` to `0.15`, where `fan_out` gains `keep`.
  `docs/pipeline.md` §2.2.

- **`docs/pipeline.md` §1.3 and §1.4: reaching a node further on, and accumulating round a
  cycle.** A node's output is the whole of what travels, and two kinds of node narrow it: one
  that calls the model produces what its `output_schema` describes, and one that fans out
  produces the outcomes. §1.3 shows a value sent to a later node on its own edge. §1.4 states
  that the edge from outside a cycle keeps the value that entered, so folding into it loses each
  fold, and shows the shape that accumulates: the node closing the cycle receives the working
  set and the latest result and hands the two back round.

- **`docs/pipeline.md` §6: running the pipeline without a backend.** `FakeModelClient` returns
  scripted responses without reading the request, so a whole run costs nothing. What it
  exercises that a test over a node's own function does not, how a tool call is scripted, and
  what it cannot show. `docs/procedure.md` stage 2 routes to it before a paid run.

- **A tool reports what it was charged, through a `SpendMeter`.** A tool whose signature asks
  for one calls `meter.spend(amount)` after the vendor answers, and what it reports is what the
  call cost: reporting nothing means the call cost nothing, which is how a cache hit inside a
  tool body reaches `spent: null`. The figure is recorded with `source: "measured"`. Unlike a
  `ModelHandle` or a `Workspace`, a meter does not stop the tool being served from the cassette,
  because it reaches nothing outside the run. **A reported currency has to be the run's**: the
  declared currencies are checked before the run and a reported one was not, so a tool
  reporting 100 JPY under a USD basis reached `charged_cost` as 100 and depleted `max_cost` by
  it, silently. `meter.spend(amount, currency=...)` naming a second currency is now refused at
  that call, against the cost basis, against what the tool declared, and against what the run
  has already been told. A run needs no cost basis where its only spend is a paid tool, so the
  first figure reported fixes the run's currency and every later one is checked against it: two
  tools reporting different currencies, neither of them declared, summed before. Suspension
  `0.1` to `0.2`, where the state gains the fixed currency; the spend it belongs to was already
  restored, so a resumed run had forgotten only which currency that spend was in.
  `docs/tools.md` §1.5.

- **`max_cost` bounds what tools spend as well as what the model spends.** It was charged
  around the model call and nowhere else, so the axis named for cost bounded one part of it. A
  paid call the limit cannot afford is refused before it is made, model-facing, so the agent
  answers with what it has rather than the run being ended. The check is against
  `DeclaredCost(max_per_call=...)` where a tool declares one, which makes the limit exact for a
  tool whose price varies, and against `per_call` otherwise. `docs/run-envelope.md` §4.4.

- **`totals.tool_spend` and `totals.charged_cost` on the manifest**, beside `totals.cost`, which
  is model spend and now says so. `tool_spend` carries the amount, the currency, how many calls
  bought something and whether the figures were measured or declared. `charged_cost` is the two
  together, which is what `max_cost` bounds. An evaluation reports the same under
  `results.totals`, per node in the report's table, and per arm in a variant comparison. Manifest
  `0.13` to `0.14`, results file `0.5` to `0.6`, variant comparison `0.1` to `0.2`.

- **A `tool_call` record says what the call spent, in `spent`.** `declared_cost` is what the
  tool charges and appears on every call it made; `spent` is what this call cost and is `null`
  where it cost nothing. A call served from a cassette, a call that failed, and a call answered
  by a cache all reach a paid tool's price and buy nothing, so summing `declared_cost` for a
  run's tool spend counts calls that never reached a vendor. Sum `spent` instead.
  `source` says whether the figure is the tool's declaration or what the tool reported.
  Trajectory format `0.16` to `0.17`. `docs/trajectory-format.md` §4.2.

- **Grounding helpers: `url_was_read`, `urls_read`, `contains_normalised`, `same_url` and
  `normalise_text`.** A claimed source that the run never touched is a claim the agent did not
  establish (FT-09, FT-10), and both dogfoods wrote the same plumbing to check it.
  `url_was_read(ctx, url)` reads `ctx.tool_calls` and is true when that address was an argument
  to a call that succeeded, whichever tool made it. `contains_normalised` folds case, accents
  and punctuation and does not join words across a separator, so `therapist` does not match
  `the rapist`. What counts as grounded stays the project's decision; `docs/tools.md` §5.3 has
  the worked check.

- **`read_page` returns a page as text rather than markup.** It composes `http_fetch` with a
  new `reduce_html`, which drops script, style, navigation and footers, keeps table structure,
  parses `ld+json` blocks without interpreting them, keeps image alt text, and collects
  same-host links. `order=` decides which parts are rendered and in what sequence, so what
  survives a `max_chars` limit is the project's choice; `link_words=` lists the links worth
  following, which are named at the end of the reply. A page that reduces to almost nothing
  fails model-facing, saying the site is rendered by JavaScript. `docs/tools.md` §4.3.

- **`HostPolicy` is a reachable set that can grow while a run proceeds.**
  `http_fetch(policy=...)` and `read_page(policy=...)` take it in place of `allow_hosts`, and
  passing both is refused. Hosts are configured up front; the project's own code admits more
  with `policy.admit(host, reason=...)` against `max_admitted`; `max_fetches` is a whole-run
  ceiling on requests that reach the network. Subdomains and a leading `www.` are handled
  inside it. `docs/tools.md` §4.4.

- **`UrlCache` serves a page or a search made before, across runs.**
  `http_fetch(cache=...)`, `read_page(cache=...)` and `web_search(cache=...)` take it. The
  cassette replays one recorded run; this is what stops a later run re-requesting what an
  earlier one read. A page served from it says how old it is, nothing served from it is charged
  against `max_fetches`, and the host checks still apply. `docs/tools.md` §4.5.

- **`web_search` can be restricted to named sites.** The tool's schema gains an optional
  `domains`, passed to a provider that accepts it; a provider without the parameter keeps
  working, and a search asking for domains against one is refused rather than run unscoped.
  `provider_options=` reaches every call uninterpreted, for settings the builder fixes rather
  than the model chooses. `docs/tools.md` §4.2.

- **The manifest records `fetch_policy`**, at format version `0.13`: the configured hosts, each
  admission with its reason, the caps, and how many requests the run made. Once a run can add
  to its reachable set, the tool declarations no longer say what the agent could touch.
  **What a project has to do:** pass the policy to the pipeline as `fetch_policy=` to have it
  recorded.

- **`value_or(value, default)`** returns the value, or the default where the agent reported
  absence. Only an `Unknown` is replaced; `None`, `""` and `0` come back as they are.
  `isinstance(value, Unknown)` remains the test where the branch matters rather than the value.
  `docs/pipeline.md` §4.

- **`DocumentIndex(stopwords=...)`** drops declared words from a query before searching. No
  list ships, the words are matched after lowercasing, and a query of nothing but stopwords is
  searched as written. `index.query_terms(query)` returns the words a query is searched on, and
  `documents_containing` counts those same words rather than every token. `docs/tools.md` §4.1.
  **What a project has to do:** nothing. An index built without the argument searches every
  word, as before.

- **A cassette carries the seed its calls were recorded at, and a replay takes it from there.**
  A model call's seed derives from the run's and is part of the key, so a run recorded without
  an explicit `seed=` could not be replayed: the replay generated its own seed and missed on
  the first call. Every entry now records `run_seed`, `Pipeline.run` with a cassette it reads
  from and no `seed=` uses it, and `Cassette.replay(path).recorded_seed` is what that would be.
  A file recorded by runs at several seeds, which is what one evaluation writes, is refused
  rather than guessed at. A miss whose difference is the seed names the run seed to pass
  instead of the derived one on the request. `docs/run-envelope.md` §3.1. **What a project has
  to do:** nothing. A cassette recorded before this names no seed and is replayed by passing
  one, as before.

- **`runs()` reads back what the envelope wrote.** `runs("runs/")` lists the run directories
  under a path, newest first by the manifest's `started_at`, each handle carrying `run_id`,
  the parsed `manifest`, `outcome`, `finished`, `node_ids`, the paths, and
  `outputs_of(node_id)` for what a node last produced. An evaluation's rollouts are one level
  deeper and are reached with `nested=True` or by naming the evaluation's directory. A run
  whose manifest cannot be parsed is still listed, with `unreadable` saying why.
  `docs/run-envelope.md` §8. **What a project has to do:** nothing, and delete any hand-rolled
  reader over `runs/*/trajectory.jsonl`.

### Fixed

- **`ablate()` works on a pipeline it did not generate.** It rebuilt every arm from the leaf
  nodes alone, which cost four things.

  A nested pipeline was flattened and its nodes renamed, so an arm's `research.hunt` came back
  as `hunt`, the sub-pipeline's budget was gone, and the comparison read one node as removed and
  its renamed twin as added. Arms now rebuild only the pipelines on the path to the node they
  change, and every constructor argument travels, so an arm pairs with the baseline node for
  node.

  A node named in another node's `successors=` could not be removed: the edge survived the
  rebuild and the arm was refused at construction, which raised out of `ablate()` and lost the
  whole standard set rather than one arm. Removing a node now re-points every edge that named it
  at what it led to, which is what a pipeline whose edges were left to the default already did.
  An arm the graph still refuses is reported in `skipped` instead of raising.

  A node that ended a nested pipeline was offered as removable without checking anything, so the
  arm changed what the container produced and failed on every rollout. It is now subject to the
  same rule as any other node with something after it.

  A change inside a nested pipeline did not mark what followed the container as needing live
  calls, so `max_live_calls` could admit a sweep that then exceeded it.

### Changed

- **`who_labels` is asked at stage `build` rather than at stage `measure`.** It governs how a
  project's ground truth gets made, and every project that made ground truth did so before it
  reached `measure`: one answered the question two hours after running the pass it describes,
  and one never reached the stage and was never asked. A project with no evaluation ahead of it
  answers `deferred` naming `measure`, which is what deferral is for. Its scaffold now names
  `role="labelling"` and `evals/labels.jsonl`.

- **The entry name is marked as not builder-facing.** `simple-agents questions` labelled each
  question with its `brief.toml` key beside the text to ask, with nothing marking the
  difference, and a builder asked to confirm `agency_boundary` answered "I don't know what
  agency_boundary is". The command's output, `docs/procedure.md` stage 1 and `Question` all say
  the key is internal and the question goes to the builder in their own words.

- **The `absence_vs_error` scaffold asks by how much.** It instructed a comparison and the
  question asks for a magnitude, so it produced a direction where the code needs a threshold.
  It now asks for a graded answer, and what the builder does with an answer before acting on
  it.

- **`docs/tools.md` §3.2 and `docs/failure-taxonomy.md` FT-27 describe the meter.** A handle no
  longer means a tool is re-run on replay, and a `tool_call` record does store a cost figure.

- **`docs/pipeline.md` §3 says a value routed through the workspace leaves the declared graph.**
  A node reading a file another node wrote receives something its `inputs` do not hold, so the
  record no longer explains what it saw. Carry the value on an edge, with a `Join` where
  several have to meet.

- **`docs/procedure.md`: two things a passing gate does not mean.** An answer naming a figure
  goes stale when the code needs a different one, and the new figure goes to the builder rather
  than being edited. A green suite at stage 2 says the run was recorded, not that the agent
  works.

- **`max_cost` is no longer enforced against a cost figure that is an upper bound.** Under a
  compute basis a call whose backend reported no concurrency is charged the whole device, which
  can be several times what it cost, so terminating on it ended runs that were inside their
  limit and the discarded work was paid for again on the re-run. The run now ends on the first
  such call, naming the flag that makes the figure exact; a run that sets no `max_cost` records
  the bound and continues. **The call is recorded before the run ends**: the refusal ran ahead
  of the manifest's own accounting, so a refused run carried `counts.model_call: 1` beside an
  empty `models.observed` and four zero token totals, for a run whose trajectory held the call.
  `docs/run-envelope.md` §4.4.

- **`VLLMClient(report_concurrency=...)` defaults to `True`.** Reading
  `vllm:num_requests_running` costs one local request per call, taken on a thread joined inside
  the call, and without it every compute-basis figure is an upper bound. Pass `False` for a
  server whose metrics endpoint cannot be reached. `docs/model-clients/vllm.md` §5.

- **A run may declare money in one currency.** A tool whose `DeclaredCost` names a currency
  other than the cost basis' is refused before the run starts, because a total cannot add two.

- **`max_cost` with no cost basis is refused only where the pipeline can make a model call.** A
  pipeline whose only spend is a paid tool needs no basis: the tool reports what it was charged.

- **`DeclaredCost` gained `max_per_call`**, the most one call can cost. `to_record()` now carries
  four keys.

- **`http_fetch` returns the whole body, and a truncated one says so.** `max_chars` defaulted
  to 100,000 characters and cut silently, which on a long page removes a table low down and
  leaves an answer read from the part that survived. It now defaults to `None`; a limit that is
  set appends how much was dropped. A page too long for the model's window is refused by the
  backend and the run stops, rather than continuing from half a page. `read_page` is the tool
  that makes a long page fit. **What a project has to do:** pass `max_chars=` where it was
  relying on the old default, or switch to `read_page`.

- **A recorded absence comes back as `Unknown` wherever it sits in a value.** `outputs_of`,
  and the output and label a node matcher or a per-node `ProjectMetric` is given, decode the
  tagged `{"type": "unknown"}` object at every depth, so `isinstance(value, Unknown)` is the
  test on a value read out of a run as much as on one a node just returned. The trajectory
  still stores the tagged object and `read_trajectory` still yields records as they are on
  disk. **What a project has to do:** a node matcher or per-node metric that reached inside the
  tagged object, as `output["answer"].get("reason")` did, compares against `Unknown` instead;
  `output["answer"] == expected` now works on both sides and is what to write.

- **A generated `run_id` carries the time the run started**: `run_20260809T014233Z_a3f9`,
  fixed width, so a run directory listing reads in the order the runs happened. Nothing parses
  the id, and a run given an explicit `run_id=` is unaffected. **What a project has to do:**
  nothing, unless it assumed the id was twelve hex characters.

- **`http_fetch` checks every redirect hop, refuses private addresses, and keeps credentials
  on the first host.** Redirects were followed by the HTTP client, so a permitted host
  answering 302 took the fetch past the allow-list and the robots check. Each hop now passes
  the same checks the first URL does, up to five, and headers named `Authorization`,
  `Proxy-Authorization` and `Cookie` are sent only to the host the agent addressed. A URL
  naming a private or reserved address, or `localhost`, is refused unless the tool is built
  with `allow_private=True`; a hostname that resolves privately is not detected. **What a
  project has to do:** re-record cassettes holding `http_fetch` calls, since the tool's
  derived version changed, and pass `allow_private=True` where it genuinely fetches from its
  own network.

- **A tool's execution time is charged to the run's wall clock.** A fetch that took a minute
  inside an `AgentNode` counted against the node's own `max_wall_clock_ms` and not the run's,
  so moving work into a tool quietly exempted it from the run axis. Every node kind now
  charges it; model calls a tool makes through a `ModelHandle` charge themselves and are not
  counted twice, and a `Deterministic` node's function is timed whole as before. **What a
  project has to do:** nothing, and expect a run whose tools work for a long time to reach
  `max_wall_clock_ms` sooner, which is the axis binding rather than a slowdown.

- **`EvalSuite` reads a dict output by key, and a name the output does not carry refuses the
  evaluation.** A pipeline whose terminal node returns a dict scored every rollout as `failed`
  under `answer="..."`, reporting `failure_rate` 1.0 after paying for all k×n rollouts. The
  mismatch is the same on every rollout, so it now raises `ConfigurationError` naming the
  output's fields before the rest are paid for. An output that is itself a reported absence is
  the answer and classifies as an abstention.

- **A project metric travels to every variant arm.** `compare_variants` rebuilt each arm's
  suite without `metrics=` and `node_metrics=`, so a declared figure was scored on the
  baseline, absent from every arm, and silently missing from every comparison. Both now carry
  over, and a per-node declaration for a node the variant removed is dropped rather than
  refusing the arm, which the comparison already reports as a removed node.

- **`too_similar` is an eighteenth elicitation question, required at `measure`.** What counts
  as the same example twice is one of the four decisions `docs/procedure.md` stage 3 already
  says the library will not make, and nothing recorded whose decision it was: an evaluation
  run without `contamination_threshold=` passed FT-03 having run no check. The gate now
  requires the decision in the brief; the check's text names the entry.

- **A comparison with nothing to pair reports no verdict rather than "did not move".**
  `MetricChange.moved` returned `False` where no shared example carried the metric; it is now
  `null` and the metric lands in `undecided`, with `reason` saying why. **What a project has
  to do:** nothing; a written comparison's `moved` field can now be `null` where it was
  `false` with no data behind it.

- **A resumed run's manifest keeps its `recording` block.** `Manifest.restore` dropped it, so
  a run suspended under a sampled envelope closed claiming `payload_rate` 1.0. The answer a
  consultation was resumed with also now files into the cassette under the node's id rather
  than the tool's name, which is what a later miss in that node is diagnosed against.

- **An interval no longer reports certainty from a set with no variation.** Where every example
  scored the same, resampling drew the same value every time and both endpoints landed on it, so
  30 of 30 correct reported the true rate as `[1.000, 1.000]` and an agent that never succeeded
  reported `[0.000, 0.000]`. Where those identical scores are 0 or 1 the quantity is a
  proportion, and `bootstrap_ci` now returns the Wilson interval for it. `Interval.method` says
  which calculation produced the endpoints. **What a project has to do:** nothing, and re-read
  any figure it reported at 100% or 0%. A set with variation is unchanged.

- **`wilson_ci(successes, n)` is new**, for a proportion judged by hand where there are no
  rollouts to resample. `wilson_ci(4, 4)` is 1.0 with an interval of 0.51 to 1.0. A labelling
  pass produces a count out of a count, which `bootstrap_ci` has no shape for.

- **Manifest format `0.11` to `0.12`.** `totals` gains `held_back_ms`, the run's model calls'
  waiting summed: retry backoff after a rate limit, and any wait a `PacedClient` imposed. The
  figure is on each `model_call` record already, and reading it meant adding a field across every
  call. **What a project has to do:** nothing. A manifest written by an earlier version carries
  no field, which reads the same as nothing having waited.

- **A run that waits through an unpaced client warns, outside an evaluation too.** The first
  model call held back against a hosted backend names `PacedClient` and does not fire again for
  the rest of the run. `EvalSuite.run` already warned when it was given one; a `Pipeline.run`
  said nothing, and a run can spend most of its wall clock throttled without any axis being
  charged for it.

- **A schema unioning a fixed label set with `Unknown` warns at construction.**
  `Maybe[Literal["a", "b"]]` offers the model a closed list and a tagged object, and the word
  `unknown` satisfies neither, so a model reaching for it fails validation and costs a step.
  Naming the tag in the description does not prevent it, so the warning is on the shape. Put the
  absence in the label set and pass `allow_unknown=False`.

- **`simple-agents check` reads the most recent run that finished**, rather than the most recent
  run. A run still executing and a run that crashed on its first node both write a manifest and a
  trajectory, so the newest by start time was not necessarily the one a project has to show.
  Where no run finished, the newest is read anyway and the checks report what is wrong with it.

- **Trajectory format `0.15` to `0.16`.** The `model_call` record gains `held_back_ms`, how long
  the call waited to be allowed to call, from an adapter's retry backoff and from a
  `PacedClient`. The record's timestamps bracket the whole call, so this is what separates
  waiting from working inside one, and `max_wall_clock_ms` is charged the call without it.
  **What a project has to do:** nothing. A record written by an earlier version carries no
  field, which reads the same as nothing having waited.

- **A model call asks for its schema in the form `strict: true` requires.** The adapters send
  the output schema with every property in `required`, `additionalProperties: false` on every
  object, and no `default`, rather than sending what Pydantic produced. A field with a default
  therefore reaches the model as one it must send: a nullable field holding a value or `null`,
  and one whose type cannot hold `null` as a value it has to choose. **Why:** a schema that does
  not meet the contract is not rejected, and `mistral-small-2603` answers one by returning field
  names padded with punctuation, such as `"source_doc "` and `"source_doc: "`, which validate as
  unknown fields and are dropped. Measured over ten real prompts: 10 of 10 responses mangled
  under the schema as Pydantic writes it, 0 of 10 under this one. **What a project has to do:**
  nothing to keep a cassette working, because the key is computed from the request the library
  builds rather than from what the adapter puts on the wire. A cassette recorded before this
  holds whatever the backend answered then, so a project that wrote its own repair for mangled
  field names should re-record before deciding the repair is still needed.

- **`PacedClient`'s request floor defaults to the number of callers sharing it.**
  `min_remaining_requests` was `1`, and `EvalSuite.run` now calls `expect_callers` with its
  concurrency, so an evaluation paces for the rollouts it is running rather than for one. A
  window reporting one request left carries one call, and the other rollouts in flight come back
  rate limited. An evaluation running more than one rollout at once through a client that does
  not pace, against a backend that publishes an allowance, now warns. **What a project has to
  do:** nothing; a `min_remaining_requests` passed to the constructor is unchanged.

- **Results file `0.4` to `0.5`.** Each rollout gains `scores`, holding the project metrics it
  was scored on, and each of its node entries gains one too. Each metric gains `unit`, which is
  `"rate"` for the six. `config` gains `metrics` and `node_metrics`, each holding a project
  metric's declaration and the version of the function that scored it. `EvalResults.read`
  refuses a `0.4` file and says to re-run the evaluation; re-running against a recorded
  cassette costs no network.

- **A comparison withholds its verdict when the scoring rule moved.** Where `config.matches`
  differs between the two evaluations, `moved` is `None` on all six rates rather than `True` or
  `False`, `MetricChange.rule_moved` holds both versions, and `verdict_reason` says the two
  sides were scored by different rules. The same applies per project metric. Before this a
  changed matcher was one key in `changed` and the verdict was issued anyway: two replays of one
  recording, differing only in the matcher, reported accuracy down 0.44 and read as the agent
  getting worse.

- **`bootstrap_ci` refuses a flat list with a message rather than a `TypeError`.** Passing one
  score per example as `[0.71, 0.33]` raised `TypeError: 'float' object is not iterable` from
  three frames in. It now raises `ConfigurationError` naming the grouped shape. A score that is
  not a number is refused the same way.

- **The `improvement` elicitation question asks which number the builder would act on**, not
  only how they will know a change helped. Its scaffold prints the six with the project's own
  numbers and offers a `ProjectMetric` where none of them is the right one.

- **FT-23 is narrowed to the half the library can enforce.** It was "tool description written
  for a human; no contract test", with a check specified over every registered tool's tests.
  Nothing can see whether a test exercises a tool: a project using a built-in has no `@tool`
  in its own source, all eight shipped tools pass `name=` a variable, and matching a tool's
  name against the test files scores 8 files for `now` and 19 for `read`. The entry is now
  about the description, which is refused empty at registration, and states what a contract
  test does not catch: a description faithful to the code and wrong about the world.

- **FT-13's message no longer tells a project to run inside the envelope when it did.** A
  project whose run directory is elsewhere had recorded everything and was told it had
  recorded nothing. The message now points at the reason, which names what was found.

### Added

- **`Comparison.report()`**, the text form of a comparison, beside `EvalResults.report()`. Every
  metric with both point estimates, the paired difference and its interval, and whether it
  moved, followed by `verdict_reason` for a metric with no verdict and by `population_note` for
  one whose denominator moved. A table written by hand from the attributes leaves those two out
  unless it asks for them.

- **`results` in `brief.toml`**, naming the evaluation the project reports. The checks that read
  a results file read that one. Optional: without it the most recent under `evals/results/` is
  read, which on a project that measured a variant after its reported number is the variant.

- **A project can declare its own metric.** `ProjectMetric(name=, definition=, score=)` declares
  a figure computed from the answer, `EvalSuite(metrics=[...])` reports it beside the six rates
  with the same interval, and `EvalSuite(node_metrics={...})` reports it per node beside `reach`
  and `accuracy`. `score` takes the answer, the label and the rollout; the rollout carries the
  outcome, the seed and the path to the trajectory, so a metric over more than the answer
  reaches them. `over` says which rollouts the figure is over, and under two of its three values
  the library reads absence, so `score` is handed two asserted values. `unit` says what the
  figure is measured in, so a cost prints as `0.000153 USD` rather than `0.0%`. A name one of
  the six already has is refused, and so is a `score` returning a boolean, which is `matches`.
  `docs/evaluation.md` §11.

- **A comparison pairs on project metrics.** Each rollout's score is written into the results
  file, so `compare()` reads them back and needs neither the labels nor the scoring functions,
  and `comparison.nodes[node].metrics[name]` does the same per node.

- **A tool can be called at a fixed point.** `Deterministic(fn, tools=[...])` declares the
  tools a node may call, and `ctx.call_tool("http_fetch", url=...)` calls one. The call is
  recorded as a `tool_call`, keyed and served from the cassette, priced by its `declared_cost`
  and counted by an evaluation, exactly as one an `AgentNode` made. Before this the tool
  contract was reachable only from inside an `AgentNode`, so a step that had to call a tool
  either paid a model call to decide something already decided or called the function
  directly, which records nothing and leaves an evaluation unable to see it. No model is
  choosing the call, so a tool raising `ModelFacingError` raises to the node rather than
  coming back as an observation. A tool taking a `ModelHandle` is refused on this node kind.

- **A tool's version is derived from its source where its author declares none.** The version
  is in the cassette key, so an edited tool body now makes a recorded call miss and name the
  re-record command, rather than serving the answer the old body gave. This covers an edit to
  the body and not a change to data the function closed over; declare `version=` where that
  matters. **Every committed cassette holding a tool call has to be re-recorded**, since every
  tool's key has changed.

- **The manifest records a tool the project registered and no node was given.**
  `Pipeline(nodes, budget=..., tools=registry)` puts the project's whole declared tool surface
  into the manifest, and each entry carries `offered`, false for a tool that was declared and
  cannot be called. **Manifest format `0.10` to `0.11`**: `tools[].offered` is new, and a node
  entry carries `tools` whatever its kind. A manifest written by an earlier version is read
  unchanged.

- **`tool_effects`, a seventeenth elicitation question**, required at stage `build`: what the
  agent may do that reaches outside the run. Its scaffold lists every tool the agent will be
  given with the side-effect class it declares. An evaluation refuses to start over a tool
  declared `spends_money` or `irreversible`, and until now the builder met that as a refusal
  rather than as a question. A project's brief needs an entry for it before its `build` gate
  passes.

- **The build procedure ships as a skill, and a command registers it.** `simple-agents init`
  links `docs/procedure.md` into the project's skills directory, `.agents/skills/` by default
  and `.claude/skills/` with `--claude`, and names it in `AGENTS.md`. The link is relative and
  points at the installed package, so the procedure tracks the installed version. `--copy`
  places a copy where symlinks are impractical, and `--no-agents-file` declines the note.
- **The procedure is staged, and a project records which stage it is at.** `shape`, `build`
  and `measure`, declared in `brief.toml`. A stage that is not one of the three is refused,
  and so is a deferral naming something that is not a stage. A brief that leaves `stage` out
  reads as `shape`, so no existing brief has to change.
- **A seventh conformance check: FT-24, elicitation skipped.** It reads the brief's entries
  against the questions required at the stage the project is at, and fails on a required
  question recorded `unanswered` or carrying no entry at all. A project whose brief answered
  nothing used to pass every check the suite ran. The stage is what the brief declares or what
  its artifacts show, whichever is further on, and the requirement is cumulative.
- **The elicitation questions ship, each with a scaffold.** `simple-agents questions --stage
  shape` prints what to put to the builder, what makes it answerable, and the entry name that
  records the answer. `--json` is the same for a gate to read.
- **A project in production bounds what its trajectories accumulate.**
  `RunEnvelope(trajectory=Trajectory.sampled(0.01))` keeps the payload fields on one run in a
  hundred and replaces them on the rest with `{"type": "not_recorded", "reason": "sampling"}`,
  naming each in the record's new `omissions` array. Every run still writes a trajectory, and
  its counts, timings, token figures, seeds, routes, terminations and derived cost are complete
  at every rate. Measured on a six-turn agent node over a 7,000-token corpus, a run directory
  goes from 368KB to 25KB on average at 1%. **What a project has to do:** nothing.
  `Trajectory.full()` is the default and is what every run does today. `docs/run-envelope.md`
  §7 covers it.
  - **A run that errored or suspended keeps its payloads whatever the rate.** Payloads are
    written in full as the run proceeds and dropped when it closes, so a run that crashed keeps
    them too.
  - **An evaluation refuses a sampled envelope**, because per-node accuracy and
    `absent_outputs` are read back out of each rollout's trajectory.
    `envelope.with_trajectory(Trajectory.full())` is the envelope to hand it.
  - **`not_recorded` is a distinct encoding from `unknown` and from `null`.** A payload dropped
    by sampling is not a node reporting that it did not find the value, and a reader counting
    absences would count wrong if the two shared a shape.

- **A model call's tool declarations and output schema are stored once per run.** A
  `model_call` record carries `params.tools_ref` and `params.output_schema_ref`, and the
  manifest's new `schemas` holds each block under that reference. The set offered is the same
  on every call a node makes, so a five-turn node offering four tools wrote the same block five
  times. **What a project has to do:** a reader of `params.tools` reads `params.tools_ref` and
  looks the block up in the manifest beside the trajectory. The cassette key is unchanged and
  hashes the declarations in full, so no recording is invalidated. `docs/trajectory-format.md`
  §4.1.5 covers it.

- **A `model_call`'s `provider` no longer repeats what `rate_limit` already holds.** The two
  headers the Mistral adapter parses into `rate_limit` are dropped from the passthrough, which
  stored the same two numbers twice on every call. Every other header is recorded as before.

- **A node says what it accepts by annotating its function's first parameter, and the library
  checks it.** A pipeline is refused at construction when a node reads a type nothing reaching
  it can be, and a run is refused when the value handed over is not that type. Nothing has to
  be annotated, and a pipeline that annotates nothing is refused nothing. **What a project has
  to do:** nothing, unless it wants the coverage, in which case annotate the first parameter
  and give a `Deterministic` node an `output_schema=` or a return annotation.
  `docs/pipeline.md` §3.1 covers what is compared and what it does not see.
  - **A fan-out node's input contract is checked at construction.** `over=` reads its key off a
    plain dict, so a fan-out node with more than one in-edge, or one whose predecessor declares
    an output schema, is refused before the run rather than on every rollout.
  - **An exception raised by a node function carries a note naming the node and what it was
    reading.** The exception itself propagates unchanged, so a caller catching it still does.

- **`compare_variants()` runs two versions of a pipeline against the same backend and reports
  what moved.** A variant is another `Pipeline`, so a different node kind, a node added or
  removed, a tool added or removed, a reworded prompt, a moved temperature and a rewired graph
  are all the same operation. `ablate()` generates the standard downgrades of one pipeline.
  `docs/evaluation.md` §10 covers it.
  - **The sweep says what it will cost before it makes a call.** `plan_variant()` decides which
    of the variant's calls the baseline's recording already answers: a node whose configuration
    is unchanged, and every node that can reach it, issues the requests it issued before at the
    same seeds. Removing a terminal node changes no request and runs entirely from the
    recording. **What a project has to do:** pass `max_live_calls=` to refuse a sweep larger
    than intended, which is checked before the first call rather than after.
  - **A variant comparison reports cost and tokens beside the metric deltas**, which is the
    figure a downgrade is usually for and which `compare()` alone does not carry.

- **`simple-agents check` runs the conformance suite over a project.** Six of the failures in
  `docs/failure-taxonomy.md` are checked: FT-13, FT-14, FT-01, FT-02, FT-06 and FT-07. Each
  reads files the project already produced and executes nothing. `docs/conformance.md` covers
  what each one reads and what the report means, and `simple_agents.conformance.run_checks`
  is the same run from Python.
  - **A project declares its tier in `brief.toml`.** A gate fires only when the project claims
    the tier it belongs to, and the claim cannot be read off the artifacts: the check for a
    missing evaluation fires exactly when a project claims `evaluated` and has none. **What a
    project has to do:** write one line, `tier = "prototype"` or `tier = "evaluated"`. Without
    it the command exits 2 rather than assuming one.
  - **Failure messages come from the shipped taxonomy**, so the text a coding agent acts on and
    the text the document specifies are one string.

### Fixed

- **A tool on a `Deterministic` node is visible to the evaluation.** `EvalSuite` read tools from
  `AgentNode` and `LLMNode` only, so a tool called at a fixed point through `ctx.call_tool` was
  absent from `config.tools` in the results file and invisible to the refusal that stops an
  evaluation executing something outside-reaching k×n times (FT-20). Both now read every node
  that carries tools.

- **Recording into a cassette that already holds one is refused.** Replay serves the first
  response recorded for a request, so a second recording into the same file was written and
  never read, and a replay returned the earlier run's answers under the later run's name.
  `Cassette.record` now refuses a file that is not empty and names `Cassette.update`. The
  evaluation's `hits`, `misses`, `recorded` and `diverged` counts are also summed into
  `config.cassette` in the results file, where reading them meant summing a field across every
  rollout manifest.

- **Two evaluations no longer write into one directory.** `eval_id` now includes the model, so
  two arms of a model comparison are two evaluations rather than one, and running into a
  directory that already holds rollouts is refused. A rollout appends to the trajectory it
  finds, so a second run into one directory doubled every per-node count and read the earlier
  run's model calls into this one's totals.

- **An evaluation names its run directory for what defines the evaluation**, rather than for a
  fresh uuid: the example set's content hash, the seed, the split, k, the pipeline's shape and
  the version of every prompt in it. One integer and one example set now reproduce the artifact
  layout as well as the numbers, and two versions of a pipeline compared against each other
  write into different directories. **What a project has to do:** nothing. A directory written
  by an earlier version keeps its name.
- **FT-14 no longer asks a pipeline that calls no model to pin one.** It reads the manifest's
  `observed` list, so a run that made no model call passes with the report saying why, and a run
  that made one and recorded no pin still fails.
- **FT-13 names a run directory it found outside `runs/`.** A project whose envelope writes
  elsewhere recorded everything and was told to run inside the run envelope. The failure now
  names what it found and the `--run` that reads it.
- **`python -m simple_agents.cli check` printed nothing and exited 0** on every project,
  including one with no brief, because the module had no `__main__` guard. A gate written that
  way reported success always. It now runs the same command as the console script.

### Changed

- **The manifest node entry carries `accepts`**, a digest of the type the node's function reads,
  and `null` where it declares none. Manifest format `0.8` to `0.9`. It is outside
  `graph_fingerprint`, so a suspended run resumes across a change to it the way it does across a
  changed prompt: named in `accept_changed=`, and recorded. **What a project has to do:**
  nothing. A reader of an older manifest finds the field absent.

- **The first node receives what was passed to `run` even where a cycle returns to it.** It
  previously received an `Unknown` on its first execution, and the run's inputs reached no node
  at all. **What a project has to do:** a first node inside a cycle that tested its input with
  `isinstance(inputs, Unknown)` now tests for what `run` was given.

- **A metric comparison withholds its verdict below 20 examples.** `MetricChange.moved` is
  `None` rather than `True` or `False` where fewer than 20 examples carry the metric, the
  metric is named in `Comparison.undecided`, and `verdict_reason` says how many it had. The
  delta and the interval are still reported. Where every example moves the same way the
  percentile bootstrap has no variation to resample and returns an interval of zero width,
  which read as certainty: a single example reported `moved` as `True`. **What a project has to
  do:** read `undecided` beside `moved`, and evaluate over at least 20 examples for a
  comparison to conclude anything. The count is of examples: k rollouts of one example
  resample together, so ten examples at k=20 is ten.

- **Manifest `0.7` → `0.8`, results file `0.3` → `0.4`.** A manifest node entry gains
  `sampling`, `tools`, `finish_check`, `node_budget` and `fan_out`, and the results file's
  `config.nodes` is now that same entry rather than a four-field subset of it, alongside a new
  `config.graph_fingerprint`. Nothing recorded a node's temperature or the tools it offered
  before, so a comparison between two evaluations differing in either reported a moved metric
  with no cause named. `Comparison.changed` also keys down to the node now:
  `nodes.hunt.node_kind` rather than one entry holding two whole lists. **What a project has to
  do:** re-run to produce artifacts at these versions.

- **Results file `0.2` → `0.3`.** `config.example_set` gains `held_out`, the name of the split
  that may not be inspected, and `config` gains `matches`, a version of the comparison that
  decided whether an answer was right. **What a project has to do:** re-run the evaluation to
  produce a file at this version. A comparison between two evaluations now reports a changed
  scoring rule, which until now moved every rate with nothing in `changed` naming it.
  - **`ExampleSet` takes `held_out=`**, defaulting to `"held_out"`. A project whose splits are
    called something else says so once, where it builds the set.

- **The chain of thought a model produces is recorded instead of discarded.** A backend that
  reports reasoning separately from the answer fills `ModelResponse.reasoning`, and the
  `model_call` record carries it on `outputs.reasoning`. Until now it was read off the wire and
  dropped, so a call could report more output tokens than its content accounts for with nothing
  in the record explaining the difference. Reasoning is charged as output tokens
  whether or not a backend returns it.
  - **An `AgentNode` gives the model its own reasoning back.** The assistant turn the loop
    appends carries it, and each adapter decides what its backend accepts: `VLLMClient` sends
    it, `MistralClient` drops it because the API has no field for it. Within a turn the model is
    still working on, a chat template that renders prior reasoning was previously given none.
    **What a project has to do:** nothing, and a backend that reports no reasoning builds the
    same conversation it built before.
  - **`Pipeline.run(on_reasoning=...)`** delivers the chain of thought as it arrives, on its own
    channel and independent of `on_token`. A `TokenEvent` carries `kind`, which is `"content"`
    or `"reasoning"`. A reasoning model can send thousands of tokens before its first word of
    answer, so `on_token` alone shows nothing for that whole period.
  - **The streaming Protocol gains an optional keyword.** `stream(request, on_chunk, *,
    on_reasoning=None)`. It is passed only to a `stream` whose signature accepts it, so an
    adapter written with two parameters keeps working; a run given `on_reasoning=` against one
    is refused by name. `PacedClient` republishes whichever form the client it wraps has.
  - **`reasoning=False` on an adapter stops a model producing a chain of thought.**
    `VLLMClient(..., reasoning=False)` sets `enable_thinking` in the chat template.
    `MistralClient(..., reasoning=False)` is refused at construction, because the API accepts no
    such setting and a control that reads as applied and changes nothing is worse than none.
  - **A reasoning model served without a reasoning parser is warned about once.** Its chain of
    thought stays inside `content`, where an output schema is validated against it. `VLLMClient`
    says so when a response opens with a `<think>` block and carries no reasoning field, and
    names the flag. **What a project has to do:** restart the server with `--reasoning-parser`,
    or pass `reasoning=False`.
  - **A cassette stores the reasoning**, including where its chunks fell, so a replayed
    trajectory does not differ from the live one and a replay re-emits the same pieces. An entry
    written before this decodes it as `null`. Appending to an existing cassette after the change
    counts old entries against new ones as a divergence; re-record the file rather than
    appending to it.
- **Trajectory format `0.14`.** `model_call.outputs` gains `reasoning`, an object carrying
  `text` and `blocks`, and `null` where the backend reported none. `stream` gains
  `reasoning_chunks`. **What a project has to do:** nothing, unless it reads `outputs` with a
  fixed key set.
- **A node's output can be delivered as it is produced.** `LLMNode(..., stream=True)` and
  `AgentNode(..., stream=True)` declare that a node's model calls may be streamed;
  `Pipeline.run(on_token=...)` says where the pieces go, receiving a `TokenEvent` per piece.
  Passing `on_token` is what turns streaming on, so a run given none makes the same calls it
  made before and an evaluation of a streaming pipeline is unchanged. Two refusals fire before
  the run starts: `on_token` with no node declaring `stream=True`, and a declaring node run
  against a client that cannot stream.
  - **The model seam gains an optional second Protocol.** `ModelClient` is unchanged at two
    methods. `StreamingModelClient` adds `stream(request, on_chunk) -> ModelResponse`, which
    returns the same assembled response `complete` does. Every existing adapter and wrapper
    keeps working; one that does not implement `stream` is refused by name rather than served
    an unstreamed call. Both shipped adapters implement it, and `PacedClient` delegates it
    where the client it wraps has one.
  - **A streamed response with no token counts is refused, and the refusal is waivable.**
    `MistralClient(..., stream_without_usage=True)` and the same on `VLLMClient` accept the
    loss: every count on a streamed call is then `unknown` rather than a number, `max_tokens`
    charges nothing for it, and the manifest's `stream_waivers` names the client. The message
    names both ways out and only the consequences the run actually has.
  - **A cassette stores where the chunks fell**, as offsets into the content, so a replay hands
    the callback the same pieces the recording did with no simulated timing. Streaming is not
    part of the key, so a recording made while streaming replays into a run that does not.
    Cassettes recorded before this replay as one piece and record `stream: null`.
  - **A `Suspend` raised from a model client is no longer recorded as a failure.** Its
    `model_call` record carries `error.class: "suspended"`, and on a streamed call the text
    that had already reached the end user. The call is made again from the start on resume.
- **A replayed model call reports the rate-limit allowance the live call met.** A cassette entry
  stores `rate_limit` alongside the token counts and concurrency it already stored, so a replayed
  trajectory no longer differs from the live one on that field. **What a project has to do:**
  nothing. An entry written before this decodes it as `null`, which is what a backend reporting
  no allowance produces, so no cassette needs re-recording. Appending to an existing cassette
  after the change counts old entries against new ones as a divergence, since divergence is
  detected by comparing whole responses; re-record the file rather than appending to it.
- **Trajectory format `0.13`.** `model_call` gains `stream`, an object carrying `chunks` and
  `first_chunk_ms` on a call that streamed and `null` on one that did not. Time to first token
  is derivable from no other field. `error.class` gains `suspended`, so it is a closed enum of
  three values. **What a project has to do:** nothing, unless it counts failures by reading
  `error` without checking `class`, which now counts suspensions unless `suspended` is
  excluded.
- **Manifest format `0.7`.** A `nodes` entry on a node that can call a model gains `stream`,
  and a new top-level `stream_waivers` array names the clients built to accept unmeasured
  streamed calls. **What a project has to do:** nothing. A reader of an older manifest finds
  neither field.
- **A run can stop and be continued in another process.** Three things stop one, and all three
  write the same state and are continued by `Pipeline.resume(run_id, ...)`: a `Suspend` raised
  from a tool, a node function or a `ModelClient`; `suspend_before=True` declared on a node;
  and `stop_when=` passed to `Pipeline.run`, which serves an end user pausing a session as well
  as work parked before a redeploy. `Pipeline.run` raises `RunSuspended` rather than returning
  a result whose output is `None`.
  - **A new artifact, `suspension.json`**, in the run directory, at format `0.1`. It carries
    the values in flight, the run's counters and the state of the walk, through the same
    redaction rules as the trajectory, and it is removed once the run has moved past it.
  - **A value in flight is rebuilt from the schema its node declared**, so a resumed node
    receives an `Answer` where the live run gave it one, rather than a `dict`. `Deterministic`
    gains an optional `output_schema=` so the cheapest node kind can cross a suspend point
    without being rewritten to return dicts. A value with no schema behind it must be plain
    data, refused otherwise at the point it would have been written down.
  - **A resume checks the pipeline against what the run recorded.** A change of shape is
    refused outright and cannot be waived, because the state is keyed on node ids. A change of
    prompt, route, tool version, model pin, cost basis or redaction rules is refused unless
    named in `accept_changed=`, and the waiver is recorded in the manifest.
  - **A run waiting on a clock carries `resume_not_before`.** `resume()` refuses before that
    time and says how long is left; `resume(wait=True)` blocks instead.
    `Pipeline.suspensions(run_dir)` lists what is waiting and what is ready. Nothing in the
    library counts the time down or wakes a run up.
  - **Time spent suspended is charged to no budget.** A node's wall clock is stored as elapsed
    and restarted on resume, and the manifest records each suspended interval.
- **Trajectory format `0.12`.** `node_execution` gains `resumed_from`, naming the record of the
  execution it continues, and `termination` gains `suspended`, so it is a closed enum of ten
  values. A `consultation` whose answer arrives in a later process is **two records**: the
  first written when the question is asked, carrying `resolution: "pending"`,
  `blocking: false`, and a `null` `response` and `ended_at`; the second written when the answer
  arrives, with a new `answers` field naming the first one's `record_id`. Counting
  consultations means counting the records where `answers` is `null`. **What this costs a
  project:** a reader that counted every `consultation` record now double-counts a question
  answered across a stop, and one that treats `resolution` as a closed set of four values fails
  on `pending`.
- **Manifest format `0.6`.** `outcome` gains `suspended`. Three new keys: `graph_fingerprint`,
  a digest of the pipeline's shape that a resume compares before restoring anything;
  `suspensions`, one entry per stop with `suspended_at`, `node_id`, `waiting_for` and
  `resumed_at`; and `resume_waivers`, the differences a resume was told to accept. A `nodes`
  entry gains `schema`, a digest of what that node declared it produces. **What this costs a
  project:** a reader asserting the exact key set of a manifest or of a `nodes` entry fails
  until it is updated.
- **A pipeline is a directed graph.** Edges are declared on the node. A node that declares no
  successors hands its output to the next node in the list, so a pipeline written before this
  runs as it did and needs no change. What is new is per node: `successors=` naming where the
  output goes, `route=` choosing between them, `loop=Loop(max_iterations=, then=)` bounding a
  cycle, `on_error=` naming where a failure goes, and `retry=RetryPolicy(attempts=)`.
  - A node with more than one in-edge receives a `Join`, which carries a key for every declared
    in-edge whether or not it fired. `.absent` names the ones that did not.
  - A node whose in-edges all resolved absent does not run and records
    `termination: "skipped"`.
  - A route may select more than one successor, and both arms run before a join downstream.
  - A cycle with no `Loop` is refused at construction. `max_iterations` counts per entry to the
    cycle, so a loop nested inside another gets its full count on every outer pass.
  - A `Pipeline` is a node in another `Pipeline` when given a `node_id`. Its nodes record under
    ids prefixed by it, and the container writes no record of its own.
  - `Pipeline.run(on_progress=)` takes a callback receiving a `NodeEvent` as each node starts,
    completes, is skipped or fails.
  - `pipeline.to_mermaid()` renders the declared graph.
  - **Nine construction refusals**, all naming the call that fixes them: a successor naming no
    node, an unreachable node, more than one node with no successors, no node with no
    successors, more than one successor with no route, a route with fewer than two successors,
    a cycle with no `Loop`, a `Loop` closing no cycle, and a `Loop(then=)` naming a node inside
    the cycle or outside the successors. At run time a route selecting an undeclared successor,
    or none at all, raises `CallerFacingError`.
- **Trajectory format `0.11`.** A `node_execution` gains `route`, the successors this execution
  handed its output to, and `loop`, the iteration it was on inside a bounded cycle or `null`
  outside one. `termination` gains `skipped` and `max_iterations`, so it is a closed enum of
  nine values. `outputs` is `null` on a skipped node as well as on one that errored. A node
  with more than one in-edge records `inputs` as `{"type": "join", "edges": {...}, "absent":
  [...]}`, and a node reached through an error edge as `{"type": "node_failure", ...}`.
  **Breaking:** a reader treating `termination` as one of seven values meets two more, and one
  treating `inputs` as opaque data meets two tagged shapes.
  - **A fan-out records one entry per input item.** `outputs.items` was a count beside a
    `values` list holding the successes alone and a `failures` list carrying indices. It is now
    an array with one `{"index": ..., "value": ...}` or `{"index": ..., "error": ...}` entry per
    item, in input order. **Breaking:** a reader of `outputs.values` or `outputs.failures` reads
    `outputs.items` instead. The `FanOutResult.values` property was removed at trajectory `0.10`
    and the record kept the shape until now.
- **Manifest format `0.5`.** Each entry in `nodes` gains `successors`, `route`, `loop`,
  `on_error` and `retry`. A nested pipeline is expanded into its own nodes under their
  prefixed ids, so `nodes` lists what a trajectory will hold and no containers. **Breaking:** a
  reader comparing a `nodes` entry for equality sees five more keys.
- **Results file `0.2`.** Each node gains `runs`, `reached`, `reach` and `accuracy`. `reach` is
  the rate of rollouts that ran the node, with an interval, and is reported beside every other
  figure the node carries, because a number that moved because routing changed is a different
  finding from one that moved because the node got worse. `accuracy` is reported for a node the
  example set labels through the new `Example.expected_by_node`, compared by
  `EvalSuite(node_matches=...)` over the node's recorded output. `executions` no longer counts a
  skipped node; `terminations["skipped"]` does. Each rollout gains `nodes`, saying which nodes
  it reached and which matched. `config.nodes[]` gains `successors` and `route`, so a routing
  change appears in `comparison.changed`. `compare()` gains `nodes` and `moved_nodes`.
  **Breaking:** a file written by an earlier version is refused, as every version change is.
- **`prompt_version()` is renamed `source_version()`** in `simple_agents.manifest`. It now
  records the version of a route as well as a prompt. The `prompt_version=` argument on a node
  is unchanged.

- **Trajectory format `0.10`.** The `context` object's `builder` field is renamed
  `context_builder`, which is the name the manifest already uses at `nodes[].context_builder`.
  **Breaking:** a reader of `record["context"]["builder"]` reads
  `record["context"]["context_builder"]`. Cassettes are unaffected, since they store requests
  and responses rather than records.
- **`DropOldestTurns` ships**, as the second context builder beside `AppendAll`. It sends the
  first message and the most recent turns, and records a `Dropped` entry for every message left
  out. Dropping stops at a turn boundary, so a tool observation is never sent without the
  assistant message that asked for it, which a backend refuses.
- **`AppendAll` warns when its ceiling cannot bind.** A backend that reports no prompt size
  leaves `max_input_tokens` with nothing to check against, and the run now says so once per
  node instead of proceeding as though the limit were in force.
- **`Estimate` and `message_chars` are exported**, so a context builder doing its own
  pre-flight check can report the ratio it used on the record.
- **`FanOutResult.values` is removed.** A fan-out result exposes `outcomes`, `failures` and
  `ok`, and iterating it yields one `ItemOutcome` per input item in input order. The removed
  property returned the successes alone, so it was shorter than the input sequence whenever an
  item failed, and pairing it back against the inputs mispaired them with nothing raised.
  **Breaking:** code reading `result.values` reads `[o.value for o in result if o.ok]` instead.
  The trajectory record is unchanged and keeps its `values` key.
- `docs/index.md` is new: what each shipped document covers, when to open it, and the fixed
  vocabulary. An installed copy carries the documents and had no index.
- **A class docstring is sent to the model as the schema's description.** Pydantic maps a
  model's docstring onto the JSON Schema `description`, and the library no longer removes it.
  A docstring on an output schema, on a model used as a tool parameter's type, or on any model
  nested inside either is prompt text the model reads. `json_schema_extra={"description": ...}`
  on a model replaces it. Two paths, `LLMNode` and `extract_to_schema`, already sent it while
  every other path removed it; all of them now agree. **A recorded cassette is affected:** the
  schema is part of a model call's key, so a project whose schemas carry docstrings re-records.
- **Trajectory format `0.9`.** A `model_call` gains `recorded_duration_ms`, which carries how
  long the live call took on a call served from a cassette, and is `null` on a live call. A
  compute basis charges it, so a replayed run prices at what the backend actually spent
  rather than at the microseconds the replay took. A cassette recorded before this stores no
  duration, and a compute-basis cost derived from it reports unknown rather than near zero;
  re-record to price such a run.
- **Trajectory format `0.8`.** The `node` record type is renamed `node_execution`, and the
  `seq` field is renamed `sequence`. Every other record type names the event it records, and
  the record covers one execution of a node rather than the node itself. **Breaking:** a
  reader matching `record_type == "node"` or sorting on `seq` reads neither.
- **Manifest format `0.4`.** `counts` is keyed by record type, so `counts.node` becomes
  `counts.node_execution`. **Breaking:** for the reason above.
- `docs/pipeline.md` is new, and covers the pipeline, the three node kinds, what a node
  receives, the output schema and `unknown`, and budgets.
