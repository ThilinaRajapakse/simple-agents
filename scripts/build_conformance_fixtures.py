"""Build the project fixtures the conformance tests run against.

A check reads artifacts, so a fixture written by hand is a claim about what an artifact
contains rather than a measurement of one. These are produced by replaying the committed
evaluation cassette through the library, then copied into `tests/fixtures/projects/`.

    uv run python scripts/build_conformance_fixtures.py

`conforming/` is a project that passes all six. It is the recorded evaluation with a dev split
added, because the shipped recording puts every example in `held_out` and so fails FT-02.
Every other fixture is that one with a single mutation, listed in MUTATIONS below, so a test
that fires a check names the one thing it changed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from record_backend_cassettes import (  # noqa: E402
    EVAL_EXAMPLES,
    EVAL_SEED,
    MISTRAL_PRICES,
    eval_pipeline,
)

from simple_agents import Cassette, MistralClient, RunEnvelope, Unknown  # noqa: E402

# The client the fixture runs replay against. `behaviour_fingerprint` covers it, because the
# pipeline's nodes declare no model of their own, so the brief's `confirmed_against` has to be
# computed against the same one the runs were made with.
REPLAY_CLIENT = MistralClient(model="mistral-small-2603", api_key="not-used-in-replay")
from simple_agents.conformance import DECISION_KINDS, required_at  # noqa: E402
from simple_agents.evaluation import Example, EvalSuite, ExampleSet  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "projects"
# Relative, and resolved against `ROOT` by the chdir in `main`. A manifest records the
# cassette path it was given, so an absolute one here writes the generating machine's home
# directory into every fixture manifest and into the committed tree behind it.
CASSETTE = Path("tests") / "cassettes" / "eval.jsonl"

DECIDED = {
    "dependency": (
        "The passages that ship with the example set, indexed in-process. No external "
        "service, because the collection is fixed and travels with the project."
    ),
    "shape": (
        "Two nodes, one agentic. `search` decides how to look, `answer` extracts the span. "
        "Both on the run's model, since neither is expensive enough to split."
    ),
    "constant": (
        "`top_k=5` on the document search. Higher crowds the turn and lower loses the "
        "answer on a question whose wording differs from the passage's."
    ),
    "prompt_rule": (
        "The answer must be a span from the passages, and absence must be reported rather "
        "than inferred. Both came from the builder rather than from testing."
    ),
    "presentation": (
        "The span, the passage it came from, and nothing else, printed. There is no reader "
        "other than the builder, so nothing renders it further."
    ),
    "measurement": (
        "Exact match over held-out questions, a third of which have no answer in the "
        "collection. Chance is near zero on a free-text span, so a rate above it is real."
    ),
}

ANSWERS = {
    "how_far": (
        "Through `measure`, at tier `evaluated`. The builder: 'People are going to act on "
        "these answers, so I want to know how often it is right before anyone does.'"
    ),
    "involvement": (
        "A batch at each stage gate. The builder: 'Show me what you picked and why when you "
        "get to the end of a stage. I do not want to be asked about every constant.'"
    ),
    "presentation": (
        "The span and the passage it came from, printed, read once by the builder and by "
        "nobody else. No page, no file, no record kept, so the output schema carries the two "
        "fields the answer needs and nothing for a reader who was not there."
    ),
    "what_it_does": (
        "It answers a question about a collection of passages with the shortest span that "
        "answers it, or reports that the collection does not answer it. It is for the support "
        "team who maintain the collection."
    ),
    "used_through": (
        "A terminal on the support team's shared machine: they run the answer script with "
        "the question and read the span it prints. A run happens when someone asks; nothing "
        "runs on a schedule and nothing is kept between runs."
    ),
    "purpose": "Something other people depend on: the support team acts on the answers.",
    "end_user": "The support team, who are not the builder and cannot check a passage themselves.",
    "one_real_input": (
        "A question and the passage collection. One real set was read before any node was "
        "written: passages run to about 120 words, and 3 of the 20 questions have no answer "
        "anywhere in the collection."
    ),
    "smallest_worthwhile": (
        "Answering questions whose answer is a span in one passage, and reporting absence for "
        "the rest."
    ),
    "parts": (
        "Four: finding the passages that bear on a question, answering from what was found, "
        "deciding a question is unanswerable, and judging whether a span is right. The "
        "builder added the fourth: 'Somebody has to say what a right answer is, and it is "
        "going to be us.'"
    ),
    "approaches": (
        "Retrieval is BM25 and embeddings together rather than either alone, since a question "
        "worded differently from its passage is what BM25 misses. Answering is one call over "
        "every retrieved passage; the per-passage variant was rejected on cost, with nothing "
        "found saying the merge was better. A hosted answering service was found and "
        "rejected: the collection may not leave the network."
    ),
    "available_material": (
        "The passage collection itself, which ships with the project and was read. No "
        "external corpus applies, since the questions are about this collection and nothing "
        "outside it can answer one. The support team's own ticket history was found and not "
        "used, because it records answers rather than the questions that produced them."
    ),
    "what_goes_wrong": (
        "A confident answer to a question the collection does not cover, which is the failure "
        "reported everywhere and the one this project has no signal for beyond its labels. A "
        "span lifted from a passage that is topically close and does not answer the question. "
        "Retrieval that finds the passage only when the question repeats its wording. Each is "
        "visible here through the held-out labels, which is why absent questions are in the "
        "set."
    ),
    "what_this_turns_on": (
        "Deciding a question is unanswerable. The other three parts have established "
        "approaches and the choice between them is cost; nothing found says how to decide "
        "absence well, and what was adopted records it rather than deciding it. Finding "
        "passages worded differently from the question is second, and is why retrieval runs "
        "both methods."
    ),
    "finished_version": (
        "The same over the whole collection, with the passage each answer came from cited "
        "beside it, so the support team can check one without reading everything."
    ),
    "ground_truth": (
        "The retailer's name, as written in the passage. Asked for a second acceptable "
        "answer, the builder gave none: the passage names one retailer and the trading name "
        "is not used. The builder decides, against the passage."
    ),
    "answer_form": (
        "One value, compared case-insensitively as a substring. Offered any-of, a "
        "collection, a tolerance and conditions, and none of them fits: a question has one "
        "span that answers it or none. The output is that span, which is what "
        "`presentation` records."
    ),
    "judged_steps": (
        "No. Both steps produce the run's own answer, `hunt` finding the span and `verify` "
        "re-checking it against the passages, so a label for either is the label the run "
        "already carries. The search is a tool inside `hunt` rather than a step of its own."
    ),
    "judged_path": (
        "Yes: an answer counts only where the span is in a passage the search returned. An "
        "answer the run did not read is a wrong answer whatever it says."
    ),
    "absence_vs_error": (
        "A wrong retailer costs more than a missing one: the order goes out. There is no "
        "third case, because a span either answers the question or does not."
    ),
    "agency_boundary": (
        "The builder wants it to find its own passages: 'I am not going to tell it where to "
        "look.' The search is the one step discovered from what the last one returned; "
        "everything else is settled before the run."
    ),
    "anything_else": (
        "brainstorm: nothing. research: 'the collection gets a new batch most Mondays, so do "
        "not build anything that assumes it is finished.' Every stage since: nothing."
    ),
    "consultation": "Nothing. Every input the agent needs is in the collection.",
    "backend": "mistral-small-2603. A change to it is the builder's to approve.",
    "budget": "8 steps, 50k tokens, no cost cap, 120s. Read off the first run.",
    "tool_effects": "Nothing. The one tool is a read-only search over a fixed collection.",
    "unproven_answer": "Report absence. An answer the passage does not support is not usable.",
    "keep_payloads": "Yes. The collection is public and the questions carry nothing personal.",
    "who_labels": "The builder wrote the labels before the first run.",
    "improvement": "Three rollouts over the held-out split, compared on the interval.",
    "leakage": "Checked: the passages carry no file names, ids or headings naming the answer.",
    "too_similar": (
        "Two examples drawn from one passage are the same example twice; the check runs at "
        "threshold 0.8."
    ),
}

IDEA = """# The passage question answerer

