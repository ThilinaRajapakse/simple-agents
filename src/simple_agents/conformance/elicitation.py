"""The questions the builder has to be asked, and the stage at which each becomes required.

The library supplies the questions and the gate. The coding agent does the asking, and the
answers land in ``brief.toml`` as entries (FT-24).

::

    from simple_agents.conformance import QUESTIONS, required_at, question

    [q.name for q in required_at("shape")]              # the entries a shape gate insists on
    [q.name for q in required_at("ship", "prototype")]  # without measure's, which that tier has not
    question("ground_truth").scaffold                   # what makes that one answerable
    question("ground_truth").title                      # the same question, named for a builder

**Every question carries a scaffold**, which is what turns it into something a builder can
answer in one sitting. A required question a builder cannot answer cold is a wall, and the
answer that comes back from a wall is invented.

A question marked optional is asked when it applies. The gate does not fail on it, so an entry
for it may be absent from the brief entirely.
"""

from __future__ import annotations

from dataclasses import dataclass

from .stages import STAGES, up_to

__all__ = ["Question", "QUESTIONS", "required_at", "questions_at", "question", "names"]


@dataclass(frozen=True, slots=True)
class Question:
    """One question put to the builder.

    ``name`` is the key of the ``brief.toml`` entry that records the answer, and is not text to
    put to the builder: a question raised as ``agency_boundary`` asks about the library's
    vocabulary rather than about the project. ``title`` is the same question named in the
    builder's words, short enough to head a list of them; `simple-agents view` shows it where
    a page would otherwise print the key. ``ask`` is the question in the words the builder
    reads. ``scaffold`` is what the coding agent does to make it answerable, which is usually a
    measurement it takes first or a choice it offers.

    **A scaffold may reach one answer through several exchanges**, and ``absence_vs_error`` is
    one: it puts two scenarios side by side, takes which is worse, then asks by how much. The
    brief records one answer per question whatever it took to get there.

    **Four rules govern how any of these is put**, and they govern a question the coding agent
    composes for itself as well. Put it against something of the builder's own, written into
    the question. Look up any number it turns on first, and say where the number came from.
    Name the options, and say which one is recommended and why. Explain every term the builder
    has not used themselves, the project's own code names included. `docs/procedure.md` carries
    them, and a question put without its scaffold is one the builder answers by guessing.
    """

    name: str
    title: str
    stage: str
    required: bool
    ask: str
    scaffold: str
    about_what_is_wanted: bool = False
    """Whether this answer says what the builder wants built, rather than how or how well. A
    ``shape`` or ``presentation`` decision names the ones it was derived from under ``from``,
    and ``simple-agents check`` prints the ones no decision names (`docs/conformance.md`
    §3.4)."""

    about_the_pipeline: bool = False
    """Whether this answer describes something ``Pipeline.behaviour_fingerprint()`` covers:
    the shape, the prompts, the sampling, the tools, the declared model, ``allow_unknown`` or
    the budgets. A moved fingerprint means the pipeline changed under these answers, and
    ``simple-agents check`` names them for re-reading (`docs/conformance.md` §4.4)."""

    re_asked_each_stage: bool = False
    """Whether one answer settles this question for good, or it is put again at every gate.

    An entry for such a question carries ``asked_at``, the stage it was last put at, and
    FT-24 refuses while that is absent or names an earlier stage than the one the project is
    at. The answer accumulates: each stage's is recorded under that stage and the earlier ones
    stay. A deferral is refused, since there is no later stage to defer to."""


