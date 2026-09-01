"""Render one project's page as it stood at each stage, to read what a builder reads.

The six fixtures under ``tests/fixtures/view_projects/`` are one project per *shape*, and the
only complex one is at ``measure``. What a builder sees at ``build``, on a pipeline with a
route, a loop, a fan-out, a failure path and a nested pipeline, was not viewable anywhere.

Every stage below is what the project's own directory holds with something taken away, so no
copy of the graph is maintained and nothing here can drift from `agent.py`:

===============  ============================================================
``shape``        the code, no runs, no evaluation, brief at ``shape``
``build``        the code and its runs, no evaluation, brief at ``build``
``measure``      everything the project has
===============  ============================================================

**A `shape` stage this produces is a built pipeline nobody has run.** A real project at that
gate has most of its steps standing in as `NotBuilt`, which is a different picture and a
different `agent.py`. What this shows is the run overlay and the evaluation removed, which is
what the drawing does with nothing to overlay.

Run it, then open each page::

    uv run python scripts/view_at_stage.py tests/fixtures/view_projects/branching
    uv run python scripts/view_at_stage.py <project> --out /tmp/stages --serve build
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

STAGES: dict[str, dict[str, bool]] = {
    "shape": {"runs": False, "evaluation": False},
    "build": {"runs": True, "evaluation": False},
    "measure": {"runs": True, "evaluation": True},
}
"""What each stage keeps of the project's own directory."""


def _brief_at(text: str, stage: str) -> str:
    """The brief with its stage moved, and the results file dropped where one is named."""
    lines = []
    for line in text.splitlines():
        head = line.split("=", 1)[0].strip()
        if head == "stage":
            lines.append(f'stage = "{stage}"')
            continue
        if head == "results" and stage != "measure":
            continue
        lines.append(line)
    if not any(ln.split("=", 1)[0].strip() == "stage" for ln in lines):
        lines.insert(0, f'stage = "{stage}"')
    return "\n".join(lines) + "\n"


def _copy_without(source: Path, target: Path, keep: dict[str, bool]) -> None:
    """The project, with the runs or the evaluation left behind."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "view.html", "*.pyc"),
    )
    if not keep["runs"]:
        shutil.rmtree(target / "runs", ignore_errors=True)
    if not keep["evaluation"]:
        shutil.rmtree(target / "evals" / "results", ignore_errors=True)
        # An evaluation's rollouts live under `runs/`, and they are its record rather than
        # the project's. A stage without an evaluation has neither. They are filed under
        # `runs/eval/` today and at `runs/eval_*` on the older flat layout, and a project
        # on either layout is legitimate input.
        shutil.rmtree(target / "runs" / "eval", ignore_errors=True)
        for held in (target / "runs").glob("eval_*"):
            shutil.rmtree(held, ignore_errors=True)


def build(source: Path, out: Path, stages: list[str]) -> list[tuple[str, Path, Path]]:
    """One copy of the project per stage, each with its page rendered beside it."""
    from simple_agents.view import generate_view

    out.mkdir(parents=True, exist_ok=True)
    made = []
    for stage in stages:
        target = out / f"{source.name}-{stage}"
        _copy_without(source, target, STAGES[stage])
        brief = target / "brief.toml"
        if brief.exists():
            brief.write_text(_brief_at(brief.read_text(encoding="utf-8"), stage), encoding="utf-8")
        page = generate_view(target, out=out / f"{source.name}-{stage}.html")
        made.append((stage, target, page))
    return made


def _said(stage: str, project: Path, page: Path) -> str:
    """One line per stage: what the page says about itself, so the list is readable."""
    from simple_agents.view import assemble

    data = assemble(project)
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    steps = sum(len(p["nodes"]) for p in declared)
    runs = sum((p.get("over_runs") or {}).get("runs", 0) for p in declared)
    measured = bool(data["measured"] and data["measured"].get("path"))
    return (
        f"{stage:<8} {steps:>3} steps · {runs:>4} run(s) · "
        f"{'measured' if measured else 'not measured':<12} · {page}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("project", help="the project directory to render")
    parser.add_argument("--out", default=None, help="where the copies and pages go")
    parser.add_argument(
        "--stage",
        action="append",
        choices=sorted(STAGES),
        default=None,
        help="render one stage rather than all three; repeatable",
    )
    parser.add_argument(
        "--serve",
        choices=sorted(STAGES),
        default=None,
        help="serve one stage after rendering, so the page is the live tool",
    )
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args(argv)

    source = Path(args.project).expanduser().resolve()
    if not (source / "agent.py").exists():
        print(f"{source} holds no agent.py, so there is no pipeline to draw.", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser() if args.out else source.parent / "_stages"
    stages = args.stage or ["shape", "build", "measure"]

    made = build(source, out, stages)
    print(f"{source.name}, one page per stage, under {out}:\n")
    for stage, project, page in made:
        print("  " + _said(stage, project, page))
    print("\nOpen each in a browser. The same pipeline, with less to overlay each time.")

    if args.serve:
        target = out / f"{source.name}-{args.serve}"
        print(f"\nServing {args.serve} from {target} on 127.0.0.1:{args.port} (ctrl-c to stop).")
        return subprocess.call(
            [
                sys.executable,
                "-m",
                "simple_agents.cli",
                "view",
                str(target),
                "--serve",
                "--port",
                str(args.port),
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
