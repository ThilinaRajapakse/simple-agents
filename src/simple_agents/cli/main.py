"""The ``simple-agents`` command.

Eight subcommands::

    simple-agents init                        # register the procedure where a coding agent reads it
    simple-agents questions --stage shape     # the questions to put to the builder at a stage
    simple-agents check                       # the conformance checks over a project
    simple-agents check --json                # the same report as JSON, for a gate to read
    simple-agents report runs/                # what every node did, over the runs on disk
    simple-agents view                        # one page of the system, for the builder
    simple-agents view --serve                # the same page, live: comments and answers land
    simple-agents comments                    # the threads the builder left, open first
    simple-agents watch runs/eval/eval_a1226bc495df   # an evaluation in progress, from another terminal

``check`` exits 0 when no check failed, 1 when one did, and 2 when the suite could not run at
all, which is a missing or unreadable brief. The JSON is the report of one run rather than an
artifact the project keeps, so nothing writes it to disk.

``report`` reads whatever it is pointed at: a directory of runs, one run, an evaluation's
directory of rollouts, or a results file. It exits 0 whatever it finds, since it reports and
gates nothing, and 2 where the path holds none of those.

``init`` exits 1 without replacing anything where the skill is already registered, and
``--force`` is what replaces it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from ..conformance import (
    DECISION_KINDS,
    STAGES,
    Scope,
    Tier,
    questions_at,
    run_checks,
    stages_for,
)
from ..errors import SimpleAgentsError
from .record import add_record_command, run_record

__all__ = ["main"]

# Where a skill goes for each harness. `.agents/skills` is the agent-neutral location; Claude
# Code reads `.claude/skills` instead.
NEUTRAL_SKILLS = Path(".agents/skills")
CLAUDE_SKILLS = Path(".claude/skills")

SKILL_NAME = "simple-agents"

# The heading the note opens with, which is how a second `init` finds a note it wrote before.
AGENTS_HEADING = "## Simple Agents"


def agents_note(skill: str) -> str:
    """The AGENTS.md note pointing a coding agent at the procedure, at ``skill``.

    ``skill`` is the path the procedure was registered at, relative to the project root, and
    the note names that path rather than a fixed one::

        agents_note(".claude/skills/simple-agents/SKILL.md")

    A note naming a path the project does not have sends the coding agent that reads it to a
    file that is not there.
    """
    return (
        f"{AGENTS_HEADING}\n"
        f"\n"
        f"This project is built with Simple Agents. The procedure is in\n"
        f"`{skill}`, and it is staged: each stage ends at a gate that runs\n"
        f"`simple-agents check`. Read it before writing a node, a tool or an evaluation.\n"
        f"The `docs/*.md` files it names install with the package;\n"
        f'`python -c "import simple_agents; print(simple_agents.docs_path())"` prints the\n'
        f"directory holding them.\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command. Returns the exit status rather than raising ``SystemExit``."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 2
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "questions":
            return _questions(args)
        if args.command == "watch":
            return _watch(args)
        if args.command == "report":
            return _report(args)
        if args.command == "view":
            return _view(args)
        if args.command == "comments":
            return _comments(args)
        if args.command == "record":
            return run_record(args, parser)
        return _check(args)
    except SimpleAgentsError as exc:
        print(str(exc), file=sys.stderr)
        return 2


def _watch(args: argparse.Namespace) -> int:
    """Follow an evaluation that is running, from another terminal.

    Reads the run directory rather than importing the project, so it needs nothing of the
    process it is watching. Returns once every rollout ``--expected`` named has finished.
    Without that total nothing says when the evaluation is over, so it follows until
    interrupted, or until ``--once`` reads a single time.
    """
    from ..evaluation.progress import progress_of
    from ..progress import ProgressBar

    bar = ProgressBar(desc=Path(args.path).name)
    try:
        while True:
            state = progress_of(args.path, expected=args.expected)
            bar(_as_rollout_progress(state))
            if state["done"]:
                return 0
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 130
    finally:
        bar.close()


def _as_rollout_progress(state: dict[str, Any]) -> Any:
    """What `progress_of` read, in the shape the display takes.

    `progress_of` reads a directory and `RolloutProgress` is what a running evaluation
    reports, so the two carry the same figures under different names.
    """
    from ..evaluation.progress import RolloutProgress

    return RolloutProgress(
        eval_id=Path(state["run_dir"]).name,
        finished=state["finished"],
        # `None` rather than the count so far: a directory holding 12 rollouts cannot say
        # whether that is all of them, and a bar reading 12 of 12 would say it is.
        total=state["expected"],
        resumed=0,
        outcomes=state["outcomes"],
        cost=state["cost"],
        currency=state["currency"],
        elapsed_s=state["elapsed_s"],
        remaining_s=state["remaining_s"],
        latest=None,
    )


def _check(args: argparse.Namespace) -> int:
    report = run_checks(
        args.path,
        brief=args.brief,
        run_dir=args.run,
        results=args.results,
        scope=Scope(
            role=args.role,
            live=args.live,
            pipeline=args.pipeline,
            scripted=None if args.scripted else False,
            since=args.since,
            last=args.last,
        ),
    )
    if args.json:
        print(json.dumps(report.to_record(), indent=2))
    else:
        print(report.text())
        _regenerate_the_view(args.path)
    return 0 if report.ok else 1


def _regenerate_the_view(root: str) -> None:
    """Every gate rewrites `view.html`, so the page cannot go stale between looks.

    A failure to generate never changes the gate's verdict: the checks read files, the view
    additionally imports the project's code, and a project whose code does not import still
    deserves its report.
    """
    from ..view import generate_view

    try:
        written = generate_view(root)
    except Exception as error:  # noqa: BLE001 - reported, never fatal to a gate
        print(f"\nview: not regenerated ({type(error).__name__}: {error})")
        return
    print(f"\nview: {written} regenerated. Open it with the builder.")


def _view(args: argparse.Namespace) -> int:
    """Generate the project's page, or serve it live."""
    if args.serve:
        from ..view.serve import serve_view

        serve_view(args.path, port=args.port)
        return 0
    from ..view import generate_view

    written = generate_view(args.path, out=args.out)
    print(f"{written}")
    return 0


