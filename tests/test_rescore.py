"""Scoring rollouts that already ran, and failing early when the scoring is wrong.

Both halves come from one failure, found in a dogfood run on 2026-08-10: a project metric that
raised `IndexError` on a malformed answer ended an evaluation after every rollout had been paid
for, and there was no way to produce a results file from the rollouts on disk. The run had no
cassette, so the only path back was the GPU time again.

`TestFailingEarly` is the first half: a scoring function is called as each rollout lands, so it
fails while there are still rollouts left to not pay for. `TestRescore` is the second: the
rollouts that did run become a results file with nothing executed.
"""

from __future__ import annotations

import json
import shutil
from collections import Counter
from pathlib import Path

import pytest
from pydantic import BaseModel

from simple_agents import (
    Prompt,
    Budget,
    Cassette,
    ConfigurationError,
    Deterministic,
    FakeModelClient,
    LLMNode,
    Pipeline,
    PriceBasis,
    RunEnvelope,
    SimpleAgentsWarning,
    Unknown,
)
from simple_agents.evaluation import evaluation_dir
from simple_agents.evaluation import (
    EvalResults,
    EvalSuite,
    Example,
    ExampleSet,
    Outcome,
    Over,
    ProjectMetric,
)
from simple_agents.evaluation.progress import RolloutProgress, progress_of
from simple_agents.evaluation.runner import output_of, terminal_node_id
from simple_agents.models import fake_response

from conftest import run_path

from schemas import Answer

N, K = 6, 3
BUDGET = Budget(max_steps=4, max_tokens=None, max_cost=None, max_wall_clock_ms=None)
EXACT = lambda s: s.answer == s.expected


def examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(id=f"q{i}", inputs={"question": f"q{i}?"}, expected="ok", split="held_out")
            for i in range(N)
        ]
    )


def prompt(inputs, ctx) -> str:
    return Prompt.user("Answer: {question}", question=inputs["question"])


def client(reached: list[str] | None = None) -> FakeModelClient:
    class Counting(FakeModelClient):
        def complete(self, request):
            if reached is not None:
                reached.append("call")
            return super().complete(request)

    return Counting(responses=[fake_response(content='{"answer": "ok", "source": null}')] * 400)


def pipeline(extra: bool = False) -> Pipeline:
    nodes = [LLMNode(prompt, output_schema=Answer, node_id="extract")]
    if extra:
        nodes.insert(0, Deterministic(lambda inputs, ctx: inputs, node_id="passthrough"))
    return Pipeline(nodes, budget=BUDGET)


def raising(s) -> float:
    """The metric as a project first writes it: assumes the answer always splits."""
    return float(len(s.answer.split(",")[1]))


def safe(s) -> float:
    parts = s.answer.split(",")
    return float(len(parts[1])) if len(parts) > 1 else 0.0


def metric(score) -> ProjectMetric:
    return ProjectMetric(
        name="segment_len",
        definition="length of the second comma-separated segment",
        score=score,
        over=Over.ASSERTED,
    )


def suite(score=safe, *, extra: bool = False, metrics: bool = True) -> EvalSuite:
    return EvalSuite(
        pipeline(extra),
        examples(),
        answer="answer",
        matches=EXACT,
        metrics=[metric(score)] if metrics else [],
    )


def ran(root: Path) -> int:
    return len(list(root.rglob("manifest.json")))


class TestFailingEarly:
    def test_a_raising_metric_stops_before_every_rollout_is_paid_for(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            suite(raising).run(
                envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
                model=client(),
                split="held_out",
                k=K,
                seed=41,
                concurrency=2,
            )

        assert "segment_len" in str(raised.value)
        paid = ran(tmp_path)
        assert 0 < paid < N * K, f"stopped after {paid} of {N * K} rollouts"

    def test_it_stops_early_when_rollouts_run_one_at_a_time_too(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError):
            suite(raising).run(
                envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
                model=client(),
                split="held_out",
                k=K,
                seed=41,
                concurrency=1,
            )

        assert ran(tmp_path) == 1

    def test_a_working_metric_still_scores_every_rollout(self, tmp_path) -> None:
        results = suite(safe).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=client(),
            split="held_out",
            k=K,
            seed=41,
        )

        assert len(results.rollouts) == N * K
        assert all("segment_len" in r.scores for r in results.rollouts)