## What this is

An agent that takes a question and a collection of passages, and returns the shortest span that
answers it. Where the collection does not answer the question, it says so instead of guessing.

## Who it is for

The support team who maintain the collection. They are not the builder, and they act on an
answer without reading the passage it came from.

## What it works on

Questions in plain English, against a passage collection the project builds into a
`DocumentIndex`. Passages run to about 120 words. Of the 20 questions read before anything was
written, 3 have no answer anywhere in the collection, which is why absence is a first-class
answer rather than a fallback.

## Where this is going, and where it is not

The smallest version worth having answers span questions and reports absence for the rest. The
finished version cites the passage each answer came from, so an answer can be checked without
reading the whole collection. Not part of this: writing new passages, answering questions that
need two passages combined, and any interface beyond the command line.

## What is still open

Whether a question needing two passages should be answered or reported as absent. The builder
has not decided, and the current behaviour reports absence.
"""
"""What FT-29 reads. Written beside the brief, which names the stage it was confirmed at."""

RESEARCH = """# What was already known about answering a question from a passage collection

## The parts, and what each has to do

1. **Finding the passages that bear on a question.** The collection is fixed and large enough
   that reading all of it per question is not affordable.
2. **Answering from what was found.** The answer is a span of the passage rather than a
   summary, and the absence of one has to be reportable.
