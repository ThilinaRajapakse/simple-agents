"""The served view: the same page, able to hear the builder back.

``simple-agents view --serve`` runs a local server on 127.0.0.1. The page it serves is the
one `generate_view` writes, plus the return path: every element takes a comment, an open
question takes an answer, an answered one takes an amendment, and each lands in
``comments.toml`` through :mod:`simple_agents.records.comments` with a snapshot of what the writer
was looking at. The page re-reads the project as it changes, so the builder keeps it open
while the coding agent works.

Nothing here writes the brief: an answer or an amendment is a thread the coding agent reads
and records, asking whatever follow-up the question's scaffold needs.
"""

from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ..records.comments import (
    DEFAULT_COMMENTS,
    append_comment,
    append_reply,
    read_comments,
    set_status,
)
from ..errors import ConfigurationError
from .assemble import assemble
from .render import render

__all__ = ["serve_view", "build_server", "project_state"]

# What a change to any of these means the page is stale: the code, the records the page
# reads, and the run directory's listing. Contents are not hashed; a save that changes
# nothing re-renders once, which costs less than hashing a large project on every poll.
_WATCHED_FILES = ("brief.toml", "comments.toml", "design.md", "idea.md", "research.md")


def _stamp(target: Path) -> str:
    stat = target.stat()
    return f"{target.name}:{stat.st_mtime_ns}:{stat.st_size}"


def _runs_pieces(runs: Path) -> list[str]:
    """The run record's part of the token.

    Runs are filed by role and day (`runs/live/<date>/<run>/`), rollouts one deeper
    (`runs/eval/<eval_id>/<rollout>/`), and a project from before the layout keeps
    `runs/<run>/`. The manifests at those depths are the runs the page reads.
    """
    manifests = [
        found
        for pattern in ("*/manifest.json", "*/*/manifest.json", "*/*/*/manifest.json")
        for found in runs.glob(pattern)
    ]
    pieces = [f"runs:{len(manifests)}"]
    if manifests:
        # The newest run's trajectory grows while a run moves, and the page follows it.
        newest = max(manifests, key=lambda held: held.stat().st_mtime_ns)
        moving = newest.parent / "trajectory.jsonl"
        if moving.exists():
            pieces.append("moving:" + _stamp(moving))
    pieces.extend(_stamp(found) for found in runs.glob("eval/*/progress.json"))
    return pieces


def _evals_pieces(evals: Path) -> list[str]:
    """The example set, the results files and the comparisons: page changes too."""
    return [
        _stamp(target)
        for pattern in ("*.jsonl", "results/*.json", "variants/*.json")
        for target in sorted(evals.glob(pattern))
    ]


def project_state(root: Path) -> str:
    """A token that moves when anything the page reads moves."""
    pieces: list[str] = []
    pieces.extend(_stamp(name) for name in sorted(root.glob("*.py")))
    pieces.extend(_stamp(root / name) for name in _WATCHED_FILES if (root / name).exists())
    if (root / "runs").exists():
        pieces.extend(_runs_pieces(root / "runs"))
    if (root / "evals").exists():
        pieces.extend(_evals_pieces(root / "evals"))
    return str(abs(hash("|".join(pieces))))


def _snapshot(data: dict[str, Any], address: str) -> dict[str, str | None]:
    """What an address resolves to right now, in words, for the thread's record."""
    about: str | None = None
    shape: str | None = None
    if address == "project":
        about = f"the whole project, {data.get('standing', '')}"[:200]
    elif address.startswith("question:"):
        name = address.removeprefix("question:")
        held = next((q for q in data.get("questions_due", []) if q["name"] == name), None)
        entry = next(
            (e for e in data.get("brief", {}).get("entries", []) if e["name"] == name), None
        )
        about = (held or {}).get("asks") or (entry or {}).get("answer", "")[:120] or name
    elif address.startswith("decision:"):
        name = address.removeprefix("decision:")
        held = next(
            (d for d in data.get("brief", {}).get("decisions", []) if d["name"] == name), None
        )
        about = f"the {name} decision" + (f": {held['chose'][:120]}" if held else "")
    elif address.startswith("resource:"):
        about = f"the {address.removeprefix('resource:')} resource"
    else:
        pipe_name = address.split("/")[0]
        pipeline = next((p for p in data.get("pipelines", []) if p.get("name") == pipe_name), None)
        if pipeline:
            shape = pipeline.get("fingerprint")
            if "/" in address:
                step_id = address.split("/", 1)[1]
                if "->" in step_id:
                    about = f"the edge {step_id} in {pipe_name}"
                else:
                    node = next((n for n in pipeline["nodes"] if n["id"] == step_id), None)
                    about = (
                        f"{step_id}, a {node['kind_word']} in {pipe_name}"
                        if node
                        else f"{step_id} in {pipe_name}"
                    )
            else:
                about = f"the {pipe_name} pipeline, {len(pipeline.get('nodes', []))} steps"
    return {"about": about, "stage": data.get("stage"), "shape": shape}