def _comments(args: argparse.Namespace) -> int:
    """Print the threads for the coding agent: open first, each with its whole exchange."""
    from ..records.comments import DEFAULT_COMMENTS, read_comments

    held = read_comments(Path(args.path) / DEFAULT_COMMENTS)
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": c.id,
                        "at": c.at,
                        "by": c.by,
                        "kind": c.kind,
                        "said": c.said,
                        "about": c.about,
                        "stage": c.stage,
                        "shape": c.shape,
                        "when": c.when,
                        "status": c.status,
                        "addressed_by": c.addressed_by,
                        "addressed_when": c.addressed_when,
                        "replies": [
                            {"by": r.by, "said": r.said, "when": r.when} for r in c.replies
                        ],
                    }
                    for c in held.all
                ],
                indent=2,
            )
        )
        return 0
    if not held.all:
        print("no comments; the builder has not said anything through the view yet")
        return 0
    shown = held.all if args.all else held.open
    closed = len(held.all) - len(held.open)
    for thread in shown:
        marker = {"open": "OPEN", "addressed": "done", "withdrawn": "gone"}[thread.status]
        kind = f" [{thread.kind}]" if thread.kind != "comment" else ""
        print(f"{marker:>4}  {thread.id}  {thread.at}{kind}")
        if thread.about:
            print(f"      about: {thread.about}")
        print(f"      {thread.by}: {thread.said}")
        for reply in thread.replies:
            print(f"      {reply.by}: {reply.said}")
        if thread.status == "addressed" and thread.addressed_by:
            print(f"      addressed by {thread.addressed_by}")
        print()
    if not args.all and closed:
        print(f"and {closed} addressed or withdrawn; --all shows them")
    if not shown and not closed:
        print("nothing open")
    return 0