3. **Deciding a question is unanswerable.** The collection does not cover everything the
   support team asks.
4. **Judging whether a span is right.** Someone has to say what a correct answer is before
   anything is measured.

## What was found against each part

| Part | Candidate | What it is | Outcome |
|---|---|---|---|
| Finding passages | a hosted answering service | question in, answer out, priced per call | rejected: the collection is internal and may not leave the network |
| Finding passages | BM25 over the collection | lexical, no model, ships with this library | adopted: `document_search` in `docs/tools.md` §4 |
| Finding passages | embeddings and a reranker | finds a passage worded differently from the question | adopted alongside BM25: `docs/retrieval.md` |
| Answering | one call reading every retrieved passage | the common shape in published work | adopted |
| Answering | one call per passage, then a merge | more calls, and the merge has to resolve disagreement | rejected: cost, and nothing said the merge was better here |
| Deciding absence | a confidence threshold on the answer | needs a calibrated score the backend does not publish | not investigated, because no backend under consideration publishes one |
| Deciding absence | an output schema that admits `unknown` | refuses to construct a schema that cannot say it | adopted: FT-09 |
| Judging | a second model scoring the span | cheap, and it agrees with itself rather than with the team | rejected for the reported number, kept for development |
| Judging | the support team labelling a held-out set | slow, and the only source of a label they would act on | adopted |

## What this turns on, having looked

**Deciding a question is unanswerable.** Every approach found for the other three parts is
established and the choice between them is cost. How to decide absence well is an open
question: the calibrated-score route needs something no candidate backend publishes, and what
was adopted records absence rather than deciding it. The failure mode reported everywhere is a confident
answer to a question the collection does not cover, and this project has no signal for it
beyond the labels.

**Finding passages worded differently from the question** is the second. BM25 alone misses it,
which is why the retrieval half runs both.

## What the builder said about it

Shown the survey and asked whether the hosted service was worth another look:

> "No. Nothing in that collection leaves our network, and that is not negotiable."

Asked what to do about absence, given nothing found solves it:

> "Then measure it. I would rather know it gets absence wrong a fifth of the time than have
> it papered over. Put absent questions in the set."

That is why the held-out split carries questions the collection does not answer, and why the
reported number is read beside the absence rate rather than alone.
"""
"""What FT-36 reads. Four sections, a survey table whose `Outcome` column is never blank."""

DESIGN = """# How the passage question answerer is built

## What it does, step by step

It reads the question and searches the passage collection for the five passages closest to it.
It then reads those passages and returns the shortest span in them that answers the question,
or reports that the collection does not answer it. Nothing else happens: one question in, one
span or one absence out.

## What it holds on to between runs

Nothing. The passage collection is fixed and ships with the project, and every run rebuilds the
index from it. A question asked twice gets the same answer for that reason, and an answer the
support team disagreed with is not remembered anywhere.

## The product

The terminal. One interaction: running the answer script with a question starts a run, and the
printed span is that run's return value, read once. Nothing reads an artifact, because none
outlives the run, and nothing records a judgement.

## What the builder said about it

Shown the two steps and asked whether searching before answering was what they pictured:

> "Yes, and I would rather it looked at five passages than one. If the wording is different
> from the passage it still needs to find it."

Asked whether an answer needing two passages combined should be attempted or reported absent:

> "Report it as absent for now. I would rather be told than guess."

That is why `top_k` is 5 rather than 1, and why the finished version reports absence for a
question no single passage answers.
"""
"""What FT-34 reads. Three sections, and the third carries the builder's own words."""

