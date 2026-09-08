"""What the evaluation measured, read from the results file the project reports.

The page reads the same file the gates read: the one ``results`` names in the brief, or the
most recent under ``evals/results/`` where the brief names none. Every figure keeps its
interval, its denominator and what was left out of it, because a bare percentage on a page is
the failure FT-06 exists to stop.

Read as plain JSON rather than through :class:`~simple_agents.evaluation.results.EvalResults`,
so a results file written by an older version of the library still renders, with the version
it was written at shown beside it.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from ..evaluation.outcomes import Outcome

__all__ = ["read_evaluation"]


def _read(path: Path) -> dict[str, Any] | None:
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return held if isinstance(held, dict) else None


def _counted(numerator: Any, denominator: Any) -> Any:
    """The figure behind a metric with no interval, or ``None`` where it reports no value."""
    if numerator is None:
        return None
    if denominator is None:
        return float(numerator)
    return None if denominator == 0 else float(numerator) / float(denominator)


def _figure(name: str, record: dict[str, Any]) -> dict[str, Any]:
    """One measured figure, with everything needed to read it honestly."""
    interval = record.get("interval") or {}
    numerator, denominator = record.get("numerator"), record.get("denominator")
    return {
        "name": name,
        "definition": record.get("definition"),
        "population": record.get("population"),
        "unit": record.get("unit"),
        # A figure the project declared a count over the run has a number and no interval, so
        # its point comes from the totals instead. Reading it off the interval showed the
        # number as absent, which is the shape of a figure that measured nothing.
        "point": interval.get("point", None) if interval else _counted(numerator, denominator),
        "numerator": numerator,
        "denominator": denominator,
        "estimated": record.get("estimated", True),
        "low": interval.get("low"),
        "high": interval.get("high"),
        "method": interval.get("method"),
        "reason": record.get("reason"),
        "rollouts": record.get("rollouts"),
        "examples": record.get("examples"),
        "left_out": dict(record.get("left_out") or {}),
        "including_left_out": (record.get("including_left_out") or {}).get("point"),
    }


def _node_figures(node_id: str, record: dict[str, Any]) -> dict[str, Any]:
    reach = (record.get("reach") or {}).get("interval") or {}
    accuracy = record.get("accuracy") or None
    spend = record.get("tool_spend")
    # What this step's model calls cost across the rollouts, derived by the evaluation itself
    # against the basis its envelope declared. `null` where the runs recorded no basis.
    cost = record.get("cost") or {}
    return {
        "cost": cost.get("value"),
        "cost_currency": cost.get("currency"),
        "cost_basis": cost.get("basis"),
        "cost_is_upper_bound": bool(cost.get("is_upper_bound")),
        "cost_unknown_because": cost.get("reason"),
        # The floor under a total that could not be derived, and how many calls are missing
        # from it. A step whose every call priced carries the same figure as `cost`.
        "cost_measured": cost.get("measured"),
        "cost_unpriced_calls": cost.get("unpriced_calls") or 0,
        "resource_reads": dict(record.get("resource_reads") or {}),
        "resource_writes": dict(record.get("resource_writes") or {}),
        "node_id": node_id,
        "kind": record.get("node_kind"),
        "runs": record.get("runs", 0),
        "reached": record.get("reached", 0),
        "reach": reach.get("point"),
        "executions": record.get("executions", 0),
        "errors": record.get("errors", 0),
        "model_calls": record.get("model_calls", 0),
        "tool_calls": record.get("tool_calls", 0),
        "paid_tool_calls": record.get("paid_tool_calls", 0),
        "tool_spend": spend,
        "tool_spend_currency": record.get("tool_spend_currency"),
        "consultations": record.get("consultations", 0),
        "consultation_answered_by": dict(record.get("consultation_answered_by") or {}),
        "consultation_misreadings": record.get("consultation_misreadings", 0),
        "wall_clock_ms": record.get("wall_clock_ms", 0),
        "absent_outputs": record.get("absent_outputs", 0),
        "unfinished_executions": record.get("unfinished_executions", 0),
        "terminations": dict(record.get("terminations") or {}),
        "accuracy": _figure("accuracy", accuracy) if accuracy else None,
        "metrics": [
            _figure(name, figure) for name, figure in (record.get("metrics") or {}).items()
        ],
    }


def _headline(raw: dict[str, Any]) -> dict[str, Any] | None:
    """The first figure a reader should see: accuracy where there is one, else the first."""
    metrics = raw.get("metrics") or {}
    for name in ("accuracy", "graded_accuracy"):
        if name in metrics:
            return _figure(name, metrics[name])
    for name, record in metrics.items():
        return _figure(name, record)
    return None


def _outcomes(raw: dict[str, Any]) -> dict[str, int]:
    return dict(Counter(str(r.get("outcome") or "unrecorded") for r in raw.get("rollouts") or []))


def _is_right(outcome: str) -> bool:
    """Whether the library counts this outcome as a right answer.

    Read off ``Outcome.succeeded`` rather than listed here. A list written beside it drifts:
    this one held ``correct_absent`` and ``right_abstention``, and the outcomes are ``correct``
    and ``correct_abstention``, so every right report of absence counted as wrong on the
    agent's line and on the floor's. An outcome this version does not know is not right.
    """
    try:
        return Outcome(outcome).succeeded
    except ValueError:
        return False


def _floor(raw: dict[str, Any]) -> dict[str, Any] | None:
    """What an agent that did nothing got right, as counts.

    Counts rather than a rate: the interval around a floor is a bootstrap this does not run,
    and a rate with no interval is the figure FT-06 refuses.
    """
    entries = raw.get("baseline") or []
    if not entries:
        return None
    right = sum(1 for e in entries if _is_right(str(e.get("outcome") or "")))
    return {"right": right, "of": len(entries)}


def _rollout_counts(raw: dict[str, Any]) -> dict[str, int]:
    entries = raw.get("rollouts") or []
    return {
        "right": sum(1 for e in entries if _is_right(str(e.get("outcome") or ""))),
        "of": len(entries),
    }


def _went_wrong(raw: dict[str, Any], limit: int = 6) -> list[dict[str, Any]]:
    """The examples whose rollouts did not come out right, so a builder can look at one."""
    found: dict[str, dict[str, Any]] = {}
    for rollout in raw.get("rollouts") or []:
        outcome = str(rollout.get("outcome") or "")
        if _is_right(outcome):
            continue
        example_id = str(rollout.get("example_id") or "?")
        held = found.setdefault(
            example_id,
            {"example": example_id, "outcomes": {}, "trajectory": rollout.get("trajectory")},
        )
        held["outcomes"][outcome] = held["outcomes"].get(outcome, 0) + 1
    return sorted(found.values(), key=lambda e: -sum(e["outcomes"].values()))[:limit]


def _history(directory: Path, reported: Path | None) -> list[dict[str, Any]]:
    """Every results file on record, newest first, with its headline figure.

    Every file, with no cut: a sweep of a dozen arms on one night pushed a whole measurement
    off the page when the list was capped.
    """
    rows = []
    for path in directory.glob("*.json"):
        raw = _read(path)
        if raw is None:
            continue
        config = raw.get("config") or {}
        headline = _headline(raw)
        rows.append(
            {
                "file": path.name,
                "eval_id": raw.get("eval_id"),
                "created_at": raw.get("created_at"),
                "split": config.get("split"),
                "k": config.get("k"),
                "n": config.get("n"),
                "reported": reported is not None and path.resolve() == reported.resolve(),
                # A session of judged pairs is drawn head to head rather than on the trend.
                "kind": _kind(config),
                "headline": {
                    "name": headline["name"],
                    "point": headline["point"],
                    "unit": headline["unit"],
                    "low": headline["low"],
                    "high": headline["high"],
                    "definition": headline["definition"],
                }
                if headline
                else None,
                # What a trend needs to say whether two points are the same figure: the
                # behaviour the file measured, and the shape it measured it over.
                "behaviour": config.get("behaviour_fingerprint"),
                "shape": config.get("graph_fingerprint"),
                "slice": config.get("slice"),
                "cost": ((raw.get("totals") or {}).get("cost") or {}).get("value"),
                "currency": ((raw.get("totals") or {}).get("cost") or {}).get("currency"),
            }
        )
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows


def _clip(value: Any, limit: int = 160) -> str | None:
    """A value as short text, for a table cell; ``None`` stays ``None``.

    An encoded absence reads as the absence it is, with its reason, rather than as the
    object that carries it.
    """
    if value is None:
        return None
    if isinstance(value, dict) and value.get("type") == "unknown":
        value = f"absence: {value.get('reason') or 'no reason given'}"
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _run_name(trajectory: Any) -> str | None:
    """The bare directory name of a rollout, which is how a page names a run to walk."""
    if not trajectory:
        return None
    return str(trajectory).replace("\\", "/").rsplit("/", 2)[-2] if "/" in str(trajectory) else None


def _unmet_parts(verdict: dict[str, Any]) -> list[str]:
    """The criteria a rollout's answer did not meet, by id, whichever way a part is recorded."""
    unmet = []
    for name, part in (verdict.get("parts") or {}).items():
        met = part.get("met") if isinstance(part, dict) else part
        if met is False or met == 0:
            unmet.append(str(name))
    return unmet