def _report(args: argparse.Namespace) -> int:
    """Print what the runs, or the evaluation, at a path did.

    Reads a results file as a measurement and anything else as runs, which is what separates
    the two views: a results file carries the rates and the rollouts it scored, and a directory
    of runs carries what the agent has been doing since.
    """
    from ..evaluation import EvalResults
    from .reporting import report_over_runs

    path = Path(args.path).expanduser()
    if path.is_file():
        if not _is_a_results_file(path):
            # A trajectory or a manifest is what gets pointed at here, and both are a run's
            # own files, so the message names the directory that holds them. A results file
            # of another version reaches `EvalResults.read`, which refuses it by version.
            print(
                f"{path} is not a results file, which is what an evaluation writes under "
                f"evals/results/. To read the run this file belongs to, point at its "
                f"directory: simple-agents report {path.parent}",
                file=sys.stderr,
            )
            return 2
        results = EvalResults.read(path)
        print(json.dumps(_measurement(results), indent=2) if args.json else results.report())
        return 0

    if getattr(args, "walk", False):
        return _walk(path, as_json=args.json)

    where = path if _holds_runs(path) else path / "runs"
    report = report_over_runs(
        where,
        role=args.role,
        live=args.live,
        pipeline=args.pipeline,
        scripted=None if args.scripted else False,
        since=args.since,
        last=args.last,
    )
    if not report.read and not report.found:
        print(
            f"No run and no results file at {path}. `simple-agents report` reads a run "
            f"directory, a directory of runs such as runs/, an evaluation's directory of "
            f"rollouts, or a results file under evals/results/.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report.to_record(), indent=2) if args.json else report.text())
    return 0


def _walk(path: Path, *, as_json: bool) -> int:
    """One run printed step by step: what each was handed, what it did, what it handed on."""
    from ..view.walk import walk_run

    held = walk_run(path)
    if held is None:
        print(
            f"No trajectory at {path}. `--walk` reads one run directory, which is the one "
            f"holding trajectory.jsonl and manifest.json.",
            file=sys.stderr,
        )
        return 2
    if as_json:
        print(json.dumps(held, indent=2))
        return 0
    for line in _walk_lines(held):
        print(line)
    return 0


def _walk_lines(held: dict[str, Any]) -> list[str]:
    """The walk as text, one block per step."""
    lines = [
        f"{held['run']} · {held.get('outcome') or 'no recorded outcome'} · "
        f"{held['ran']} step(s) ran, {held['skipped']} never reached",
        "",
    ]
    for number, step in enumerate(held["steps"], start=1):
        if step["termination"] == "skipped":
            lines.append(f"{number:>3}. {step['node_id']}  (the run did not reach it)")
            continue
        went = f" → {', '.join(step['route'])}" if step["route"] else ""
        lines.append(
            f"{number:>3}. {step['node_id']}  {step['took_in_volume']} in, "
            f"{step['handed_on_volume']} out, {round(step['ms']):,} ms{went}"
        )
        if step["error"]:
            lines.append(f"     failed: {step['error']}")
        for one in step["did"]:
            lines.append(f"     {_walk_call(one)}")
        if step["did_not_shown"]:
            lines.append(f"     (and {step['did_not_shown']:,} more it did, not shown)")
        lines.append("")
    if held["left_out"]:
        lines.append(f"({held['left_out']:,} more steps are not shown.)")
    return lines


def _walk_call(one: dict[str, Any]) -> str:
    """One thing a step did, as a line under it."""
    if one["kind"] == "model":
        asked = f", called {', '.join(one['asked_for'])}" if one["asked_for"] else ""
        return f"asked {one['name']}{asked}: {one['said'][:120]}"
    if one["kind"] == "tool":
        return f"called {one['name']}({one['asked'][:60]}) → {one['got'][:100]}"
    if one["kind"] == "access":
        way = "wrote" if one["direction"] == "write" else "read"
        return f"{way} {one['name']}: {one['asked'][:60]} → {one['got'][:100]}"
    return f"asked a person: {one['prompt'] or ''} → {one['answer'] or one['resolution']}"


def _is_a_results_file(path: Path) -> bool:
    """Whether this file is an evaluation's results, whatever version it declares."""
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False
    return isinstance(parsed, dict) and "eval_format_version" in parsed


def _holds_runs(path: Path) -> bool:
    """Whether this directory is a run, or holds runs at any depth."""
    from ..envelope import runs

    return bool(runs(path, nested=True))


def _measurement(results: Any) -> dict[str, Any]:
    """One evaluation's figures, for something that reads them rather than a person.

    The rollouts are in the results file itself, which a reader who wants them opens. So is the
    floor an agent that did nothing would have scored, which the text report prints under each
    figure and this does not carry.
    """
    outcomes: dict[str, int] = {}
    for rollout in results.rollouts:
        outcomes[rollout.outcome.value] = outcomes.get(rollout.outcome.value, 0) + 1
    return {
        "eval_id": results.eval_id,
        "created_at": results.created_at,
        "path": str(results.path) if results.path else None,
        "config": results.config,
        "metrics": {name: m.to_record() for name, m in results.metrics.items()},
        "criteria": {name: m.to_record() for name, m in results.criteria.items()},
        "nodes": {node_id: m.to_record() for node_id, m in results.nodes.items()},
        "totals": results.totals,
        "outcomes": outcomes,
    }


def _decision_kinds(*, as_json: bool) -> int:
    """Print the six kinds of decision that go to the builder rather than being made for them."""
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "name": k.name,
                        "ask": k.ask,
                        "covers": k.covers,
                        "example": k.example,
                        "produces": k.produces,
                    }
                    for k in DECISION_KINDS
                ],
                indent=2,
            )
        )
        return 0
    print(
        "Six kinds of decision belong to the builder. Record each under [decisions] in "
        "brief.toml with its kind, what was chosen, what else was considered and why, then "
        "put it to them and record the answer. FT-30 refuses a gate while one is `proposed`.\n"
        "Every decision records `recorded_at`, the system clock in ISO 8601 with a zone, "
        "which is what says whether the code has moved since it was made:\n"
        '  [decisions.<name>] kind = "shape", status = "agreed", '
        'recorded_at = "<now>", chose = "...", considered = ["..."], because = "..."\n'
        "Four of the six also record what the decision became, under `produces`, once the "
        "code exists. FT-42 reads those against every run the project has made.\n"
    )
    for entry in DECISION_KINDS:
        print(f"  {entry.name}")
        print(f"    ask:      {entry.ask}")
        print(f"    covers:   {entry.covers}")
        print(f"    example:  {entry.example}")
        if entry.produces:
            print(f"    produces: {entry.produces}")
        print()
    return 0


