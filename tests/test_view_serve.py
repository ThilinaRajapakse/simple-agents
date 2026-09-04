"""The served view, driven over real HTTP against a copy of the mid-build fixture."""

from __future__ import annotations

import json
import shutil
import threading
import urllib.request
from pathlib import Path

import pytest

from simple_agents.records.comments import append_comment, read_comments
from simple_agents.view.serve import build_server, project_state

FIXTURE = Path(__file__).parent / "fixtures" / "view_projects" / "mid-build"


@pytest.fixture()
def served(tmp_path):
    root = tmp_path / "project"
    shutil.copytree(FIXTURE, root)
    server = build_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield root, f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def call(base: str, path: str, payload: dict | None = None):
    if payload is None:
        request = urllib.request.Request(base + path)
    else:
        request = urllib.request.Request(
            base + path,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


class TestServing:
    def test_the_page_is_live(self, served) -> None:
        _root, base = served
        status, body = call(base, "/")
        assert status == 200
        assert b'"live": true' in body

    def test_commenting_is_visible_before_the_selected_step_details(self, served) -> None:
        _root, base = served
        status, body = call(base, "/")
        assert status == 200
        assert b"Comment on this project" in body
        assert body.index(b'id="composerwrap"') < body.index(b'id="stepcard"')

    def test_a_comment_lands_with_its_snapshot(self, served) -> None:
        root, base = served
        status, body = call(
            base,
            "/api/comment",
            {
                "at": "next_pick/judge_books",
                "said": "Only unread books, ever.",
            },
        )
        assert status == 200
        held = read_comments(root / "comments.toml")
        mine = held.thread(json.loads(body)["id"])
        assert mine.said == "Only unread books, ever."
        assert mine.about == "judge_books, a model call in next_pick"
        assert mine.stage == "build"
        assert mine.shape and mine.shape.startswith("sha256:")
        assert mine.when

    def test_an_answer_records_the_question_it_answers(self, served) -> None:
        root, base = served
        status, body = call(
            base,
            "/api/comment",
            {
                "at": "question:what_it_does",
                "said": "It picks my next book.",
                "kind": "answer",
            },
        )
        assert status == 200
        mine = read_comments(root / "comments.toml").thread(json.loads(body)["id"])
        assert mine.kind == "answer"
        assert "what does the agent do" in (mine.about or "")

    def test_a_reply_joins_the_thread(self, served) -> None:
        root, base = served
        status, body = call(base, "/api/comment", {"at": "next_pick", "said": "A thread."})
        assert status == 200
        mine = json.loads(body)["id"]
        status, _body = call(base, "/api/reply", {"id": mine, "said": "Still true today."})
        assert status == 200
        thread = read_comments(root / "comments.toml").thread(mine)
        assert [(r.by, r.said) for r in thread.replies] == [("builder", "Still true today.")]

    def test_withdrawing_needs_a_builder_thread(self, served) -> None:
        root, base = served
        status, _body = call(base, "/api/withdraw", {"id": "c1"})
        assert status == 200
        assert read_comments(root / "comments.toml").thread("c1").status == "withdrawn"
        status, body = call(base, "/api/withdraw", {"id": "missing"})
        assert status == 400 and b"missing" in body

    def test_a_withdrawn_thread_comes_back(self, served) -> None:
        """Taking a comment back is not deleting it: the builder can put it back."""
        root, base = served
        call(base, "/api/withdraw", {"id": "c1"})
        status, body = call(base, "/api/reopen", {"id": "c1"})
        assert status == 200 and json.loads(body)["status"] == "open"
        assert read_comments(root / "comments.toml").thread("c1").status == "open"

    def test_only_the_writer_puts_a_thread_back(self, served) -> None:
        root, base = served
        append_comment(root / "comments.toml", at="next_pick", said="Theirs.", by="coding_agent")
        held = read_comments(root / "comments.toml").all[-1]
        status, body = call(base, "/api/reopen", {"id": held.id})
        assert status == 400 and b"writer" in body

    def test_an_empty_comment_is_refused(self, served) -> None:
        _root, base = served
        status, body = call(base, "/api/comment", {"at": "next_pick", "said": "  "})
        assert status == 400
        assert b"said" in body

    def test_the_state_token_moves_when_the_project_does(self, served) -> None:
        root, base = served
        _status, before = call(base, "/version")
        (root / "agent.py").write_text((root / "agent.py").read_text() + "\n# moved\n")
        _status, after = call(base, "/version")
        assert json.loads(before)["state"] != json.loads(after)["state"]

    def test_a_second_request_reuses_the_reading(self, served, monkeypatch) -> None:
        """A page held open polls, and assembling a project is hundreds of milliseconds."""
        from simple_agents.view import serve as module

        root, base = served
        counted = []
        real = module.assemble
        monkeypatch.setattr(module, "assemble", lambda where: counted.append(where) or real(where))

        call(base, "/data")
        call(base, "/data")
        call(base, "/")
        assert len(counted) == 1

        (root / "agent.py").write_text((root / "agent.py").read_text() + "\n# moved\n")
        call(base, "/data")
        assert len(counted) == 2

    def test_the_reading_the_caller_gets_is_its_own(self, served) -> None:
        """A caller writing into what it was handed leaves the kept reading alone."""
        _root, base = served
        _status, first = call(base, "/data")
        held = json.loads(first)
        held["project"] = "written over"
        _status, second = call(base, "/data")
        assert json.loads(second)["project"] != "written over"

    def test_state_moves_when_a_run_beside_the_newest_grows(self, tmp_path) -> None:
        """Two runs can be in flight together, and the page reads the trajectory of each.

        The token stamped only the newest run's trajectory, so a second run's growth left it
        still and the served page sat through it.
        """
        root = tmp_path / "p"
        shutil.copytree(
            FIXTURE.parent / "shipped", root, ignore=shutil.ignore_patterns("__pycache__")
        )
        beside = sorted((root / "runs").glob("*/*/*/trajectory.jsonl"))[0]
        one = project_state(root)
        beside.write_text(beside.read_text() + '{"kind": "note"}\n', encoding="utf-8")
        assert project_state(root) != one

    def test_state_reads_without_a_server_too(self, tmp_path) -> None:
        root = tmp_path / "p"
        shutil.copytree(FIXTURE, root)
        one = project_state(root)
        (root / "comments.toml").write_text("")
        assert project_state(root) != one

    def test_state_moves_when_a_run_lands_in_the_role_layout(self, tmp_path) -> None:
        """Runs are filed `runs/<role>/<date>/<run>/`, and a run landing there is a change.

        The token read `runs/` one level deep, so on the role layout a new run never moved
        it and the served page sat still through a run happening beside it."""
        root = tmp_path / "p"
        shutil.copytree(FIXTURE, root)
        one = project_state(root)
        made = root / "runs" / "live" / "2026-08-29" / "run_20260829T000000Z_aaaaaaaa"
        made.mkdir(parents=True)
        (made / "manifest.json").write_text("{}", encoding="utf-8")
        two = project_state(root)
        assert two != one
        (made / "trajectory.jsonl").write_text('{"kind": "run_start"}\n', encoding="utf-8")
        assert project_state(root) != two

    def test_state_moves_when_a_results_file_lands(self, tmp_path) -> None:
        """The measure page reads `evals/`, so a results file landing is a change too."""
        root = tmp_path / "p"
        shutil.copytree(FIXTURE, root)
        one = project_state(root)
        results = root / "evals" / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "held-out.json").write_text("{}", encoding="utf-8")
        assert project_state(root) != one