class TestRecordingByDefault:
    """An evaluation keeps its rollouts, so scoring them again costs nothing.

    The rollouts are what the money and the wall clock buy, and scoring is where the mistakes
    are. Before this, an evaluation run with no cassette left nothing to score a second time.
    """

    def test_an_evaluation_records_into_its_own_directory(self, tmp_path) -> None:
        results = suite().run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
        )

        cassette = evaluation_dir(tmp_path, results.eval_id) / "cassette.jsonl"
        assert cassette.exists()
        assert results.config["cassette"]["mode"] == "record"

    def test_the_recording_replays_the_evaluation_it_was_made_from(self, tmp_path) -> None:
        first = suite().run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=client(),
            split="held_out",
            k=K,
            seed=41,
        )
        cassette = evaluation_dir(tmp_path, first.eval_id) / "cassette.jsonl"
        reached: list[str] = []

        replayed = suite().run(
            envelope=RunEnvelope(
                run_dir=str(tmp_path / "again"), cassette=Cassette.replay(cassette)
            ),
            model=client(reached),
            split="held_out",
            k=K,
            seed=41,
        )

        assert reached == [], "a replayed evaluation must not reach the backend"
        assert replayed.metrics["accuracy"].value == first.metrics["accuracy"].value

    def test_an_envelope_naming_a_cassette_is_left_alone(self, tmp_path) -> None:
        chosen = tmp_path / "mine.jsonl"

        suite().run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.record(str(chosen))),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
        )

        assert chosen.exists()

    def test_record_false_writes_no_cassette(self, tmp_path) -> None:
        """The one reason to turn it off is responses that must not reach disk."""
        results = suite().run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
            record=False,
        )

        assert not (evaluation_dir(tmp_path, results.eval_id) / "cassette.jsonl").exists()
        assert results.config["cassette"]["mode"] == "off"

    def test_a_replaying_envelope_still_replays(self, tmp_path) -> None:
        first = suite().run(
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
        )
        cassette = evaluation_dir(tmp_path, first.eval_id) / "cassette.jsonl"

        replayed = suite().run(
            envelope=RunEnvelope(
                run_dir=str(tmp_path / "again"), cassette=Cassette.replay(cassette)
            ),
            model=client(),
            split="held_out",
            k=1,
            seed=41,
        )

        assert replayed.config["cassette"]["mode"] == "replay"


class TestRecoveringTheAnswer:
    def test_the_terminal_node_is_the_one_a_trajectory_records(self) -> None:
        assert terminal_node_id(pipeline()) == "extract"

    def test_a_container_terminal_resolves_to_its_leaf(self) -> None:
        inner = Pipeline(
            [LLMNode(prompt, output_schema=Answer, node_id="extract")],
            budget=BUDGET,
            node_id="inner",
        )
        outer = Pipeline([Deterministic(lambda i, c: i, node_id="first"), inner], budget=BUDGET)

        assert terminal_node_id(outer) == "inner.extract"

    def test_the_output_comes_back_as_the_schema_rather_than_a_dict(self, tmp_path) -> None:
        """A callable `answer` reads a field off the object, so a plain dict would break it."""
        built = pipeline()
        result = built.run(
            {"question": "q?"},
            envelope=RunEnvelope(run_dir=str(tmp_path)),
            model=client(),
        )

        back = output_of(built, result.trajectory_path)

        assert isinstance(back, Answer)
        assert back == result.output

    def test_an_absence_comes_back_as_unknown(self, tmp_path) -> None:
        class Held(BaseModel):
            answer: str | Unknown

        def absent(inputs, ctx) -> Held:
            return Held(answer=Unknown(reason="nothing said"))

        built = Pipeline(
            [Deterministic(absent, node_id="absent", output_schema=Held)], budget=BUDGET
        )
        result = built.run({}, envelope=RunEnvelope(run_dir=str(tmp_path)))

        back = output_of(built, result.trajectory_path)

        assert isinstance(back.answer, Unknown)

    def test_a_run_that_never_reached_the_terminal_answers_nothing(self, tmp_path) -> None:
        assert output_of(pipeline(), run_path(tmp_path, "absent", "trajectory.jsonl")) is None