QUESTIONS: tuple[Question, ...] = (
    # -- brainstorm -------------------------------------------------------------------------
    Question(
        name="what_it_does",
        title="What it does",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask="In two or three sentences, what does the agent do, and who is it for?",
        scaffold=(
            "Ask it open, and write the answer down as the builder gave it before rephrasing "
            "anything. Read what comes back for three things: what the agent receives, what it "
            "produces, and who receives that. An answer carrying all three is a developed idea, "
            "and the work is to record it and confirm the reading back. An answer missing any "
            "of them is where the optional questions at this stage apply, because the builder "
            "is exploring rather than specifying and a design settled now is settled against a "
            "guess."
        ),
    ),
    Question(
        name="used_through",
        title="What the end user opens",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask="What does the end user open to use this, and what happens when they do?",
        scaffold=(
            "Ask for the surface: a page, a chat, a terminal, a feed, someone else's tool, or "
            "something else. Then what the end user can do there, and what makes a run "
            "happen: they ask, a schedule fires, something changes, or the builder runs it by "
            "hand. The product is what these answers describe, and the design stage "
            "classifies each interaction (`docs/product.md`).\n"
            "Where the builder runs a script and reads what it prints, record that; it is an "
            "answer, and the rest of the product questions are then short."
        ),
    ),
    Question(
        name="how_far",
        title="How finished it needs to be",
        stage="brainstorm",
        required=True,
        ask="How finished does this need to be, and what would the builder stop at?",
        scaffold=(
            "The builder cannot answer this without knowing what the stages produce, so say "
            "it first. Stopping after `research` leaves a survey of how this is done and a "
            "recommendation. Stopping after `shape` leaves a design and no code. Stopping after "
            "`build` leaves an agent that runs on real input, with nothing said about how "
            "often it is right. Going through `measure` leaves a number with an interval over "
            "a held-out split, which costs an example set, labels and k rollouts. Going on to "
            "`ship` is somebody else using it, with the runs a person made separable from the "
            "runs made building it.\n"
            "The stage and the tier are two answers. The tier is `prototype` where the "
            "project reports no number and `evaluated` where it reports one, and it decides "
            "which gates fire and which stages the project has: a project at `prototype` has "
            "no `measure` stage. Shipping is not a tier, so a project may go live from "
            "either.\n"
            "Ask which of those they are after, and write the tier into the brief now. Most "
            "answers are `build` for something they will use themselves and `measure` for "
            "anything whose answers other people act on. An unfinished project that stopped "
            "where the builder meant to stop is finished."
        ),
    ),
    Question(
        name="involvement",
        title="How much the builder wants to decide",
        stage="brainstorm",
        required=True,
        ask=(
            "Building this means deciding things the builder has not been asked about. How "
            "much of that do they want to see, and when?"
        ),
        scaffold=(
            "Offer the three, and say what each costs them: every decision as it comes, which "
            "is slowest and misses nothing; a batch at each stage gate, which is one review "
            "per stage; or only the ones that change what the agent does, which is fewest and "
            "relies on the coding agent's judgement of which those are.\n"
            "This sets when the six decision kinds are put to the builder, not whether. All "
            "six are recorded and settled at every level (FT-30), because a decision the "
            "builder never saw is one they cannot change later. Ask this before the design "
            "starts, since it "
            "governs every exchange after it."
        ),
    ),
    Question(
        name="existing_solution",
        title="What is done today",
        stage="brainstorm",
        required=False,
        ask="What does the builder do about this today, and what is wrong with it?",
        scaffold=(
            "The current approach is what the agent has to beat, and it is often not automation "
            "at all. Record it. An agent slower and less accurate than what already happens has "
            "no reason to exist."
        ),
    ),
    Question(
        name="success_story",
        title="One occasion it works well",
        stage="brainstorm",
        required=False,
        about_what_is_wanted=True,
        ask=("What happens, start to finish, on one occasion where the finished agent works well?"),
        scaffold=(
            "Have the builder narrate it rather than summarise it. A walkthrough surfaces steps "
            "that a description of the goal leaves out, and it names the intermediate values "
            "the pipeline will have to carry."
        ),
    ),
    Question(
        name="alternatives",
        title="Other versions of the idea",
        stage="brainstorm",
        required=False,
        ask="What are two other versions of this idea?",
        scaffold=(
            "Ask for versions that differ in what the agent does rather than in how it is "
            "built. The answer says whether the first statement was the idea or the first thing "
            "that came to mind."
        ),
    ),
    Question(
        name="purpose",
        title="Who will depend on it",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask=(
            "Is this something the builder will use, something they will show other people, or "
            "something other people will depend on?"
        ),
        scaffold=(
            "Offer the three and take one. Each sets a different bar. A tool the builder uses "
            "answers to one person who recognises its mistakes. Something shown is finished "
            "when a reader can follow what it did. Something others depend on answers to people "
            "who cannot recognise its mistakes. The answer decides the tier the project claims, "
            "and whether a wide interval is a finding or a problem."
        ),
    ),
    Question(
        name="end_user",
        title="Who uses it",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask="Who uses the finished agent, and is that the builder?",
        scaffold=(
            "Where the builder is the only user, record that. The answer decides how much the "
            "output has to explain itself, and whether consultation reaches somebody other than "
            "the person who built it."
        ),
    ),
    Question(
        name="one_real_input",
        title="What it receives",
        stage="brainstorm",
        required=True,
        ask="What does the agent receive, and can one real example of it be produced now?",
        scaffold=(
            "Obtain one and read it before any node is designed. Record what it holds rather "
            "than what it is assumed to hold: the fields present, the fields absent, and the "
            "range of values. A field assumed present and missing from the real file is found "
            "here rather than after the pipeline is written."
        ),
    ),
    Question(
        name="smallest_worthwhile",
        title="The smallest worthwhile version",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask="What is the smallest version that would still be worth having?",
        scaffold=(
            "Ask it beside `finished_version` and record both together, since a floor and a "
            "destination are easier to state against each other than alone. Record it as "
            "something the project could stop at: it is what the first working version aims at, "
            "and it is the fallback where a later stage shows the full version is not reachable."
        ),
    ),
    Question(
        name="finished_version",
        title="What finished looks like",
        stage="brainstorm",
        required=True,
        about_what_is_wanted=True,
        ask=(
            "What does this look like when it is finished, and what does it do then that the "
            "first working version will not?"
        ),
        scaffold=(
            "Ask for what the end user gets rather than for a list of capabilities. It is the "
            "answer most likely to change as the project is built, and recording it is what "
            "makes that change visible at a later gate (FT-29)."
        ),
    ),
    Question(
        name="not_building",
        title="What it will not do",
        stage="brainstorm",
        required=False,
        about_what_is_wanted=True,
        ask="What has the builder decided this will not do?",
        scaffold=(
            "Record the exclusions in the builder's words. An exclusion recorded now is a "
            "refusal the coding agent can point at later, rather than a scope decision it makes "
            "alone."
        ),
    ),
    Question(
        name="abandon_condition",
        title="When to stop",
        stage="brainstorm",
        required=False,
        ask="What would show that this is not worth continuing?",
        scaffold=(
            "Ask for a condition that could be observed, such as a source that turns out not to "
            "publish the data, or a figure the agent cannot beat. Recorded now it is a decision "
            "the builder already made. Discovered later it is a decision made under sunk cost."
        ),
    ),
    # -- research ---------------------------------------------------------------------------
    Question(
        name="parts",
        title="The problems to solve",
        stage="research",
        required=True,
        about_what_is_wanted=True,
        ask=("What problems does this have to solve, from what it receives to what it produces?"),
        scaffold=(
            "Name the parts before knowing how any of them work. A part is a problem the "
            "system has to solve; `shape` settles what the agent is for and `build` settles "
            "the nodes, so neither belongs here. The questions below are asked against each "
            "part in turn. Put the list to the builder before going further."
        ),
    ),
    Question(
        name="approaches",
        title="How others do it",
        stage="research",
        required=True,
        ask=(
            "For each part, how do other people do it, and does anything already do it well "
            "enough that it should not be built?"
        ),
        scaffold=(
            "Go and look, part by part. For each part, two searches: what already does it, "
            "which is products, services, libraries and what this library ships "
            "(the feature index at the end of `docs/procedure.md`, and `docs/tools.md` §4's "
            "fourteen tools); and how it is built when "
            "it is built, which is the pipeline shapes and the retrieval, ranking and judging "
            "methods people report working. Record everything that comes back before deciding "
            "anything about it. Then filter with the builder and record what each part is "
            "taking. Adopting something instead of building it is a real answer, for one part "
            "or for the whole project."
        ),
    ),
    Question(
        name="available_material",
        title="What else it can draw on",
        stage="research",
        required=True,
        ask="What could the agent draw on besides what the builder has handed over?",
        scaffold=(
            "Per part, go and find the data, APIs, catalogues, corpora and internal systems "
            "that bear on it. For each: whether it is reachable, at what cost, on what terms, "
            "and what one real response holds. Fetch one. Every candidate carries an outcome, "
            'and "not investigated, because..." is one. Then put the shortlist to the builder.'
        ),
    ),
    Question(
        name="what_goes_wrong",
        title="What is known to go wrong",
        stage="research",
        required=True,
        ask="What is known to go wrong in each part?",
        scaffold=(
            "For each approach recorded above, find the failure modes people report and state "
            "each in terms of this project. `docs/failure-taxonomy.md` carries the ones the "
            "library checks for; these are the ones it cannot. Record beside each what would "
            "make it visible in this project's own output."
        ),
    ),
    Question(
        name="what_this_turns_on",
        title="The deciding factor",
        stage="research",
        required=True,
        ask="Having looked, which parts decide whether this works at all?",
        scaffold=(
            "Answer this last. Name the parts the research says are hard: where nothing "
            "existing does it, where the approaches disagree, where the material is thin, or "
            "where a failure mode has no signal here. Record a part the research found "
            "nothing about as exactly that. Put them to the builder and take their correction."
        ),
    ),
    # -- shape ------------------------------------------------------------------------------
    Question(
        name="ground_truth",
        title="What counts as correct",
        stage="shape",
        required=True,
        ask=(
            "For one input, which answers would the builder accept, and who decides that they "
            "are correct?"
        ),
        scaffold=(
            "Take one real input the agent will meet. Write down what the builder says is "
            "correct, then ask whether a different answer would have been as correct, and "
            "record every one they accept. Asking for the correct answer returns one answer "
            "whatever the task is, and a second arrives only where it is asked for. Then "
            "record whether the judgement came from the builder, from an existing labeled "
            "set, or from a source that has to be consulted each time. The shape those "
            "answers take is `answer_form`.\n"
            "Some tasks have no acceptable answer to write down, and that is an answer to "
            "record rather than a question to skip. Where the builder can say which of two "
            "results they would rather have but cannot say what a right one looks like, write "
            "that down here, with what makes one better than the other. That is scored by "
            "comparing two results on the same input rather than against a key "
            "(`docs/evaluation.md` §11.9), and it changes what the measure stage builds."
        ),
    ),
    Question(
        name="answer_form",
        title="The form of a correct answer",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask=(
            "For one of the builder's own inputs, written out: is there one correct answer, "
            "or several that would all be right? Does the answer have to contain particular "
            "things, land near a number, or meet a set of conditions?"
        ),
        scaffold=(
            "Read `ground_truth`'s answers back and write one of them five ways against the "
            "builder's own input, all five in front of them before the question is asked. "
            "The five names below are the library's, and they belong in the code rather than "
            "in the question. One value is a plain label, several is "
            "`AnyOf`, a collection the answer has to hold is `Contains`, a quantity is "
            "`WithinTolerance`, and conditions are `Criteria` (`docs/evaluation.md` §1.6). The "
            "answer decides what an example's `expected` holds and how many comparisons one "
            "rollout is scored by. A project whose answer is one value records that, which is "
            "different from the question never having been asked.\n"
            "Where the answer is conditions, the builder writes them, since nothing else can: "
            "each is one statement judged yes or no, carrying how much it counts toward the "
            "rest and whether an answer that fails it is wrong rather than partly right. Ask "
            "which of them are about a value that is sometimes not there at all, because a "
            "condition whose right answer is that the value is absent is declared "
            "`expects_absence` and is what makes an absent case visible where the answer is a "
            "record and the absence is one empty field (FT-04).\n"
            "What the end user reads is `presentation`, and it is a different answer: an agent "
            "that returns a shortlist of five books is right where the shelf's title is among "
            "them, so the output is a list of five and the answer key is one title the answer "
            "has to hold."
        ),
    ),
    Question(
        name="judged_steps",
        title="Steps with their own right answer",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask=(
            "Here are the steps this agent takes. Is there any one whose output the builder "
            "could call right or wrong without looking at what the run finally returned?"
        ),
        scaffold=(
            "List the steps first, in the builder's words rather than by node id, and put "
            "the list in front of them. Most projects name none or one, and naming none is "
            "an answer. A step they can judge is labelled per example with "
            "`Example.expected_by_node` and "
            "compared with `EvalSuite(node_matches=...)`, which reports that step's own "
            "accuracy over the rollouts that reached it (FT-08, `docs/evaluation.md` §5.2). "
            "It has to be its own node to be scored at all, so the answer reaches the graph "
            "and not only the evaluation. A step that runs on some inputs and not others is "
            "ordinary: its figures are over the rollouts that reached it, with `reach` beside "
            "them (`docs/evaluation.md` §5.1)."
        ),
    ),
    Question(
        name="judged_path",
        title="Whether the route matters",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask="Does it matter how the agent reached an answer, and not only what the answer was?",
        scaffold=(
            "Name what the agent has to have done, or not done, for an answer to count: "
            "retrieving before answering, asking before acting, stopping rather than "
            "guessing, reading one source rather than another. Where there is nothing, record "
            "that. Each one is a condition over the run rather than over the answer, written "
            "as a criterion whose check reads `s.trajectory` (`docs/evaluation.md` §1.6), and "
            "it is judged in the same list as the conditions about the answer. A condition "
            "nothing in the record would show is not one to take, so ask what in the run "
            "would show it."
        ),
    ),
    Question(
        name="absence_vs_error",
        title="What a wrong answer costs",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask=(
            "Here are two things that could happen on one of the builder's own inputs: the "
            "agent asserts a wrong value, and the agent reports that it found nothing. Which "
            "is worse, and by how much?"
        ),
        scaffold=(
            "Write the two scenarios out of the builder's own domain first; the question is "
            "unanswerable until both are in front of them (FT-10). By how much is the second "
            "half, and it is asked because a direction alone does not set a threshold and "
            "the code needs one: offer a graded scale rather than worse, the same, or "
            "better. Ask what the builder does with an answer before acting on it, since one "
            "who checks every suggestion sits "
            "somewhere different on that scale from one who does not.\n"
            "Where the answer key has parts, put a third scenario beside them: an answer that "
            "met some of them and not others. It is its own outcome (`docs/evaluation.md` "
            "§2), so its cost is a third point on the same scale rather than a rounding of "
            "the other two. A condition that is worth nothing unless it is met is recorded "
            "`required`, which makes an answer failing it wrong rather than partly right. A "
            "key that admits no partial answer has no third scenario, and recording that is "
            "an answer."
        ),
    ),
    Question(
        name="agency_boundary",
        title="What the agent works out for itself",
        stage="shape",
        required=True,
        about_what_is_wanted=True,
        about_the_pipeline=True,
        ask=(
            "What would the builder like the agent to work out for itself while it runs, and "
            "what should it be told before it starts?"
        ),
        scaffold=(
            "Ask what they want it to be able to do without them, in the terms of their own "
            "work, and write that down before saying anything about node kinds. Then put "
            "`consultation` beside it, the same subject from the other side: a step that "
            "decides for itself is a step that can decide wrongly, so what should it "
            "check with a person first?\n"
            "Then read the answer back as a list of steps, saying for each whether the path "
            "is known in advance or discovered from what the previous step returned. The "
            "fixed ones are `Deterministic` and `LLMNode`, and only the discovered ones need "
            "an `AgentNode` (FT-11). Where a step the builder wants working alone comes out "
            "fixed, say so and ask whether that is what they meant.\n"
            "A `shape` decision names this entry under `from`, and `simple-agents check` "
            "prints the answers about what is wanted that no decision rests on."
        ),
    ),
    Question(
        name="consultation",
        title="What it must ask the end user",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask="What must the agent ask the end user while it runs, and when?",
        scaffold=(
            "Put this together with `agency_boundary`, which is the same subject from the "
            "other side: the first is what the agent settles alone and this is what it takes "
            "to a person.\n"
            "Name the values the agent cannot derive: a preference, a disambiguation, an "
            "authorization. Where there are none, record that. An empty answer is an answer "
            "and a blank is not (FT-25).\n"
            "Then take what happens to a question from `used_through`, which the builder "
            "answered a stage ago: what makes a run happen decides what a run can do about a "
            "question. Somebody who asked for this and is waiting can be kept waiting, so the "
            "run stops and continues when they answer. A run a schedule fired, or a change in "
            "a store, has no one waiting, so it cannot stop. Its question goes on a list and "
            "the run finishes. A run that will never get an answer finishes without one and "
            "says what it lacked. A project can need more than one of the three, and "
            "which one applies is decided per trigger. The three are `Suspend`, `Shelved` and "
            "`Unavailable`, and `docs/product.md` §4 is what each takes to build."
        ),
    ),
    # -- build ------------------------------------------------------------------------------
    Question(
        name="presentation",
        title="What a result looks like",
        stage="shape",
        required=True,
        about_the_pipeline=True,
        ask="What does a result have to look like, and who reads it besides the builder?",
        scaffold=(
            "Ask what they do with an answer once they have it. A result read once in a "
            "terminal and a result kept, shared or shown to someone who was not there are "
            "different outputs, and the difference lands in the output schema rather than in "
            "the rendering: a page needs one record per item carrying its own reasons, and a "
            "glance needs one line.\n"
            "The library ships nothing that shows the agent's output to an end user. What it "
            "needs from this answer is the shape of that output, which every node upstream is "
            "then built to produce; the surface showing it is `used_through`'s answer and the "
            "design section's subject (`docs/product.md`). Record the decision under "
            "`presentation` as well (FT-30)."
        ),
    ),
    Question(
        name="backend",
        title="Which model it runs against",
        stage="build",
        required=True,
        about_the_pipeline=True,
        ask="Which model should this run against, at what price, and who approves a change?",
        scaffold=(
            "Run one example against the candidate and read the token counts off the record. "
            "State the per-example cost at that model and at the alternative being considered, "
            "then ask. Confirm the credential is available before the first run (FT-14). "
            "A project that searches a corpus by meaning runs a second model, and changing it "
            "means re-embedding everything already stored, so settle that one here too "
            "(`docs/retrieval.md` §3)."
        ),
    ),
    Question(
        name="budget",
        title="The four budget numbers",
        stage="build",
        required=True,
        about_the_pipeline=True,
        ask=(
            "One run of this agent has been measured. Given what it took in steps, tokens, "
            "money and wall clock, where should each of those stop?"
        ),
        scaffold=(
            "Run one example, read what it consumed from the manifest's totals, and propose "
            "the four numbers from that with headroom. They are derivable, so nothing here "
            "has to be guessed (FT-18)."
        ),
    ),
    Question(
        name="tool_effects",
        title="What it may do outside the run",
        stage="build",
        required=True,
        about_the_pipeline=True,
        ask=(
            "What may this agent do that reaches outside the run: spend money, write "
            "somewhere permanent, or take an action that cannot be undone?"
        ),
        scaffold=(
            "List every tool the agent will be given, with the side-effect class it declares "
            "and what one call does. Have the builder confirm each or correct it. An "
            "evaluation runs k rollouts over n examples, so it refuses to start over a tool "
            "declared `spends_money` or `irreversible`, and the builder meets that as a "
            "refusal, not as a question that was never asked (FT-19, FT-20)."
        ),
    ),
    Question(
        name="unproven_answer",
        title="An answer it cannot support",
        stage="build",
        required=True,
        ask=(
            "When the agent can produce an answer but cannot support it from what it "
            "retrieved, should it report the answer or report that it found nothing?"
        ),
        scaffold=(
            "Show one worked example of each outcome from the builder's own material and have "
            "them pick. Ask this whether or not the project builds any verification step, "
            "because the decision is as often made by leaving one out (FT-04)."
        ),
    ),
    Question(
        name="unknown_literal",
        title="The word unknown in a result",
        stage="build",
        required=False,
        about_the_pipeline=True,
        ask=(
            "If the model writes the word `unknown` where a real value was expected, is "
            "that the agent saying it does not know, or a run that went wrong?"
        ),
        scaffold=(
            "Offer the two behaviours and what each costs: reading it as absence decides what "
            "the model meant, and refusing it risks a rejection loop the model cannot escape "
            "(FT-09)."
        ),
    ),
    Question(
        name="context_limit",
        title="How much one step may read",
        stage="build",
        required=False,
        about_the_pipeline=True,
        ask=(
            "How much of what the model can read at once may one step fill, and what should "
            "happen when there is more to send than fits?"
        ),
        scaffold=(
            "Read the window from the backend's model list, run one example, and set the "
            "limit from those two with headroom for the output. For the behaviour, offer the "
            "three: stop the run, send less and record what was dropped, or give the node "
            "less to begin with (FT-17)."
        ),
    ),
    Question(
        name="rerun_cost",
        title="The cost of re-running",
        stage="build",
        required=False,
        ask="How many times may this be re-run before the builder wants to see the bill?",
        scaffold=(
            "Run one example, read the cost and the wall clock, and multiply by the number of "
            "examples and rollouts being proposed. Say that the figure is paid once rather "
            "than per attempt at scoring it: an evaluation records its rollouts, and a metric "
            "that raised or a rule that was wrong is applied again with suite.rescore."
        ),
    ),
    Question(
        name="keep_payloads",
        title="Whether runs keep what was sent",
        stage="build",
        required=True,
        ask=(
            "Every run keeps a record of what was sent to the model and what came back. "
            "Should this agent's runs keep it?"
        ),
        scaffold=(
            "Say what is kept and why, then take the answer. Each run writes a trajectory and "
            "a cassette into its own directory, both holding the whole prompt and the whole "
            "response, under the redaction rules the envelope declares. It is on because which "
            "run turns out to be worth reading is not knowable while it is running, and an "
            "unrecorded run cannot be debugged, evaluated, re-scored or replayed afterwards. "
            "Redaction removes credentials and the values the project declares and nothing "
            "else, so a no is for material it would not recognise. A no is "
            "`RunEnvelope(trajectory=Trajectory.sampled(0.0))`, which drops the payloads from "
            "both files and gives up replay and re-scoring; counts, timings, token figures, "
            "seeds and cost are written for every run at every rate."
        ),
    ),
    Question(
        name="reproduce",
        title="Whether a past run must be reproducible",
        stage="build",
        required=False,
        ask="Does a specific past run have to be reproducible later?",
        scaffold=(
            "Every run records into its own directory, so this is yes unless the project keeps "
            "less than everything. Under `Trajectory.sampled(rate)` the runs that can be "
            "replayed are the ones their run id selects, decided as each run starts rather "
            "than nominated afterwards, and a run selected out keeps neither its payloads nor "
            "its cassette. A run that has to be reproducible is made through "
            "`envelope.with_trajectory(Trajectory.full())`, which keeps both for that run. A "
            "seed alone does not reproduce a run against a hosted API, because the provider "
            "does not promise determinism at a fixed seed."
        ),
    ),
    Question(
        name="who_labels",
        title="Who writes the correct answers",
        stage="build",
        required=True,
        ask="Who writes the correct answers for the example set, and when?",
        scaffold=(
            "Offer the two routes: the builder writes the labels now, or the first run's "
            "output is reviewed and the reviewed output becomes the labels. Both are "
            "legitimate and they cost the builder's time at different moments (FT-01). "
            "Where a model writes or checks any label, run that pass through the envelope "
            "with `role='labelling'` rather than calling a client directly, so the model that "
            "decided the ground truth is pinned the way the agent's is and the pass is not "
            "read as a run of the agent (`docs/evaluation.md` §1.4). Labels go in "
            "`evals/labels.jsonl`, one per judgement, each naming what decided it "
            "(`docs/evaluation.md` §1.5). Where `answer_form` settled on conditions, what is "
            "written per example is the conditions rather than a value, and each one's check "
            "is registered on the suite under its id (`docs/evaluation.md` §1.6)."
        ),
    ),
    # -- measure ----------------------------------------------------------------------------
    Question(
        name="improvement",
        title="The number the builder acts on",
        stage="measure",
        required=True,
        ask="Which number would the builder act on, and how will they know a change helped?",
        scaffold=(
            "Run the first evaluation and print the eight rates with this project's own numbers "
            "beside them. Ask which one the builder would act on, and what it would take to "
            "move it. Where the number they name is computed from the answer, it is a "
            "`ProjectMetric` (`docs/evaluation.md` §11). Where it counts things the answer "
            "holds rather than scoring the answer, such as how many results were already seen "
            "or how many sources were unreachable, it is one count over another and is a "
            "`ProjectRatio` (`docs/evaluation.md` §11.7): ask what the count is out of, because "
            "a bare total cannot "
            "be compared between two versions. Where the builder cannot name a number at all "
            "but can say which of two results they prefer, the figure is over pairs "
            "(`docs/evaluation.md` §11.9). "
            "Then offer the default method and let "
            "the builder override it: k rollouts over the held-out split before and after, "
            "compared on the interval rather than on the point estimate (FT-05, FT-06).\n"
            "Ask which step the number would have been lost at, and report a figure there as "
            "well as end to end (FT-08). Where the builder can say what a step should have "
            "produced, that is `Example.expected_by_node` and `EvalSuite(node_matches=...)`; "
            "where they name a count over what a step handled rather than a score for it, "
            "that is a `ProjectRatio` in `EvalSuite(node_metrics=...)` "
            "(`docs/evaluation.md` §11.5). Where the whole pipeline scores badly and every "
            "step looks fine on the inputs it got, run the steps back to front: "
            "`pipeline.slice(start=...)` returns the last step as a pipeline of its own, and "
            "`examples.entering(...)` builds what it is run on out of the labels already "
            "there (`docs/evaluation.md` §5.6)."
        ),
    ),
    Question(
        name="leakage",
        title="Whether the input gives away the answer",
        stage="measure",
        required=True,
        ask="Is anything the agent is given quietly giving away the answer?",
        scaffold=(
            "Walk the usual leaks with the builder: file names, identifiers, the order the "
            "material is in, metadata, and section headings. Each one is a channel that "
            "carries the answer without the agent doing the work (FT-03)."
        ),
    ),
    Question(
        name="too_similar",
        title="Duplicates in the example set",
        stage="measure",
        required=True,
        ask="Of the most similar pairs in the example set, which are the same example twice?",
        scaffold=(
            "Run examples.nearest_cross_split() and read the pairs to the builder, each "
            "example in full. Ask which of them are the same example twice.\n"
            "Then set contamination_threshold= to a similarity that separates the pairs they "
            "called duplicates from the ones they did not, and record what they said about "
            "each. A project that assigns whole sources to a split and needs no text "
            "threshold records that instead (FT-03)."
        ),
    ),
    Question(
        name="prices",
        title="Where the cost figures come from",
        stage="measure",
        required=False,
        ask=(
            "Is anyone billed for the compute this agent uses, and if so, where do the "
            "figures in the cost basis come from and when were they last checked?"
        ),
        scaffold=(
            "A hosted API is billed per token, so record the provider's pricing page and the "
            "date it was read next to the figures themselves (FT-27). A device the builder "
            "already owns has no bill: declare no rate, bound the run with "
            "max_wall_clock_ms, and use DeviceBasis to report device-seconds. Do not invent "
            "an hourly rate to fill in a cost."
        ),
    ),
    # -- ship -------------------------------------------------------------------------------
    Question(
        name="someone_there",
        title="Whether anyone is there",
        stage="ship",
        required=True,
        ask="Will anyone be there when this runs for real?",
        scaffold=(
            "Read the `consultation` answer back to the builder first, because this decides "
            "whether the agent can get what that answer says it needs. Offer the three shapes "
            "and what each means for a run: a person who answers while the run waits, which "
            "is `ask_on_stdin` or the project's own channel; a person who answers later, "
            "which is `Suspend` and `Pipeline.resume`; and `nobody`, which is `unattended()`, "
            "where every consultation returns `Unavailable` and the agent reports what it "
            "could not settle. An agent that cannot finish without an answer and an "
            "unattended run do not go together, and this answer says which of the two "
            "changes. The "
            "channel the project registers has to declare the same thing (FT-31)."
        ),
    ),
    Question(
        name="live_records",
        title="What real runs may keep",
        stage="ship",
        required=True,
        ask=(
            "The runs a real person makes are recorded the way the builder's were. What may "
            "be kept?"
        ),
        scaffold=(
            "Say what a run keeps and what has changed. Each run writes a trajectory and a "
            "cassette holding the whole prompt and the whole response, under the redaction "
            "the envelope declares, plus counts, timings, token figures, seeds and cost at "
            "every rate. What has changed is that the material is the end user's rather than "
            "the builder's, and redaction removes credentials and the values the project "
            "declares and nothing else.\n"
            "Offer the three and what each gives up: `Trajectory.full()`; "
            "`Trajectory.sampled(rate)`, decided as each run starts, which is what a project "
            "running many times a day reaches for; and `Trajectory.sampled(0.0)`, which drops "
            "the payloads from both files and gives up replay, re-scoring and any later use "
            "of the runs as training data. Where the answer names material that must not be "
            "kept, declare it for redaction rather than dropping the record. Read the "
            "`keep_payloads` answer back first, since it was given about the builder's own "
            "runs."
        ),
    ),
    Question(
        name="watching_live",
        title="Noticing when it stops being right",
        stage="ship",
        required=True,
        ask="What would tell the builder that the agent has stopped being right, and who looks?",
        scaffold=(
            "Every live run is recorded, and `runs('runs/', live=True)` reads them back. "
            "Offer the forms and ask which: a person reads a sample of live runs on a "
            "schedule; the end user has a way to say an answer was wrong, and that judgement "
            "lands in `evals/labels.jsonl` naming what decided it; a fresh evaluation runs at "
            "an interval against the same held-out split. Then ask who does it and how often. "
            '"The builder notices" is an answer, and recording it makes it a deliberate '
            "choice. Where live judgements are collected, "
            "they are the example set the next version is measured against."
        ),
    ),
    Question(
        name="stored_output",
        title="What the end user reads",
        stage="ship",
        required=True,
        ask="What does the end user read, and what writes it?",
        scaffold=(
            "A run returns a value, and what the end user reads is often something the project "
            "keeps instead: a queue, a table, an index, a file the agent appends to. Name that "
            "artifact and what writes it. Where the end user reads a run's return value and "
            "the project keeps nothing between runs, record that and the answer is finished.\n"
            "Where it accumulates, two more things go in the answer, because the artifact "
            "outlives the pipeline that wrote it and no later version rewrites what an earlier "
            "one left there. First, each stored result carries "
            "`pipeline.behaviour_fingerprint(model=client)`, which moves when a prompt, a "
            "sampling parameter, a tool body or the model moves, and is on each run's "
            "manifest to join against. Second, what "
            "re-runs the results a current pipeline did not produce: a step that selects work "
            "usually skips what it has already done, which is what leaves a stale result in "
            "place forever. Where a surface is built by plain code and calls no model, the "
            "stamp is a digest of what actually decides it and the answer says which artifacts "
            "carry which. `docs/shipping.md` §6 and `docs/product.md` §5.\n"
            "Ask the builder how much of what is read may predate the last change. Nothing in "
            "the library can answer it: an evaluation reads seeded examples and the checks "
            "read a run and a results file."
        ),
    ),
    Question(
        name="unevaluated_effects",
        title="Real actions never evaluated",
        stage="ship",
        required=False,
        ask=(
            "Here is what this agent does for real outside the run, and which of those no "
            "evaluation has ever exercised. What should happen the first time one of them "
            "runs for somebody who is not the builder?"
        ),
        scaffold=(
            "An evaluation refuses a rollout over an `irreversible` tool, and over a "
            "`spends_money` one with no declared ceiling (FT-20), so a tool in either class "
            "has run in development and in no rollout. The path it offers instead is "
            "`suite.record(...)` followed by `Cassette.replay(path)`, where each distinct call "
            "is performed once and every rollout after that is served from the file. List "
            "the tools from the manifest's entries with what one call does, work out which of "
            "them the project has recorded, and put both lists in front of the builder before "
            "asking."
        ),
    ),
    # -- asked again at every stage -------------------------------------------------------
    # Last in the tuple rather than in the brainstorm group, because `questions_at` keeps
    # this order and this one is asked after the stage's own questions, at every stage.
    Question(
        name="anything_else",
        title="Anything else",
        stage="brainstorm",
        required=True,
        re_asked_each_stage=True,
        ask=(
            "Is there anything else about this the builder wants known, that nothing has "
            "asked about?"
        ),
        scaffold=(
            "Ask it at the end of every stage, after that stage's own questions and before "
            "the gate, and ask it open. Every other question is the library's; this one is "
            "the builder's. What comes back is a want no question covers, a correction to an "
            "answer already recorded, or something they have thought of since.\n"
            "The answer accumulates. Add what they said under the stage it was asked at, "
            'keep every earlier stage\'s, and write `asked_at` naming the stage. "Nothing" '
            "is an answer and is recorded as one; a blank is not, and the gate refuses while "
            "`asked_at` names an earlier stage than the project is at (FT-24).\n"
            "Then read what came back against what is already recorded. Anything that "
            "changes an earlier answer goes back to the builder as a change to that entry, "
            "and anything that changes what is being built is a decision to put to them."
        ),
    ),
)


