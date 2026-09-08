"""Record the run records the view fixtures hold, and verify their cassettes still serve.

The projects under ``tests/fixtures/view_projects/`` are one shape each, and four of them
hold runs. A record written under an older format is not the artifact the view will meet,
and ``tests/test_view_fixtures.py`` fails when they drift; this script is how they are made
current again. Each project's ``record.py`` is the spec: which runs, which inputs, which
seeds, which evaluation.

    uv run python scripts/build_view_fixtures.py            # verify the cassettes serve, offline
    uv run python scripts/build_view_fixtures.py --record   # re-record everything, live

**The committed records are live recordings, deliberately.** A replayed call is served and
spends nothing, so records regenerated offline carry ``tool_spend: null`` and
``paid_tool_calls: 0`` however much the recorded run spent, and the page's money surfaces
would be tested against files that cannot carry a spend. ``--record`` therefore deletes each
project's cassettes and records everything against the live backend under ``GEMINI_API_KEY``
(about 0.15 USD for the lot, most of it ``measured``), which is the regeneration path after any change that moves a
format or invalidates a recorded call.

The default invocation is offline and writes nothing: it replays each project's spec from
the committed cassettes into a scratch copy and fails if a call no longer serves or the
evaluation's outcomes differ from the committed results file. ``--record`` also rebuilds
``_stages/``, which is derived from ``branching`` by ``scripts/view_at_stage.py``; its
pages embed the time they were generated, so a rebuild always dirties them and belongs
with a re-record rather than with a check.

**``many-pipelines`` is never touched.** Its run asserts ``code_moved_since`` on ``ingest``,
whose generating code was replaced by a ``NotBuilt`` afterwards and is gone, so the
staleness of that one run is the property under test. ``FROZEN`` names it, and the currency
check exempts exactly that name for this reason.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[1]
VIEW = ROOT / "tests" / "fixtures" / "view_projects"

# Projects whose runs are recorded here, in the order they are made.
RECORDED = ("one-pipeline", "branching", "measured", "prompted")

# Derived, not recorded: `shipped` is `measured` at stage `ship` with its product declared and
# two live runs replayed from the committed cassettes. See `build_shipped`.
DERIVED = "shipped"

# The run that is deliberately stale, and must never be re-recorded or deleted here.
FROZEN = "many-pipelines/runs/run_20260826T005906Z_2d8817fc"


@contextmanager
def _inside(project: Path):
    """Run with the project as the working directory and its modules importable.

    Every fixture project holds an ``agent`` and a ``record`` module under the same names,
    so the previous project's are dropped from ``sys.modules`` on the way in and out.

    The pipeline registry is emptied with them. It is process-global, and `shipped` is a copy
    of `measured` carrying the same factory names, so a `--record` of the whole set imported
    the second one into a registry still holding the first and was refused.
    """
    from simple_agents import clear_registered_pipelines

    held_cwd = Path.cwd()
    held_path = list(sys.path)
    for name in ("agent", "record"):
        sys.modules.pop(name, None)
    clear_registered_pipelines()
    os.chdir(project)
    sys.path.insert(0, str(project))
    try:
        yield
    finally:
        os.chdir(held_cwd)
        sys.path[:] = held_path
        for name in ("agent", "record"):
            sys.modules.pop(name, None)
        clear_registered_pipelines()


def _spec_of(project: Path):
    """The project's ``record`` module, loaded fresh from its own directory."""
    spec = importlib.util.spec_from_file_location("record", project / "record.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["record"] = module
    spec.loader.exec_module(module)
    return module


def record_project(project: Path) -> None:
    """Delete the project's runs and cassettes, and record everything live."""
    from simple_agents import Cassette

    with _inside(project):
        record = _spec_of(project)
        shutil.rmtree(project / "runs", ignore_errors=True)
        shutil.rmtree(project / "cassettes", ignore_errors=True)
        (project / "cassettes").mkdir()

        def cassette_for(label: str, evaluation: bool = False) -> Cassette:
            return Cassette.record(Path("cassettes") / f"{label}.jsonl")

        record.make(cassette_for, record.client())
        # The spec keeps the run directories the page reads and drops the rest, which it
        # does for itself when run as a script and has to be asked for here.
        if hasattr(record, "prune"):
            record.prune()


def _outcome_counts(results_path: Path) -> Counter:
    raw = json.loads(results_path.read_text())
    return Counter(str(r.get("outcome")) for r in raw.get("rollouts") or [])


def _session_verdicts(results_path: Path) -> list[tuple[str, str]]:
    """What a session of judged pairs decided, pair by pair, for comparing two copies of it."""
    raw = json.loads(results_path.read_text())
    return [(str(p.get("id")), str(p.get("verdict"))) for p in raw.get("pairs") or []]


def verify_project(project: Path) -> None:
    """Replay the project's spec from its cassettes into a scratch copy.

    Passes when every call still serves and, where the project holds an evaluation, the
    replayed evaluation sorts its rollouts into the same outcomes the committed results
    file records. Replay accounting differs from a live run's (a served call spends
    nothing), which is why the comparison is outcomes rather than bytes.
    """
    from simple_agents import Cassette

    committed = project / "evals" / "results" / "held-out.json"
    before = _outcome_counts(committed) if committed.exists() else None
    session = project / "evals" / "results" / "head-to-head.json"
    judged = _session_verdicts(session) if session.exists() else None
    with tempfile.TemporaryDirectory(prefix=f"view-fixture-{project.name}-") as scratch:
        copy = Path(scratch) / project.name
        shutil.copytree(project, copy, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.rmtree(copy / "runs", ignore_errors=True)
        with _inside(copy):
            record = _spec_of(copy)

            def cassette_for(label: str, evaluation: bool = False) -> Cassette:
                return Cassette.replay(Path("cassettes") / f"{label}.jsonl")

            record.make(cassette_for, record.client("not-used-in-replay"), replaying=True)
        if before is not None:
            after = _outcome_counts(copy / "evals" / "results" / "held-out.json")
            if after != before:
                raise SystemExit(
                    f"{project.name}: the replayed evaluation sorts its rollouts as "
                    f"{dict(after)} and the committed results file records {dict(before)}. "
                    f"The cassettes no longer reproduce the committed record; re-record "
                    f"with --record and commit what it writes."
                )
        if judged is not None:
            again = _session_verdicts(copy / "evals" / "results" / "head-to-head.json")
            if again != judged:
                raise SystemExit(
                    f"{project.name}: the session of judged pairs rebuilt from the replayed "
                    f"arms decides {sum(a != b for a, b in zip(again, judged))} pair(s) "
                    f"differently from the committed head-to-head.json. Re-record with "
                    f"--record and commit what it writes."
                )


def build_shipped() -> None:
    """Derive ``shipped`` from ``measured``: the same project, taken to `ship`.

    Three things are added and nothing is invented. The brief's stage moves to ``ship``.
    ``surface.py`` declares the product, and ``agent.py`` imports it, because the view reads
    what ``agent.py`` reaches; the surface's own numbers live there beside the declaration,
    which is what separates them from the pipeline's. ``design.md`` carries the four sections
    FT-34 requires, with a product section naming two of the three surfaces, so the check that
    reads the declaration against it has something to report. ``surface.py`` also declares the
    two jobs the operate runs below record as their ``trigger``.

    **The live runs are real runs, replayed.** Each of ``measured``'s two claims is run again
    under an envelope that says an end user was on the other end, against the committed
    cassette, so the records are written by the library rather than edited: `runs/live/` holds
    what a shipped project's own traffic leaves behind. They cost nothing and spend nothing,
    and a replayed run carries no tool spend, which is why the priced records the page's money
    surfaces are tested against stay the recorded ones under `runs/dev/`.
    """
    source = VIEW / "measured"
    out = VIEW / DERIVED
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(source, out, ignore=shutil.ignore_patterns("__pycache__"))

    held = HERE / "fixture_shipped"
    brief = out / "brief.toml"
    text = brief.read_text(encoding="utf-8").replace(
        'stage = "measure"',
        'stage = "ship"\n'
        # A key written after a table belongs to that table, so the four the `ship` gate reads
        # off the brief's own header go in beside the stage.
        'understanding_confirmed_at = "ship"\n'
        'design_confirmed_at = "ship"\n'
        'research_confirmed_at = "ship"\n'
        'confirmed_against = "__FINGERPRINT__"',
        1,
    )
    # `anything_else` is put again at every stage, so it carries the stage it was last put at.
    text = text.replace(
        '[entries.anything_else]\nstatus = "answered"',
        '[entries.anything_else]\nstatus = "answered"\nasked_at = "ship"',
        1,
    )
    # FT-32 reads whether the answer names each class of effect the run declares, by the
    # class's own words, so the answer says "spends money" where it said "costs money".
    text = text.replace(
        "the supplier registry costs money per lookup",
        "the supplier registry spends money per lookup",
        1,
    )
    brief.write_text(
        text + (held / "brief_additions.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    for name in ("surface.py", "reconcile.py", "design.md", "idea.md", "research.md"):
        shutil.copy(held / name, out / name)
    with (out / "agent.py").open("a", encoding="utf-8") as agent:
        agent.write(
            "\n\n# -- the product ----------------------------------------------------------"
            "--------------------\n"
            "# `simple-agents view` reads what `agent.py` reaches, so the module declaring the\n"
            "# product is imported here. Its own numbers live beside the declaration, and the\n"
            "# background pipeline is registered the same way.\n"
            "import reconcile  # noqa: E402,F401\n"
            "import surface  # noqa: E402,F401\n"
        )

    from simple_agents import Cassette

    with _inside(out):
        record = _spec_of(out)
        model = record.client("not-used-in-replay")
        for label, inputs, seed in record.RUNS:
            cassette = Cassette.replay(Path("cassettes") / f"{label}.jsonl")
            result = record.claims().run(
                inputs,
                envelope=record.envelope(cassette).with_live(),
                model=model,
                seed=seed,
            )
            print(f"  live run: {result.paths.manifest}")
        # FT-38 asks the brief to record the pipeline its entries were last read against, and
        # the fingerprint is what the code produces rather than something written by hand. It
        # is taken here rather than in a pass of its own, because importing the project twice
        # in one process registers its pipeline factory twice, which the registry refuses.
        # The model-calling nodes take whatever client the run is given, so the stamp is
        # computed against the one these runs used.
        stamp = record.claims().behaviour_fingerprint(model=model)

    brief.write_text(
        brief.read_text(encoding="utf-8").replace("__FINGERPRINT__", stamp, 1), encoding="utf-8"
    )
    build_operating(out)


def build_operating(project: Path) -> None:
    """The runs the operate page reads: what a shipped project leaves behind.

    Six runs of the background pipeline, all deterministic, so none calls a model and none
    costs anything. Each is a real run written by the library rather than a record edited into
    place: one waiting on a person, one waiting on a clock, one that shelved a question nobody
    has answered, one whose tool was throttled until its attempts were spent, and two turns of
    one conversation. The seventh is killed mid-run in a process of its own, which is the only
    way to leave the open manifest a run reads as abandoned from.

    Each records the job that started it: the five are the nightly reconcile, the two turns
    are the month-end close, and the killed one carries a trigger the product never declared,
    which is what the operate page's undeclared row is read from.
    """
    from simple_agents import ConversationStore, RunEnvelope, RunSuspended

    env = RunEnvelope(
        run_dir="runs",
        conversations=ConversationStore("conversations"),
    ).with_live()

    with _inside(project):
        import reconcile as background

        made = background.reconcile()
        for mode in ("waiting", "clock", "shelve", "throttled", "settle"):
            try:
                made.run({"mode": mode}, envelope=env, model=None, trigger="nightly reconcile")
            except RunSuspended as stopped:
                print(f"  suspended: {stopped.run_id} ({mode})")
                continue
            except Exception as error:  # noqa: BLE001 - the throttled arm ends in a failure
                print(f"  ended: {mode}: {type(error).__name__}")
                continue
            print(f"  live run: {mode}")
        for turn in (1, 2):
            made.run(
                {"mode": "settle", "since": f"2026-08-2{turn}"},
                envelope=env,
                model=None,
                conversation_id="finance-august-close",
                trigger="month-end close",
            )
            print(f"  conversation turn {turn}")

    _abandon_one(project)


def _abandon_one(project: Path) -> None:
    """One run killed between its manifest being written and being rewritten.

    A killed process writes nothing, so `RunHandle.liveness` derives `abandoned` from a
    manifest with no outcome. Producing one means actually killing a process: a node calls
    `os._exit`, so the library's own bookkeeping never runs, which is the state a machine
    losing power leaves behind.
    """
    script = (
        "import os, sys\n"
        "sys.path.insert(0, '.')\n"
        "from simple_agents import Budget, Deterministic, Pipeline, RunEnvelope\n"
        "import reconcile as background\n"
        "def die(inputs, ctx):\n"
        "    os._exit(9)\n"
        "made = Pipeline([Deterministic(background.pick_up, node_id='pick_up',\n"
        "                               successors=['settle'], tools=[background.ledger_rows]),\n"
        "                 Deterministic(die, node_id='settle', successors=[])],\n"
        "                budget=Budget(max_steps=4, max_tokens=None, max_cost=None,\n"
        "                              max_wall_clock_ms=1000))\n"
        "made.run({'mode': 'settle'}, envelope=RunEnvelope(run_dir='runs').with_live(),\n"
        "         model=None, trigger='weekly digest')\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", script], cwd=project, capture_output=True, text=True
    )
    print(f"  abandoned: the killed run exited {done.returncode}")


def build_stages() -> None:
    """Rebuild ``_stages/`` from ``branching``, one derived project and page per stage."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from view_at_stage import STAGES, build

    out = VIEW / "_stages"
    if out.exists():
        shutil.rmtree(out)
    build(VIEW / "branching", out, sorted(STAGES))


def main(*, record: bool = False, announce: bool = True) -> None:
    if record and not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("--record makes live calls and GEMINI_API_KEY is not set.")
    for name in RECORDED:
        if announce:
            print(f"== {name}")
        (record_project if record else verify_project)(VIEW / name)
    frozen = VIEW / FROZEN
    if not frozen.exists():
        raise SystemExit(
            f"the frozen run {FROZEN} is missing. It cannot be regenerated (its generating "
            f"code is gone) and must be restored from git."
        )
    if announce:
        print(f"== many-pipelines: frozen, untouched ({FROZEN})")
    if record:
        if announce:
            print(f"== {DERIVED}")
        build_shipped()
    # `_stages/` is derived from `branching` with no live call, and it is not tracked, so a
    # fresh clone rebuilds it here on every invocation rather than only under --record.
    if announce:
        print("== _stages")
    build_stages()
    if announce:
        print("done")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--record",
        action="store_true",
        help="delete each project's cassettes and record everything against the live backend",
    )
    args = parser.parse_args()
    main(record=args.record)
