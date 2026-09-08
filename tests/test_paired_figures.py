"""Two things put side by side, and a figure over what was preferred.

The numbers are dogfood #5's, which is the run this seam came from: 40 pairwise comparisons
drawn from two bands of one live ordering, 7 preferring each side and 26 preferring neither.
The builder's account of those 26 is that both shows were ones he did not want to watch, which
is a different finding from the two bands being indistinguishable, and the tests here check
that both come out as their own figure.
"""

from __future__ import annotations

import pytest

from simple_agents import ConfigurationError
from simple_agents.evaluation import (
    Pair,
    paired_figure,
    pairs_from_arms,
    unjudged_pairs,
)
from simple_agents.evaluation.outcomes import Outcome, RolloutOutcome
from simple_agents.evaluation.results import EvalResults


def chose(pair: Pair, verdict):
    """Which side a verdict picked, by name. The library never knows this; a project does."""
    if verdict == "prefer_a":
        return pair.a_arm
    if verdict == "prefer_b":
        return pair.b_arm
    return verdict


def band_pairs() -> tuple[list[Pair], dict[str, str]]:
    """The forty, with the verdicts the end user actually recorded."""
    pairs, verdicts = [], {}
    for index in range(40):
        pair = Pair(
            id=f"p{index:03d}",
            a=f"high{index}",
            b=f"low{index}",
            a_arm="high_band",
            b_arm="low_band",
        )
        pairs.append(pair)
        verdicts[pair.id] = (
            "prefer_a" if index < 7 else "prefer_b" if index < 14 else "neither_wanted"
        )
    return pairs, verdicts


def arm(eval_id: str, answers: dict[tuple[str, int], str]) -> EvalResults:
    return EvalResults(
        eval_id=eval_id,
        created_at="t",
        config={},
        metrics={},
        nodes={},
        rollouts=tuple(
            RolloutOutcome(
                example_id=example_id,
                rollout=index,
                seed=index,
                outcome=Outcome.CORRECT,
                answer=answer,
            )
            for (example_id, index), answer in sorted(answers.items())
        ),
    )


class TestTheFortyComparisons:
    """The instrument this project built outside the library, run through it.

    It computed a win rate and reported no signal. The figure it never computed is that two
    thirds of the pairs held nothing the end user wanted, which is the finding.
    """

    def test_the_win_rate_over_pairs_with_a_preference(self) -> None:
        pairs, verdicts = band_pairs()

        figure = paired_figure(
            pairs,
            verdicts,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "high_band",
            denominator=lambda p, v: chose(p, v) in ("high_band", "low_band"),
            resamples=2000,
        )

        assert (figure.numerator, figure.denominator) == (7, 14)
        assert figure.value == pytest.approx(0.5)
        assert figure.interval is not None

    def test_the_figure_the_instrument_never_computed(self) -> None:
        pairs, verdicts = band_pairs()

        figure = paired_figure(
            pairs,
            verdicts,
            name="nothing_wanted",
            definition="d",
            numerator=lambda p, v: v == "neither_wanted",
            denominator=lambda p, v: 1.0,
            resamples=2000,
        )

        assert (figure.numerator, figure.denominator) == (26, 40)
        assert figure.value == pytest.approx(0.65)
        assert figure.interval.low > 0.4

    def test_counting_a_neither_as_a_loss_reports_a_different_number(self) -> None:
        """Both denominators are defensible, and they support opposite readings."""
        pairs, verdicts = band_pairs()

        over_everything = paired_figure(
            pairs,
            verdicts,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "high_band",
            denominator=lambda p, v: 1.0,
            resamples=2000,
        )

        assert over_everything.value == pytest.approx(0.175)


class TestWhatAPairCarries:
    def test_the_side_names_survive_a_randomised_order(self) -> None:
        """A verdict names a position; a counting rule reads what that position held."""
        flipped = Pair(id="p", a="b", b="a", a_arm="baseline", b_arm="variant")
        assert chose(flipped, "prefer_a") == "baseline"
        assert chose(flipped, "prefer_b") == "variant"

    def test_two_things_from_one_arm_fall_outside_a_figure_between_arms(self) -> None:
        """A within-arm pair ranks inside the arm and says nothing between arms."""
        within = Pair(id="w", a="x", b="y", a_arm="high_band", b_arm="high_band")
        pairs, verdicts = band_pairs()
        verdicts["w"] = "prefer_a"

        figure = paired_figure(
            [*pairs, within],
            verdicts,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "high_band" and p.a_arm != p.b_arm,
            denominator=lambda p, v: (
                p.a_arm != p.b_arm and chose(p, v) in ("high_band", "low_band")
            ),
            resamples=200,
        )

        assert (figure.numerator, figure.denominator) == (7, 14)
        assert within.arms == ("high_band", "high_band")

    def test_an_empty_id_is_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="empty id"):
            Pair(id="  ", a="a", b="b")

    def test_the_resampling_unit_is_the_example_where_there_is_one(self) -> None:
        assert Pair(id="p", a="a", b="b", example_id="q29").unit == "q29"
        assert Pair(id="p", a="a", b="b").unit == "p"