class TestRescore:
    def dead(self, tmp_path) -> Path:
        """An evaluation killed by a raising metric, leaving its rollouts on disk."""
        with pytest.raises(ConfigurationError):
            suite(raising).run(
                envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
                model=client(),
                split="held_out",
                k=K,
                seed=41,
                concurrency=2,
            )
        return next((Path(tmp_path) / "eval").glob("eval_*"))

    def complete(self, tmp_path) -> tuple[Path, EvalResults]:
        results = suite(safe).run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=client(),
            split="held_out",
            k=K,
            seed=41,
        )
        return next((Path(tmp_path) / "eval").glob("eval_*")), results

    def test_it_scores_the_rollouts_that_ran_without_running_anything(self, tmp_path) -> None:
        eval_dir = self.dead(tmp_path)
        reached: list[str] = []

        results = suite(safe).rescore(run_dir=eval_dir, split="held_out")

        assert reached == []
        assert len(results.rollouts) == ran(eval_dir)
        assert all(r.outcome is Outcome.CORRECT for r in results.rollouts)
        assert "segment_len" in results.metrics

    def test_it_writes_a_results_file_that_reads_back(self, tmp_path) -> None:
        eval_dir = self.dead(tmp_path)
        out = tmp_path / "results.json"

        suite(safe).rescore(run_dir=eval_dir, split="held_out").write(out)

        assert EvalResults.read(out).config["scored_from"] == "run_directory"

    def test_it_agrees_with_the_evaluation_that_produced_the_rollouts(self, tmp_path) -> None:
        """The point of the whole thing: the same rollouts score the same either way."""
        eval_dir, live = self.complete(tmp_path)

        again = suite(safe).rescore(run_dir=eval_dir, split="held_out")

        assert again.metrics["accuracy"].value == live.metrics["accuracy"].value
        assert again.metrics["segment_len"].value == live.metrics["segment_len"].value
        assert Counter(r.outcome for r in again.rollouts) == Counter(
            r.outcome for r in live.rollouts
        )
        assert again.config["incomplete"] is None

    def test_a_metric_added_afterwards_is_computed_from_the_same_rollouts(self, tmp_path) -> None:
        eval_dir, _ = self.complete(tmp_path)
        added = EvalSuite(
            pipeline(),
            examples(),
            answer="answer",
            matches=EXACT,
            metrics=[
                ProjectMetric(
                    name="answer_chars",
                    definition="characters in the asserted answer",
                    score=lambda s: float(len(s.answer)),
                    over=Over.ASSERTED,
                )
            ],
        )

        results = added.rescore(run_dir=eval_dir, split="held_out")

        assert results.metrics["answer_chars"].value == 2.0

    def test_a_partial_set_is_scored_and_says_so(self, tmp_path) -> None:
        eval_dir = self.dead(tmp_path)

        results = suite(safe).rescore(run_dir=eval_dir, split="held_out")
        partial = results.config["incomplete"]

        assert partial["rollouts_expected"] == N * K
        assert partial["rollouts_scored"] == len(results.rollouts)
        assert partial["examples_in_split"] == N
        assert results.n == partial["examples_scored"] < N
        assert "INCOMPLETE" in results.report()

    def test_a_changed_pipeline_is_refused(self, tmp_path) -> None:
        eval_dir, _ = self.complete(tmp_path)

        with pytest.raises(ConfigurationError) as raised:
            suite(safe, extra=True).rescore(run_dir=eval_dir, split="held_out")

        message = str(raised.value)
        assert "graph_fingerprint" in message
        assert "FT-15" in message
        assert suite(safe, extra=True).pipeline.graph_fingerprint() in message

    def test_a_directory_holding_no_rollouts_is_refused(self, tmp_path) -> None:
        with pytest.raises(ConfigurationError) as raised:
            suite(safe).rescore(run_dir=tmp_path / "nothing", split="held_out")

        assert "holds no run directory" in str(raised.value)

    def test_the_seed_it_reports_is_a_rollout_s_and_says_so(self, tmp_path) -> None:
        eval_dir, _ = self.complete(tmp_path)

        results = suite(safe).rescore(run_dir=eval_dir, split="held_out")

        assert results.config["seed_source"] == "rollout"
        assert results.config["seed"] != 41

    def test_what_did_not_run_is_null_rather_than_invented(self, tmp_path) -> None:
        eval_dir, _ = self.complete(tmp_path)

        config = suite(safe).rescore(run_dir=eval_dir, split="held_out").config

        assert config["concurrency"] is None
        assert config["max_spend"] is None

    def test_per_node_cost_needs_the_basis_the_run_used(self, tmp_path) -> None:
        eval_dir, _ = self.complete(tmp_path)
        basis = PriceBasis(currency="USD", input_uncached_per_mtok=0.1, output_per_mtok=0.3)

        without = suite(safe).rescore(run_dir=eval_dir, split="held_out")
        with_basis = suite(safe).rescore(run_dir=eval_dir, split="held_out", cost_basis=basis)

        assert without.nodes["extract"].cost.value is None
        assert with_basis.nodes["extract"].cost.value > 0

    def test_a_rollout_the_backend_never_answered_reads_back_the_same_way(self, tmp_path) -> None:
        """A run that errored produced no answer, and re-reading it must not invent one.

        A client with nothing to return raises on the first call, so the rollout stopped on a
        model call that recorded an error and no response. Live and re-scored have to sort that
        the same way, or a re-score reports a different set of rates over the same rollouts.
        """
        empty = EvalSuite(pipeline(), examples(), answer="answer", matches=EXACT)
        live = empty.run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            # No responses at all, so every rollout stops on its first model call.
            model=FakeModelClient(responses=[], scripted=False),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        assert all(r.outcome is Outcome.NO_RESPONSE for r in live.rollouts)
        assert live.metrics["failure_rate"].value is None
        assert live.metrics["failure_rate"].left_out["no_response"] == len(live.rollouts)
        eval_dir = next((Path(tmp_path) / "eval").glob("eval_*"))

        results = empty.rescore(run_dir=eval_dir, split="held_out")

        assert all(r.outcome is Outcome.NO_RESPONSE for r in results.rollouts)
        assert results.metrics["failure_rate"].left_out["no_response"] == len(results.rollouts)

    def test_a_rollout_whose_answer_did_not_validate_stays_failed(self, tmp_path) -> None:
        """The backend answered and the agent produced nothing usable, which is a failure."""
        empty = EvalSuite(pipeline(), examples(), answer="answer", matches=EXACT)
        live = empty.run(
            envelope=RunEnvelope(run_dir=str(tmp_path), cassette=Cassette.off()),
            model=FakeModelClient(responses=["not json at all"] * 9, scripted=False),
            split="held_out",
            k=1,
            seed=41,
            concurrency=1,
        )
        assert all(r.outcome is Outcome.FAILED for r in live.rollouts)
        assert live.metrics["failure_rate"].value == 1.0
        eval_dir = next((Path(tmp_path) / "eval").glob("eval_*"))

        results = empty.rescore(run_dir=eval_dir, split="held_out")

        assert all(r.outcome is Outcome.FAILED for r in results.rollouts)
        assert results.metrics["failure_rate"].value == 1.0