HOW_A_QUESTION_IS_PUT = """\
Put `ask` to the builder in the terms of their own work, and follow the scaffold where it \
asks for more than one exchange: several exchanges are recorded as one answer. The heading \
is the same question named for a builder, and `key` is what brief.toml records the answer \
under.

How to ask a question, here and for any question composed later:
  - Involve something of the builder's own: one of their inputs, one of their rows, one
    run's output, written into the question.
  - Any number it turns on is looked up first, and the question says where the number
    came from.
  - The options are named, with which one is recommended and why.
  - Every term the builder has not used themselves is explained, including names from the
    project's own code.
  - Do not mix prose questions into an exchange that puts questions through the session's
    question mechanism: only the mechanism's questions come back answered. A question that
    got no answer stays unanswered, and is put again.

An entry the builder has not seen records source = "coding_agent", and a required one fails \
the gate until it is put to them (FT-24).
"""
"""The preamble `simple-agents questions` prints above a stage's questions.

The five rules govern a question the coding agent composes as well as these, and
`docs/procedure.md` carries them where the procedure itself is read.
"""


def _questions(args: argparse.Namespace) -> int:
    """Print the questions that apply at a stage, each with what makes it answerable."""
    if getattr(args, "decisions", False):
        return _decision_kinds(as_json=args.json)
    tier = getattr(args, "tier", None)
    if tier is not None and tier not in Tier.ORDER:
        print(
            f"{tier!r} is not a tier. The three are {', '.join(Tier.ORDER)}, and the tier "
            f"decides which stages a project has: {', '.join(stages_for('prototype'))} at "
            f"prototype, and all five above it.",
            file=sys.stderr,
        )
        return 2
    asked = questions_at(args.stage, tier)
    if not asked:
        print(
            f"{args.stage!r} is not a stage. The six are {', '.join(STAGES)}, in that "
            f"order, and each includes the questions of the ones before it.",
            file=sys.stderr,
        )
        return 2
    if args.json:
        print(
            json.dumps(
                [
                    {
                        "name": q.name,
                        "title": q.title,
                        "stage": q.stage,
                        "required": q.required,
                        "re_asked_each_stage": q.re_asked_each_stage,
                        "ask": q.ask,
                        "scaffold": q.scaffold,
                    }
                    for q in asked
                ],
                indent=2,
            )
        )
        return 0
    if asked:
        print(HOW_A_QUESTION_IS_PUT)
    for q in asked:
        _print_one_question(q, at=args.stage)
    return 0