# Which answers each shaping decision was derived from, as `from` in the brief. A `shape` or
# `presentation` decision names them, and the report prints the answers none of them name.
RESTS_ON = {
    "shape": [
        "what_it_does",
        "used_through",
        "smallest_worthwhile",
        "finished_version",
        "purpose",
        "end_user",
        "parts",
        "what_this_turns_on",
        "agency_boundary",
    ],
    "presentation": ["what_it_does", "purpose", "end_user"],
    "dependency": ["approaches", "available_material"],
}


# What each decision became, as `produces` in the brief. These are the fixture pipeline's own
# node ids, its one tool, and the module-level numbers the module its callables live in
# defines, so FT-42 reads a join that resolves and the report's complement is empty.
PRODUCES = {
    "dependency": ["catalogue_search"],
    "shape": ["hunt", "verify"],
    "constant": ["EVAL_K", "EVAL_SEED", "SEED"],
    "prompt_rule": ["hunt", "verify"],
}

GENERIC_ALTERNATIVES = '["what was rejected", "and the other thing"]'

# The alternatives a `dependency` decision weighed, which are the ones `research.md` records
# against the same part. Every other kind carries the generic pair.
CONSIDERED = {
    "dependency": (
        '["a hosted answering service", "the support team\'s ticket history as a second corpus"]'
    ),
}


A_STAMP = "2026-08-27T09:14:02Z"
"""When a fixture's answers and decisions were written down.

Fixed rather than read off the clock, so rebuilding the fixtures leaves the same bytes and a
diff shows what actually moved.
"""


def _decisions(
    proposed: str | None = None,
    *,
    omit: str | None = None,
    produces_nothing: str | None = None,
) -> list[str]:
    """One decision per kind, built from the shipped taxonomy for the same reason `_brief` is.

    `proposed` leaves one kind unsettled and `omit` leaves one out entirely, which are the two
    ways FT-30 fires. `produces_nothing` gives one kind a `produces` naming something no run
    recorded, which is what FT-42 fires on.
    """
    lines: list[str] = []
    for entry in DECISION_KINDS:
        if entry.name == omit:
            continue
        status = "proposed" if entry.name == proposed else "agreed"
        lines += [
            "",
            f"[decisions.{entry.name}_of_this_project]",
            f'kind = "{entry.name}"',
            f'status = "{status}"',
            f'recorded_at = "{A_STAMP}"',
            f'chose = "{DECIDED[entry.name]}"',
            f"considered = {CONSIDERED.get(entry.name, GENERIC_ALTERNATIVES)}",
            'because = "the builder said so, and the reason is recorded here"',
        ]
        if entry.name in RESTS_ON:
            named = ", ".join(f'"{name}"' for name in RESTS_ON[entry.name])
            lines.append(f"from = [{named}]")
        if entry.name in PRODUCES:
            became = list(PRODUCES[entry.name])
            if entry.name == produces_nothing:
                became.append("a_step_that_was_never_built")
            named = ", ".join(f'"{name}"' for name in became)
            lines.append(f"produces = [{named}]")
    return lines


def _brief(
    tier: str = "evaluated",
    *,
    unanswered: str | None = None,
    proposed: str | None = None,
    omit_kind: str | None = None,
    produces_nothing: str | None = None,
) -> str:
    """A brief answering every required question, built from the shipped set.

    Generated rather than transcribed, so a question added to the set leaves the fixtures
    failing FT-24 until they are rebuilt rather than passing against a stale list.
    """
    # A tier decides which stages a project has, and `prototype` has no `measure`, so the
    # stage follows the tier rather than being fixed. `Brief.read` refuses the pairing that
    # does not hold, which is what this got wrong while nothing ran it.
    stage = "measure" if tier != "prototype" else "build"
    lines = [
        "# What this project claims about itself, and what its builder was asked.",
        "# `docs/conformance.md` covers the file; `simple-agents check` reads it.",
        f'tier = "{tier}"',
        f'stage = "{stage}"',
        f'understanding_confirmed_at = "{stage}"',
        f'design_confirmed_at = "{stage}"',
        f'research_confirmed_at = "{stage}"',
        f'confirmed_against = "{eval_pipeline().behaviour_fingerprint(model=REPLAY_CLIENT)}"',
    ]
    for question in required_at(stage, tier):
        if question.name == unanswered:
            lines += ["", f"[entries.{question.name}]", 'status = "unanswered"']
            continue
        lines += [
            "",
            f"[entries.{question.name}]",
            'status = "answered"',
            f'recorded_at = "{A_STAMP}"',
        ]
        if question.re_asked_each_stage:
            # A question every gate puts again is settled only where `asked_at` names the
            # stage the project is at, so a fixture that omitted it would fail FT-24.
            lines.append(f'asked_at = "{stage}"')
        lines.append(f'answer = "{ANSWERS[question.name]}"')
    # One deferral, so the fixture demonstrates the third status as well. It is on an optional
    # question, since a required one deferred to a stage the project has reached is already due
    # and FT-24 counts it unanswered. A tier with no `measure` never reaches `prices`, and a
    # deferral to a stage the tier excludes is refused, so that tier defers to `ship` instead.
    deferred_to = "measure" if tier != "prototype" else "ship"
    lines += ["", "[entries.prices]", 'status = "deferred"', f'deferred_to = "{deferred_to}"']
    lines += _decisions(proposed, omit=omit_kind, produces_nothing=produces_nothing)
    return "\n".join(lines) + "\n"