class _Handler(BaseHTTPRequestHandler):
    server_version = "simple-agents-view"
    root: Path  # set by serve_view on the class it builds
    lock: threading.Lock

    # -- plumbing --------------------------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature
        pass

    def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The page closed the socket first, which a reload does mid-response. Nothing
            # is lost: the next request asks again.
            pass

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _refuse(self, why: str) -> None:
        self._json({"error": why}, HTTPStatus.BAD_REQUEST)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            held = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return held if isinstance(held, dict) else {}

    def _fresh(self) -> dict[str, Any]:
        data = assemble(self.root)
        data["live"] = True
        return data

    # -- routes ----------------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - stdlib name
        if self.path in ("/", "/index.html"):
            page = render(self._fresh())
            self._send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if self.path == "/data":
            self._json(self._fresh())
            return
        if self.path == "/version":
            self._json({"state": project_state(self.root)})
            return
        if self.path.startswith("/record/"):
            self._one_record(self.path[len("/record/") :])
            return
        if self.path.startswith("/compare?"):
            self._compare(self.path[len("/compare?") :])
            return
        if self.path.startswith("/run/"):
            self._one_run(self.path.removeprefix("/run/"))
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    def _one_run(self, name: str) -> None:
        """One run walked, read when it is asked for.

        The static page carries the newest run of each shape and the rollouts that came out
        wrong. Every other run is on disk and reachable here, so the whole record can be
        opened without any of it being written into the file.
        """

        from .walk import walk_run

        target = self._a_run_called(name)
        held = walk_run(target) if target is not None else None
        if held is None:
            self._send(HTTPStatus.NOT_FOUND, b"no such run", "text/plain")
            return
        self._json(held)

    def _a_run_called(self, name: str) -> Path | None:
        return run_called(self.root, name)

    def _compare(self, query: str) -> None:
        """Two results files compared on request, the way the library compares them."""
        held, status = comparison_of(self.root, query)
        self._json(held, status)

    def _one_record(self, rest: str) -> None:
        """One trajectory record, raw, read when the page asks for it."""
        line = record_line(self.root, rest)
        if line is None:
            self._send(HTTPStatus.NOT_FOUND, b"no such record", "text/plain")
            return
        self._send(HTTPStatus.OK, line.encode("utf-8"), "application/json")

    def _start_a_thread(self, target: Path, body: dict[str, Any]) -> None:
        at = str(body.get("at") or "").strip()
        said = str(body.get("said") or "").strip()
        if not at or not said:
            self._refuse("a comment needs `at` and `said`")
            return
        held = _snapshot(self._fresh(), at)
        thread = append_comment(
            target,
            at=at,
            said=said,
            kind=str(body.get("kind") or "comment"),
            by="builder",
            **held,
        )
        print(f"view: {thread.kind} {thread.id} on {thread.at}: {thread.said[:80]!r}", flush=True)
        self._json({"id": thread.id})

    def _add_a_reply(self, target: Path, body: dict[str, Any]) -> None:
        thread = append_reply(
            target,
            str(body.get("id") or ""),
            by="builder",
            said=str(body.get("said") or ""),
        )
        print(
            f"view: reply on {thread.id} ({thread.at}): {thread.replies[-1].said[:80]!r}",
            flush=True,
        )
        self._json({"id": thread.id})

    def _move_a_thread(self, target: Path, body: dict[str, Any], *, taking_back: bool) -> None:
        wanted = str(body.get("id") or "")
        held = read_comments(target).thread(wanted)
        if held is None:
            self._refuse(f"no thread {wanted!r}")
            return
        if held.by != "builder":
            self._refuse(
                "only the writer withdraws a thread"
                if taking_back
                else "only the writer puts a thread back"
            )
            return
        thread = set_status(target, wanted, "withdrawn" if taking_back else "open")
        print(
            f"view: {'withdrew' if taking_back else 'reopened'} {thread.id} ({thread.at})",
            flush=True,
        )
        self._json({"id": thread.id, "status": thread.status})

    def do_POST(self) -> None:  # noqa: N802 - stdlib name
        body = self._body()
        target = self.root / DEFAULT_COMMENTS
        try:
            with self.lock:
                if self.path == "/api/comment":
                    self._start_a_thread(target, body)
                    return
                if self.path == "/api/reply":
                    self._add_a_reply(target, body)
                    return
                if self.path in ("/api/withdraw", "/api/reopen"):
                    self._move_a_thread(target, body, taking_back=self.path == "/api/withdraw")
                    return
        except ConfigurationError as error:
            self._refuse(str(error))
            return
        self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")


