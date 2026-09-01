"""What an evaluation measured, attached to the steps, and the findings over it.

Every finding here reads the results file: what it covers, what it leaves out, and where
a figure stands over too few examples to mean anything. The families over the code, the
brief and the runs are in `findings.py`, which calls `_measure_findings` last.
"""

from __future__ import annotations

from typing import Any

from .words import _rate


def _measure_one(node: dict[str, Any], held: dict[str, Any], coverage: dict[str, Any]) -> None:
    """Give one step its figures, and record what its coverage says."""
    figures = held.get(node["id"])
    node["measured"] = figures
    if figures is None:
        return
    if figures["reached"]:
        coverage["measured"].append(node["id"])
    else:
        coverage["never_reached"].append(node["id"])
    if figures["accuracy"] or figures["metrics"]:
        coverage["scored"].append(node["id"])


def _attach_measurements(
    pipelines: list[dict[str, Any]], measured: dict[str, Any] | None
) -> dict[str, Any]:
    """Give each step the figures the evaluation holds for it, and say what it never reached.

    The evaluation names steps by the same ids the manifest does, so the join is exact where
    the shape it measured is the shape in the code. Where the shape moved, a step the
    evaluation knows and the code does not is named rather than dropped.
    """
    coverage: dict[str, Any] = {
        "measured": [],
        "never_reached": [],
        "unknown_here": [],
        "scored": [],
        "built_here": 0,
        "unmeasured_pipelines": [],
    }
    for pipeline in pipelines:
        pipeline["measured_here"] = bool(
            measured and measured.get("fingerprint") == pipeline["fingerprint"]
        )
    if not measured or not measured.get("nodes"):
        for pipeline in pipelines:
            for node in pipeline["nodes"]:
                node["measured"] = None
        return coverage
    held = measured["nodes"]
    for pipeline in pipelines:
        if not pipeline["measured_here"]:
            coverage["unmeasured_pipelines"].append(pipeline["name"])
        else:
            coverage["built_here"] += sum(1 for n in pipeline["nodes"] if not n["planned"])
        for node in pipeline["nodes"]:
            _measure_one(node, held, coverage)
    coverage["unknown_here"] = sorted(
        set(held) - set(coverage["measured"]) - set(coverage["never_reached"])
    )
    return coverage


def _measured(data: dict[str, Any]) -> dict[str, Any] | None:
    """The evaluation the project reports, where it has one worth saying anything about."""
    measured = data.get("measured")
    return measured if measured and measured.get("path") else None


def _about_the_results_file(data: dict[str, Any]) -> list[dict[str, Any]]:
    """What could not be read, or was read at a format this library no longer writes."""
    measured = data.get("measured")
    if not measured:
        return []
    return [
        {
            "severity": "info",
            "head": "About the results file.",
            "body": problem,
            "target": {"section": "measure"},
        }
        for problem in measured.get("problems", [])
    ]