class TestBuildingPairsFromTwoArms:
    def test_it_pairs_each_rollout_with_its_own_index(self) -> None:
        before = arm("a", {("q1", 0): "old1", ("q1", 1): "old2", ("q2", 0): "old3"})
        after = arm("b", {("q1", 0): "new1", ("q1", 1): "new2", ("q2", 0): "new3"})

        pairs = pairs_from_arms(before, after)

        assert [p.id for p in pairs] == ["q1#0", "q1#1", "q2#0"]
        assert [(p.a, p.b) for p in pairs][0] == ("old1", "new1")
        assert pairs[0].example_id == "q1"

    def test_a_rollout_only_one_side_has_is_left_out(self) -> None:
        before = arm("a", {("q1", 0): "old", ("q2", 0): "old"})
        after = arm("b", {("q1", 0): "new"})

        assert [p.id for p in pairs_from_arms(before, after)] == ["q1#0"]

    def test_two_arms_sharing_no_rollout_are_refused(self) -> None:
        with pytest.raises(ConfigurationError, match="share no rollout"):
            pairs_from_arms(arm("a", {("q1", 0): "x"}), arm("b", {("q2", 0): "y"}))

    def test_a_seed_randomises_the_order_and_records_what_each_side_holds(self) -> None:
        """A judge shown one arm first prefers it, so the figure would measure the order too."""
        answers = {("q%d" % i, 0): "old" for i in range(40)}
        before = arm("a", answers)
        after = arm("b", dict.fromkeys(answers, "new"))

        pairs = pairs_from_arms(before, after, before_arm="baseline", after_arm="variant", seed=41)

        flipped = [p for p in pairs if p.a_arm == "variant"]
        assert 0 < len(flipped) < len(pairs)
        # Whichever way round, the side name always matches what that side holds.
        assert all((p.a == "new") == (p.a_arm == "variant") for p in pairs)

    def test_without_a_seed_the_order_is_fixed(self) -> None:
        answers = {("q%d" % i, 0): "old" for i in range(20)}
        pairs = pairs_from_arms(arm("a", answers), arm("b", dict.fromkeys(answers, "new")))
        assert all(p.a_arm == "before" for p in pairs)


class TestWhatIsStillOutstanding:
    def test_unjudged_pairs_names_them(self) -> None:
        pairs, verdicts = band_pairs()
        some = dict(list(verdicts.items())[:10])

        waiting = unjudged_pairs(pairs, some)

        assert len(waiting) == 30
        assert waiting[0].id == "p010"

    def test_a_figure_counts_what_it_could_not_score(self) -> None:
        """A denominator that shrank without saying so reads as a measurement over the whole set."""
        pairs, verdicts = band_pairs()
        some = dict(list(verdicts.items())[:14])

        figure = paired_figure(
            pairs,
            some,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "high_band",
            denominator=lambda p, v: 1.0,
            resamples=500,
        )

        assert figure.left_out == {"unjudged": 26}
        assert figure.denominator == 14


class TestWhatAPairedFigureRefuses:
    def test_no_pairs(self) -> None:
        with pytest.raises(ConfigurationError, match="no pairs"):
            paired_figure([], {}, name="x", definition="d", numerator=lambda p, v: 1)

    def test_two_pairs_sharing_an_id(self) -> None:
        twice = [Pair(id="p", a="a", b="b"), Pair(id="p", a="c", b="d")]
        with pytest.raises(ConfigurationError, match="two pairs with id"):
            paired_figure(twice, {}, name="x", definition="d", numerator=lambda p, v: 1)

    def test_a_rule_that_raises_names_the_pair(self) -> None:
        pairs, verdicts = band_pairs()
        with pytest.raises(ConfigurationError, match="p000"):
            paired_figure(
                pairs,
                verdicts,
                name="x",
                definition="d",
                numerator=lambda p, v: 1 / 0,
                denominator=lambda p, v: 1,
            )

    def test_a_rule_returning_something_other_than_a_number(self) -> None:
        pairs, verdicts = band_pairs()
        with pytest.raises(ConfigurationError, match="returned"):
            paired_figure(
                pairs,
                verdicts,
                name="x",
                definition="d",
                numerator=lambda p, v: "yes",
                denominator=lambda p, v: 1,
            )

    def test_a_total_with_no_denominator_and_no_declared_reason(self) -> None:
        """The same rule a ProjectRatio follows: a count says it is one."""
        pairs, verdicts = band_pairs()
        with pytest.raises(ConfigurationError, match="no denominator"):
            paired_figure(pairs, verdicts, name="x", definition="d", numerator=lambda p, v: 1)