def _print_one_question(question: Any, *, at: str) -> None:
    """One question, and the brief line that records its answer.

    The line names every key an answered entry needs, so a coding agent that copies it
    writes a brief the library reads back rather than one it refuses.
    """
    mark = "required" if question.required else "optional"
    if question.re_asked_each_stage:
        mark += ", asked again at every stage"
    print(f"[{question.stage}] {question.title}  ({mark})")
    print(f"  key:      {question.name}   <- brief.toml key, not builder-facing")
    print(f"  ask:      {question.ask}")
    print(f"  scaffold: {question.scaffold}")
    dated = f', asked_at = "{at}"' if question.re_asked_each_stage else ""
    print(
        f'  record:   [entries.{question.name}] status = "answered", '
        f'recorded_at = "<now, ISO 8601 with a zone>"{dated}, answer = "..."'
    )
    print()


def _init(args: argparse.Namespace) -> int:
    """Put the procedure where the coding agent working on this project will read it."""
    source = _skill_source()
    if source is None:
        print(
            "The procedure did not install with this package, so there is nothing to "
            "register. Reinstall simple-agents, or read docs/procedure.md in the repository.",
            file=sys.stderr,
        )
        return 2

    root = Path(args.path).expanduser()
    into = Path(args.to) if args.to else (CLAUDE_SKILLS if args.claude else NEUTRAL_SKILLS)
    target = root / into / SKILL_NAME
    # What the note names, which is where this run of `init` put the skill rather than where
    # the default would have put it.
    skill = (into / SKILL_NAME / "SKILL.md").as_posix()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if not args.force:
            print(
                f"{target} already exists, so the procedure was not replaced. Pass --force "
                f"to replace it.",
                file=sys.stderr,
            )
            if not args.no_agents_file:
                _note(root / "AGENTS.md", skill)
            return 1
        _remove(target)

    how = _place(source, target, copy=args.copy)
    print(f"{how} {target}")

    if not args.no_agents_file:
        _note(root / "AGENTS.md", skill)

    print(
        "\nThe procedure is registered. Tell the coding agent what to build, and it reads "
        "the procedure from there."
    )
    return 0