def _measured_another_shape(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The evaluation scored a graph the code no longer has."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    shapes = {p["fingerprint"] for p in declared}
    if measured.get("fingerprint") and declared and measured["fingerprint"] not in shapes:
        found.append(
            {
                "severity": "attention",
                "head": "The evaluation measured a shape the code no longer has.",
                "body": f"{measured['path']} was scored over a different graph. Its figures "
                f"describe a system that has since changed. Re-run it to measure what "
                f"is here now.",
                "target": {"section": "measure"},
            }
        )
    return found


def _reports_an_older_file(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The brief names one results file and a newer one sits beside it."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    newest = next((row for row in measured.get("history", [])), None)
    if newest is not None and not newest["reported"]:
        found.append(
            {
                "severity": "attention",
                "head": "The evaluation this project reports is not the most recent one.",
                "body": f"The brief names {measured['path']}, and every check reads it. "
                f"{newest['file']} is newer. Either the newer one is the real result and "
                f"the brief should name it, or it was a side experiment.",
                "target": {"section": "measure"},
            }
        )
    return found


def _steps_the_evaluation_never_reached(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps every rollout skipped, so nothing measured describes them."""
    if _measured(data) is None:
        return []
    found: list[dict[str, Any]] = []
    coverage = data.get("coverage") or {}
    unreached = coverage.get("never_reached") or []
    if unreached:
        found.append(
            {
                "severity": "note",
                "head": (
                    f"{unreached[0]}: unreached by the evaluation."
                    if len(unreached) == 1
                    else f"{len(unreached)} steps unreached by the evaluation."
                ),
                "body": "Unmeasured."
                if len(unreached) == 1
                else ", ".join(unreached[:4])
                + (f", and {len(unreached) - 4} more" if len(unreached) > 4 else "")
                + ". Unmeasured.",
                "target": {"section": "measure"},
            }
        )
    return found


def _steps_the_evaluation_does_not_hold(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Steps in the pipeline it measured that carry no figure of their own."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    missing = [
        n["id"]
        for p in declared
        if p["measured_here"]
        for n in p["nodes"]
        if n.get("measured") is None and not n["planned"]
    ]
    if missing and measured.get("nodes"):
        found.append(
            {
                "severity": "note",
                "head": (
                    "One step is in the code and not in the evaluation."
                    if len(missing) == 1
                    else f"{len(missing)} steps are in the code and not in the evaluation."
                ),
                "body": ", ".join(missing[:4])
                + (f", and {len(missing) - 4} more" if len(missing) > 4 else "")
                + f". {measured['path']} carries no figure for them.",
                "target": {"section": "measure"},
            }
        )
    return found


def _pipelines_never_measured(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pipelines the reported evaluation did not measure at all."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    coverage = data.get("coverage") or {}
    never = coverage.get("unmeasured_pipelines") or []
    if never and measured.get("nodes"):
        found.append(
            {
                "severity": "note",
                "head": (
                    f"{never[0]}: unmeasured."
                    if len(never) == 1
                    else f"{len(never)} pipelines unmeasured."
                ),
                "body": (
                    f"{measured['path']} measured a different pipeline."
                    if len(never) == 1
                    else ", ".join(never) + f". {measured['path']} measured a different pipeline."
                ),
                "target": {"pipeline": never[0]},
            }
        )
    return found


def _figures_over_less_than_the_split(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A figure whose denominator shrank, and one that has no denominator at all."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    leaking = [m for m in measured["metrics"] if m["left_out"]]
    if leaking:
        one = leaking[0]
        causes = ", ".join(
            f"{count} {cause.replace('_', ' ')}" for cause, count in one["left_out"].items()
        )
        found.append(
            {
                "severity": "note",
                "head": f"{one['name']} is over fewer rollouts than the split has.",
                "body": f"{causes} left out. The figure is {_rate(one['point'], one['unit'])} over "
                f"{one['rollouts']}"
                + (
                    f", and {_rate(one['including_left_out'], one['unit'])} counting them as they "
                    f"scored."
                    if one["including_left_out"] is not None
                    else "."
                ),
                "target": {"section": "measure"},
            }
        )
    undefined = [m for m in measured["metrics"] + measured["criteria"] if m["reason"]]
    if undefined:
        found.append(
            {
                "severity": "info",
                "head": (
                    "One figure has no denominator."
                    if len(undefined) == 1
                    else f"{len(undefined)} figures have no denominator."
                ),
                "body": "; ".join(f"{m['name']}: {m['reason']}" for m in undefined[:2]),
                "target": {"section": "measure"},
            }
        )
    return found


def _answers_the_route_never_read(data: dict[str, Any]) -> list[dict[str, Any]]:
    """A step whose questions were all answered and whose branches were never taken."""
    measured = _measured(data)
    if measured is None:
        return []
    found: list[dict[str, Any]] = []
    declared = [p for p in data["pipelines"] if p["origin"] == "declared"]
    misread = [
        (p["name"], n)
        for p in declared
        for n in p["nodes"]
        if n.get("measured")
        and n["measured"]["consultations"]
        and n["measured"]["consultation_misreadings"] >= n["measured"]["consultations"]
    ]
    if misread:
        names = ", ".join(n["id"] for _, n in misread)
        found.append(
            {
                "severity": "attention",
                "head": "A question was asked and the answer was never read.",
                "body": f"{names}: every answer came back, and the rule that reads which option "
                f"was chosen matched none of them. The branches behind that question "
                f"were never taken.",
                "target": {"pipeline": misread[0][0], "node": misread[0][1]["id"]},
            }
        )
    return found


def _measure_findings(data: dict[str, Any], found: list[dict[str, Any]]) -> None:
    """What an evaluation says that a builder has to see, in the builder's words."""
    for family in (
        _about_the_results_file,
        _measured_another_shape,
        _reports_an_older_file,
        _steps_the_evaluation_never_reached,
        _steps_the_evaluation_does_not_hold,
        _pipelines_never_measured,
        _figures_over_less_than_the_split,
        _answers_the_route_never_read,
    ):
        found.extend(family(data))