class TestSelfConsistencyWithNoLabel:
    """Shape G2, which the pair seam made expressible without being designed for it.

    The k rollouts of one example are pairs, so agreement across them is a figure over pairs
    with no answer key anywhere. The survey recorded this as needing "the resampling unit to
    become the score's input, which nothing supports".
    """

    def test_agreement_across_an_examples_own_rollouts(self) -> None:
        from itertools import combinations

        answers = ["Paris", "Paris", "Lyon"]
        pairs = [
            Pair(
                id=f"q1-{i}",
                a=a,
                b=b,
                a_arm="rollout_a",
                b_arm="rollout_b",
                example_id="q1",
            )
            for i, (a, b) in enumerate(combinations(answers, 2))
        ]
        verdicts = {p.id: ("same" if p.a == p.b else "different") for p in pairs}

        figure = paired_figure(
            pairs,
            verdicts,
            name="self_consistency",
            definition="rollout pairs of one example that agree",
            numerator=lambda p, v: v == "same",
            denominator=lambda p, v: 1.0,
            resamples=500,
        )

        assert (figure.numerator, figure.denominator) == (1, 3)
        # Every pair came from one example, so the resampling unit is that example.
        assert figure.examples == 1


class TestTheDocumentedPath:
    """`docs/evaluation.md` §11.9's example, run rather than read.

    Every other test here passes raw verdicts. The documented call passes what `read_labels`
    returns, which is a `Label` per id, and a counting rule comparing that to a string matched
    nothing: the figure came back 0 of 0 with a reason blaming the denominator.
    """

    def _labelled(self, tmp_path, verdict: str):
        from simple_agents.evaluation.labels import Label, write_labels

        path = tmp_path / "labels.jsonl"
        pairs = [
            Pair(id=f"p{i}", a="new", b="old", a_arm="variant", b_arm="baseline") for i in range(4)
        ]
        write_labels(path, [Label(id=p.id, verdict=verdict, decided_by="human") for p in pairs])
        return pairs, path

    def test_it_takes_what_read_labels_returns(self, tmp_path) -> None:
        from simple_agents.evaluation import read_labels

        pairs, path = self._labelled(tmp_path, "prefer_a")

        figure = paired_figure(
            pairs,
            read_labels(path),
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "variant",
            denominator=lambda p, v: chose(p, v) in ("variant", "baseline"),
            resamples=500,
        )

        assert (figure.numerator, figure.denominator) == (4, 4)

    def test_a_plain_mapping_of_raw_verdicts_still_works(self, tmp_path) -> None:
        pairs, _ = self._labelled(tmp_path, "prefer_a")
        raw = {p.id: "prefer_b" for p in pairs}

        figure = paired_figure(
            pairs,
            raw,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "variant",
            denominator=lambda p, v: 1.0,
            resamples=500,
        )

        assert figure.numerator == 0