def _criteria_words(parts: list[dict[str, Any]]) -> str | None:
    """A key with parts as words: the required conditions first, then the rest."""
    required = [c.get("text") for c in parts if c.get("required") and c.get("text")]
    rest = [c.get("text") for c in parts if not c.get("required") and c.get("text")]
    return _clip("; ".join([*required, *rest]))


def _tolerance_words(expected: dict[str, Any]) -> str:
    if expected.get("absolute") is not None:
        return f"{expected.get('value')} ±{expected['absolute']}"
    return f"{expected.get('value')} ±{100 * float(expected.get('relative') or 0):g}%"


_KEY_WORDS = {
    "unknown": lambda e: "An absence" + (f": {e['reason']}" if e.get("reason") else ""),
    "criteria": lambda e: _criteria_words(e.get("criteria") or []),
    "any_of": lambda e: _clip("One of: " + ", ".join(str(v) for v in e.get("values") or [])),
    "contains": lambda e: _clip("Holds: " + ", ".join(str(v) for v in e.get("values") or [])),
    "within_tolerance": _tolerance_words,
}
"""Each answer key's encoded form, as the words the grid shows for what an example expects."""


def _key_words(expected: Any) -> str | None:
    """An answer key in words, read off its encoded form: what the example expects."""
    if expected is None:
        return None
    if not isinstance(expected, dict):
        return _clip(expected)
    words = _KEY_WORDS.get(str(expected.get("type")))
    return words(expected) if words else _clip(expected)


