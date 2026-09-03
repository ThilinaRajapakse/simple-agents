"""What a run's record says about its money, its waiting, and whether it is alive.

Three subjects that dogfood #5's one Gemini evaluation produced, and one that fell out of the
third. Each is a run's own record failing to say something true about it (`P3-50`):

- an evaluation that cost $5.5024 reported `null` on every surface that read it, and `$0` on
  one, because the total is unknown wherever one call is and nothing carried the floor;
- 54 calls each climbed a 31-second retry ladder against a monthly spending cap, 28 minutes in
  total, because the message saying the allowance would not clear was read by nothing;
- 13 killed runs read as still executing, and will forever, because a manifest is written at
  the start and rewritten at the end and a killed process never reaches the end;
- and a run recorded nothing about what it was given, so a run that died inside its first node
  could not be run again without the caller remembering.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from pydantic import BaseModel

from simple_agents import (
    Budget,
    Deterministic,
    LLMNode,
    Pipeline,
    Prompt,
    Redaction,
    RunEnvelope,
    runs,
)
from simple_agents.adapters._http import HTTPBackend, Retry, _is_spent_quota
from simple_agents.records.cassette import Cassette
from simple_agents.cost import DEVICE_SECONDS, Cost, DeviceBasis, PriceBasis, total_cost
from simple_agents.envelope import ABANDONED, LIVENESS_UNKNOWN, RUNNING
from simple_agents.errors import CallerFacingError, ConfigurationError, Suspend
from simple_agents.models import FakeModelClient, fake_response
from simple_agents.records.trajectory import read_trajectory, strip_payloads

PRICE = PriceBasis(
    currency="USD",
    input_uncached_per_mtok=1.00,
    input_cache_read_per_mtok=0.0,
    output_per_mtok=0.0,
    input_cache_write_per_mtok=0.0,
)

SPEND_CAP = json.loads(
    (Path(__file__).parent / "fixtures/wire/gemini/error_spend_cap.json").read_text()
)

PREPAID_SPENT = json.loads(
    (Path(__file__).parent / "fixtures/wire/gemini/error_prepaid_spent.json").read_text()
)


def call(*, priced: bool = True) -> dict[str, object]:
    """One `model_call` record, priced at 1.00 USD or reporting no input count."""
    tokens: dict[str, object] = {
        "input_uncached": 1_000_000,
        "input_cache_read": 0,
        "output": 0,
        "input_cache_write": 0,
    }
    if not priced:
        tokens["input_uncached"] = {
            "type": "unknown",
            "reason": "the call raised before the backend returned a response",
        }
    return {"record_type": "model_call", "record_id": "r", "tokens": tokens}


class Answer(BaseModel):
    text: str


def double(inputs, ctx):
    return {"n": inputs["n"] * 2}


class TestTheFloorUnderATotalThatCouldNotBeDerived:
    """`totals.cost.value` is `null` where one call was unmeasured, and that stays true.

    Measured on `runs/eval_b7c83906be49` of dogfood #5: 27 rollouts, 994 model calls, 54 of
    them refused with a 429 that reported no token counts. Pricing each call individually
    comes to $5.5024 over the 940 that priced. The results file said `null` with
    `measured: null`, `simple-agents report` said `3.9744 USD` over the 16 rollouts where every
    call priced, and the view read `$0`.
    """

    def test_one_unpriced_call_still_leaves_the_total_unknown(self):
        """The rule the floor does not weaken: an unmeasured token count is not zero."""
        figure = total_cost([call(), call(), call(priced=False)], PRICE)

        assert figure.value is None

    def test_the_calls_that_priced_are_summed_beside_it(self):
        figure = total_cost([call(), call(), call(priced=False)], PRICE)

        assert figure.measured == pytest.approx(2.0)
        assert (figure.priced_calls, figure.unpriced_calls) == (2, 1)

    def test_a_figure_with_nothing_priced_reports_no_floor(self):
        """`measured` absent and `measured` of zero are different statements."""
        figure = total_cost([call(priced=False), call(priced=False)], PRICE)

        assert figure.measured is None
        assert figure.unpriced_calls == 2

    def test_a_run_that_made_no_call_reports_no_floor_either(self):
        assert total_cost([], PRICE).measured is None

    def test_a_call_less_run_reports_the_unit_a_call_would_have(self):
        """676 runs of dogfood #5 reported `0.0` with no unit beside it.

        Device time is not a currency, so `currencies_in` excludes it, and the zero a run with
        no model call reports had nothing to name itself in while a run with one said
        `device_seconds`.
        """
        empty = total_cost([], DeviceBasis(device="RTX-3090"))

        assert (empty.value, empty.currency) == (0.0, DEVICE_SECONDS)

    def test_a_fully_priced_figure_is_its_own_floor(self):
        figure = total_cost([call(), call()], PRICE)

        assert figure.value == pytest.approx(2.0)
        assert figure.measured == pytest.approx(2.0)

    def test_two_currencies_add_to_no_total_and_no_floor(self):
        """Device time is what a run used and money is what it was charged."""
        mixed = Cost(0.4, "device_seconds", "device", measured=0.4, priced_calls=1).plus(
            Cost(0.01, "USD", "price", measured=0.01, priced_calls=1)
        )

        assert mixed.value is None
        assert mixed.measured is None
        assert mixed.priced_calls == 2

    def test_describe_says_which_figure_is_which(self):
        figure = total_cost([call(), call(priced=False)], PRICE)

        described = figure.describe()
        assert described.startswith("at least 1.000000 USD")
        assert "1 of 2 call(s) could not be priced" in described

    def test_a_record_round_trips(self):
        figure = total_cost([call(), call(priced=False)], PRICE)

        assert Cost.from_record(figure.to_record()) == figure

    def test_a_record_written_before_the_floor_existed_reads_back(self):
        """Every manifest dogfood #5 wrote carries the five old keys and none of the three."""
        old = {"value": None, "currency": "USD", "basis": "price", "reason": "..."}

        figure = Cost.from_record(old)

        assert figure.measured is None
        assert (figure.priced_calls, figure.unpriced_calls) == (0, 0)

    def test_a_hand_built_figure_carries_its_value_as_its_floor(self):
        """A `Cost` built without one is its own floor, so a sum over such figures has one."""
        summed = Cost(1.0, "USD", "price").plus(Cost(2.0, "USD", "price"))

        assert summed.measured == pytest.approx(3.0)

    def test_the_manifest_carries_all_eight_keys(self, tmp_path):
        Pipeline([Deterministic(double, node_id="double")]).run(
            {"n": 21}, envelope=RunEnvelope(run_dir=tmp_path)
        )

        manifest = json.loads(next(tmp_path.rglob("manifest.json")).read_text())
        assert set(manifest["totals"]["cost"]) == {
            "value",
            "currency",
            "basis",
            "is_upper_bound",
            "reason",
            "measured",
            "priced_calls",
            "unpriced_calls",
        }