class TestASessionOnTheRecord:
    """`paired_results`: the pairs, their verdicts and the figures as one results file."""

    def _session(self, tmp_path, **kw):
        from simple_agents.evaluation import Label, paired_results, read_labels, write_labels

        pairs, raw = band_pairs()
        path = tmp_path / "labels.jsonl"
        write_labels(
            path,
            [
                Label(
                    id=p.id,
                    verdict=raw[p.id],
                    decided_by="human",
                    decided_at=f"2026-09-0{1 + (i % 7)}T10:00:00+00:00",
                )
                for i, p in enumerate(pairs)
            ],
        )
        labels = read_labels(path)
        figure = paired_figure(
            pairs,
            labels,
            name="win_rate",
            definition="d",
            numerator=lambda p, v: chose(p, v) == "high_band",
            denominator=lambda p, v: chose(p, v) in ("high_band", "low_band"),
            resamples=200,
        )
        return (
            pairs,
            labels,
            paired_results(
                pairs,
                labels,
                figures=[figure],
                eval_id="bands",
                blind=True,
                verdicts_mean={"prefer_a": "a", "prefer_b": "b", "neither_wanted": "neither"},
                **kw,
            ),
        )

    def test_it_writes_and_reads_back_as_a_results_file(self, tmp_path) -> None:
        pairs, labels, results = self._session(tmp_path)
        out = results.write(tmp_path / "bands.json")

        back = EvalResults.read(out)

        assert back.config["kind"] == "pairs"
        assert back.config["contest"] == ["high_band", "low_band"]
        assert back.config["blind"] is True
        assert back.config["decided_by"] == ["human"]
        assert back.config["verdicts"] == {
            "prefer_a": "a",
            "prefer_b": "b",
            "neither_wanted": "neither",
        }
        assert (back.config["n"], back.config["units"], back.config["unjudged"]) == (40, 40, 0)
        assert len(back.pairs) == 40
        assert back.pairs[0] == {
            "id": "p000",
            "a": "high0",
            "b": "low0",
            "a_arm": "high_band",
            "b_arm": "low_band",
            "example_id": None,
            "verdict": "prefer_a",
            "decided_by": "human",
            "decided_at": "2026-09-01T10:00:00+00:00",
            "reason": "",
        }
        assert back.metrics["win_rate"].numerator == 7
        assert back.rollouts == () and back.nodes == {}
        assert back.carries("pairs")

    def test_it_is_dated_by_the_last_judgement(self, tmp_path) -> None:
        _, _, results = self._session(tmp_path)
        assert results.created_at == "2026-09-07T10:00:00+00:00"
        _, _, told = self._session(tmp_path, created_at="2026-09-08T00:00:00+00:00")
        assert told.created_at == "2026-09-08T00:00:00+00:00"

    def test_an_unjudged_pair_is_on_the_record_with_no_verdict(self, tmp_path) -> None:
        from simple_agents.evaluation import paired_results

        pairs, verdicts = band_pairs()
        some = dict(list(verdicts.items())[:30])
        figure = paired_figure(
            pairs,
            some,
            name="w",
            definition="d",
            numerator=lambda p, v: 1,
            denominator=lambda p, v: 1,
            resamples=200,
        )

        results = paired_results(
            pairs, some, figures=[figure], eval_id="s", blind=False, decided_by="human"
        )

        assert results.config["unjudged"] == 10 and results.config["n"] == 30
        assert results.pairs[-1]["verdict"] is None and results.pairs[-1]["decided_by"] is None

    def test_a_plain_mapping_needs_a_decider(self) -> None:
        from simple_agents.evaluation import paired_results

        pairs, verdicts = band_pairs()
        figure = paired_figure(
            pairs,
            verdicts,
            name="w",
            definition="d",
            numerator=lambda p, v: 1,
            denominator=lambda p, v: 1,
            resamples=200,
        )
        with pytest.raises(ConfigurationError, match="no decided_by"):
            paired_results(pairs, verdicts, figures=[figure], eval_id="s", blind=False)

    def test_a_meaning_outside_the_four_is_refused(self) -> None:
        from simple_agents.evaluation import paired_results

        pairs, verdicts = band_pairs()
        with pytest.raises(ConfigurationError, match="a, b, both, neither"):
            paired_results(
                pairs,
                verdicts,
                figures=[],
                eval_id="s",
                blind=False,
                decided_by="human",
                verdicts_mean={"prefer_a": "left"},
            )

    def test_two_figures_of_one_name_are_refused(self) -> None:
        from simple_agents.evaluation import paired_results

        pairs, verdicts = band_pairs()
        figure = paired_figure(
            pairs,
            verdicts,
            name="w",
            definition="d",
            numerator=lambda p, v: 1,
            denominator=lambda p, v: 1,
            resamples=200,
        )
        with pytest.raises(ConfigurationError, match="two figures named"):
            paired_results(
                pairs,
                verdicts,
                figures=[figure, figure],
                eval_id="s",
                blind=False,
                decided_by="human",
            )

    def test_the_report_reads_as_a_session(self, tmp_path) -> None:
        _, _, results = self._session(tmp_path)
        text = results.report()
        assert text.splitlines()[0] == (
            "40 judged pair(s) over 40 unit(s), high_band v low_band, decided by human blind"
        )
        assert "win_rate" in text

    def test_a_file_written_before_the_section_says_it_carries_none(self, tmp_path) -> None:
        import json

        _, _, results = self._session(tmp_path)
        raw = results.to_json()
        raw["eval_format_version"] = "0.31"
        del raw["pairs"]
        path = tmp_path / "old.json"
        path.write_text(json.dumps(raw))

        back = EvalResults.read(path)

        assert back.carries("pairs") is False and back.pairs == ()
