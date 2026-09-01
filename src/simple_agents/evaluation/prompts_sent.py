"""Which examples were sent more than one prompt, read from what the rollouts recorded.

Nothing here imports the project's pipeline or example set, so an evaluation is read from
another process or another terminal, while it runs or after.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from ..envelope import rollouts_under, runs
from ..errors import ConfigurationError
from ..records.trajectory import read_trajectory
from .declared import _declarations_in, _held_declarations


def prompt_differences(
    run_dir: str | os.PathLike[str],
    *,
    against: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    """Which examples were sent more than one prompt, read from what the rollouts recorded.

    Nothing here imports the project's pipeline or example set, so this reads an evaluation from
    another process or another terminal::

        prompt_differences("runs/eval/eval_a1226bc495df")
        # {'run_dir': 'runs/eval/eval_a1226bc495df', 'against': None, 'rollouts': 96,
        #  'compared': 33, 'unreadable': 0, 'declarations': [],
        #  'differing': [{'example': 'q1', 'node': 'hunt', 'item': None, 'distinct': 2,
        #                 'across_runs': False,
        #                 'prompts': {'sha256:aa4d52b117e0': ['q1-0', 'q1-1'],
        #                             'sha256:42608933a241': ['q1-2']}}]}

    What is compared is the first model call of each node execution, per fan-out item, which is
    the call built from the example alone. A later call in an ``AgentNode``'s loop carries what
    the model said.

    ``against`` names a second evaluation and reads both, so one example's prompts are compared
    across two runs rather than inside one. A rollout is then named ``<evaluation>/<rollout>``,
    ``across_runs`` says the two directories disagree, and ``declarations`` holds each version
    declared alike in both whose source hash differs (FT-15)::

        prompt_differences("runs/eval/eval_new", against="runs/eval/eval_old")

    Nothing here decides whether a difference is a defect: a prompt reading the clock, a tool
    holding state across rollouts and memory that accumulates each produce one legitimately.

    ``unreadable`` counts model calls whose payloads the run did not keep. An evaluation refuses
    a sampled trajectory, so those arise over ordinary runs.
    """
    here = Path(run_dir)
    _refuse_a_directory_of_evaluations(here)
    sent, rollouts, unreadable = _prompts_under(here, side=0)
    declarations: list[dict[str, Any]] = []
    if against is not None:
        there = Path(against)
        _refuse_a_directory_of_evaluations(there)
        if here.resolve() == there.resolve():
            raise ConfigurationError(
                f"run_dir and against are both {str(run_dir)!r}, so there is nothing to "
                f"compare. Two evaluations of one configuration write into one directory "
                f"name, so pass the two envelope run_dirs they were written under."
            )
        more, seen, missed = _prompts_under(there, side=1)
        sent.update(more)
        rollouts += seen
        unreadable += missed
        declarations = _held_between(here, there)

    named = {0: str(run_dir), 1: str(against)}
    groups: dict[tuple[str, str, Any], dict[str, list[tuple[int, str]]]] = {}
    for (side, rollout, node, item), digest in sent.items():
        example = _example_named(rollout)
        groups.setdefault((example, node, item), {}).setdefault(digest, []).append((side, rollout))

    def _shown(rollout: tuple[int, str]) -> str:
        side, name = rollout
        return name if against is None else f"{named[side]}/{name}"

    differing = [
        {
            "example": example,
            "node": node,
            "item": item,
            "distinct": len(prompts),
            "across_runs": len({side for side, _ in _flat(prompts)}) > 1,
            "prompts": {
                digest: sorted(_shown(r) for r in found)
                for digest, found in sorted(prompts.items())
            },
        }
        for (example, node, item), prompts in sorted(groups.items(), key=lambda kv: str(kv[0]))
        if len(prompts) > 1
    ]
    return {
        "run_dir": str(run_dir),
        "against": None if against is None else str(against),
        "rollouts": rollouts,
        "compared": len(groups),
        "unreadable": unreadable,
        "differing": differing,
        "declarations": declarations,
    }


def _refuse_a_directory_of_evaluations(given: Path) -> None:
    """Refuse a directory holding evaluations rather than rollouts.

    An evaluation writes its rollouts into `<run_dir>/eval/<eval_id>/`, so a caller who
    passes `run_dir` gets no rollouts and a report saying nothing differed.
    """
    if rollouts_under(given) or not runs(given, nested=True):
        return
    found = sorted(
        {
            handle.evaluation.eval_id if handle.evaluation is not None else handle.path.parent.name
            for handle in runs(given, nested=True)
        }
    )
    raise ConfigurationError(
        f"{str(given)!r} holds evaluation directories rather than rollouts, so there are no "
        f"prompts here to compare and an empty report would read as agreement.\n"
        f"Pass one evaluation's directory: "
        f"{', '.join(repr(str(given / name)) for name in found[:3])}"
        + (f", and {len(found) - 3} more" if len(found) > 3 else "")
    )


def _flat(prompts: Mapping[str, list[tuple[int, str]]]) -> list[tuple[int, str]]:
    return [rollout for found in prompts.values() for rollout in found]


def _example_named(rollout: str) -> str:
    """The example a rollout directory belongs to, which is its name without the index."""
    stem, _, index = rollout.rpartition("-")
    return stem if stem and index.isdigit() else rollout


def _prompts_under(
    eval_dir: Path, *, side: int
) -> tuple[dict[tuple[int, str, str, Any], str], int, int]:
    """A digest of the first prompt each node execution sent, keyed by rollout, node and item.

    `side` separates the two directories a comparison reads. Two evaluations of one declared
    configuration write into one directory name, which is the case this exists for, so the name
    cannot be what tells them apart.

    A `node_execution` record is written after the calls it holds, so the calls are collected
    first and mapped to their node afterwards.
    """
    sent: dict[tuple[int, str, str, Any], str] = {}
    rollouts = unreadable = 0
    for handle in rollouts_under(eval_dir):
        if not handle.trajectory_path.exists():
            continue
        rollouts += 1
        name = str(handle.run_id)
        node_of: dict[str, str] = {}
        calls: list[Mapping[str, Any]] = []
        for record in read_trajectory(handle.trajectory_path):
            if record.get("record_type") == "node_execution":
                node_of[str(record.get("record_id"))] = str(record.get("node_id"))
            elif record.get("record_type") == "model_call":
                calls.append(record)
        seen: set[tuple[str, Any]] = set()
        for record in sorted(calls, key=lambda r: r.get("sequence") or 0):
            node = node_of.get(str(record.get("parent_id")))
            if node is None:
                continue
            where = (node, record.get("item_index"))
            if where in seen:
                continue
            seen.add(where)
            messages = (record.get("inputs") or {}).get("messages")
            if not isinstance(messages, list):
                unreadable += 1
                continue
            material = json.dumps(messages, sort_keys=True, default=str).encode("utf-8")
            sent[(side, name, node, record.get("item_index"))] = (
                f"sha256:{hashlib.sha256(material).hexdigest()[:12]}"
            )
    return sent, rollouts, unreadable


def _held_between(here: Path, there: Path) -> list[dict[str, Any]]:
    """Versions declared alike in two evaluations whose source hash differs.

    One rollout's manifest speaks for its evaluation, since every rollout of one evaluation
    ran one pipeline.
    """
    first, second = rollouts_under(here), rollouts_under(there)
    if not first or not second:
        return []
    held = _held_declarations(
        _declarations_in(second[0].manifest), _declarations_in(first[0].manifest)
    )
    return [
        {"where": where, "version": version, "source": [was, now]}
        for where, (was, now, version) in sorted(held.items())
    ]
