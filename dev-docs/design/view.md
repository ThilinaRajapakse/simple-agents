# The view

**Design of record for `simple-agents view`, the common language.** Written as `P3-35`'s item
record; **built 2026-08-26**, and
[`build-logs/the-common-language-build-log.md`](../build-logs/the-common-language-build-log.md#L1)
is how the build went and what it found. The decisions and mechanics below are standing; the
prototype history at the end is why they are what they are. `docs/view.md` is the shipped
surface and authoritative on detail.

## Where it came from

Thilina, 2026-08-26, at dogfood #5's sitting 3. His words, unedited, because the framing is in
the wording:

> designing an agentic system really isn't an easy project. I think what we are doing is
> helping, by forcing these conversations between builder and coding agent, and the checks. But
> I feel like we are missing a sort of "common language". All the docs and the briefs and the
> whatnot are a coding agent's wheelhouse. It's a lot of text, and a coding agent reads text in
> seconds. Put a few thousand lines of text in front of a human, and the typical reaction is to
> zone out and say "just do what you think is best". But the builder is the one with the idea
> for the project, the creativity, and intuition. We need to build a bridge. What we have now is
> a few lines strung over the river. I am not saying that's not helpful, it is, I am asking if
> we can do more. Off the top of my head, can we build something where we have a (mostly) visual
> design that both the builder and coding agent can look at and easily understand the parts and
> what's going on. I am thinking of literally something out of a sci-fi movie. The system
> imagined/drawn in 3D space with all the pieces of the pipeline or pipelines. Not a drag and
> drop, but a visualizer that acts as the common language and at a level of abstraction where
> both a builder and a coding agent can function.

And on the two views, the same day:

> I agree on the 2D vs 3D. And they are not mutually exclusive. Zoom in (by clicking, selecting,
> whatever) on one pipeline in the system view, you go to the 2D pipeline view.

And on who may see it, correcting a scope objection raised at the sitting:

> you are straying into dogmatic doctrine territory again. The library exists to help the builder
> and the coding agent. We provide the functionality, and the builder decides what they want to
> do with it, including showing the cool 3D scifi diagram to the user IF they want to.

**So the library ships the view and says nothing about who is shown it.** The objection raised
against it, that `simple-agents.md` §1.6 puts content on the project's side, does not apply: what
is shipped is a facility, and what a project does with the file it produces is the project's.

**Two more, added to Thilina's Corner on 2026-08-26**, verbatim. They are constraints on the
design rather than notes about it:

> - This might seem trivial, but it really isn't. It's a visualization, and a big part of whether
>   one gets used depends on how attractive (and yes, _cool_) it looks. So we need to make it look
>   the part.
> - The ability for the builder to directly add comments to part of the pipeline.

**The first is a requirement and not a preference.** A generated view that nobody opens is worth
nothing, and this item's whole premise is that the text surface loses the reader.

**And on being shown the second prototype, 2026-08-26, the reframe that now governs the item.**
The rebuild had answered the first rejection (findings first, the picture as evidence for each
sentence) and was rejected for its subject:

> Exactly. I wasn't asking for an audit mirror. I'm not saying that's useless, I am saying that's
> not the gap I was trying to close. This is a classic tunnel vision situation where something was
> built for a project and not the library (in this case for the _finished_ version of the
> project).

> What's needed is a common language so that the agent can show the builder what it's thinking of
> building, what it has built, what it still needs to build, what it thinks the final shape is
> going to look like, etc. Don't just focus on the exact things I spell out, I give examples or
> specifics to explain what I mean, not to scope.

> And from the builder's perspective, this is the tool that gives them the bigger picture without
> having to crawl through markdown files. See if the plan matches what they want to build, if what
> they said was understood correctly, and if there is something they didn't think about.

> The _run count_ is not what I was concerned about when I was trying to build the project. It's a
> useful statistic, maybe, but not a highlight. I need to see the data, where it goes, what
> happens, how, why, where the system branches, how the pieces fit together, what are the nodes
> and where, what tools are available, what gets used where etc. etc.

> It's for a builder USING the library on an arbitrary project, not just DF5.

And on whether `DF5-N2` is the moment to design against:

> That is _one_ of the moments, but it happens the whole time. It becomes harder and harder to
> keep track of everything when mountains of text pile up in multiple markdowns.

## What the problem is

**The builder's half of the bridge is text, and the evidence is that it does not carry.**
Measured against dogfood #5, where the builder read every artifact the procedure produced:

**Four of the six notes he wrote during the run are things a picture would have surfaced.**
[`runs/dogfood-5/inventory.md` §5](../runs/dogfood-5/inventory.md#L1) holds them verbatim.

- `DF5-N2`: *"It still didn't tell me exactly how it plans to wire things up. Now it does tell me
  what it uses, but not really the specifics."* That is the graph, and it is `DF5-I22`, absorbed
  into this item.
- `DF5-N3`: *"gather_candidate_pool filters the catalogue, ranks all 67,353 eligible shows, then
  truncates … It made this unbelievably dumb decision WITHOUT asking me."* A node card reading
  **in: 67,353 · out: 12** is not something a reader scrolls past.
- `DF5-N4`: *"I don't think the coding agent is making use of per node metrics."* Per-node figures
  belong on the nodes.
- `DF5-N1`: the wish to say something no question elicited. A person says it by pointing at a
  thing.

**And the run's own headline finding is a one-glance error in a picture and was invisible in
prose.** [`findings.md` `DF5-D7`](../runs/dogfood-5/findings.md#L486): the brief's
`agency_boundary` named two steps that decide for themselves, the pipeline had none, and
`simple-agents check` passed 21 times across 116 commits. In a view where a node that decides for
itself is drawn differently from one that does not, the builder sees zero of them under a claim
of two.

**The gap is standing, not momentary.** The notes above are moments; the reframe quote names the
condition: the record accumulates across `idea.md`, `research.md`, `design.md`, the brief and the
build log, and keeping track of what is planned, built, changed and owed gets harder every day of
a build. The view is the standing map a builder returns to, not an artifact of any one gate.

## The reframe, 2026-08-26

**The subject of the view is the design, and what happened at runtime is one overlay on it.**
Both prototypes inverted this: they read `runs/` because run manifests were the richest artifact
on disk for the one finished project available, and each produced an instrument useful at the one
point in a project's life where the bridge is least needed. Prototyping only against
`dogfood-5-frozen` selected for a tool shaped like a finished project, which is the tunnel vision
the reframe quote names.

What the view is instead, over the whole life of an arbitrary project built with the library:
the coding agent shows the builder what it proposes to build, what exists, what changed, what is
still owed, and what the final shape is; the builder checks that the plan matches what they want,
that what they said was understood, and sees what nobody thought about. The content is the
system itself: the steps and their kinds, the data and where it flows, the branches including the
failure branches, the tools and what uses them, the resources shared between pipelines, the seams
where a person is asked and where the end user meets it.

## What is decided

All 2026-08-26, at the reframe conversation.

1. **Drawn from introspection and the brief, never maintained by hand.** The proposal is code:
   the coding agent writes the pipeline skeleton early, and the view imports `agent.py` under a
   factory convention and introspects `Pipeline` objects without running them. Things decided but
   still shapeless appear as ghosts sourced from the brief, exact once `P3-29`'s `produces` lands
   (a decision whose `produces` names nothing yet in code is a ghost). Thilina's reason for
   choosing this over a maintained plan file: *"the view is generated, not drawn, so less risk of
   drift."* Nothing in the library imports project code today (`simple-agents check` reads only
   files), so this is a first, and the convention requires import to be effect-free.
2. **Resources are declared.** A tool names what it touches (`touches="catalogue"`), direction
   derived from its declared side-effect class; `Deterministic` may declare it too, for code that
   touches a resource without a tool. Flows between pipelines are then computed facts: one
   pipeline's tools write a resource that another's read. Without this the system level is
   geometry with nothing true to say. Inference was rejected because resources across arbitrary
   projects are anything: a database, a file, an inbox, a third-party API.
3. **Four levels, adapted to the project's shape, statuses everywhere.** *(Amended
   2026-08-26 after a rendered review: the product level opens the page as the builder's stated
   purpose, intended user and useful outcome. It is a small orientation card rather than a
   separate diagram, so the map still starts at the level the project actually has.)* Product (what the end
   user meets, where the agent can stop and ask, what artifact is kept), system (pipelines,
   resources, flows, triggers, seams), pipeline (the graph: steps, branches, loops, the data on
   every edge), step (kind, schemas in and out, tools with side-effect classes, budget, status,
   and the builder's own recorded decision via `P3-29`). Every element carries a status: planned,
   built, changed since confirmed, proven by runs. The levels derive from what the project
   declares: a one-pipeline project opens at the pipeline level, a batch project has a near-empty
   product level and the view says so plainly instead of rendering empty furniture.
4. **The return path is a comment record, and gate behaviour is the builder's toggle.** Thilina:
   *"Can we let the builder decide? So basically a toggle to say, refuse to advance without
   resolving."* Gates always report open comments; a brief key the builder sets decides whether
   gates refuse over them.
5. **The page relays; the coding agent records.** Added 2026-08-27, on Thilina's
   instruction to build the live tool in full: *"can the builder answer outstanding
   questions directly in the viewer? or maybe amend previous answers?"* and *"Implement the
   live version. the actual tool that we want. not a half assed version."* The served page
   takes a comment on any element, an answer typed on an open question, and an amendment on
   a recorded answer or decision; each is a thread in `comments.toml` with a snapshot of
   what the writer was looking at (`about`, `stage`, `shape`, `when`), and replies
   accumulate under it from both sides. **Nothing the page writes reaches the brief**: an
   answer or amendment is the builder speaking without waiting to be asked, and the coding
   agent still does the asking (scaffolds, follow-ups) and the recording. That is how this
   sits beside the glossary rule that the library never asks the builder directly: the page
   shows the questions and relays the words; the elicitation stays the coding agent's. The
   glossary sentence in `CLAUDE.md` reads narrower than this and is Thilina's to amend.
6. **Validation is a set of project shapes, not one project.** Fixture projects for: day zero
   (a brief in progress, nothing built), mid-build (some steps real, some `NotBuilt`, decisions
   changing), a single-pipeline tool, a many-pipeline system with shared resources, a batch
   project with no end-user surface. `dogfood-5-frozen` is test data for the finished
   many-pipeline shape only. **A sixth was added at `P3-40`, 2026-08-27**: `branching`, which
   carries a three-way route, a bounded loop, a fan-out, an error path, a nested pipeline and
   joins, with a live Gemini run and a live evaluation committed beside it. Every hard shape
   the drawing has to survive is in one project, and the rank layout had never met one.
   **A seventh was added at `P3-42`, 2026-08-28**: `skeleton`, `branching`'s pipelines with
   every callable a `NotBuilt` marker, which is the page a builder meets at the `shape` gate
   and the one shape none of the other six holds. `scripts/view_at_stage.py` derives a
   `shape` page by subtraction and so shows twelve built steps; the fixture shows thirteen
   owed.
   [`test_view_at_shape.py` `TestPinnedToBranching`](../../tests/test_view_at_shape.py#L43)
   pins its node ids, kinds, edges, error paths, fan-out, tools, `touches` and budgets to
   `branching`, so a second graph cannot drift from the first.

**All four decided at `P3-40`, 2026-08-27**, which is where the item record left them open.

7. **What a step is handed is derived, and "whatever came before" is not an answer.** It is
   computed from the steps whose edges reach it: one edge names the step and the schema it
   carries, several name a `Join` with a key per edge, an error edge names the `NodeFailure`,
   and a step nothing reaches takes what the run is given, or what its own pipeline is handed
   where it opens a nested one. Beside it the page carries **one real value from the newest
   run**, 220 characters a field over at most eight fields, labelled with the run it came from
   so it reads as one run's value rather than as a schema. A record over a million characters
   is reported by its size and never parsed.
8. **The evaluation lands on the page at both levels.** The page reads the results file the
   gates read (the brief's `results`, or the most recent), keeps every figure's definition,
   denominator, interval and left-out counts, puts per-node figures on the steps, and says
   what was never reached, never scored and never measured. Where the suite declared a
   `baseline=`, the floor travels with the figure as counts, because an interval around a
   floor is a bootstrap the page does not run and a rate without one is what FT-06 refuses.
   Both levels, because a builder asks "how good is it" of the system and "which step is
   wrong" of a step.
9. **The drawing opens in place.** A step in the graph expands to its facts without leaving
   the picture; the rail card keeps the schemas field by field, the recorded decisions and the
   conversation. Ranks skip a cycle's closing edge and a layered column assignment puts each
   step under the steps that feed it, which is also what makes a nested pipeline's frame a
   tight box. A graph wider than its panel scrolls sideways and says so.
10. **The data path is a section, not an overlay.** One row per step in graph order: what
    enters, what each step receives and produces, the resources it reads and writes, and what
    leaves. Chosen over drawing it on the graph, which already carries branches, loops and
    error edges.

**All six decided at `P3-41`, 2026-08-28**, at a sitting where six of the seven strands were
Thilina's to settle.
[`build-logs/what-the-picture-cannot-say-build-log.md`](../build-logs/what-the-picture-cannot-say-build-log.md#L1)
§2 has the options each was chosen against.

11. **A node records what its own code did to a store, and records the value.** The library
    already held that an unrecorded store read is a defect: `memory.py` has no `ctx.memory`
    because "a value read from a store that no record names cannot be explained from the
    trajectory". `touches=` named that hole without closing it, so the completeness of the
    data view turned on whether a project happened to reach a store through a tool.
    `ctx.record_access` closes it, and `touches=` moved to all three node kinds because a
    prompt function is plain code too. Trajectory `0.28`, and a describe callable stays
    declined: it is empty at `shape`, which is the stage that most needs a store card, and by
    `build` the record says what actually came out.
12. **The whole record is read, not the newest run.** What a step costs, how often each edge
    is taken and every access to each store are questions about the system rather than about
    one run. Measured at 4.3 seconds over 2,393 runs and 2.54 GB, in a page that takes 6.5
    seconds to build for that project against 1.4 before, and every figure is keyed by the
    basis its runs declared. **Cost per unit
    is exact only where the unit is declared**: `over=` declares a fan-out's, and a recorded
    access carries a store's. Nothing divides by a count nobody declared.
13. **The drawing's geometry carries two things and they never compete.** Edge width is how
    often that edge was taken, which makes the spine of the system draw itself and is the one
    genuinely geometric encoding available; a bar inside each step carries one figure, chosen
    from what the record can fill. Box height was already spent on expand-in-place, border
    weight now says status, and colour was already spent on severity. Two controls say what
    the drawing is over and what the bar shows, so one picture answers "what should I make
    cheaper" and "where do the runs go" without either being baked in.
14. **One frame, one glyph tile, three related marks.** Thilina's, against a first proposal of
    three arbitrary outlines: *"The shapes for the three node kinds are chosen pretty
    arbitrarily."* Code, then a model, then a model that loops. It scales to a fourth kind by
    a fourth glyph, survives being small far better than a corner radius, and frees the
    outline to mean status alone. Drawn SVG rather than emoji: emoji carry their own colour,
    render differently per platform, and this page is printed and screenshotted.
15. **A run walks in three places.** The page carries the newest run of each shape and the
    rollouts that came out wrong; the served page reads any other on demand; and
    `simple-agents report <run> --walk` prints the same walk for a reader in a terminal. Both
    surfaces, on Thilina's call, because they are two readers.
16. **The picture is dated as well as the answers.** `shape_confirmed` holds one
    `graph_fingerprint` per pipeline. `design/view.md` said confirmations would record what
    they were shown against and `P3-35` never built it, so "changed since you agreed" was
    measured against the last run, which at `shape` is nothing. The confirmed *step list* is
    deliberately not stored: that puts a copy of the graph in the brief, which is the drift
    the view exists to remove, and per-step change comes from the run ledger.

**Decided at `P3-42`, 2026-08-28.**

17. **The check that counts unbuilt steps reads the project's code.** Every other check reads
    files, and [`docs/view.md`](../../docs/view.md#L32) states it: *"the checks read files,
    `view` additionally imports the project's code, and a project whose code does not import
    still deserves its report."* FT-40 is the exception. Its subject is `NotBuilt`, which is a
    declaration in `agent.py`; the manifest is a record of a run, so a check reading only the
    manifest can never see a project that has not run, and a project that has not run is
    exactly the project with unbuilt steps. **Measured 2026-08-26**: over `skeleton`, whose
    every one of thirteen steps is a placeholder, FT-40 reported `n/a` at `shape`, `build` and
    `measure` and `pass` at `ship`, where `ft_14`, `ft_15` and `ft_25` all report `blocked` on
    the identical missing input. It now counts at every stage and fails from `ship`, which is
    the shape this record has assumed since `P3-35`. **The guarantee the rule protects is
    kept**: [`run.py`](../../src/simple_agents/conformance/run.py#L505)
    `_pipelines_in_the_code` is guarded, and code that will not import, or that declares no
    pipeline the convention can find, falls back to the manifest and the report names which
    it read. Reading `agent.py` inside `check` is not new exposure: `_regenerate_the_view`
    already imports it in the same process, and the second import measured 1ms.
18. **A question is named for the builder wherever a page would print its brief key.**
    Thilina, 2026-08-28, on the rendered answered-entries list: *"we need human understandable
    and readable names for the questions."*
    [`elicitation.py`](../../src/simple_agents/conformance/elicitation.py#L34) `Question`
    already said the key *"is not text to put to the builder"*, and the page printed
    `what_it_does`, `used_through`, `agency_boundary` as headings. `Question` gains a required
    `title`, so the 48th question cannot ship without one, and `ask` travels with it: the
    heading is the question named short, the line under it is the question as it was put. The
    key stays the address a thread is filed under in `comments.toml`, so nothing about the
    comment record moves. A brief entry the library never asked for has its own key spaced and
    capitalised, and a decision, which the project names itself, gets the same treatment.

19. **The system level uses the pipeline level's encoding, one level up.** Thilina's call,
    2026-08-28, over drawing structure instead (box size is step count) and over baking run
    count in with no controls. **A link's width is what that pipeline moves through that store
    per run of it**, and the totals are on the store's card, also his call: a total draws its
    thickest line for the pipeline that ran most often, which is a fact about how often it ran
    rather than about how much it leans on the store. **A bar inside each pipeline box carries
    the selected measure**, summed over its steps, under the same two controls. Chosen because
    it is the only option that degrades at `shape`: with nothing recorded there is no bar and
    no width, and the boxes carry status and step counts, where an encoding keyed on run count
    draws every box the same size at the stage the view most matters. `flow` on each resource
    card, in [`assemble.py`](../../src/simple_agents/view/assemble.py#L497)
    `_give_resources_the_record`, is one end of every link.
20. **A design nobody has agreed to says so.** Found by reading the `shape` page as a builder,
    which the `skeleton` fixture made possible. The page said *"Changed since you agreed to
    it"* and *"Still the shape you agreed to"*, and where no confirmation existed it said
    nothing: `shape_moved` is `null` then, and both branches were `true`/`false`. **That
    silence is the normal state at `shape`**, which is the gate this whole item was built for,
    so a proposal read as a design already settled. It is now the page's first finding at
    `shape` and a note after it, and it is `DF5-D7`'s shape again: an absence that passed
    quietly. The gate already knew (FT-34 fails on it); the surface the builder reads did not.

**Added 2026-08-27, on Thilina's readability audit of the rendered page.**

22. **The page is measured in a browser, and the floors are what the measurement produced.**
    Thilina: *"Some text is miniscule. Some are overlapping. Some arrows are barely visible.
    And that's not all. Do a full audit."* Measured in headless Chrome at four widths and both
    themes, and every complaint was real and larger than it looked: the graph was scaled to
    0.78 on a 1440 screen so its 9.5px labels rendered at **7.4px**, and widening the window
    never helped because the page capped at 1500px; four pairs of labels overlapped, one of
    them (`more +` against a step's name) deterministically for any name over 20 characters;
    the lines a reader follows were drawn in the border colour at **1.3:1**, where 3:1 is what
    a shape needs. `--faint` failed as text in both themes, at 3.85:1 dark and 2.61:1 light.
    **The floors now are 11px for anything in a drawing, 4.5:1 for text and 3:1 for a line**,
    and [`tests/test_view_readability.py`](../../tests/test_view_readability.py#L1) holds them
    by parsing the stylesheet, so a sixth palette is checked by being added. Three of the
    audit's suspicions measured clean and are recorded here so they are not re-opened: nothing
    is clipped by overflow, no control is under 24px, and the widest strokes at 1:1 are the
    transparent hit areas working as intended. **Added 2026-08-29:** a page is read at 1440px
    and 1920px, still and served, before it is called read. Each of the six stage pages had
    been read at 1500 to 1800px, and at 1440px the rail sat under the drawing with the right
    half of the page empty. Thilina: *"the width needs to work correctly on laptops and
    standard desktops."* The rail sits beside the drawing from 1280px up; where the drawing
    needs the whole width it says so (`drawGraph` sets `stacked`) and the rail's two panels
    sit side by side under it. **The map no longer breaks out of the text column** (it took
    1700px against the column's 1500px, which read as misaligned on a wide monitor: Thilina,
    on the writing panel sitting 130px left of the cards, *"This is misaligned and looks
    sloppy"*), and the rail is a share of the window, 320px to 440px, so a wide monitor
    gives the card room as well as the drawing.
23. **Five palettes and a picker, because a tool nobody opens is worth nothing.** Thilina:
    *"I guess a theme toggle would be nice. Can we add some more themes while we are at it.
    This one looks a bit depressing."* Paper and dawn are light, forest is what shipped, slate
    and midnight are dark. The CSS carried `[data-theme]` support from `P3-35` with nothing
    to set it, so this is that mechanism finished rather than a new one. **A colour in the
    drawing is resolved to a literal at the moment it is drawn**, so the picker redraws the
    page rather than restyling it; the system-change listener already did this and is why the
    bug never showed. The choice is kept in the reader's own browser, and a browser that
    refuses storage loses it at the next reload rather than failing.
24. **A step's name and the affordance beside it share one line, so the name's budget comes
    from what the box has left.** It was truncated at 22 characters against room for 12. The
    same pass gave every truncation a word boundary and a `title` carrying the whole of it,
    and gave the drawing a label placer that keeps a record of what it has already written:
    a route's arms, a failure path and a container's caption were each placed from their own
    geometry and knew nothing of the others.

25. **A step's card reads in three bands, and every level looks like what it is.** Thilina,
    on the card as it stood: *"Even I am not sure what some of these things are... even when
    the things are expanded, it's very difficult to follow, because there are no markers and
    no levels."* Eleven collapsibles sat in one flat list, each styled in the same small
    uppercase as a plain heading, and `summary{display:flex}` had silently dropped every
    `::marker`, so a control and a label were the same object to look at. **The card is now
    how it is wired, what it has done, and what has been said**; a band is a heading and never
    a control, a row inside one opens and carries a marker, and a row inside a row is indented
    under it. **A shut row says on its right what it holds** (`→ Reply`, `4 limits`, `6 lines`),
    which is what lets a reader skip it without opening it. The fourth level came out: "The
    code it runs · 6 lines" opened onto "The code · 6 lines".
26. **What waits on the builder is separated from what is worth knowing.** Thilina: *"clicking
    Open answer_directly jumps to the node, but then what are you supposed to do? What's the
    purpose of this?"* There was none: `answer_directly: decides for itself` is a fact about
    the design, and it sat under a heading promising eight items needing attention. **A finding
    carries `waits` naming the act where there is one** — read the thread, answer it, walk the
    drawing — and those sort first whatever their severity; the rest go under "Worth knowing",
    shut. `branching`, a finished project, reported eight items needing attention and now
    reports none, which is the true answer. Mixing the two taught a reader to skip the count,
    and the count is the first thing on the page.

27. **A system is many pipelines and many stores, and both drawings assumed one row of each.**
    Thilina asked whether a multi-pipeline project was handled; measured against eight
    pipelines and nine stores, it was not. **Four store capsules were drawn outside the system
    map**, spanning x=-189 to x=1369 in a frame 1,180 wide, and **a pipeline reaching all nine
    put three of them below the bottom of its own graph**, whose height was measured from its
    rows of steps alone. Neither was clipped or scrolled to: they were painted where the frame
    is not. Both rows wrap now, the map takes the width the panel has rather than a number
    written into it, and a graph's frame is as tall as whichever of its two sides is taller.
    `view_projects/wide-system` is the shape, and
    [`tests/test_view_wide_system.py`](../../tests/test_view_wide_system.py#L1) holds it by
    reading the geometry back out of the drawn page.
    **Crossing links are a different problem and are not solved.** Once pipelines wrap, a link
    from an upper row passes behind the boxes below it: 11 of 23 do on that project. Drawing
    every pipeline on one row removes all of them and makes the map 1,726px wide, which trades
    a readable picture for a scrolling one. What is done instead is that **the selected
    pipeline's links are drawn at full strength and the rest are held back**, so the shape of
    the whole system stays on the page and the one being read is followable through it, and
    the note under the drawing says so. Ordering the stores by the average position of what
    touches them is one barycentre pass and is kept, though on that project it moved the count
    by one.

28. **Words on the page are sentence-cased; a name keeps its spelling and is set in
    monospace.** Thilina, 2026-08-29, on the shipped measure page: *"why are there sentences
    that are not sentence-cased? Wtf is that."* It was never decided: the first prototype set
    two kinds of thing in lowercase, an identifier the code spells (`measure`, `held_out`, a
    step's id) and a badge fragment (`evaluated`), and every later slot that inherited those
    styles was filled with lowercase text, so whole clauses ended up there ("the project is
    at measure", "calls made live", "show on the drawing", "walk it"). **The rule, approved
    the same day:** anything a person reads as words, a heading, a button, a badge, a caption,
    a tile's label, a control, is sentence-cased; only a name the code spells (a step, a file,
    a figure's id, a stage's key) keeps its spelling, and it is set in monospace so a reader
    can tell a name from a word. Applied to the measure page at
    [`P3-60`](../build-logs/the-measure-page-as-a-visualisation-build-log.md#L1); the shared
    chrome (the stage strip's lowercase stage names, "the project is at measure", the dials'
    lowercase options) and the other pages take it as each is redesigned under the process
    below.

29. **A title is a noun phrase, and a label says the plain thing.** Thilina, 2026-08-29, on
    the sitting that designed the remaining pages: *"Can you make the language less AI
    slop?"* Struck from the wireframes: "nobody agreed to" (write *unconfirmed*, *not
    agreed*, *undecided*), "the numbers it runs on" (write *Constants* or *Parameters*),
    "what this turns on" (write *The deciding factor*), "where the build departs from the
    design" (*Build inconsistent with the design*), "what waits on you" (*Waiting on you*),
    "read it as a story" (*The story*). **The rule:** a region's title, a column heading, a
    button and a badge are plain noun phrases, never a "what/where/who …" clause and never a
    rhetorical construction; and he named those six as the ones he happened to read, so the
    rule is applied to every label on a page and not to those six.

    **Extended 2026-08-29**, on the pages as built: *"Write this like a human. Never use the
    construction 'Nobody does…', 'Nobody agreed…', 'Nobody saw…'. Don't string multiple
    clauses together unnecessarily with commas. Split into sentences."* His three rewrites,
    which are the standard:

    | Was | Is |
    |---|---|
    | A question put off is counted where it is answered, so a deferral reads as a deferral rather than as an omission. | A deferred question is counted when it is eventually answered, so it shows up as deferred rather than missing. |
    | idea.md is what the next session reads first, and it is written from the answers above. | The next session reads idea.md first. It is generated from the answers above. |
    | Nobody opens a window; the claimant gets a notice and approved claims land in the ledger. | The claimant receives a notice, and approved claims are added to the ledger automatically. |

    Applied to every sentence on the page, the findings, the question texts and the fixture
    briefs the same day; `prose_check`'s `nobody` rule holds the construction out of shipped
    text, and `tests/test_view.py` holds it off the rendered page. "What this turns on", the
    question title, is *The deciding factor*; the `research.md` section heading of the same
    words is an artifact format and is in [`plan.md` §2.2](../plan.md#L1).

**Considered and rejected at `P3-42`, 2026-08-28.**

- **A trigger declared on `Pipeline`.** Proposed as `trigger=` with the four kinds
  `docs/product.md` §6 already names, joining `used_through`'s answer to the pipeline it
  belongs to. Thilina: *"I don't think this is worth adding another argument to pipeline.
  Besides, the trigger may not always be static."* The second half is the reason that settles
  it: a pipeline can be started by a request today and a schedule tomorrow, and by more than
  one thing at once, so a value frozen in a constructor would be a declaration the page
  repeats as fact while the project has moved. **What would reopen it** is a way to observe
  what started a run rather than declare it, which nothing records today.

**Added after the build, 2026-08-28, on Thilina's** *"just add node in the test suite then"*.

21. **The page's script is executed by the suite.** About 3,000 lines of JavaScript ship inside
    the wheel and nothing ran a line of it: every other test reads `assemble`'s output or greps
    the rendered markup, and a control that hid the one measure `many-pipelines` had went out
    under a green 3,353-test run. [`tests/view_harness.mjs`](../../tests/view_harness.mjs#L1)
    runs one rendered page under a DOM small enough to read in a sitting, then drives every
    control: each pipeline, each step, each store, each measure, each population.
    **It was checked against three deliberate regressions** rather than trusted for passing,
    which is `simple-agents.md` §1.6's requirement applied to the harness itself. It is not a
    browser, so what it establishes is that the page runs and what it chose; how it looks is
    still read by eye, and the cool-factor constraint is judged the same way it always was.
    `node` is pinned in CI and the tests skip without it, which is how the cassette tests
    already handle a missing prerequisite.

**Found by dogfood #6 and fixed the same day, 2026-09-01.** Two reports from the builder
mid-run: the answers on the research page were cut, and *"the pipeline disappeared once build
started"*.

30. **A project's virtual environment is inside the project, so "under the project root" does
    not mean "the project's own".** `simple-agents view --serve` lost the drawing after its
    first render, and a malformed `brief.toml` killed a request with a traceback instead of
    landing in `problems`. One cause.

    [`discovery.py`](../../src/simple_agents/view/discovery.py#L217)
    `_drop_the_projects_modules` forgets the project's modules after loading it, so that a
    registration in a module beside `agent.py` runs again on the next load. It decided a
    module was the project's when its file resolved inside the project directory. `uv` writes
    the environment to `<project>/.venv`, which put every installed package inside the project
    directory: **183 modules on that project, `simple_agents` among them.** The library
    unimported itself on every load.

    Both symptoms follow. The registry `agent.py` registers into is a module-level dict, and a
    re-imported module has a new one, so the second load read an empty registry and reported
    no problem: `imported: True`, `problems: []`, three pipelines and then none. And
    `ConfigurationError` re-imported as a second class object, so `except ConfigurationError`
    in [`assemble.py`](../../src/simple_agents/view/assemble.py#L41) `_brief_data` stopped
    matching the error `brief.py` raised.

    A module is the project's own when it is under the project root, outside `site-packages`
    and `dist-packages`, and outside the library's own directory:
    [`discovery.py`](../../src/simple_agents/view/discovery.py#L181) `_the_projects_own`.
    **The docstring already said this** — "the library's own, and every installed package,
    stay imported" — and the path test did not implement it, which is why nothing read as
    wrong. `tests/test_view.py`'s
    `test_a_project_holding_its_own_environment_keeps_the_library_imported` builds that layout
    and fails without the fix.

    The general form, and the reason this is worth a decision rather than a line in a build
    log: **a check written against a directory boundary is not a check against ownership.** A
    project directory holds what the project installed as well as what it wrote.

    A failed import is now said where it is seen. The empty frame names the error rather than
    reading "Registered pipelines: none", which blamed the project for declaring nothing, and
    [`findings.py` `_the_code_would_not_import`](../../src/simple_agents/view/findings.py#L158)
    puts it first among the findings.
    [`discovery.py`](../../src/simple_agents/view/discovery.py#L123) `_would_not_import`
    records the two forms: the error alone for the frame and the card, and the sentence saying
    what the page did about it for `problems`.

31. **Text is carried whole and cut where it is drawn.** The page cut every piece of builder
    prose in Python at a fixed character count: brief answers and decisions at 600,
    `research.md` sections at 600 and 800, `idea.md` at 1200, decision reasoning at 300.
    Dogfood #6's five research answers were 1,013 to 3,687 characters, so **7,805 of 10,405
    characters never reached the page**, and one `because` lost 89% of itself. Nothing marked
    a cut. The questions cell also had no `white-space`, so nine labelled parts written over
    twelve lines drew as one run-on line.

    A cut in the data layer is permanent: the page never receives what was removed. **The data carries the whole of the text
    and the page decides how much of it to show**, which it can do because it knows the width
    it has and the reader can act on it.

    Two forms, and which one applies follows from what the text is drawn as.

    - **A paragraph** — a question's answer, a decision, a `research.md` or `idea.md` section
      — is [`template.html`](../../src/simple_agents/view/template.html#L4444) `longText`. It
      renders whole with `white-space: pre-wrap`, clamped to 10.5em with a fade, and a **Show
      all of it** under it. Expanded rows are held in a set across re-renders.
    - **A summary** — the masthead, a step's rail, a table cell, a tooltip — is
      [`template.html`](../../src/simple_agents/view/template.html#L4435) `short`. It cuts at
      a word, ends in an ellipsis, and hands the whole to the `title` beside it. The page the
      text files under holds all of it.

    **The clamp is measured, never counted.**
    [`template.html`](../../src/simple_agents/view/template.html#L5824) `renderSections`
    compares `scrollHeight` to `clientHeight` after the render and adds the control only where
    the text is taller than the row shows. A line the builder wrote can wrap into several and
    how many depends on the reader's width, so a line count would put a control on rows that
    do not need one and miss rows that do. Under a stub DOM both are zero, which degrades to
    showing everything, and that is what a non-visual reader wants.

    **`renderSections` measures `#lead` and `#sections` and not `#map`.** A `longText` in the
    step rail would stay clipped with no control, so the rail is `short` territory. This was
    found by building it the other way first.

    **Decision 24 is extended by this.** Its rule was right and was applied to the drawing
    alone. It now holds everywhere: no cut in the view lands mid-word, and every cut says that
    it cut. [`words.py`](../../src/simple_agents/view/words.py#L14) `_clip` is the Python half
    and `short` the page half.

**`findings.py` was split the same day**, on the shape ratchet rather than on a reading: a
finding family is a function, so the module grew with the page's vocabulary and stood at 1,191
lines. The seam was already in the file: the measurement families end at a separate entry
point that the family loop does not carry.

| Module | Holds | Entry point |
|---|---|---|
| [`words.py`](../../src/simple_agents/view/words.py#L14) | The formatters used by more than one family | `_clip` |
| [`measured.py`](../../src/simple_agents/view/measured.py#L295) | Everything over an evaluation's results file | `_measure_findings` |
| [`findings.py`](../../src/simple_agents/view/findings.py#L833) | Every other family, and the assembly | `_findings` |

One direction throughout: `words` then `measured` then `findings`. The baseline did not move.

## Mechanics

- **`NotBuilt`, not a flag.** `planned=True` was proposed and rejected: *"planned=True sounds
  ambiguous to me."* The marker moves to where the hole is: a sentinel standing in the callable's
  slot, carrying the step's intent in words::

      Deterministic(NotBuilt("filters the catalogue to eligible titles and ranks them"))
      LLMNode(NotBuilt("writes the recap from the watched summaries"), output_schema=Recap)

  It cannot be ambiguous because it occupies the position of the thing that is absent; the view
  renders the node dashed with its intended behaviour on the card, so a skeleton is readable;
  running one raises `ConfigurationError` naming the node; the `ship` gate fails while one
  survives.
- **The comment record, as built 2026-08-27.** `comments.toml` (format `1`) beside the
  brief: one `[[comment]]` thread per thing said, carrying `id`, `at` (the address every
  element shows: step, edge, pipeline, `resource:`, `question:`, `decision:`, `project`),
  `by`, `kind` (`comment` | `answer` | `amendment`), the words verbatim, the snapshot
  (`about`, `stage`, `shape`, `when`), `status` (`open` | `addressed` + `addressed_by` +
  `addressed_when` | `withdrawn`), and `[[comment.replies]]` turns from either side.
  Writers (`append_comment`, `append_reply`, `set_status`) rewrite the file atomically
  through JSON-escape TOML strings, so anything typed round-trips. The served page writes
  the builder's side; `simple-agents comments` is the coding agent's inbox.
- **The gate generates the view.** `simple-agents check` runs at every gate; generating the view
  inside the check run makes a stale view impossible, and the coding agent's job reduces to
  showing it.
- **Confirmations record what they were shown against.** `graph_fingerprint` exists in the
  manifest already; computing it from the introspected pipelines lets `design_confirmed_at`
  record the fingerprint the builder confirmed. "Changed since you confirmed" then becomes exact,
  and a check can say the builder agreed to a different system than the one shipping, which is
  `DF5-D7`'s general form and an `FT-38` sibling (same shape as "a brief nobody re-read", applied
  to the picture).
- **Edge data.** Every out-edge today carries the producing node's whole output
  ([`plan.md` §2.2, the per-edge entry](../plan.md#L475)), so an edge honestly shows the
  producing step's output schema, fields behind a click. **Built for that entry landing**, on
  Thilina's instruction at `P3-41`: *"build this assuming the per-edge thing will land soon.
  So even if it appears over-engineered right now, that is fine."* The edge card holds a
  per-edge slot that today is filled with the one shared object and carries the sentence saying
  what separates two arms is which fired. **What actually travelled is read from the receiving
  end**: a step with several in-edges records a `Join` with one entry per declared edge, so
  per-edge truth is already on disk.
- **An edge is countable only where its source recorded a route.** A nested pipeline's last
  step routes inside its own graph and the container writes no record of its own, so an edge out
  of it can never be counted. The drawing shows no count there rather than "never taken", which
  is the worse of the two errors.
- **The command.** `simple-agents view` writes one self-contained HTML file, regenerated at every
  gate and on demand. A `--serve` live mode is a later stage; `watch` is the CLI precedent.

## What the view carries beyond what was asked

Found by looking, per the reframe's instruction that examples explain and do not scope:

- **The change ledger opens the page.** Once a confirmation exists, the first thing shown is
  what changed since the builder last confirmed: steps added or removed, decisions with status
  `changed`, schemas that moved. This is the "mountains of text" problem made computed.
- **A "to done" panel.** What is still owed is computable, not asserted: `NotBuilt` nodes
  remaining, required questions still open or deferred to a stage now reached, open comments.
- **Failure paths are branches.** Every node declares `on_error`, `retry` and
  `consultation_route`; where the system can fail and what happens next is drawn with the same
  weight as routes, and a step with no declared failure handling is a visible absence.
- **Where money can leave.** Tools declared `SPENDS_MONEY` plus node budgets give a map of every
  point that can spend, with its cap or its lack of one. `DF5-N3`'s class of surprise, visible
  before it happens.
- **Measurement coverage, at `measure`.** `judged_steps` and `judged_path` say which parts of the
  system an evaluation exercises; the overlay shows what has never been measured.
- **Absence as a first-class finding.** A resource written that nothing reads, a consult channel
  no step holds, an empty product level. The view cannot know what a builder did not think about;
  it can make every hole visible, which is the mechanism for finding out.
- **Findings first survives the reframe**, with the sentences changing per stage: at `shape`,
  "two steps will decide for themselves, both can ask you a question" and "these four steps trace
  to no decision you agreed"; at `build`, the change ledger; at `measure`, the coverage holes;
  the run overlay's sentences arrive last and matter least.

## The instruction surface

Thilina's requirement: the coding agent is instructed to use this *"basically everywhere"*.
Instructions go at the points of use, and two mechanisms make freshness structural rather than
remembered (the gate generating the view, and fingerprint-pinned confirmations, both above):

- [`docs/procedure.md`](../../docs/procedure.md#L1) stage texts gain their view moments: at
  `shape`, the FT-34 iteration happens over the view (show the skeleton, not prose about wiring);
  at `build`, regenerate when presenting anything structural; "what to settle first, and what to
  keep doing" gains: when the builder asks where things stand, the answer is the view.
- A `docs/view.md` owning the command, the levels, the statuses and the comment record, with its
  row and condition in `docs/index.md`.

## What has to be decided

Still open; everything above the previous heading is settled.

- The factory convention's exact shape (decorator vs module-level dict), decided at build. The
  name it registers is also what a manifest could record for resume, which is the one question
  [`plan.md` §2.2's supervisor entry](../plan.md#L462) says decides it: that entry now has a
  second customer.
- Trigger declarations (what causes a pipeline to run). Sourced from the brief and `design.md`.
  **A declaration was proposed and rejected 2026-08-28**, under "Considered and rejected"
  above: a trigger that can change is not a value to freeze in a constructor.
- ~~The system level's dimensionality.~~ **Built 2026-08-28** at `P3-42`, and decision 19
  above is what it became: the pipeline level's encoding one level up, with a link's width
  read per run.
- ~~What `check` does with `NotBuilt` at each gate before `ship`.~~ **Built 2026-08-28** at
  `P3-42`, and the assumed shape is what it became: expected at `shape`, counted at `build`,
  failed at `ship`. Decision 17 above is what it cost.
- ~~The served mode and direct in-page comment writing.~~ **Built 2026-08-27**:
  `simple-agents view --serve` on stdlib `http.server`, 127.0.0.1 only; the page polls a
  project-state token and re-renders in place, preserving selection, open sections and
  drafts.

## Build order

1. This record.
2. The comment record and gate reporting (no collision with anything live).
3. The factory convention and `simple-agents view` over built pipelines: levels, statuses,
   findings, change ledger. Gate generation and fingerprint pinning ride with this.
4. The fixture projects, and the view validated against every shape.
5. `NotBuilt` and `touches=`, **after `P3-36` lands** (both live in `nodes.py`/`tools.py`, which
   that item is editing; Thilina says when).
6. The docs: `docs/view.md`, the `procedure.md` amendments, the `index.md` row.

## Deferred-list intersections

Read before this design, per `CLAUDE.md`:
[the supervisor entry](../plan.md#L462) (its registry question answered by the factory
convention, above); [a starting plan that pre-answers elicitation](../plan.md#L261) (a seeded
start could hatch both brief entries and a first skeleton; not taken here);
[the per-edge value entry](../plan.md#L464) (fixes what an edge honestly carries today).

## The prototypes, and how each failed

Both built 2026-08-26 off `/home/thilina/Projects/dogfood-5-frozen`; each rejection narrowed the
item and both are kept here as evidence.

### The first: right facts, wrong order

An extractor reading 2,393 run manifests, their trajectories and `brief.toml` in 0.3 seconds
without importing a line of the project's code, and one self-contained page led by a 3D system
view. What it established survives:

- **A trajectory cannot be parsed, only streamed.** One `node_execution` payload is megabytes and
  a full `json.loads` over one 15MB file did not finish in two minutes. Any command reading
  trajectories has that constraint.
- **A figure without its basis is not a figure.** The first pass summed device-seconds and
  dollars into one number. The view carries the basis beside every total and never sums across
  two.
- **It found something the written analysis missed.** Three steps ran as `AgentNode`, not two;
  `judge_candidates` was named nowhere. Logged as `DF5-X9`, corrected in `DF5-D7`. Assembling the
  artifacts is what found it.
- **The orphan is the strongest thing on the node card.** 24 of 31 decisions name no step; a name
  match over prose cannot separate a step nobody agreed to from one agreed under different words.
  `P3-29`'s `produces` is what makes it exact.

**Thilina, on being shown it, verbatim:** *"What am I supposed to do with this? How do I use it?
Clicking on anything does nothing. This is more cryptic than a bunch of markdown lol"*

Clicking was not broken; the response happened 800 pixels below the viewport. **A tool that
responds where the reader is not looking has not responded.** The page led with the picture and
buried six plain sentences at the bottom. The lesson, which survives the reframe: the page says
what matters in sentences first, and the picture is the evidence for each sentence.

### The second: right order, wrong subject

The rebuild put computed findings first, made every sentence a generic detector over the
artifacts, and re-measured the frozen tree. The re-measurement corrected three things the record
held wrongly: **zero suspensions exist in all 2,393 manifests** (the first prototype's "runs
suspended and never resumed" reading was false; all 1,605 consultations were answered without any
run stopping, 1,602 of them through `resolve_ambiguity` at about 45 a run), the busiest pipeline
is the 1,318-run resolution chain and not the 992-run summariser, and the extractor's `models`
read reported the dict keys `configured`/`observed` as model names. The published page is
`https://claude.ai/code/artifact/b00fe8e9-a9d0-49a5-9fa0-9e016de6ff28`.

Rejected as an audit mirror over a finished project: the reframe quotes above are the record.
What survives into the real build: the extractor as the `proven` overlay's source, the 2D
pipeline graph panel's bones, and the detectors that never needed runs at all (the orphan join,
the agency claim beside the record), which become design-time findings. What died: run count as
the organizing encoding, and 3D because 3D.

### Where the prototype code is

**Deleted 2026-08-27, at `P3-40`.** `scripts/extract_view.py`, `scripts/render_view.py` and
`scripts/view.tmpl.html` held the two prototypes: the artifact reading with its streaming and
cost-basis handling, and the second prototype's page. They were moved into the repository on
2026-08-26 out of a session scratchpad, superseded the same day by
[`src/simple_agents/view/`](../../src/simple_agents/view/assemble.py#L666) `assemble`, and
imported by nothing. What survived them is described above; the files are in git history at
`e686b21`.

## What it waits on

- **Step 5 of the build order waits on `P3-36`**, which is editing `nodes.py` and `tools.py`;
  Thilina says when it lands. No other work item collides with it.
- **Ghost pipelines and the exact decision-to-step join wait on `P3-29`** (`produces`), scheduled
  and adjacent; the view reads what it writes.
- **`DF5-I22` is part of this item**, moved 2026-08-26, now in its general form: the `shape`
  gate's design conversation happens over the generated view rather than over prose.

**Adjacent and not absorbed**, so neither is decided here:
[`plan.md` §2.1](../plan.md#L1)'s feature-indexed lookup of the shipped documents is the other
bridge and its subject is navigating `docs/`;
[`runs/dogfood-5/inventory.md`](../runs/dogfood-5/inventory.md#L1) `DF5-I28`, evaluating back to
front, is the method that makes per-node figures worth drawing.

## The stage pages, 2026-08-28

**The page is a page per stage now, in one file, anchored to the project's own stage.** Decided
at `P3-51`'s sitting and built as `P3-59`; the architecture's six points, the section filing
rules and the measure page's design are in
[`results-visualiser.md`](results-visualiser.md#L98), which is the design of record for both.
Decision 1 above (one page, four levels) stands inside each stage page: the levels are what
the `shape`, `build` and `measure` pages draw.

**Every page is designed before it is coded, and designed means what it looks like.** Ruled
by Thilina on 2026-08-29, reopening the measure page: *"It's a visualization tool. Visuals are
the most important part."* A page's item begins with a sitting that puts to him, region by
region, what the builder sees and what happens when they click, as wireframes in the
builder's words; each region is settled before code; the `dataviz` skill is loaded before
anything is drawn; and each built region is read in a real browser before the next.
[`build-logs/the-measure-page-as-a-visualisation-build-log.md`](../build-logs/the-measure-page-as-a-visualisation-build-log.md#L1) is the first item under it.