@pytest.fixture()
def served_with_runs(tmp_path):
    """The branching fixture served, for the endpoints that read a run's own records."""
    root = tmp_path / "project"
    shutil.copytree(
        FIXTURE.parent / "branching", root, ignore=shutil.ignore_patterns("__pycache__")
    )
    server = build_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    yield root, f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


class TestReadingEveryRunForThePrompts:
    """`/prompts/every-run`: the button beside a step no recent run reached.

    The page reads back through the newest runs of each pipeline, which leaves a step down a
    branch nothing recent took without a filled prompt. This reads the lot instead.
    """

    def test_it_returns_the_page_read_over_every_run(self, served_with_runs) -> None:
        _root, base = served_with_runs
        status, body = call(base, "/prompts/every-run")
        assert status == 200
        held = json.loads(body)
        assert held["counts"]["prompts"] == 5
        assert held["counts"]["unfilled"] == 0
        assert [one["name"] for one in held["pipelines"]] == ["triage"]
        assert all(step["filled"] for one in held["pipelines"] for step in one["steps"])

    def test_it_finds_a_step_the_bounded_read_would_not(self, served_with_runs) -> None:
        """`most_runs=0` is the bounded read at its limit, and this is what it misses."""
        from simple_agents.view.assemble import assemble
        from simple_agents.view.prompts import read_prompts

        root, base = served_with_runs
        data = assemble(root)
        declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
        bounded = read_prompts(root, declared, None, most_runs=0)
        assert bounded["counts"]["unfilled"] == 5

        status, body = call(base, "/prompts/every-run")
        assert status == 200 and json.loads(body)["counts"]["unfilled"] == 0