class TestAResultsFileIsNotOverwritten:
    """The only durable record of a measurement, and a deterministic name made it temporary.

    Dogfood #3's baseline was accuracy 6.1%, two hits in 33 rollouts, and its brief quoted it as
    the number the builder would act on. It was written to a path derived from the split, k and
    the backend, and the next evaluation wrote over it. The rollouts survived and could not be
    rescored, because the pipeline had moved (`dev-docs/runs/dogfood-3/findings.md` DF3-D5).
    """

    def _results(self, eval_id: str = "eval_a1226bc495df") -> EvalResults:
        return EvalResults(
            eval_id=eval_id,
            created_at="2026-08-11T00:00:00.000Z",
            config={"split": "held_out", "k": 3, "n": 11, "seed": 41},
            metrics={},
            nodes={},
            rollouts=(),
        )

    def test_writing_over_one_is_refused(self, tmp_path):
        target = tmp_path / "held_out-k3-vllm.json"
        self._results().write(target)

        with pytest.raises(ConfigurationError) as caught:
            self._results().write(target)

        assert "already holds a results file" in str(caught.value)
        assert "overwrite=True" in str(caught.value)

    def test_overwrite_replaces_it(self, tmp_path):
        target = tmp_path / "held_out-k3-vllm.json"
        self._results().write(target)

        assert self._results("eval_second").write(target, overwrite=True) == target
        assert json.loads(target.read_text())["eval_id"] == "eval_second"

    def test_the_default_name_is_the_evaluation_and_cannot_collide(self, tmp_path):
        first = self._results("eval_first").write(directory=tmp_path)
        second = self._results("eval_second").write(directory=tmp_path)

        assert first.name == "eval_first.json"
        assert second.name == "eval_second.json"
        assert first.exists() and second.exists()

    def test_an_empty_file_is_not_a_results_file(self, tmp_path):
        """A path a project touched, or one a failed write left behind, is not a measurement."""
        target = tmp_path / "held_out.json"
        target.touch()

        assert self._results().write(target) == target