def build_conforming(into: Path) -> None:
    """Replay the committed evaluation into a project directory that passes all ten."""
    _build(into, examples=_examples())


def build_contaminated(into: Path) -> None:
    """The same evaluation over a split whose two sides share a source, which FT-03 reads.

    Built rather than mutated, so the pairs in the results file are the ones
    ``ExampleSet.contamination`` computed. ``allow_contaminated_split`` is what a project
    passes to get a number over a split like this, and getting one is the failure.
    """
    _build(into, examples=_examples(shared_source=True), allow_contaminated=True)


def build_without_absence(into: Path) -> None:
    """The same evaluation with the absence example moved to dev, which FT-04 reads.

    The example is kept rather than deleted, so the set still holds one and the held-out split
    is what lacks it.
    """
    _build(into, examples=_examples(absence_in_held_out=False))


def _build(
    into: Path,
    *,
    examples: ExampleSet,
    allow_contaminated: bool = False,
) -> None:
    """One fixture project: the brief, the example set, and one replayed evaluation."""
    shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)

    examples.to_jsonl(into / "evals" / "examples.jsonl")
    (into / "brief.toml").write_text(_brief(), encoding="utf-8")
    (into / "idea.md").write_text(IDEA, encoding="utf-8")
    (into / "design.md").write_text(DESIGN, encoding="utf-8")
    (into / "research.md").write_text(RESEARCH, encoding="utf-8")

    envelope = RunEnvelope(
        run_dir=into / "runs",
        cost_basis=MISTRAL_PRICES,
        cassette=Cassette.replay(CASSETTE),
    )
    suite = EvalSuite(
        eval_pipeline(),
        examples,
        answer="answer",
        matches=lambda s: s.expected.lower() in str(s.answer).lower(),
        # `hunt` is labelled, so the conforming project reports a figure per step as well as
        # end to end. Without one every figure it reports is end to end, which is what the
        # `end-to-end-only` mutation is and what FT-08's note reads.
        node_matches={"hunt": _hunt_found_it},
        contamination_threshold=0.8,
    )
    results = suite.run(
        envelope=envelope,
        model=REPLAY_CLIENT,
        split="held_out",
        k=3,
        seed=EVAL_SEED,
        concurrency=1,
        allow_contaminated_split=allow_contaminated,
    )
    results.write(into / "evals" / "results" / "held-out.json")
    _drop_live_progress(into)
    _make_portable(into)


def _hunt_found_it(scoring: Any) -> bool:
    """Whether `hunt` put the labelled answer forward, read off its recorded output.

    The label is what the whole pipeline expects, because `verify` passes an answer it agrees
    with through unchanged, so the same string is the right answer at both steps.
    """
    answer = (scoring.answer or {}).get("answer")
    return str(scoring.expected).lower() in str(answer).lower()