def run_called(root: Path, name: str) -> Path | None:
    """The run directory a page named, or ``None``.

    A page names a run by its directory name alone, and runs are filed by what they are
    (`runs/dev/<date>/`, `runs/eval/<id>/`), so a bare name is searched for wherever it
    sits. A relative path is taken as given. Either way the result is refused if it leaves
    `runs/`: the name arrives over a socket.
    """
    from urllib.parse import unquote

    from ..envelope import manifest_paths

    wanted = unquote(name).strip("/")
    runs = (root / "runs").resolve()
    try:
        target = (runs / wanted).resolve()
        target.relative_to(runs)
    except (OSError, ValueError):
        return None
    if target.is_dir():
        return target
    if "/" not in wanted:
        for manifest in manifest_paths(runs, rollouts=None):
            if manifest.parent.name == wanted:
                return manifest.parent
    return None


def record_line(root: Path, rest: str) -> str | None:
    """One trajectory record, raw, or ``None``: the full value behind a clipped one.

    ``rest`` is ``<run>/<sequence>``. The line is found by scanning and served without being
    parsed: one record can be megabytes, and a trajectory is streamed or not read at all.
    """
    from urllib.parse import unquote

    wanted = unquote(rest).strip("/")
    run, _, sequence = wanted.rpartition("/")
    if not run or not sequence.isdigit():
        return None
    target = run_called(root, run)
    trajectory = target / "trajectory.jsonl" if target is not None else None
    if trajectory is None or not trajectory.exists():
        return None
    marks = (f'"sequence": {int(sequence)},', f'"sequence":{int(sequence)},')
    with trajectory.open("r", encoding="utf-8") as lines:
        for line in lines:
            if any(mark in line for mark in marks):
                return line
    return None


def comparison_of(root: Path, query: str) -> tuple[dict[str, Any], HTTPStatus]:
    """Two results files compared on request, the way the library compares them.

    ``before=<file>&after=<file>`` names two files under ``evals/results/``; the answer is
    the record ``compare()`` writes, or a refusal saying why the two cannot be compared (a
    different example set, a file outside the version window). Computed here rather than in
    the page, so the verdict is the library's.
    """
    from urllib.parse import parse_qs, unquote

    from ..evaluation.compare import compare
    from ..evaluation.results import EvalResults

    held = parse_qs(query)
    before = unquote((held.get("before") or [""])[0]).strip("/")
    after = unquote((held.get("after") or [""])[0]).strip("/")
    results = (root / "evals" / "results").resolve()
    paths = []
    for name in (before, after):
        try:
            target = (results / name).resolve()
            target.relative_to(results)
        except (OSError, ValueError):
            target = None
        if target is None or not target.is_file():
            return (
                {"problem": f"no results file called {name!r} under evals/results/"},
                HTTPStatus.NOT_FOUND,
            )
        paths.append(target)
    try:
        comparison = compare(EvalResults.read(paths[0]), EvalResults.read(paths[1]))
    except Exception as exc:  # noqa: BLE001 - the refusal is the answer, in the library's words
        return {"problem": str(exc), "before": before, "after": after}, HTTPStatus.OK
    from .evaluation import _comparison_for_the_page

    return (
        {
            "before": before,
            "after": after,
            "comparison": _comparison_for_the_page(comparison.to_record()),
        },
        HTTPStatus.OK,
    )


def build_server(root: str | Path = ".", *, port: int = 7350) -> ThreadingHTTPServer:
    """The server `serve_view` runs, unstarted, for a caller that manages its own loop.

    ::

        server = build_server(".", port=0)      # port 0 picks a free one
        server.server_address[1]                # where it landed
    """
    where = Path(root).expanduser()
    handler = type(
        "_BoundHandler",
        (_Handler,),
        {
            "root": where,
            "lock": threading.Lock(),
        },
    )
    return ThreadingHTTPServer(("127.0.0.1", port), handler)


def serve_view(root: str | Path = ".", *, port: int = 7350) -> None:
    """Serve the live view for one project until interrupted.

    ::

        serve_view(".", port=7350)

    Binds 127.0.0.1 only: the page writes into the project, and the project is the
    builder's. Prints the address, then one line per thing the builder sends.
    """
    where = Path(root).expanduser()
    server = build_server(where, port=port)
    bound = server.server_address[1]
    print(
        f"view: serving {where.name} at http://127.0.0.1:{bound}/. Open it with the "
        f"builder; comments, answers and replies land in {DEFAULT_COMMENTS}, and "
        f"`simple-agents comments` reads them.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