def questions_at(stage: str, tier: str | None = None) -> tuple[Question, ...]:
    """Every question that applies at ``stage``, including those of the stages before it.

    ::

        [q.name for q in questions_at("build")]
        [q.name for q in questions_at("ship", "prototype")]

    The set is cumulative, so a project that declares a later stage is asked the earlier
    questions too. ``tier`` drops the stages that tier does not have, so a project reporting no
    number is not asked what its held-out split is. Without it every stage is included.
    """
    covered = set(up_to(stage, tier))
    return tuple(q for q in QUESTIONS if q.stage in covered)


def required_at(stage: str, tier: str | None = None) -> tuple[Question, ...]:
    """The questions a gate at ``stage`` refuses to advance without (FT-24)."""
    return tuple(q for q in questions_at(stage, tier) if q.required)


def question(name: str) -> Question:
    """One question by the name of the brief entry that records it.

    Raises ``KeyError`` naming the known questions when nothing carries that name.
    """
    for candidate in QUESTIONS:
        if candidate.name == name:
            return candidate
    raise KeyError(f"{name!r} is not a question. The names are {', '.join(names())}.")


def names() -> tuple[str, ...]:
    """Every question name, in the order they are asked."""
    return tuple(q.name for q in QUESTIONS)


# Every question names a stage that exists, checked at import so a typo cannot ship as a
# question nothing ever requires.
assert all(q.stage in STAGES for q in QUESTIONS)
assert len({q.name for q in QUESTIONS}) == len(QUESTIONS)