def _examples(*, shared_source: bool = False, absence_in_held_out: bool = True) -> ExampleSet:
    """The recorded evaluation's held-out examples, plus a dev split beside them.

    The dev examples are never run: FT-02 reads the splits the set declares, and the cassette
    holds responses for the held-out three alone.

    ``shared_source`` gives one example on each side of the split the same source, which is
    what a contamination report flags whatever the wording overlap. ``absence_in_held_out``
    false moves the example whose answer is absence to the dev split, leaving the held-out
    side with none.
    """
    absence_split = "held_out" if absence_in_held_out else "dev"
    held_out = [
        Example(
            id=example_id,
            inputs={"question": question},
            expected=expected
            if expected is not None
            else Unknown(reason="the notes give no figure"),
            split="held_out" if expected is not None else absence_split,
            source="doc:kirkwall-history" if shared_source and example_id == "e1" else None,
            expected_by_node={"hunt": expected} if expected is not None else {},
        )
        for example_id, question, expected in EVAL_EXAMPLES
    ]
    dev = [
        Example(
            id="d1",
            inputs={"question": "Which retailer ships from Bristol?"},
            expected="Northgate",
            split="dev",
            source="doc:kirkwall-history" if shared_source else None,
        ),
        Example(
            id="d2",
            inputs={"question": "How many depots does Kirkwall run?"},
            expected=Unknown(reason="the notes give no count"),
            split="dev",
        ),
    ]
    return ExampleSet([*dev, *held_out])


def _drop_live_progress(root: Path) -> None:
    """Remove the ``progress.json`` an evaluation keeps while it runs.

    It carries wall-clock figures and is read by the served view alone; a fixture holding it
    would differ on every regeneration and exercise no check.
    """
    for path in root.rglob("progress.json"):
        path.unlink()


def _make_portable(root: Path) -> None:
    """Rewrite the absolute paths the library records so the fixture survives being copied.

    A results file records each rollout's trajectory by absolute path, and a manifest records
    its own. Both are correct for the run that wrote them and meaningless once committed, so
    they are rewritten relative to the project root and the tests resolve them from there.
    """
    for path in [*root.glob("runs/**/manifest.json"), *root.glob("evals/results/*.json")]:
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace(str(root) + "/", ""), encoding="utf-8")


# -- the mutations --------------------------------------------------------------------------


def _drop_trajectory(root: Path) -> None:
    for path in root.glob("runs/**/trajectory.jsonl"):
        path.unlink()


def _garble_trajectory(root: Path) -> None:
    """A file that exists and is not a trajectory, which `touch` alone would also produce."""
    for path in root.glob("runs/**/trajectory.jsonl"):
        path.write_text('{"note": "ran ok"}\n', encoding="utf-8")


def _float_the_model(root: Path) -> None:
    _edit_json(
        root.glob("runs/**/manifest.json"),
        lambda data: data["models"]["configured"].__setitem__(
            "request_model", "mistral-small-latest"
        ),
    )


def _unversioned_prompt(root: Path) -> None:
    """A prompt whose source could not be read, which is what FT-15 fails on.

    What a REPL-defined prompt leaves in the manifest: the entry is there and the version is
    not, so an edit to it has nothing to be traced to.
    """

    def blank(data: dict) -> None:
        node_id = sorted(data["prompts"])[0]
        data["prompts"][node_id] = {"version": None, "source": "unavailable"}

    _edit_json(root.glob("runs/**/manifest.json"), blank)


def _one_split(root: Path) -> None:
    _edit_json(
        root.glob("evals/results/*.json"),
        lambda data: data["config"]["example_set"].__setitem__("splits", {"held_out": 3}),
    )


def _bare_metric(root: Path) -> None:
    _edit_json(
        root.glob("evals/results/*.json"),
        lambda data: data["metrics"].__setitem__("accuracy", 0.87),
    )


def _end_to_end_only(root: Path) -> None:
    """Every figure end to end: the per-node accuracy goes, and so does its label.

    What FT-08's note reads. The library computes per-node metrics out of the trajectories with
    no project effort, so a project that localised nothing still has a `nodes` section; what it
    does not have is a figure of its own on any node.
    """

    def strip(data: dict[str, Any]) -> None:
        for node in (data.get("nodes") or {}).values():
            node["accuracy"] = None
        for rollout in data["rollouts"]:
            for observed in (rollout.get("nodes") or {}).values():
                observed["matched"] = None
        data["config"]["node_metrics"] = {}

    _edit_json(root.glob("evals/results/*.json"), strip)


def _drop_rollout_seeds(root: Path) -> None:
    def strip(data: dict[str, Any]) -> None:
        for rollout in data["rollouts"]:
            rollout["seed"] = None

    _edit_json(root.glob("evals/results/*.json"), strip)