def _expects(root: Path, raw: dict[str, Any]) -> dict[str, str]:
    """What each example expects, in words, from the example file beside the results.

    The results file records a single-valued label and no more, so a key with parts is
    read off ``evals/examples.jsonl`` where the project still has it. An example the file
    no longer holds, or a file that cannot be read, leaves the row's words to the record.
    """
    path = root / "evals" / "examples.jsonl"
    found: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return found
    wanted = set(raw.get("examples") or {})
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and str(entry.get("id")) in wanted:
            words = _key_words(entry.get("expected"))
            if words:
                found[str(entry["id"])] = words
    return found


def _browser(raw: dict[str, Any], expects: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Every example with its rollouts: what it expected, what came back, how each was sorted.

    The hub the page's drill-downs open into. Examples that came out wrong sort first.
    ``expects`` is the key in words per example, from the example file, where it is there.
    """
    examples = raw.get("examples") or {}
    expects = expects or {}
    held: dict[str, dict[str, Any]] = {}
    for rollout in raw.get("rollouts") or []:
        example_id = str(rollout.get("example_id") or "?")
        entry = examples.get(example_id) or {}
        row = held.setdefault(
            example_id,
            {
                "example": example_id,
                "split": entry.get("split"),
                "source": entry.get("source"),
                "label": _clip(entry.get("label")),
                "expects": expects.get(example_id),
                "expects_absence": bool(entry.get("expects_absence")),
                "rollouts": [],
                "right": 0,
                "of": 0,
            },
        )
        one = _rollout_row(rollout)
        row["rollouts"].append(one)
        row["of"] += 1
        row["right"] += 1 if _is_right(one["outcome"]) else 0
    return sorted(
        held.values(),
        key=lambda r: (r["right"] == r["of"], r["right"] / max(1, r["of"]), r["example"]),
    )


def _rollout_row(rollout: dict[str, Any]) -> dict[str, Any]:
    """One rollout as the browser shows it: how it was sorted, what it answered, its verdict."""
    verdict = rollout.get("verdict") or {}
    left_out = rollout.get("left_out") or {}
    error = rollout.get("error")
    return {
        "rollout": rollout.get("rollout"),
        "outcome": str(rollout.get("outcome") or "unrecorded"),
        "answer": _clip(rollout.get("answer")),
        "grade": verdict.get("grade"),
        "met": verdict.get("met"),
        "total": verdict.get("total"),
        "unmet": _unmet_parts(verdict),
        "unmet_required": list(verdict.get("unmet_required") or []),
        "left_out": sorted(left_out) if isinstance(left_out, dict) else list(left_out),
        "error": _clip(error.get("message") if isinstance(error, dict) else error),
        "run": _run_name(rollout.get("trajectory")),
    }


def _by_outcome(raw: dict[str, Any]) -> dict[str, list[str]]:
    """Which examples produced each outcome, so an outcome on the page opens its examples."""
    found: dict[str, set[str]] = {}
    for rollout in raw.get("rollouts") or []:
        found.setdefault(str(rollout.get("outcome") or "unrecorded"), set()).add(
            str(rollout.get("example_id") or "?")
        )
    return {name: sorted(ids) for name, ids in found.items()}


def _criteria_failed(raw: dict[str, Any]) -> dict[str, list[str]]:
    """Which examples had a rollout fall short of each criterion, by criterion id."""
    found: dict[str, set[str]] = {}
    for rollout in raw.get("rollouts") or []:
        for name in _unmet_parts(rollout.get("verdict") or {}):
            found.setdefault(name, set()).add(str(rollout.get("example_id") or "?"))
    return {name: sorted(ids) for name, ids in found.items()}


def _cost_per(raw: dict[str, Any]) -> dict[str, Any] | None:
    """What the evaluation spent per rollout and per example, beside its quality."""
    cost = (raw.get("totals") or {}).get("cost") or {}
    value = cost.get("value")
    rollouts = len(raw.get("rollouts") or [])
    examples = len({str(r.get("example_id")) for r in raw.get("rollouts") or []})
    if not isinstance(value, (int, float)) or not rollouts:
        return None
    return {
        "value": value,
        "currency": cost.get("currency"),
        "basis": cost.get("basis"),
        "per_rollout": value / rollouts,
        "per_example": value / examples if examples else None,
        "rollouts": rollouts,
        "examples": examples,
        "is_upper_bound": bool(cost.get("is_upper_bound")),
    }


def _groups(path: Path) -> dict[str, Any]:
    """Every figure over each cell of each key the evaluation can be grouped by.

    Read through :class:`EvalResults`, which computes the cells from the rollouts on file;
    a file outside the version window it reads carries no groups and says so.
    """
    from ..evaluation.results import EvalResults

    try:
        results = EvalResults.read(path)
    except Exception as exc:  # noqa: BLE001 - a file the reader refuses loses this section only
        return {"keys": {}, "problem": f"Grouped figures need a file this library reads: {exc}"}
    keys: dict[str, list[dict[str, Any]]] = {}
    for key in results.groupable()[:6]:
        try:
            cells = results.grouped(key)
            members = results.groups(key)
        except Exception:  # noqa: BLE001 - one key that cannot be grouped loses that key only
            continue
        rows = []
        for value, cell in list(cells.items())[:12]:
            figures = {
                name: _figure(name, metric.to_record()) for name, metric in cell.metrics.items()
            }
            headline = (
                figures.get("accuracy")
                or figures.get("graded_accuracy")
                or (next(iter(figures.values())) if figures else None)
            )
            rows.append(
                {
                    "value": str(value),
                    "examples": cell.examples,
                    "example_ids": sorted(str(x) for x in members.get(value, ())),
                    "headline": headline,
                    "figures": list(figures.values()),
                }
            )
        if len(rows) > 1:
            keys[key] = rows
    return {"keys": keys, "problem": None}


def _comparisons(root: Path) -> list[dict[str, Any]]:
    """Every written variant comparison under ``evals/variants/``, newest file first."""
    directory = root / "evals" / "variants"
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        raw = _read(path)
        if raw is None or "variants" not in raw:
            continue
        found.append(
            {
                "file": path.name,
                "format": raw.get("variant_format_version"),
                "baseline": {"eval_id": (raw.get("baseline") or {}).get("eval_id")},
                "variants": {
                    name: {
                        "eval_id": held.get("eval_id"),
                        "comparison": _comparison_for_the_page(held.get("comparison") or {}),
                        "cost": held.get("cost") or {},
                        "tool_spend": held.get("tool_spend") or {},
                    }
                    for name, held in (raw.get("variants") or {}).items()
                },
            }
        )
    return found[:6]


_DIFFERENCE_WORDS = {
    "graph_fingerprint": "the shape of the pipeline",
    "behaviour_fingerprint": "its behaviour (prompts, schemas, tools)",
    "baseline": "the do-nothing baseline",
    "model": "the model",
    "prompts": "a prompt",
}

_DERIVED_DIFFERENCES = ("graph_fingerprint", "behaviour_fingerprint")
"""Differences that follow from another one: a fingerprint moves because something in it did."""


def _difference_words(key: str) -> str:
    """One configuration difference named for the builder, where the key is the library's."""
    parts = key.split(".")
    if parts[0] == "tools" and len(parts) == 2:
        return f"the tool {parts[1]}"
    if parts[0] == "nodes" and len(parts) >= 3:
        node, rest = parts[1], parts[2:]
        if rest == ["tools"]:
            return f"the tools {node} can call"
        if rest == ["loop", "max_iterations"]:
            return f"how many times {node} may loop"
        if rest == ["model"]:
            return f"the model {node} calls"
        return f"{node}'s {' '.join(rest)}"
    for prefix, words in _DIFFERENCE_WORDS.items():
        if key == prefix or key.startswith(prefix + "."):
            return words
    return key


def _side(value: Any) -> str:
    """One side of a difference as words: what was declared, or that nothing was."""
    if value is None:
        return "none"
    if isinstance(value, dict):
        if "version" in value and "name" in value:
            return "declared"
        if "version" in value:
            return "declared"
        return json.dumps(value, ensure_ascii=False)[:40]
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)[:60] or "none"
    return str(value)[:40]