def _note(note: Path, skill: str) -> None:
    """Put the pointer to the procedure in AGENTS.md, or bring an older one up to date.

    A project's own AGENTS.md is appended to rather than overwritten. A note this command
    wrote before is replaced where it names a different path, which is what a project gets
    when `init` is run again with `--claude` or `--to`.
    """
    wanted = agents_note(skill)
    if not note.exists():
        note.write_text(wanted, encoding="utf-8")
        print(f"wrote {note}")
        return

    existing = note.read_text(encoding="utf-8")
    if wanted in existing:
        print(f"{note} already points at {skill}")
        return

    replaced = _replaced_note(existing, wanted)
    if replaced is not None:
        note.write_text(replaced, encoding="utf-8")
        print(f"updated {note} to point at {skill}")
        return

    with note.open("a", encoding="utf-8") as handle:
        handle.write("\n" + wanted)
    print(f"appended to {note}")


def _replaced_note(existing: str, wanted: str) -> str | None:
    """``existing`` with an older copy of the note swapped for ``wanted``, or ``None``.

    ``None`` where the file carries no note of this command's, which is what makes the caller
    append rather than rewrite. The section runs from the heading to the next heading at the
    same level or above, so a project's own text below it is left where it is.
    """
    lines = existing.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == AGENTS_HEADING]
    if not starts:
        return None
    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].lstrip()
        if stripped.startswith("# ") or stripped.startswith("## "):
            end = index
            break
    after = "".join(lines[end:])
    return "".join(lines[:start]) + wanted + ("\n" + after if after else "")


def _skill_source() -> Path | None:
    """Where the procedure is on disk, or ``None`` where the package shipped without it.

    An installed wheel carries the whole skill directory, so that directory is the source. A
    source checkout has the same bytes as ``docs/procedure.md`` and no directory around them,
    so the file is the source and ``_place`` builds the directory.
    """
    package = Path(__file__).resolve().parents[1]
    installed = package / ".agents" / "skills" / SKILL_NAME
    if (installed / "SKILL.md").exists():
        return installed
    repo = package.parents[1] / "docs" / "procedure.md"
    return repo if repo.exists() else None


def _place(source: Path, target: Path, *, copy: bool) -> str:
    """Put the skill at ``target``, by symlink where the platform allows one.

    A symlink means the procedure tracks the installed version rather than going stale. It
    points into the environment simple-agents is installed in, so a committed link resolves
    to nothing in a clone of the project made without that environment. ``--copy`` writes the
    bytes into the project, which is what a clone carries with it.
    """
    if source.is_dir():
        return _link_or(lambda: shutil.copytree(source, target), source, target, copy=copy)
    target.mkdir(parents=True)
    inner = target / "SKILL.md"
    return _link_or(lambda: shutil.copy2(source, inner), source, inner, copy=copy)


def _link_or(fallback, source: Path, at: Path, *, copy: bool) -> str:
    if not copy:
        try:
            at.symlink_to(Path(os.path.relpath(source, at.parent)))
            return "linked"
        except (OSError, ValueError):
            pass
    fallback()
    return "copied"