class TestTheFullRecord:
    """`/record/<run>/<sequence>`: the full record behind a clipped value on the page."""

    def test_a_record_is_served_raw_by_run_and_sequence(self, served_with_runs) -> None:
        import urllib.parse

        root, base = served_with_runs
        run = next((root / "runs" / "dev").glob("*/run_*"))
        rel = urllib.parse.quote(str(run.relative_to(root / "runs")), safe="")
        status, body = call(base, f"/record/{rel}/1")
        assert status == 200
        record = json.loads(body)
        assert record["sequence"] == 1
        assert record["record_type"] == "run_start"

    def test_a_sequence_nothing_recorded_is_refused(self, served_with_runs) -> None:
        import urllib.parse

        root, base = served_with_runs
        run = next((root / "runs" / "dev").glob("*/run_*"))
        rel = urllib.parse.quote(str(run.relative_to(root / "runs")), safe="")
        status, _ = call(base, f"/record/{rel}/99999")
        assert status == 404

    def test_a_path_that_leaves_runs_is_refused(self, served_with_runs) -> None:
        _root, base = served_with_runs
        status, _ = call(base, "/record/..%2F..%2Fbrief.toml/1")
        assert status == 404

    def test_a_bare_run_name_is_found_wherever_the_run_is_filed(self, served_with_runs) -> None:
        """A page names a run by its directory name; runs are filed by role and date.

        `/run/<bare name>` resolved `runs/<name>` literally, so the served open-another-run
        control returned 404 for every run once runs were filed under `runs/dev/<date>/`.
        """
        root, base = served_with_runs
        run = next((root / "runs" / "dev").glob("*/run_*"))
        status, body = call(base, f"/run/{run.name}")
        assert status == 200
        assert json.loads(body)["run"] == run.name
        status, body = call(base, f"/record/{run.name}/1")
        assert status == 200
        assert json.loads(body)["sequence"] == 1

    def test_a_rollouts_record_is_reachable_by_its_bare_name(self, served_with_runs) -> None:
        root, base = served_with_runs
        rollout = next((root / "runs" / "eval").glob("eval_*/t-*"))
        status, body = call(base, f"/run/{rollout.name}")
        assert status == 200
        assert json.loads(body)["run"] == rollout.name


class TestComparingTwoResultsFilesOnRequest:
    """`/compare?before=&after=`: the library's own verdict on two results files on record."""

    def test_two_files_are_compared_the_way_the_library_compares_them(
        self, served_with_runs
    ) -> None:
        _root, base = served_with_runs
        status, body = call(base, "/compare?before=held-out.json&after=held-out-no-revision.json")
        assert status == 200
        held = json.loads(body)
        assert held["before"] == "held-out.json"
        assert "metrics" in held["comparison"]
        assert "accuracy" in held["comparison"]["metrics"]

    def test_a_pair_the_library_refuses_is_refused_with_its_reason(self, served_with_runs) -> None:
        """A file the reader refuses (a format below the floor) is the library's refusal,
        said in its words, and not a page error."""
        root, base = served_with_runs
        stale = json.loads((root / "evals" / "results" / "held-out.json").read_text())
        stale["eval_format_version"] = "0.10"
        (root / "evals" / "results" / "stale.json").write_text(json.dumps(stale))
        status, body = call(base, "/compare?before=held-out.json&after=stale.json")
        assert status == 200
        held = json.loads(body)
        assert held.get("problem"), held

    def test_a_file_that_is_not_there_is_refused(self, served_with_runs) -> None:
        _root, base = served_with_runs
        status, _ = call(base, "/compare?before=held-out.json&after=..%2F..%2Fbrief.toml")
        assert status == 404