class TestResumingAnEvaluationThatStopped:
    """A killed evaluation loses every rollout it paid for, unless it can be re-entered.

    Dogfood #3's Mistral baseline was killed by the coding agent's own two-hour timeout after
    17 of 33 rollouts and $3.2266. Nothing resumed, so the directory was deleted and the whole
    thing paid for again (`dev-docs/runs/dogfood-3/findings.md` DF3-D3).
    """

    def _env(self, root: Path) -> RunEnvelope:
        return RunEnvelope(run_dir=str(root), cassette=Cassette.off())

    def _run(self, root: Path, *, calls: list[str] | None = None, **extra):
        return suite(metrics=False).run(
            envelope=self._env(root),
            model=client(calls),
            split="held_out",
            k=K,
            seed=41,
            concurrency=1,
            **extra,
        )

    def _killed_part_way(self, root: Path, keep: int) -> Path:
        """An evaluation directory holding only its first `keep` rollouts, as a kill leaves."""
        results = self._run(root)
        directory = evaluation_dir(root, results.eval_id)
        for rollout in sorted(p for p in directory.iterdir() if p.is_dir())[keep:]:
            shutil.rmtree(rollout)
        return directory

    def test_only_the_missing_rollouts_are_run(self, tmp_path) -> None:
        directory = self._killed_part_way(tmp_path, keep=7)
        calls: list[str] = []

        results = self._run(tmp_path, calls=calls, resume_from=directory)

        assert len(results.rollouts) == N * K
        assert len(calls) == N * K - 7, "the seven on disk were scored, not run again"

    def test_the_resumed_rollouts_keep_their_own_trajectories(self, tmp_path) -> None:
        directory = self._killed_part_way(tmp_path, keep=7)
        # The rollout directories, and not `progress.json`, which the runner keeps current
        # and rewrites as the resumed evaluation lands its remaining rollouts.
        before = {p.name: p.stat().st_mtime_ns for p in sorted(directory.iterdir()) if p.is_dir()}

        self._run(tmp_path, resume_from=directory)

        after = {p.name: p.stat().st_mtime_ns for p in sorted(directory.iterdir()) if p.is_dir()}
        assert all(after[name] == stamp for name, stamp in before.items())

    def test_the_numbers_match_running_the_whole_thing(self, tmp_path) -> None:
        """A resumed evaluation is the evaluation, not an approximation of it."""
        whole = self._run(tmp_path / "whole")
        directory = self._killed_part_way(tmp_path / "part", keep=7)
        resumed = self._run(tmp_path / "part", resume_from=directory)

        assert resumed.eval_id == whole.eval_id
        assert resumed.metrics["accuracy"].value == whole.metrics["accuracy"].value
        assert [r.example_id for r in resumed.rollouts] == [r.example_id for r in whole.rollouts]

    def test_a_rollout_that_never_finished_is_run_again(self, tmp_path) -> None:
        """A kill leaves a manifest with no `ended_at`, and a rollout appends to what it finds."""
        directory = self._killed_part_way(tmp_path, keep=7)
        half = sorted(p for p in directory.iterdir() if p.is_dir())[-1]
        manifest = json.loads((half / "manifest.json").read_text())
        manifest["ended_at"] = None
        (half / "manifest.json").write_text(json.dumps(manifest))
        calls: list[str] = []

        self._run(tmp_path, calls=calls, resume_from=directory)

        assert len(calls) == N * K - 6, "the half-written one is run again, not scored"
        lines = (half / "trajectory.jsonl").read_text().splitlines()
        assert len({json.loads(line)["record_id"] for line in lines}) == len(lines)

    def test_another_evaluations_directory_is_refused(self, tmp_path) -> None:
        directory = self._killed_part_way(tmp_path, keep=7)
        renamed = directory.parent / "eval_something_else"
        directory.rename(renamed)

        with pytest.raises(ConfigurationError) as caught:
            self._run(tmp_path, resume_from=renamed)

        assert "is not this evaluation's directory" in str(caught.value)

    def test_a_moved_pipeline_cannot_be_resumed_into(self, tmp_path) -> None:
        """A changed graph is already a different evaluation, and the name is what says so.

        `eval_id` covers the pipeline's shape, so a resumed run under a changed pipeline never
        reaches the fingerprint comparison: the directory it is pointed at is not the one these
        arguments name. The message says that and points at `rescore`, which is what scores
        rollouts a pipeline has moved past.
        """
        directory = self._killed_part_way(tmp_path, keep=7)

        with pytest.raises(ConfigurationError) as caught:
            suite(metrics=False, extra=True).run(
                envelope=self._env(tmp_path),
                model=client(),
                split="held_out",
                k=K,
                seed=41,
                concurrency=1,
                resume_from=directory,
            )

        assert "is not this evaluation's directory" in str(caught.value)
        assert "rescore" in str(caught.value)

    def test_without_resume_from_the_directory_is_still_refused(self, tmp_path) -> None:
        """The refusal that protects a trajectory from holding two runs does not move."""
        self._killed_part_way(tmp_path, keep=7)

        with pytest.raises(ConfigurationError) as caught:
            self._run(tmp_path)

        assert "already holds an evaluation's rollouts" in str(caught.value)


