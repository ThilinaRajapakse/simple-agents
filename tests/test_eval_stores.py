"""What each rollout of an evaluation runs against, for a pipeline that reaches a store.

The pipeline here is the shape the mechanism is for, and the shape that produced the finding:
a step that reads a store, and a last step that writes it back. Sharing one store across
rollouts is what let each rollout answer out of what the last one wrote, and the assertion
that catches it is what each rollout's own write saw, not the answer it produced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from simple_agents import (
    Budget,
    ConfigurationError,
    Deterministic,
    Pipeline,
    RunEnvelope,
    RunSuspended,
    SideEffectClass,
    Suspend,
    tool,
)
from simple_agents.evaluation import CopyPerRollout, EvalSuite, Example, ExampleSet, Shared
from simple_agents.evaluation.results import EVAL_FORMAT_VERSION

BUDGET = Budget(max_steps=None, max_tokens=100_000, max_cost=None, max_wall_clock_ms=None)


def store_at(path: Path, rows: list[str]) -> Path:
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


def exclude_first(inputs: dict, ctx) -> dict:
    queued = Path(ctx.run_inputs["queue"]).read_text(encoding="utf-8").split()
    return {"pick": next(s for s in inputs["shows"] if s not in queued)}


def store_queue(inputs: dict, ctx) -> dict:
    """Writes the store, and reads how many rows it held when it did."""
    target = Path(ctx.run_inputs["queue"])
    rows = target.read_text(encoding="utf-8").split() + [inputs["pick"]]
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")
    ctx.record_access("queue", "write", inputs={"pick": inputs["pick"]}, outputs={"n": len(rows)})
    return {"answer": "ok", "total": len(rows)}


def recommend() -> Pipeline:
    return Pipeline(
        [
            Deterministic(
                exclude_first, node_id="exclude_first", successors=["store_queue"], touches="queue"
            ),
            Deterministic(store_queue, node_id="store_queue", successors=[], touches="queue"),
        ],
        budget=BUDGET,
    )


def examples() -> ExampleSet:
    return ExampleSet(
        [
            Example(
                id=f"u{i}",
                inputs={"user": f"u{i}", "shows": ["a", "b", "c", "d", "e"]},
                expected="ok",
                split="held_out" if i % 2 else "dev",
            )
            for i in range(4)
        ]
    )


def suite(pipeline: Pipeline | None = None, given: ExampleSet | None = None) -> EvalSuite:
    return EvalSuite(
        pipeline or recommend(),
        given or examples(),
        answer="answer",
        matches=lambda s: s.answer == s.expected,
    )


def env(tmp_path: Path) -> RunEnvelope:
    return RunEnvelope(run_dir=tmp_path / "runs")


def totals_written(run_dir: Path) -> list[int]:
    """What each rollout's own write saw in the store, which is where contamination shows."""
    seen = []
    for manifest in sorted(run_dir.rglob("manifest.json")):
        for line in (manifest.parent / "trajectory.jsonl").read_text().splitlines():
            record = json.loads(line)
            if (
                record.get("record_type") == "resource_access"
                and record.get("direction") == "write"
            ):
                seen.append(record["outputs"]["n"])
    return sorted(seen)


