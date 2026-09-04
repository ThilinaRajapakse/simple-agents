"""The numbers and the prompts the code carries, against the decisions that name them.

A module-level number changes what the agent does and somebody chose it. The manifest records
every one a run reached, and a ``constant`` decision names the ones the builder agreed to
under ``produces``; a ``prompt_rule`` decision does the same for a rule a prompt carries.
Both halves are on disk and nothing joined them, so a number the coding agent picked alone
read the same as one the builder settled.

::

    numbers = read_constants(".", pipelines, brief)
    [n["name"] for n in numbers if n["decision"] is None]     # unconfirmed

What is here is read from what the project's own runs recorded, so a number added since the
last run appears once something has run.

**A name the newest run of its own pipeline no longer carries is marked gone**, and the page
offers no agreement on it. A manifest is a record of what the code held when it ran, so a
number deleted from the code stays in every older manifest: one project agreed to a constant
that had been removed, and the decision answering it is in that brief.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["read_constants", "read_prompt_rules", "across_the_runs"]


# How many of the newest runs are read. A project's numbers and prompts are gathered across
# runs rather than off the newest one: a project with more than one pipeline runs whichever it
# was asked for, so the newest run describes one of them and the others would vanish from the
# page on the morning a background pass ran last. FT-42 reads the record the same way.
MOST_RUNS = 200


def across_the_runs(root: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every number and every prompt the project's own runs recorded, newest value first.

    An evaluation's rollouts are left out: a rollout is measurement, and the numbers it ran
    against are its own run's. A name recorded by more than one run keeps what the newest of
    them carried, which is what the code has now.

    Each number carries ``last_seen``, the day of the newest run holding it, and ``gone``,
    which is true where the newest run of every pipeline that ever recorded it no longer does.
    **Nothing is gone on a project whose runs record no pipeline name**, which is every project
    whose runs predate manifest format ``0.41``: a number missing from the newest run of any
    pipeline is a number the pipeline that ran last does not reach, and which that was is
    unrecorded.

    A run whose model answered from a script is read here. It recorded the numbers the code
    held as faithfully as a paid one, which is what this page is about.
    """
    from ..envelope import runs

    directory = Path(root).expanduser() / "runs"
    if not directory.is_dir():
        return [], {}
    read = runs(directory, scripted=None)[:MOST_RUNS]
    numbers: dict[str, dict[str, Any]] = {}
    prompts: dict[str, Any] = {}
    for handle in read:
        for one in _constants_of(handle):
            numbers.setdefault(str(one.get("name") or ""), {**one, "last_seen": _day(handle)})
        for node_id, one in (handle.manifest.get("prompts") or {}).items():
            _keep_the_prompt(prompts, str(node_id), one)
    still_there = _what_the_code_still_has(read)
    return [
        {**held, "gone": still_there is not None and name not in still_there}
        for name, held in numbers.items()
    ], prompts


def _keep_the_prompt(held: dict[str, Any], node_id: str, one: Any) -> None:
    """Keep the newest run's account of one prompt, with every instruction the runs saw.

    The version, the source and the shape of the text are the newest run's, which is what the
    code had last. ``observed`` is the union: a step whose instruction arrives as data sends a
    different one each run, and reading the newest run alone would report one.

    ``distinct`` is the count of what was seen, and no smaller than the largest a single run
    reported: a run that sent more than the twenty a manifest lists carries the true count
    there and not the digests behind it.
    """
    if not isinstance(one, dict):
        return
    # Seeded without the counts, so the run that seeds it is added once like every other.
    kept = held.setdefault(node_id, {k: v for k, v in one.items() if k != "observed"})
    seen = dict(kept.get("observed") or {})
    for digest, calls in (one.get("observed") or {}).items():
        seen[str(digest)] = seen.get(str(digest), 0) + _a_count(calls)
    if not seen:
        return
    kept["observed"] = seen
    kept["distinct"] = max(len(seen), _a_count(kept.get("distinct")), _a_count(one.get("distinct")))


def _a_count(value: Any) -> int:
    """One number a manifest recorded, and ``0`` for anything that is not one."""
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _constants_of(handle: Any) -> list[dict[str, Any]]:
    """The ``constants`` array one run recorded, as a list whatever the manifest holds."""
    held = handle.manifest.get("constants")
    return [one for one in held if isinstance(one, dict)] if isinstance(held, list) else []


def _what_the_code_still_has(read: list[Any]) -> set[str] | None:
    """Every name the newest run of some pipeline still records, or ``None`` where nothing says.

    ``None`` where no run read names a pipeline, which is every project whose runs predate
    manifest format ``0.41``: a name missing from the newest run of any pipeline is a name the
    pipeline that ran last does not reach, and which that was is unrecorded.
    """
    newest: dict[str, set[str]] = {}
    for handle in read:
        if handle.pipeline:
            newest.setdefault(
                handle.pipeline, {str(one.get("name") or "") for one in _constants_of(handle)}
            )
    return set().union(*newest.values()) if newest else None