def _remove(target: Path) -> None:
    if target.is_symlink() or target.is_file():
        target.unlink()
    else:
        shutil.rmtree(target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="simple-agents",
        description="Build an agent whose behaviour can be measured.",
    )
    subcommands = parser.add_subparsers(dest="command")

    init = subcommands.add_parser(
        "init", help="register the procedure where a coding agent will read it"
    )
    init.add_argument("path", nargs="?", default=".", help="the project directory")
    init.add_argument("--claude", action="store_true", help="install into .claude/skills instead")
    init.add_argument("--to", default=None, help="a skills directory, instead of the default")
    init.add_argument("--copy", action="store_true", help="copy rather than symlink")
    init.add_argument("--force", action="store_true", help="replace what is already there")
    init.add_argument(
        "--no-agents-file", action="store_true", help="do not write or extend AGENTS.md"
    )

    asked = subcommands.add_parser(
        "questions", help="the questions to put to the builder at a stage"
    )
    asked.add_argument(
        "--stage",
        default="shape",
        help=f"{', '.join(STAGES[:-1])} or {STAGES[-1]}. Earlier stages are included",
    )
    asked.add_argument(
        "--tier",
        default=None,
        help="prototype, evaluated or trained. Drops the stages that tier does not have",
    )
    asked.add_argument(
        "--decisions",
        action="store_true",
        help="the six kinds of decision to put to the builder rather than making alone",
    )
    asked.add_argument("--json", action="store_true", help="print them as JSON")

    watch = subcommands.add_parser(
        "watch", help="follow an evaluation that is running, from another terminal"
    )
    watch.add_argument("path", help="the evaluation's directory, <run_dir>/eval/<eval_id>")
    watch.add_argument(
        "--expected",
        type=int,
        default=None,
        help="examples times k, which the directory cannot say. Without it there is no total",
    )
    watch.add_argument(
        "--interval", type=float, default=5.0, help="seconds between readings, default 5"
    )
    watch.add_argument("--once", action="store_true", help="read once and return")

    check = subcommands.add_parser(
        "check", help="run the conformance checks over a project directory"
    )
    check.add_argument("path", nargs="?", default=".", help="the project directory")
    check.add_argument("--brief", default=None, help="the brief, instead of ./brief.toml")
    check.add_argument("--run", default=None, help="a run directory, instead of the latest")
    check.add_argument("--results", default=None, help="a results file, instead of the latest")
    check.add_argument("--json", action="store_true", help="print the report as JSON")
    _scoping(check, reads="FT-35 reads, which is agent runs by default")

    report = subcommands.add_parser(
        "report", help="what every node did, over the runs or the evaluation at a path"
    )
    report.add_argument(
        "path",
        nargs="?",
        default="runs",
        help="runs/, one run, an evaluation's directory, or a results file",
    )
    report.add_argument("--json", action="store_true", help="print the report as JSON")
    report.add_argument(
        "--walk",
        action="store_true",
        help="print one run step by step, in the order it happened",
    )
    _scoping(report, reads="is read, which is every role by default")

    view = subcommands.add_parser(
        "view",
        help="one page showing the system, for the builder: what is built, what is "
        "planned, what changed, and where everything flows",
    )
    view.add_argument("path", nargs="?", default=".", help="the project directory")
    view.add_argument(
        "-o", "--out", default=None, help="where to write the page, instead of <project>/view.html"
    )
    view.add_argument(
        "--serve",
        action="store_true",
        help="serve the page live on 127.0.0.1, taking the builder's comments "
        "and answers into comments.toml",
    )
    view.add_argument(
        "--port",
        type=int,
        default=7350,
        help="the port --serve binds (default 7350; 0 picks a free one)",
    )

    comments = subcommands.add_parser(
        "comments", help="the threads the builder left through the view, open first"
    )
    comments.add_argument("path", nargs="?", default=".", help="the project directory")
    comments.add_argument("--all", action="store_true", help="addressed and withdrawn threads too")
    comments.add_argument("--json", action="store_true", help="every thread, as JSON")
    add_record_command(subcommands)
    return parser


def _scoping(command: argparse.ArgumentParser, *, reads: str) -> None:
    """The four filters that narrow which runs are read, on the commands that read many.

    A figure over fewer runs is a figure over fewer runs, so what these left out is named in
    the output rather than left for a reader to know.
    """
    command.add_argument("--role", default=None, help=f"one role, of what {reads}")
    command.add_argument(
        "--live",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="only runs an end user made, or with --no-live only the others",
    )
    command.add_argument(
        "--since", default=None, help="runs that started at or after an ISO timestamp"
    )
    command.add_argument("--last", type=int, default=None, help="the newest N runs of what is left")
    command.add_argument(
        "--pipeline",
        default=None,
        help="one registered pipeline, by the name it is registered under",
    )
    command.add_argument(
        "--scripted",
        action="store_true",
        help="include runs whose model answered from a script, which are left out by default",
    )


def _entry_point() -> None:
    """What the console script calls."""
    raise SystemExit(main())


if __name__ == "__main__":  # `python -m simple_agents.cli` runs the same command
    _entry_point()