class TestAStoreNoOneSaidAnythingAbout:
    def test_it_is_refused_naming_the_store_and_the_steps(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            suite().run(envelope=env(tmp_path), split="held_out", k=2, seed=41)

        assert "'queue' (declared by exclude_first, store_queue)" in str(refusal.value)
        assert "CopyPerRollout" in str(refusal.value) and "Shared" in str(refusal.value)

    def test_a_pipeline_declaring_no_store_needs_nothing(self, tmp_path: Path) -> None:
        plain = Pipeline(
            [Deterministic(lambda i, ctx: {"answer": "ok"}, node_id="only")], budget=BUDGET
        )

        results = suite(plain).run(envelope=env(tmp_path), split="held_out", k=2, seed=41)

        assert results.config["stores"] == {}

    def test_a_store_declared_shared_is_enough_to_run(self, tmp_path: Path) -> None:
        store_at(tmp_path / "queue.txt", ["z"])
        seeded = ExampleSet(
            [
                Example(
                    id=e.id,
                    inputs={**e.inputs, "queue": str(tmp_path / "queue.txt")},
                    expected=e.expected,
                    split=e.split,
                )
                for e in examples()
            ]
        )

        results = suite(given=seeded).run(
            envelope=env(tmp_path),
            split="held_out",
            k=2,
            seed=41,
            stores={"queue": Shared("the test says so")},
        )

        assert results.config["stores"] == {
            "queue": {"isolation": "shared", "reason": "the test says so"}
        }

    def test_a_shared_store_is_what_lets_rollouts_read_each_others_writes(
        self, tmp_path: Path
    ) -> None:
        """The counterfactual. One project measured its headline figure this way."""
        store_at(tmp_path / "queue.txt", ["z"])
        seeded = ExampleSet(
            [
                Example(
                    id=e.id,
                    inputs={**e.inputs, "queue": str(tmp_path / "queue.txt")},
                    expected=e.expected,
                    split=e.split,
                )
                for e in examples()
            ]
        )

        suite(given=seeded).run(
            envelope=env(tmp_path),
            split="held_out",
            k=2,
            seed=41,
            stores={"queue": Shared("the test says so")},
            concurrency=1,
        )

        assert totals_written(tmp_path / "runs") == [2, 3, 4, 5]


class TestAStoreAPipelineInsideThePipelineReaches:
    def test_a_nested_step_declaring_one_is_refused_under_its_prefixed_id(
        self, tmp_path: Path
    ) -> None:
        """`declared_nodes` reaches into a pipeline used as a node, so a store the outer
        pipeline never names is still covered."""
        inner = Pipeline(
            [Deterministic(lambda i, ctx: {"answer": "ok"}, node_id="deep", touches="ledger")],
            budget=BUDGET,
            node_id="inner",
        )
        outer = Pipeline(
            [
                Deterministic(lambda i, ctx: i, node_id="top", successors=["inner"]),
                inner,
            ],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as refusal:
            suite(outer).run(envelope=env(tmp_path), split="held_out", k=1, seed=41)

        assert "'ledger' (declared by inner.deep)" in str(refusal.value)


class TestACopyPerRollout:
    def _run(self, tmp_path: Path, **kw):
        source = store_at(tmp_path / "queue.txt", ["z"])
        return source, suite().run(
            envelope=env(tmp_path),
            split="held_out",
            k=2,
            seed=41,
            stores={"queue": CopyPerRollout(source, as_input="queue")},
            concurrency=1,
            **kw,
        )

    def test_no_rollout_reads_what_another_wrote(self, tmp_path: Path) -> None:
        self._run(tmp_path)

        assert totals_written(tmp_path / "runs") == [2, 2, 2, 2]

    def test_the_real_store_is_untouched(self, tmp_path: Path) -> None:
        source, _ = self._run(tmp_path)

        assert source.read_text(encoding="utf-8") == "z\n"

    def test_every_copy_is_deleted_when_its_rollout_ends(self, tmp_path: Path) -> None:
        self._run(tmp_path)

        assert list((tmp_path / "runs").rglob("stores/*")) == []

    def test_the_results_file_records_what_each_store_did(self, tmp_path: Path) -> None:
        source, results = self._run(tmp_path)
        written = json.loads(Path(results.write(tmp_path / "out.json")).read_text())

        assert written["eval_format_version"] == EVAL_FORMAT_VERSION
        assert written["config"]["stores"] == {
            "queue": {
                "isolation": "copy_per_rollout",
                "source": str(source),
                "as_input": "queue",
            }
        }

    def test_the_path_stays_out_of_the_example_sets_hash(self, tmp_path: Path) -> None:
        """One project put the copies' paths into the examples, and `compare()` then refused
        to pair two of its own runs."""
        before = examples().content_hash()
        _, results = self._run(tmp_path)

        assert examples().content_hash() == before
        assert results.config["example_set"]["content_hash"] == before

    def test_a_source_that_is_not_there_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            suite().run(
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={"queue": CopyPerRollout(tmp_path / "gone.txt", as_input="queue")},
            )

        assert "is not there" in str(refusal.value)

    def test_a_directory_store_is_copied_whole(self, tmp_path: Path) -> None:
        source = tmp_path / "corpus"
        (source / "inner").mkdir(parents=True)
        (source / "inner" / "one.txt").write_text("z\n", encoding="utf-8")

        def read_it(inputs: dict, ctx) -> dict:
            held = Path(ctx.run_inputs["corpus"]) / "inner" / "one.txt"
            return {"answer": "ok" if held.read_text(encoding="utf-8") == "z\n" else "no"}

        pipeline = Pipeline(
            [Deterministic(read_it, node_id="read_it", touches="corpus")], budget=BUDGET
        )

        results = suite(pipeline).run(
            envelope=env(tmp_path),
            split="held_out",
            k=1,
            seed=41,
            stores={"corpus": CopyPerRollout(source, as_input="corpus")},
        )

        assert results.metrics["accuracy"].interval.point == 1.0

    def test_a_resource_name_that_would_escape_stays_inside_the_rollout(
        self, tmp_path: Path
    ) -> None:
        """`touches=` takes any non-empty string, and the name becomes part of a path here."""
        from simple_agents.evaluation.stores import copies_for

        source = store_at(tmp_path / "queue.txt", ["z"])
        root = tmp_path / "rollout"

        _, made = copies_for(root, {"../../escaped": CopyPerRollout(source, as_input="q")})

        assert made[0].parent == root / "stores"
        assert root in made[0].parents

    def test_examples_that_are_not_a_mapping_are_refused(self, tmp_path: Path) -> None:
        source = store_at(tmp_path / "queue.txt", ["z"])
        bare = ExampleSet(
            [
                Example(id="d1", inputs="a question", expected="ok", split="dev"),
                Example(id="h1", inputs="another", expected="ok", split="held_out"),
            ]
        )

        with pytest.raises(ConfigurationError) as refusal:
            suite(given=bare).run(
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={"queue": CopyPerRollout(source, as_input="queue")},
            )

        assert "no key for the path to arrive under" in str(refusal.value)


class TestAnExampleWithTurns:
    """Each turn of one rollout runs against the same copy, and the injected path is not
    mistaken for the key that carries what was said: `_said` reads the example's own inputs,
    which the overlay is never added to."""

    def test_every_turn_reads_the_same_copy_and_the_question_still_carries(
        self, tmp_path: Path
    ) -> None:
        seen: list = []

        def answers(inputs: dict, ctx) -> dict:
            seen.append((inputs["question"], ctx.run_inputs["queue"]))
            return {"answer": "ok"}

        pipeline = Pipeline(
            [Deterministic(answers, node_id="answers", touches="queue")], budget=BUDGET
        )
        source = store_at(tmp_path / "queue.txt", ["z"])
        talking = ExampleSet(
            [
                Example(
                    id="h1",
                    inputs={"question": "first"},
                    expected="ok",
                    split="held_out",
                    turns=["second"],
                ),
                Example(id="d1", inputs={"question": "other"}, expected="ok", split="dev"),
            ]
        )

        suite(pipeline, talking).run(
            envelope=env(tmp_path),
            split="held_out",
            k=1,
            seed=41,
            stores={"queue": CopyPerRollout(source, as_input="queue")},
        )

        assert [question for question, _ in seen] == ["first", "second"]
        assert len({copy for _, copy in seen}) == 1
        assert Path(seen[0][1]) != source


class TestARolloutThatDidNotFinish:
    def test_a_failed_rollout_leaves_no_copy_behind(self, tmp_path: Path) -> None:
        def falls_over(inputs: dict, ctx) -> dict:
            raise RuntimeError("the store was down")

        pipeline = Pipeline(
            [Deterministic(falls_over, node_id="only", touches="queue")], budget=BUDGET
        )
        source = store_at(tmp_path / "queue.txt", ["z"])

        suite(pipeline).run(
            envelope=env(tmp_path),
            split="held_out",
            k=1,
            seed=41,
            stores={"queue": CopyPerRollout(source, as_input="queue")},
        )

        assert list((tmp_path / "runs").rglob("stores/*")) == []

    def test_a_suspended_rollout_keeps_its_copy(self, tmp_path: Path) -> None:
        """The run is waiting and can be continued, and the copy is what it would continue
        against. `resume_from` removes the whole directory before running it again."""

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def confirm() -> str:
            """Ask the viewer."""
            raise Suspend(waiting_for="confirmation")

        def asks(inputs: dict, ctx) -> dict:
            return {"answer": ctx.call_tool("confirm")}

        pipeline = Pipeline(
            [Deterministic(asks, node_id="only", tools=[confirm], touches="queue")], budget=BUDGET
        )
        source = store_at(tmp_path / "queue.txt", ["z"])

        with pytest.raises(RunSuspended):
            suite(pipeline).run(
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={"queue": CopyPerRollout(source, as_input="queue")},
                concurrency=1,
            )

        kept = list((tmp_path / "runs").rglob("stores/queue.txt"))
        assert len(kept) == 1
        assert kept[0].read_text(encoding="utf-8") == "z\n"


class TestTwoStoresThatWouldWriteOverEachOther:
    """Both would produce a figure measured against a store the caller did not describe, and
    both are refused before any rollout runs."""

    def test_two_stores_sharing_an_input_key_are_refused(self, tmp_path: Path) -> None:
        source = store_at(tmp_path / "queue.txt", ["z"])

        with pytest.raises(ConfigurationError) as refusal:
            suite().run(
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={
                    "queue": CopyPerRollout(source, as_input="queue"),
                    "other": CopyPerRollout(source, as_input="queue"),
                },
            )

        assert "the same as_input='queue'" in str(refusal.value)
        assert list((tmp_path / "runs").rglob("stores/*")) == []

    def test_two_names_that_file_alike_are_refused(self, tmp_path: Path) -> None:
        """`a/b` and `a_b` both file as `a_b`, and one copy would overwrite the other."""
        source = store_at(tmp_path / "queue.txt", ["z"])

        with pytest.raises(ConfigurationError) as refusal:
            suite().run(
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={
                    "queue": Shared("declared so the pipeline's own store is covered"),
                    "a/b": CopyPerRollout(source, as_input="one"),
                    "a_b": CopyPerRollout(source, as_input="two"),
                },
            )

        assert "'a_b.txt'" in str(refusal.value)

    def test_two_stores_that_differ_are_both_copied(self, tmp_path: Path) -> None:
        first = store_at(tmp_path / "queue.txt", ["z"])
        second = store_at(tmp_path / "notes.txt", ["y"])

        def reads_both(inputs: dict, ctx) -> dict:
            held = Path(ctx.run_inputs["queue"]).read_text(encoding="utf-8")
            beside = Path(ctx.run_inputs["notes"]).read_text(encoding="utf-8")
            return {"answer": "ok" if (held, beside) == ("z\n", "y\n") else "no"}

        pipeline = Pipeline(
            [Deterministic(reads_both, node_id="both", touches=["queue", "notes"])],
            budget=BUDGET,
        )

        results = suite(pipeline).run(
            envelope=env(tmp_path),
            split="held_out",
            k=1,
            seed=41,
            stores={
                "queue": CopyPerRollout(first, as_input="queue"),
                "notes": CopyPerRollout(second, as_input="notes"),
            },
        )

        assert results.metrics["accuracy"].interval.point == 1.0


class TestMakingTheRecordingAnEvaluationReplays:
    """`suite.record` runs the real code once per rollout, so a store its runs share is
    written before the evaluation that replays them has begun."""

    def test_an_undeclared_store_is_refused(self, tmp_path: Path) -> None:
        from simple_agents import Cassette

        with pytest.raises(ConfigurationError) as refusal:
            suite().record(
                envelope=env(tmp_path).with_cassette(Cassette.record(tmp_path / "c.jsonl")),
                split="held_out",
                k=1,
            )

        assert "Evaluation refused to record" in str(refusal.value)
        assert "'queue'" in str(refusal.value)

    def test_each_run_gets_its_own_copy_and_the_real_store_is_untouched(
        self, tmp_path: Path
    ) -> None:
        from simple_agents import Cassette

        source = store_at(tmp_path / "queue.txt", ["z"])

        made = suite().record(
            envelope=env(tmp_path).with_cassette(Cassette.record(tmp_path / "c.jsonl")),
            split="held_out",
            k=2,
            seed=41,
            stores={"queue": CopyPerRollout(source, as_input="queue")},
        )

        assert made.failed == ()
        assert source.read_text(encoding="utf-8") == "z\n"
        assert totals_written(tmp_path / "runs") == [2, 2, 2, 2]
        assert list((tmp_path / "runs").rglob("stores/*")) == []


class TestASweepOverVariants:
    """`compare_variants` says it refuses before anything runs, so an arm whose steps declare
    a store the baseline's do not is refused before the baseline arm is paid for."""

    def test_an_arm_declaring_an_uncovered_store_is_refused_before_the_baseline_runs(
        self, tmp_path: Path
    ) -> None:
        from simple_agents.evaluation import compare_variants

        source = store_at(tmp_path / "queue.txt", ["z"])
        arm = Pipeline(
            [
                Deterministic(
                    exclude_first,
                    node_id="exclude_first",
                    successors=["store_queue"],
                    touches="queue",
                ),
                Deterministic(
                    store_queue, node_id="store_queue", successors=[], touches=["queue", "ledger"]
                ),
            ],
            budget=BUDGET,
        )

        with pytest.raises(ConfigurationError) as refusal:
            compare_variants(
                suite(),
                {"with a ledger": arm},
                envelope=env(tmp_path),
                split="held_out",
                k=1,
                seed=41,
                stores={"queue": CopyPerRollout(source, as_input="queue")},
            )

        assert "'with a ledger' arm" in str(refusal.value) and "'ledger'" in str(refusal.value)
        assert not (tmp_path / "runs").exists() or list((tmp_path / "runs").rglob("*.jsonl")) == []


class TestWhatTheDeclarationsRefuse:
    def test_a_copy_with_no_input_key_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            CopyPerRollout("data/store.db", as_input="  ")

        assert "no as_input" in str(refusal.value)

    def test_a_shared_store_with_no_reason_is_refused(self) -> None:
        with pytest.raises(ConfigurationError) as refusal:
            Shared("")

        assert "declares no reason" in str(refusal.value)


class TestARescoredFile:
    def test_it_says_what_the_rollouts_ran_against_is_unrecorded(self, tmp_path: Path) -> None:
        """`null` rather than `{}`: nothing ran here, and no store declared is a different
        answer from one nothing on disk records."""
        source = store_at(tmp_path / "queue.txt", ["z"])
        results = suite().run(
            envelope=env(tmp_path),
            split="held_out",
            k=1,
            seed=41,
            stores={"queue": CopyPerRollout(source, as_input="queue")},
        )

        rescored = suite().rescore(
            run_dir=Path(tmp_path / "runs") / "eval" / results.eval_id, split="held_out"
        )

        assert rescored.config["stores"] is None