def _day(handle: Any) -> str:
    """The day one run started, which is what a gone number is dated by."""
    return str(handle.manifest.get("started_at") or "")[:10]


def _decision_card(decision: Any) -> dict[str, Any]:
    """One decision as the page shows it beside what it names."""
    from .claims import title_of

    return {
        "name": decision.name,
        "title": title_of(decision.name),
        "status": getattr(decision, "status", None),
        "chose": str(getattr(decision, "chose", "") or ""),
        "because": str(getattr(decision, "because", "") or ""),
    }


def _named_by(brief: Any, kind: str) -> dict[str, dict[str, Any]]:
    """What each decision of one kind names under ``produces``, keyed by the name."""
    found: dict[str, dict[str, Any]] = {}
    for decision in getattr(brief, "decisions", ()) or ():
        if getattr(decision, "kind", None) != kind:
            continue
        card = _decision_card(decision)
        for produced in getattr(decision, "produces", ()) or ():
            found.setdefault(str(produced), card)
    return found


def _writes_it(code: Any, name: str) -> bool:
    return name in (((code or {}).get("source") or {}).get("text") or "")


def _reached_from(pipelines: list[dict[str, Any]], name: str) -> dict[str, list[str]]:
    """Where this name is written: the steps that reach it, and the tools they reach it through.

    A text match over the source the page already shows, which is the same kind of join the
    brief-against-code comparison uses. It reports where the name is written and never that it
    is unused: a number reached through a helper neither the step nor its tools name is not
    found here, and a step's source clipped for length can hide one.
    """
    steps: list[str] = []
    tools: list[str] = []
    for pipeline in pipelines:
        for node in pipeline["nodes"]:
            through = [t["name"] for t in node["tools"] if _writes_it(t.get("code"), name)]
            if through or _writes_it(node.get("code"), name):
                steps.append(node["id"])
                tools.extend(through)
    return {"steps": sorted(set(steps)), "through": sorted(set(tools))}


def read_constants(
    root: str | Path,
    pipelines: list[dict[str, Any]],
    brief: Any,
    across: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every module-level number the project's runs carried, with the decision that names it.

    ::

        read_constants(".", pipelines, brief)[0]
        # {'name': 'MAX_AGE_DAYS', 'value': 90, 'module': 'agent',
        #  'reached_from': {'steps': ['policy_check'], 'through': ['policy_lookup']},
        #  'decision': None, 'gone': False, 'last_seen': '2026-09-03'}

    ``decision`` is ``None`` where no ``constant`` decision names the number, which is the
    page's **Unconfirmed**. Empty where the project has no run, since the numbers are read
    from what a run recorded.

    ``across`` is what `across_the_runs` read, which the prompt rules and the prompt page read
    too. Passing it shares one reading of the manifests between the three.

    ``gone`` is true where the newest run of every pipeline that recorded the number no longer
    carries it, and ``last_seen`` is the day the newest run that did began. The page shows
    those as removed from the code and offers no agreement on them: agreeing to a number
    nothing has records a decision about nothing.

    A run records every module-level number its own nodes reach, so a number stays until every
    pipeline that reached it has run again. Two pipelines in one module record one set of
    numbers between them, and a number deleted from that module reads as gone once either of
    them has run.
    """
    numbers, _prompts = across if across is not None else across_the_runs(root)
    agreed = _named_by(brief, "constant")
    rows = []
    for held in numbers:
        name = str(held.get("name") or "")
        rows.append(
            {
                "name": name,
                "value": held.get("value"),
                "module": held.get("module"),
                "reached_from": _reached_from(pipelines, name),
                "decision": agreed.get(name),
                "gone": bool(held.get("gone")),
                "last_seen": held.get("last_seen"),
            }
        )
    return sorted(rows, key=lambda row: (row["gone"], row["decision"] is not None, row["name"]))


def read_prompt_rules(
    root: str | Path,
    pipelines: list[dict[str, Any]],
    brief: Any,
    across: tuple[list[dict[str, Any]], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every prompt the project's runs recorded, with the rule decision that names its step.

    ::

        read_prompt_rules(".", pipelines, brief)[0]
        # {'node_id': 'decide', 'version': 'sha256:80bf…', 'source': 'derived',
        #  'decision': {'name': 'say_why_it_declined', ...}}

    ``decision`` is ``None`` where no ``prompt_rule`` decision names the step, which is the
    page's **Unconfirmed**: the prompt tells the model something and nobody said it should.

    ``across`` is what `across_the_runs` read, which the constants and the prompt page read
    too. Passing it shares one reading of the manifests between the three.
    """
    _numbers, prompts = across if across is not None else across_the_runs(root)
    agreed = _named_by(brief, "prompt_rule")
    rows = []
    for node_id, held in prompts.items():
        rows.append(
            {
                "node_id": str(node_id),
                "version": (held or {}).get("version"),
                "source": (held or {}).get("source"),
                "decision": agreed.get(str(node_id)),
            }
        )
    return sorted(rows, key=lambda row: (row["decision"] is not None, row["node_id"]))