class TestWatchingAnEvaluationRun:
    """An evaluation writes its results file at the end and nothing before it.

    Dogfood #3 wrote a 12KB `watch_eval.py` because of it, and the absence is what let the
    coding agent set a two-hour timeout on a four-hour run and not see it overrunning
    (`dev-docs/runs/dogfood-3/findings.md` §9.3).
    """

    def _run(self, root: Path, **extra):
        return suite(metrics=False).run(
            envelope=RunEnvelope(run_dir=str(root), cassette=Cassette.off()),
            model=client(),
            split="held_out",
            k=K,
            seed=41,
            concurrency=1,
            **extra,
        )

    def test_on_rollout_is_called_once_per_rollout_and_counts_up(self, tmp_path) -> None:
        seen: list[RolloutProgress] = []

        self._run(tmp_path, on_rollout=seen.append)

        assert len(seen) == N * K
        assert [p.finished for p in seen] == list(range(1, N * K + 1))
        assert {p.total for p in seen} == {N * K}
        assert seen[-1].outcomes == {"correct": N * K}

    def test_it_estimates_what_is_left_once_there_is_a_rate(self, tmp_path) -> None:
        seen: list[RolloutProgress] = []

        self._run(tmp_path, on_rollout=seen.append)

        assert seen[-1].remaining_s == 0 or seen[-1].remaining_s is None
        assert any(p.remaining_s for p in seen[:-1]), "a rate is available after the first"
        assert "rollouts" in seen[0].describe()

    def test_a_callback_that_raises_does_not_lose_the_evaluation(self, tmp_path) -> None:
        def explode(progress: RolloutProgress) -> None:
            raise RuntimeError("the project's own bug")

        with pytest.warns(SimpleAgentsWarning, match="on_rollout raised"):
            results = self._run(tmp_path, on_rollout=explode)

        assert len(results.rollouts) == N * K

    def test_progress_of_reads_a_directory_from_outside_the_process(self, tmp_path) -> None:
        """The half that would have saved dogfood #3: a second terminal, no pipeline imported."""
        results = self._run(tmp_path)
        directory = evaluation_dir(tmp_path, results.eval_id)

        progress = progress_of(directory, expected=N * K)

        assert progress["finished"] == N * K
        assert progress["running"] == 0
        assert progress["done"] is True
        assert progress["outcomes"] == {"completed": N * K}
        assert progress["elapsed_s"] is not None

    def test_it_reports_a_part_populated_directory_as_unfinished(self, tmp_path) -> None:
        results = self._run(tmp_path)
        directory = evaluation_dir(tmp_path, results.eval_id)
        for rollout in sorted(p for p in directory.iterdir() if p.is_dir())[7:]:
            shutil.rmtree(rollout)

        progress = progress_of(directory, expected=N * K)

        assert progress["finished"] == 7
        assert progress["done"] is False
        assert progress["remaining_s"] is not None

    def test_a_rollout_still_running_is_counted_apart_from_a_finished_one(self, tmp_path) -> None:
        results = self._run(tmp_path)
        directory = evaluation_dir(tmp_path, results.eval_id)
        first = sorted(p for p in directory.iterdir() if p.is_dir())[0]
        manifest = json.loads((first / "manifest.json").read_text())
        manifest["ended_at"] = None
        (first / "manifest.json").write_text(json.dumps(manifest))

        progress = progress_of(directory, expected=N * K)

        assert progress["running"] == 1
        assert progress["finished"] == N * K - 1

    def test_without_expected_it_does_not_guess_whether_it_is_done(self, tmp_path) -> None:
        """A directory holding 12 rollouts cannot say whether that is all of them."""
        results = self._run(tmp_path)

        progress = progress_of(evaluation_dir(tmp_path, results.eval_id))

        assert progress["done"] is None
        assert progress["expected"] is None
        assert progress["remaining_s"] is None