class TestARefusalThatRetryingCannotClear:
    """A 429 whose allowance resets monthly is not a 429 the backoff ladder is for.

    Measured on 2026-08-24: every one of the 54 refusals waited exactly 31,000 ms, which is
    the bare 1+2+4+8+16 ladder, so no `Retry-After` was present on any of them. Gemini
    publishes no rate-limit headers at all, so the message was what said which kind it was.
    """

    def backend(
        self,
        status: int,
        body: dict,
        *,
        headers: dict | None = None,
        publishes_allowance: bool = True,
        **retry,
    ):
        calls = {"n": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(status, json=body, headers=headers or {})

        client = httpx.Client(transport=httpx.MockTransport(handle), base_url="https://backend/v1")
        made = HTTPBackend(
            base_url="https://backend/v1",
            client=client,
            retry=Retry(**retry),
            publishes_allowance=publishes_allowance,
        )
        slept: list[float] = []
        made.sleep = slept.append
        return made, calls, slept

    def test_the_recorded_refusal_is_recognised(self):
        """The body is what dogfood #5's trajectory recorded, verbatim."""
        assert _is_spent_quota(SPEND_CAP["response"]["error"]["message"])

    def test_it_stops_the_run_on_the_first_refusal(self):
        backend, calls, slept = self.backend(429, SPEND_CAP["response"])

        with pytest.raises(Suspend):
            backend.post_json("/chat", {})

        assert calls["n"] == 1
        assert slept == [], "the ladder was climbed against an allowance it cannot clear"

    def test_the_stop_carries_the_backend_s_own_message(self):
        backend, _, _ = self.backend(429, SPEND_CAP["response"])

        with pytest.raises(Suspend) as stop:
            backend.post_json("/chat", {})

        assert "monthly spending cap" in stop.value.waiting_for
        # The backend said the cap was reached and not when it lifts, and a guessed date would
        # refuse a resume that would have worked.
        assert stop.value.resume_not_before is None

    def test_a_depleted_prepaid_balance_is_recognised_too(self):
        """Dogfood #6 retried this one six times on each of 150 items, three times over.

        The phrase was not in `QUOTA_PHRASES`, so `P3-50`'s stop never fired.
        """
        assert _is_spent_quota(PREPAID_SPENT["response"]["error"]["message"])

    def test_it_stops_the_run_rather_than_retrying(self):
        backend, calls, slept = self.backend(429, PREPAID_SPENT["response"])

        with pytest.raises(Suspend) as stop:
            backend.post_json("/chat", {})

        assert (calls["n"], slept) == (1, [])
        assert "prepayment credits are depleted" in stop.value.waiting_for

    def test_a_wording_the_library_has_not_met_is_named_by_the_project(self):
        """`Retry(spent_quota_phrases=...)` adds to the shipped phrases rather than replacing
        them, so a project that names one does not lose the stop on the others."""
        body = {"error": {"message": "The account balance is too low to serve requests."}}

        climbed, calls, slept = self.backend(429, body, max_attempts=3)
        with pytest.raises(CallerFacingError):
            climbed.post_json("/chat", {})
        assert calls["n"] == 3

        stopped, calls, slept = self.backend(
            429, body, spent_quota_phrases=("account balance is too low",)
        )
        with pytest.raises(Suspend):
            stopped.post_json("/chat", {})
        assert (calls["n"], slept) == (1, [])

        shipped, calls, _ = self.backend(
            429, SPEND_CAP["response"], spent_quota_phrases=("account balance is too low",)
        )
        with pytest.raises(Suspend):
            shipped.post_json("/chat", {})
        assert calls["n"] == 1

    def test_the_advice_names_a_paced_client_where_the_backend_publishes_an_allowance(self):
        backend, _, _ = self.backend(
            429, {"error": {"message": "rate limit exceeded"}}, max_attempts=2
        )

        with pytest.raises(CallerFacingError) as refusal:
            backend.post_json("/chat", {})

        assert "PacedClient(client)" in str(refusal.value)

    def test_the_advice_names_fewer_calls_where_the_backend_publishes_none(self):
        """Dogfood #6 put a PacedClient in front of Gemini because this message said to, and
        Gemini reports no allowance on any response for it to read."""
        backend, _, _ = self.backend(
            429,
            {"error": {"message": "rate limit exceeded"}},
            max_attempts=2,
            publishes_allowance=False,
        )

        with pytest.raises(CallerFacingError) as refusal:
            backend.post_json("/chat", {})

        assert "publishes no allowance" in str(refusal.value)
        assert "EvalSuite.run(concurrency=...)" in str(refusal.value)

    def test_one_phrase_written_as_a_bare_string_is_refused(self):
        """It would read as a phrase per character, and every 429 would stop the run."""
        with pytest.raises(ValueError) as refusal:
            Retry(spent_quota_phrases="account balance is too low")

        assert "one string" in str(refusal.value)

    def test_a_per_minute_refusal_still_climbs_the_ladder(self):
        backend, calls, slept = self.backend(
            429, {"error": {"message": "rate limit exceeded"}}, max_attempts=3
        )

        with pytest.raises(CallerFacingError):
            backend.post_json("/chat", {})

        assert calls["n"] == 3
        assert slept == [1.0, 2.0]

    def test_a_named_interval_is_capped_at_the_backoff_ceiling(self):
        """A budget is checked between steps, so nothing interrupts a wait inside a call."""
        backend, _, slept = self.backend(
            429,
            {"error": {"message": "slow down"}},
            headers={"Retry-After": "3600"},
            max_attempts=2,
            max_backoff_s=60.0,
        )

        with pytest.raises(CallerFacingError):
            backend.post_json("/chat", {})

        assert slept == [60.0]

    def test_a_named_interval_shorter_than_the_backoff_still_wins(self):
        backend, _, slept = self.backend(
            429,
            {"error": {"message": "slow down"}},
            headers={"Retry-After": "2"},
            max_attempts=3,
            initial_backoff_s=10.0,
        )

        with pytest.raises(CallerFacingError):
            backend.post_json("/chat", {})

        assert slept == [2.0, 2.0]


class TestWhetherARunWithNoOutcomeIsStillGoing:
    """13 of dogfood #5's 2,393 top-level runs carry `outcome: null` and always will.

    Their processes were killed. The manifest is written when a run starts and rewritten when
    it ends, so a process that died between the two leaves the start copy. All 13 declared a
    `max_wall_clock_ms`, of 3,600,000 or 900,000, so their own bound dates every one of them.
    """

    def handle(self, tmp_path, manifest: dict, records: list[dict] | None = None):
        directory = tmp_path / "runs" / "run_1"
        directory.mkdir(parents=True)
        (directory / "manifest.json").write_text(json.dumps(manifest))
        if records is not None:
            (directory / "trajectory.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in records)
            )
        return runs(tmp_path / "runs")[0]

    def ago(self, **kwargs) -> str:
        moment = datetime.now(timezone.utc) - timedelta(**kwargs)
        return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def test_a_run_inside_its_bound_reads_as_running_even_though_it_was_killed(self, tmp_path):
        """Measured live: a run killed 30 seconds into an hour-long budget reads `running`.

        Nothing on disk distinguishes it from one still working, and the bound is what the run
        said about itself. This is the limit of the reading rather than a defect in it.
        """
        handle = self.handle(
            tmp_path,
            {
                "outcome": None,
                "started_at": self.ago(seconds=30),
                "budget": {"max_wall_clock_ms": 3_600_000},
            },
        )

        assert handle.liveness == RUNNING

    def test_the_grace_is_a_fixed_margin_and_not_a_share_of_the_budget(self, tmp_path):
        """A run declaring four hours would otherwise get sixteen hours of slack.

        What a run can overshoot its own bound by is one call, which the client's timeout
        bounds, so the margin does not scale with what the run declared.
        """
        handle = self.handle(
            tmp_path,
            {
                "outcome": None,
                "started_at": self.ago(hours=6),
                "budget": {"max_wall_clock_ms": 4 * 3_600_000},
            },
        )

        assert handle.liveness == ABANDONED

    def test_a_run_far_past_the_wall_clock_it_declared_cannot_still_be_running(self, tmp_path):
        handle = self.handle(
            tmp_path,
            {
                "outcome": None,
                "started_at": self.ago(days=4),
                "budget": {"max_wall_clock_ms": 3_600_000},
            },
        )

        assert handle.liveness == ABANDONED

    def test_a_run_inside_its_own_bound_is_still_running(self, tmp_path):
        handle = self.handle(
            tmp_path,
            {
                "outcome": None,
                "started_at": self.ago(seconds=30),
                "budget": {"max_wall_clock_ms": 3_600_000},
            },
        )

        assert handle.liveness == RUNNING

    def test_a_run_that_declared_no_bound_is_read_from_its_last_record(self, tmp_path):
        handle = self.handle(
            tmp_path,
            {"outcome": None, "started_at": self.ago(days=2), "budget": {}},
            [{"record_type": "run_start", "started_at": self.ago(days=2), "ended_at": None}],
        )

        assert handle.liveness == ABANDONED
        assert handle.last_activity_at is not None

    def test_a_run_that_declared_no_bound_and_wrote_recently_is_still_running(self, tmp_path):
        handle = self.handle(
            tmp_path,
            {"outcome": None, "started_at": self.ago(days=2), "budget": {}},
            [{"record_type": "model_call", "started_at": self.ago(seconds=5)}],
        )

        assert handle.liveness == RUNNING

    def test_a_manifest_whose_start_cannot_be_read_is_still_dated_by_its_records(self, tmp_path):
        """The trajectory dates itself, so the manifest does not have to be readable."""
        handle = self.handle(
            tmp_path,
            {"outcome": None, "started_at": "not a timestamp", "budget": {}},
            [{"record_type": "model_call", "started_at": self.ago(days=2)}],
        )

        assert handle.liveness == ABANDONED

    def test_a_run_with_no_bound_and_no_records_settles_nothing(self, tmp_path):
        handle = self.handle(
            tmp_path, {"outcome": None, "started_at": self.ago(days=2), "budget": {}}, []
        )

        assert handle.liveness == LIVENESS_UNKNOWN
        assert handle.last_activity_at is None

    def test_a_run_that_recorded_an_outcome_is_outcome_s_question(self, tmp_path):
        """Exactly one of the two is set on any run."""
        handle = self.handle(
            tmp_path, {"outcome": "completed", "started_at": self.ago(days=4), "budget": {}}
        )

        assert handle.liveness is None
        assert handle.outcome == "completed"

    def test_a_real_run_reports_running_for_neither(self, tmp_path):
        Pipeline([Deterministic(double, node_id="double")]).run(
            {"n": 21}, envelope=RunEnvelope(run_dir=tmp_path)
        )

        [handle] = runs(tmp_path, nested=True)
        assert (handle.outcome, handle.liveness) == ("completed", None)


class TestTheReadersThatCountAnAbandonedRunApart:
    """Three surfaces said `still running` about a run that will never run again.

    Found by running the code rather than by the tests: the conformance coverage sentence has
    two counting sites and only the one for a scope where nothing finished was changed first.
    """

    def a_project_with_one_of_each(self, tmp_path):
        """One run that completed, and one whose process ended long past its own bound."""
        done = tmp_path / "runs" / "done"
        gone = tmp_path / "runs" / "gone"
        for directory, manifest in (
            (
                done,
                {
                    "outcome": "completed",
                    "role": "agent",
                    "started_at": "2026-08-01T00:00:00.000Z",
                    "behaviour_fingerprint": "bf_1",
                    "counts": {"records": 1},
                    "budget": {"max_wall_clock_ms": 60_000},
                    "unfinished": {},
                },
            ),
            (
                gone,
                {
                    "outcome": None,
                    "role": "agent",
                    "started_at": "2026-08-01T00:00:00.000Z",
                    "behaviour_fingerprint": "bf_1",
                    "budget": {"max_wall_clock_ms": 60_000},
                },
            ),
        ):
            directory.mkdir(parents=True)
            (directory / "manifest.json").write_text(json.dumps(manifest))
            # `report` reads the trajectory beside the manifest, so a run without one is
            # unread rather than counted.
            (directory / "trajectory.jsonl").write_text("")
        return tmp_path

    def test_the_conformance_coverage_sentence_counts_it_apart(self, tmp_path):
        from simple_agents.conformance.spend import unfinished_across

        read = unfinished_across(self.a_project_with_one_of_each(tmp_path))

        assert (read.still_running, read.abandoned) == (0, 1)
        assert "nothing will ever say what they produced" in read.covered()

    def test_the_report_outcome_line_names_it(self, tmp_path):
        from simple_agents.cli.reporting import report_over_runs

        read = report_over_runs(self.a_project_with_one_of_each(tmp_path) / "runs")

        assert read.outcomes.get("abandoned") == 1
        assert "still running" not in read.outcomes


class TestWhatARunWasGiven:
    """A trajectory said what happened and never what the run was asked to do.

    `node_execution` records land when their node finishes, so a run killed inside its first
    node recorded its inputs nowhere. Three of dogfood #5's four such runs had made 29, 37 and
    27 model calls by then.
    """

    def run_in(self, tmp_path, inputs=None):
        Pipeline([Deterministic(double, node_id="double")]).run(
            inputs if inputs is not None else {"n": 21},
            envelope=RunEnvelope(run_dir=tmp_path),
        )
        return next(tmp_path.rglob("trajectory.jsonl"))

    def test_it_is_the_first_record_a_run_writes(self, tmp_path):
        records = list(read_trajectory(self.run_in(tmp_path)))

        assert [r["record_type"] for r in records] == ["run_start", "node_execution"]
        assert records[0]["sequence"] == 1

    def test_it_carries_the_inputs_and_the_seed(self, tmp_path):
        [start, _] = list(read_trajectory(self.run_in(tmp_path)))

        assert start["inputs"] == {"n": 21}
        assert isinstance(start["seed"], int)

    def test_it_hangs_off_no_node(self, tmp_path):
        """It belongs to the run, so it is a root record (`docs/trajectory-format.md` §1.2)."""
        [start, _] = list(read_trajectory(self.run_in(tmp_path)))

        assert start["parent_id"] is None
        assert start["ended_at"] is None

    def test_the_manifest_counts_it(self, tmp_path):
        self.run_in(tmp_path)

        counts = json.loads(next(tmp_path.rglob("manifest.json")).read_text())["counts"]
        assert counts["run_start"] == 1

    def test_a_secret_in_the_inputs_is_redacted_out_of_it(self, tmp_path, monkeypatch):
        """It puts a payload where the run's shape used to be alone, so this is what pays for it.

        Every trajectory record goes through the `Redactor` on its way to disk, so the new
        record needed nothing of its own. This is the check that it is on that path.
        """
        monkeypatch.setenv("A_TOKEN_FOR_THIS_TEST", "sk-live-abcdef123456789")
        Pipeline([Deterministic(double, node_id="double")]).run(
            {"n": 21, "token": "sk-live-abcdef123456789"},
            envelope=RunEnvelope(
                run_dir=tmp_path, redaction=Redaction(secret_env=["A_TOKEN_FOR_THIS_TEST"])
            ),
        )

        [start, _] = list(read_trajectory(next(tmp_path.rglob("trajectory.jsonl"))))
        assert start["inputs"]["token"] == "[redacted:env:A_TOKEN_FOR_THIS_TEST]"
        assert start["redactions"] == ["inputs.token"]
        written = "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())
        assert "sk-live-abcdef123456789" not in written

    def test_its_payload_is_dropped_with_every_other(self, tmp_path):
        """`inputs` is a payload, so what a project does not keep it does not keep here."""
        path = self.run_in(tmp_path)
        strip_payloads(path, reason="sampling")

        [start, _] = list(read_trajectory(path))
        assert start["inputs"] == {"type": "not_recorded", "reason": "sampling"}
        assert start["omissions"] == ["inputs"]


class TestRunningAgainWhatADeadRunWasGiven:
    """`rerun` reads the dead run's own record rather than asking the caller to remember."""

    def dead_run(self, tmp_path):
        """A run that raised inside its only node, leaving a `run_start` behind it."""
        state = {"first": True}

        def explode_once(inputs, ctx):
            if state["first"]:
                state["first"] = False
                raise RuntimeError("the process died here")
            return {"n": inputs["n"] * 2}

        pipeline = Pipeline([Deterministic(explode_once, node_id="work")])
        with pytest.raises(RuntimeError):
            pipeline.run({"n": 21}, envelope=RunEnvelope(run_dir=tmp_path / "first"))
        return pipeline, next((tmp_path / "first").rglob("trajectory.jsonl")).parent

    def test_it_runs_what_the_dead_run_was_given(self, tmp_path):
        pipeline, dead = self.dead_run(tmp_path)

        result = pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        assert result.output == {"n": 42}

    def test_the_result_is_a_new_run(self, tmp_path):
        pipeline, dead = self.dead_run(tmp_path)

        result = pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        assert result.run_id != dead.name
        assert (dead / "manifest.json").exists(), "the dead run stays on disk as it was"

    def test_a_run_whose_payloads_were_not_kept_is_refused(self, tmp_path):
        pipeline, dead = self.dead_run(tmp_path)
        strip_payloads(dead / "trajectory.jsonl", reason="sampling")

        with pytest.raises(ConfigurationError) as refusal:
            pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        assert "kept no payloads" in str(refusal.value)
        assert "Cassette.update" in str(refusal.value), "the refusal names what to do instead"

    def test_a_run_written_before_the_record_existed_is_refused(self, tmp_path):
        pipeline, dead = self.dead_run(tmp_path)
        kept = [
            line
            for line in (dead / "trajectory.jsonl").read_text().splitlines()
            if json.loads(line)["record_type"] != "run_start"
        ]
        (dead / "trajectory.jsonl").write_text("".join(line + "\n" for line in kept))

        with pytest.raises(ConfigurationError) as refusal:
            pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        assert "0.29" in str(refusal.value)

    def test_the_calls_the_dead_run_paid_for_are_served_from_its_own_file(self, tmp_path):
        """The point of it: a node that finished re-executes and its calls are not re-bought.

        The rerun's client is scripted with nothing, so a live call would raise. It made none:
        the cassette answered, and only the node that never finished cost anything.
        """
        state = {"first": True}

        def then_explode(inputs, ctx):
            if state["first"]:
                state["first"] = False
                raise RuntimeError("the process died here")
            return {"done": True}

        pipeline = Pipeline(
            [
                LLMNode(
                    lambda inputs, ctx: Prompt.user("say something"),
                    output_schema=Answer,
                    node_id="ask",
                    allow_unknown=False,
                ),
                Deterministic(then_explode, node_id="after"),
            ],
            budget=Budget.unbounded(),
        )
        paid = FakeModelClient(responses=[fake_response(content='{"text": "hello"}')])
        with pytest.raises(RuntimeError):
            pipeline.run({}, envelope=RunEnvelope(run_dir=tmp_path / "first"), model=paid)
        dead = next((tmp_path / "first").rglob("trajectory.jsonl")).parent
        assert len(paid.requests) == 1

        empty = FakeModelClient(responses=[])
        result = pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"), model=empty)

        assert result.output == {"done": True}
        assert empty.requests == [], "the recorded call was bought a second time"
        cassette = json.loads((result.paths.root / "manifest.json").read_text())["cassette"]
        assert (cassette["hits"], cassette["misses"]) == (1, 0)

    def test_a_directory_that_is_not_a_run_is_refused_by_name(self, tmp_path):
        """Pointing it at the wrong path is the likeliest mistake, and it raised OSError."""
        pipeline, _ = self.dead_run(tmp_path)

        with pytest.raises(ConfigurationError) as refusal:
            pipeline.rerun(tmp_path / "nothing", envelope=RunEnvelope(run_dir=tmp_path / "x"))

        assert "is not a run this can read" in str(refusal.value)
        assert "run.path" in str(refusal.value), "the refusal names what to pass"

    def test_a_directory_holding_two_runs_continues_the_one_that_ran_last(self, tmp_path):
        """One directory used twice appends into one trajectory, so it holds two starts."""
        pipeline = Pipeline([Deterministic(double, node_id="double")])
        env = RunEnvelope(run_dir=tmp_path / "shared")
        pipeline.run({"n": 1}, envelope=env, run_id="shared")
        pipeline.run({"n": 99}, envelope=env, run_id="shared")
        directory = next((tmp_path / "shared").rglob("trajectory.jsonl")).parent

        result = pipeline.rerun(directory, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        assert result.output == {"n": 198}, "it continued the first run rather than the last"

    def test_a_seed_the_caller_named_overrides_the_dead_run_s(self, tmp_path):
        """`run` takes `seed=` too, so passing one raised for two values of one argument."""
        pipeline, dead = self.dead_run(tmp_path)

        result = pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"), seed=99)

        assert json.loads((result.paths.root / "manifest.json").read_text())["seed"] == 99

    def test_a_cassette_the_caller_named_is_left_alone(self, tmp_path):
        """The dead run's own recording is the default and not an override."""
        pipeline, dead = self.dead_run(tmp_path)
        named = tmp_path / "mine.jsonl"

        result = pipeline.rerun(
            dead,
            envelope=RunEnvelope(run_dir=tmp_path / "again", cassette=Cassette.update(named)),
        )

        cassette = json.loads((result.paths.root / "manifest.json").read_text())["cassette"]
        assert cassette["path"] == str(named)

    def test_the_dead_run_s_own_recording_is_the_default(self, tmp_path):
        pipeline, dead = self.dead_run(tmp_path)

        result = pipeline.rerun(dead, envelope=RunEnvelope(run_dir=tmp_path / "again"))

        cassette = json.loads((result.paths.root / "manifest.json").read_text())["cassette"]
        assert cassette["path"] == str(dead / "cassette.jsonl")
        assert cassette["mode"] == "update"