def _comparison_for_the_page(record: dict[str, Any]) -> dict[str, Any]:
    """A comparison record with its configuration differences named for the builder."""
    changed = record.get("changed") or {}
    rows = []
    for key, value in changed.items():
        pair = value if isinstance(value, list) and len(value) == 2 else [value, None]
        rows.append(
            {
                "key": key,
                "words": _difference_words(key),
                "before": _side(pair[0]),
                "after": _side(pair[1]),
                "derived": key in _DERIVED_DIFFERENCES,
            }
        )
    # A fingerprint moved because something named beside it did; it leads only where it is
    # the whole of what differed.
    rows.sort(key=lambda r: r["derived"])
    return {**record, "changed": rows}


def _ladders(directory: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Results files that are rungs of one pipeline, related through ``config.slice``.

    A rung's file names the pipeline it was cut from by ``graph_fingerprint``; the file
    that measured the whole pipeline is the top rung. A ladder is two rungs or more.
    """
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        held = row.get("slice") or None
        source = held.get("of") if held else row.get("shape")
        raw = _read(directory / row["file"]) if source else None
        if raw is not None:
            by_source.setdefault(str(source), []).append(_rung(row, held, raw))
    ladders = []
    for source, rungs in by_source.items():
        rungs = _one_top_rung(rungs)
        if len(rungs) < 2:
            continue
        rungs.sort(key=lambda r: (not r["whole"], -len(r["nodes"] or []), str(r["created_at"])))
        ladders.append({"of": source, "rungs": rungs})
    return ladders


def _one_top_rung(rungs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The rungs with one whole-pipeline evaluation at the top.

    Every whole-pipeline evaluation of one shape names it, and a ladder has one top rung:
    the reported one where it is whole, else the newest. The rest are history, which the
    trend draws.
    """
    whole = [r for r in rungs if r["whole"]]
    sliced = [r for r in rungs if not r["whole"]]
    if not whole:
        return sliced
    top = next((r for r in whole if r["reported"]), None) or max(
        whole, key=lambda r: str(r["created_at"] or "")
    )
    return [top, *sliced]


def _rung(row: dict[str, Any], held: dict[str, Any] | None, raw: dict[str, Any]) -> dict[str, Any]:
    """One rung of a ladder: the file, its node set, and its figures over its own examples."""
    held = held or {}
    return {
        "file": row["file"],
        "eval_id": row.get("eval_id"),
        "created_at": row.get("created_at"),
        "whole": not held,
        "nodes": list(held.get("nodes") or []) if held else None,
        "start": held.get("start"),
        "end": held.get("end"),
        "dropped": list(held.get("dropped") or []),
        "n": row.get("n"),
        "k": row.get("k"),
        "split": row.get("split"),
        "reported": row.get("reported"),
        "figures": [_figure(n, r) for n, r in (raw.get("metrics") or {}).items()],
        "headline": _headline(raw),
    }


def _kind(config: dict[str, Any]) -> str:
    """What a results file records: ``rollouts`` of a pipeline, or judged ``pairs``."""
    return "pairs" if config.get("kind") == "pairs" else "rollouts"


_TIE = {"both": "both", "neither": "neither"}


def _tally(pairs: list[dict[str, Any]], meanings: dict[str, Any]) -> dict[str, Any]:
    """The decided pairs per arm, the two kinds of tie, and every verdict outside the mapping.

    A verdict's meaning is the project's, read from ``config.verdicts``: ``a`` credits the arm
    shown as ``a``, ``b`` the other, ``both`` and ``neither`` are ties. A preference inside a
    pair whose two sides are one arm is counted under that arm apart from the decided pairs.
    A verdict the mapping does not name is counted under its own name, so the bar never
    absorbs a verdict into a side the project did not say it was.
    """
    for_arm: Counter[str] = Counter()
    within: Counter[str] = Counter()
    ties: Counter[str] = Counter()
    other: Counter[str] = Counter()
    unjudged = 0
    for pair in pairs:
        verdict = pair.get("verdict")
        if pair.get("decided_by") is None:
            unjudged += 1
            continue
        meaning = meanings.get(str(verdict))
        if meaning in ("a", "b") and pair.get("a_arm") == pair.get("b_arm"):
            # Two things from one arm: a preference between them says nothing between arms.
            within[str(pair.get("a_arm"))] += 1
        elif meaning == "a":
            for_arm[str(pair.get("a_arm"))] += 1
        elif meaning == "b":
            for_arm[str(pair.get("b_arm"))] += 1
        elif meaning in _TIE:
            ties[meaning] += 1
        else:
            other[str(verdict)] += 1
    return {
        "for_arm": dict(for_arm),
        "decided": sum(for_arm.values()),
        "within_arm": dict(within),
        "both": ties.get("both", 0),
        "neither": ties.get("neither", 0),
        "other": dict(other),
        "unjudged": unjudged,
    }


def _session(path: Path, raw: dict[str, Any], reported: Path | None) -> dict[str, Any]:
    """One session of judged pairs, for the head-to-head region."""
    config = raw.get("config") or {}
    pairs = [p for p in raw.get("pairs") or [] if isinstance(p, dict)]
    meanings = {str(k): v for k, v in (config.get("verdicts") or {}).items()}
    return {
        "file": path.name,
        "eval_id": raw.get("eval_id"),
        "created_at": raw.get("created_at"),
        "reported": reported is not None and path.resolve() == reported.resolve(),
        "format": str(raw.get("eval_format_version") or "unversioned"),
        **_session_header(config, pairs),
        "verdicts": meanings,
        "tally": _tally(pairs, meanings),
        "figures": [_figure(n, r) for n, r in (raw.get("metrics") or {}).items()],
        "pairs": [_pair_row(p, meanings) for p in pairs],
        "totals": raw.get("totals") or {},
    }


def _session_header(config: dict[str, Any], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the session was: the arms, whether blind, who judged, and how many of what."""
    contest = [str(arm) for arm in config.get("contest") or []]
    if not contest:
        contest = sorted({str(p.get(side)) for p in pairs for side in ("a_arm", "b_arm")})
    return {
        "contest": contest,
        "blind": config.get("blind"),
        "decided_by": [str(who) for who in config.get("decided_by") or []],
        "n": config.get("n"),
        "units": config.get("units"),
    }


def _pair_row(p: dict[str, Any], meanings: dict[str, Any]) -> dict[str, Any]:
    """One pair for the table: both sides clipped, the verdict and what the file says it means."""
    return {
        "id": str(p.get("id")),
        "a": _clip(p.get("a"), 80),
        "b": _clip(p.get("b"), 80),
        "a_arm": p.get("a_arm"),
        "b_arm": p.get("b_arm"),
        "example_id": p.get("example_id"),
        "verdict": None if p.get("decided_by") is None else _clip(p.get("verdict"), 40),
        "meaning": meanings.get(str(p.get("verdict"))),
        "decided_by": p.get("decided_by"),
        "decided_at": p.get("decided_at"),
        "reason": _clip(p.get("reason"), 160) or None,
    }


def _sessions(directory: Path, reported: Path | None) -> list[dict[str, Any]]:
    """Every session of judged pairs on record, newest first."""
    found = []
    for path in directory.glob("*.json"):
        raw = _read(path)
        if raw is None or _kind(raw.get("config") or {}) != "pairs":
            continue
        found.append(_session(path, raw, reported))
    found.sort(key=lambda s: str(s.get("created_at") or ""), reverse=True)
    return found


def _how_it_was_run(config: dict[str, Any]) -> dict[str, Any]:
    """What the evaluation was: its split, its size, its backend and its example set."""
    example_set = config.get("example_set") or {}
    model = config.get("model") or {}
    cassette = config.get("cassette") or {}
    basis = config.get("cost_basis") or {}
    return {
        "split": config.get("split"),
        "k": config.get("k"),
        "n": config.get("n"),
        "seed": config.get("seed"),
        "example_set": example_set.get("content_hash"),
        "absent_proportion": example_set.get("absent_proportion"),
        "fingerprint": config.get("graph_fingerprint"),
        "model": model.get("request_model"),
        "cassette": cassette.get("mode"),
        "device": basis.get("device"),
        "scored_from": config.get("scored_from"),
        "kind": _kind(config),
    }


def _format_problem(path: Path, written_at: str) -> list[str]:
    """A results file written at a format this library no longer writes, said plainly."""
    from ..evaluation.results import EVAL_FORMAT_VERSION

    if written_at == EVAL_FORMAT_VERSION:
        return []
    return [
        f"{path.name} was written at evaluation format {written_at} and this library "
        f"writes {EVAL_FORMAT_VERSION}. The figures are shown as the file has them; "
        f"re-running the evaluation writes the current format."
    ]


def _reported_file(root: Path) -> Path | None:
    """The results file the gates read: the brief's, or the most recent."""
    from ..conformance.artifacts import Artifacts

    try:
        reported = Artifacts.discover(root).results
    except Exception:  # noqa: BLE001 - a brief that cannot be read must not lose the section
        return None
    return Path(reported) if reported is not None and Path(reported).exists() else None


def read_evaluation(root: str | Path) -> dict[str, Any] | None:
    """What the project's reported evaluation measured, or ``None`` where it has none.

    ::

        measured = read_evaluation(".")
        measured["headline"]["point"]        # the figure, with low/high beside it
        measured["nodes"]["judge"]["reach"]  # the share of rollouts that reached one step
        measured["sessions"][0]["tally"]     # a session of judged pairs, per arm

    The file is the one the brief's ``results`` names, or the most recent under
    ``evals/results/``, which is the rule the gates follow.
    """
    root = Path(root).expanduser()
    directory = root / "evals" / "results"
    if not directory.is_dir():
        return None

    reported = _reported_file(root)
    if reported is None:
        return {
            "path": None,
            "history": _history(directory, None),
            "sessions": _sessions(directory, None),
            "problems": ["No results file could be read under evals/results/."],
        }
    raw = _read(reported)
    if raw is None:
        return {
            "path": str(reported.name),
            "history": _history(directory, reported),
            "sessions": _sessions(directory, reported),
            "problems": [f"{reported.name} could not be read as an evaluation."],
        }

    written_at = str(raw.get("eval_format_version") or "unversioned")
    history = _history(directory, reported)
    return {
        "path": reported.name,
        "eval_id": raw.get("eval_id"),
        "created_at": raw.get("created_at"),
        "format": written_at,
        **_how_it_was_run(raw.get("config") or {}),
        "headline": _headline(raw),
        "metrics": [_figure(n, r) for n, r in (raw.get("metrics") or {}).items()],
        "criteria": [_figure(n, r) for n, r in (raw.get("criteria") or {}).items()],
        "nodes": {
            node_id: _node_figures(node_id, record)
            for node_id, record in (raw.get("nodes") or {}).items()
        },
        "totals": raw.get("totals") or {},
        "outcomes": _outcomes(raw),
        "went_wrong": _went_wrong(raw),
        "floor": _floor(raw),
        "counts": _rollout_counts(raw),
        "history": history,
        "problems": _format_problem(reported, written_at),
        "browser": _browser(raw, _expects(root, raw)),
        "by_outcome": _by_outcome(raw),
        "criteria_failed": _criteria_failed(raw),
        "cost_per": _cost_per(raw),
        "groups": _groups(reported),
        "comparisons": _comparisons(root),
        "ladders": _ladders(directory, history),
        "sessions": _sessions(directory, reported),
    }