def _drop_node_seed(root: Path) -> None:
    """One agent node's seed, which is the record `docs/trajectory-format.md` §3 requires."""
    for path in sorted(root.glob("runs/**/trajectory.jsonl"))[:1]:
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("record_type") == "node_execution":
                record["seed"] = None
            lines.append(json.dumps(record))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _spun_node(root: Path) -> None:
    """One run in which `hunt` spent its budget without calling anything, which FT-35 reads.

    Written into the manifest rather than produced by a run: the recording the fixtures replay
    answers every call with a `finish`, and a loop that spins is a different recording. What
    the check reads is this block, and `tests/test_unfinished_work.py` is where the block
    itself is checked against the trajectory it is derived from.
    """
    newest = sorted(root.glob("runs/**/manifest.json"))[:1]
    _edit_json(
        newest,
        lambda data: data.__setitem__(
            "unfinished",
            {
                "hunt": {
                    "executions": 1,
                    "items": 0,
                    "without_tool_calls": 1,
                    "model_calls": 8,
                    "model_calls_without_tool_calls": 8,
                }
            },
        ),
    )


def _no_evaluation(root: Path) -> None:
    shutil.rmtree(root / "evals" / "results")


def _prototype_tier(root: Path) -> None:
    (root / "brief.toml").write_text(_brief("prototype"), encoding="utf-8")


def _unanswered_question(root: Path) -> None:
    """One required question recorded as unanswered, which is what FT-24 fires on."""
    (root / "brief.toml").write_text(_brief(unanswered="absence_vs_error"), encoding="utf-8")


def _unsettled_decision(root: Path) -> None:
    """One decision the builder never saw, which is the first way FT-30 fires."""
    (root / "brief.toml").write_text(_brief(proposed="constant"), encoding="utf-8")


def _missing_decision_kind(root: Path) -> None:
    """A kind with no entry at all, which is the second. Absent is not the same as none."""
    (root / "brief.toml").write_text(_brief(omit_kind="dependency"), encoding="utf-8")


def _decision_produced_nothing(root: Path) -> None:
    """A `shape` decision naming a step no run recorded, which is what FT-42 fires on."""
    (root / "brief.toml").write_text(_brief(produces_nothing="shape"), encoding="utf-8")


def _edit_json(paths: Any, edit: Callable[[dict[str, Any]], None]) -> None:
    for path in paths:
        data = json.loads(path.read_text(encoding="utf-8"))
        edit(data)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


MUTATIONS: dict[str, Callable[[Path], None]] = {
    "no-trajectory": _drop_trajectory,
    "unreadable-trajectory": _garble_trajectory,
    "floating-model": _float_the_model,
    "unversioned-prompt": _unversioned_prompt,
    "one-split": _one_split,
    "bare-metric": _bare_metric,
    "end-to-end-only": _end_to_end_only,
    "no-rollout-seeds": _drop_rollout_seeds,
    "no-node-seed": _drop_node_seed,
    "spun-node": _spun_node,
    "no-evaluation": _no_evaluation,
    "prototype": _prototype_tier,
    "unanswered-question": _unanswered_question,
    "unsettled-decision": _unsettled_decision,
    "missing-decision-kind": _missing_decision_kind,
    "decision-produced-nothing": _decision_produced_nothing,
}

BUILT: dict[str, Callable[[Path], None]] = {
    "contaminated-split": build_contaminated,
    "no-absent-examples": build_without_absence,
}


def main(into: Path | None = None, *, announce: bool = True) -> None:
    """Build every fixture project under ``into``, which defaults to the committed tree.

    ``into`` is what lets a test regenerate into a temporary directory and compare, so a
    fixture whose contents no longer match what the library writes is caught rather than only
    one whose declared format version is stale.
    """
    # `CASSETTE` is relative so it stays out of the fixtures. Resolve it the same way
    # wherever this is invoked from.
    os.chdir(ROOT)
    fixtures = FIXTURES if into is None else Path(into)

    def built(target: Path) -> None:
        if announce:
            print(f"built {target.relative_to(ROOT) if into is None else target.name}")

    conforming = fixtures / "conforming"
    build_conforming(conforming)
    built(conforming)
    for name, mutate in MUTATIONS.items():
        target = fixtures / name
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(conforming, target)
        mutate(target)
        built(target)
    # Two fixtures a copy-and-edit cannot produce: what they carry is what the library computed
    # from an example set, so each is built from its own set rather than written into the file
    # the conforming run wrote.
    for name, build in BUILT.items():
        target = fixtures / name
        build(target)
        built(target)


if __name__ == "__main__":
    main()
