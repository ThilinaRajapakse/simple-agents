"""What a pipeline declares that decides what an evaluation of it measures.

Two views of the same declarations: what a pipeline declares now, and what a run's manifest
recorded. The runner compares the two field by field before scoring rollouts, and
``prompt_differences`` compares two evaluations' recordings the same way.
"""

from __future__ import annotations

from typing import Any, Mapping

from ..pipeline import Pipeline
from ..pipeline.recording import _without_derived


def _declarations_in(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Every versioned declaration a manifest records, keyed by where it was declared.

    One entry per prompt, per `Deterministic` node's function and per tool. Each carries a
    `version`, which is what identity is built from, and a `derived` hash of the source, which
    is what says the source moved under a version that did not.
    """
    found: dict[str, dict[str, Any]] = {
        f"prompt {node_id!r}": entry for node_id, entry in (manifest.get("prompts") or {}).items()
    }
    found.update(
        {
            f"node {entry.get('node_id')!r}": entry["fn"]
            for entry in (manifest.get("nodes") or [])
            if entry.get("fn")
        }
    )
    found.update({f"tool {entry.get('name')!r}": entry for entry in (manifest.get("tools") or [])})
    return found


def _declarations_of(pipeline: Pipeline) -> dict[str, dict[str, Any]]:
    """The same, for what a pipeline declares now rather than what a run recorded."""
    return _declarations_in(
        {
            "prompts": pipeline.manifest_prompts(),
            "nodes": pipeline.manifest_nodes(),
            "tools": pipeline.manifest_tools(),
        }
    )


def _held_declarations(
    was: Mapping[str, dict[str, Any]], now: Mapping[str, dict[str, Any]]
) -> dict[str, tuple[str, str, Any]]:
    """Where a version is declared on both sides, is equal, and the source under it is not.

    A name on one side only is a changed pipeline, which the refusals cover. A missing hash is
    a function whose source could not be read, and nothing is concluded from it.
    """
    held: dict[str, tuple[str, str, Any]] = {}
    for where in sorted(set(was) & set(now)):
        before, after = was[where], now[where]
        if before.get("version") != after.get("version"):
            continue
        first, second = before.get("derived"), after.get("derived")
        if first and second and first != second:
            held[where] = (str(first), str(second), after.get("version"))
    return held


def _measured_configuration(pipeline: Pipeline) -> dict[str, Any]:
    """Everything about a pipeline that decides what an evaluation of it measures.

    What the manifest records for every node, for every pipeline used as a node, and for the
    run's budget. Wider than :meth:`Pipeline.graph_fingerprint`, which is shape alone: two
    pipelines of one shape differing in a temperature, a tool, ``allow_unknown`` or a budget
    produce different numbers and this separates them::

        _measured_configuration(pipeline)["budget"]["max_steps"]   # 12

    Read back from a run's manifest by :func:`_measured_configuration_of`, so the two compare
    field by field. The hash recorded beside a declared version is taken out first, so a change
    made under a version the project did not move is reported by
    :meth:`EvalSuite._warn_a_moved_declaration` rather than refused here.
    """
    return _without_derived(
        {
            "nodes": pipeline.manifest_nodes(),
            "containers": pipeline.manifest_containers(),
            "tools": pipeline.manifest_tools(),
            "budget": pipeline.budget.to_record(),
        }
    )


def _measured_configuration_of(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """The same, read back from what one run's manifest recorded.

    Empty values where the manifest holds none, which is what a run written by an earlier
    version leaves. Nothing is concluded from an absent record.
    """
    return _without_derived(
        {
            "nodes": list(manifest.get("nodes") or []),
            "containers": list(manifest.get("containers") or []),
            "tools": list(manifest.get("tools") or []),
            "budget": dict(manifest.get("budget") or {}),
        }
    )


def config_differences(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """What differs in the two configurations, as ``path -> [before, after]``.

    A moved metric with nothing here changed for a reason the results do not record, which is
    itself worth knowing (FT-15)::

        config_differences(was, now)
        # {'nodes.hunt.sampling.temperature': [0.0, 0.7]}

    A list whose entries name themselves, such as ``nodes`` or ``tools``, is paired on the
    name, so a changed node kind reads as ``nodes.hunt.node_kind`` rather than as two whole
    lists.
    """
    found: dict[str, list[Any]] = {}
    _walk(before, after, "", found)
    return found


def _walk(before: Any, after: Any, path: str, found: dict[str, list[Any]]) -> None:
    if isinstance(before, dict) and isinstance(after, dict):
        for key in dict.fromkeys([*before, *after]):
            _walk(before.get(key), after.get(key), f"{path}.{key}" if path else key, found)
        return
    if _keyed(before) and _keyed(after):
        for key in dict.fromkeys([*_by_key(before), *_by_key(after)]):
            _walk(
                _by_key(before).get(key),
                _by_key(after).get(key),
                f"{path}.{key}" if path else key,
                found,
            )
        return
    if before != after:
        found[path] = [before, after]


# A list of objects each naming itself. `config.nodes` and `config.tools` are both this shape,
# and comparing them whole reports one difference carrying two entire lists, which names no
# node and no tool. Paired on the name, a changed node kind reads as
# `nodes.hunt.node_kind: ['agent', 'llm']`.
_KEYS = ("node_id", "name")


def _keyed(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict) and any(k in item for k in _KEYS) for item in value
    )


def _by_key(value: list[Any]) -> dict[str, Any]:
    return {str(next(item[k] for k in _KEYS if k in item)): item for item in value}
