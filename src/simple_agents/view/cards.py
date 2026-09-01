"""One card per thing the page draws: a step, a pipeline, a resource, the path through it.

Everything here is derived from the pipelines `agent.py` declares, without running any of
them. Nothing is asserted by hand and nothing reads a run: the run overlay and the evaluation
are joined onto these cards afterwards.
"""

from __future__ import annotations

from typing import Any

from ..shapes import accepted_by, produced_by
from .callables import read_callable
from .words import _clip


_KIND_WORDS = {
    "deterministic": "fixed step",
    "llm": "model call",
    "agent": "decides for itself",
    "pipeline": "pipeline",
}


def _redactor() -> Any:
    """The library's own rules, applied to source text before it reaches the page.

    `view.html` is a file a builder shares, and a project's own code is the one thing on the
    page the library did not write. The rules are the ones a run's records go through.
    """
    from ..redaction import Redaction

    rules = Redaction()

    def scrub(text: str) -> str:
        cleaned, _found = rules.redact(text)
        return cleaned if isinstance(cleaned, str) else text

    return scrub


def _type_name(annotation: Any) -> str | None:
    """A type written the way the builder reads it, never a `typing` repr."""
    import types
    import typing

    if annotation is None:
        return None
    origin = typing.get_origin(annotation)
    if origin is None:
        name = getattr(annotation, "__name__", None)
        return name or str(annotation).replace("typing.", "")
    args = typing.get_args(annotation)
    if origin is typing.Union or origin is types.UnionType:
        parts = [_type_name(a) for a in args if a is not type(None)]
        named = [p for p in parts if p and p != "Unknown"]
        if len(named) < len(parts):
            return (" | ".join(named) if named else "answer") + ", or unknown"
        return " | ".join(p for p in parts if p)
    inner = ", ".join(filter(None, (_type_name(a) for a in args)))
    name = getattr(origin, "__name__", None) or str(origin)
    return f"{name}[{inner}]" if inner else name


def _schema_card(schema: Any) -> dict[str, Any] | None:
    """A schema as the builder reads it: its name and its fields, never a digest."""
    if schema is None:
        return None
    fields = getattr(schema, "model_fields", None)
    if not isinstance(fields, dict):
        return {"name": _type_name(schema), "fields": []}
    return {
        "name": _type_name(schema),
        "fields": [
            {"name": name, "type": _type_name(info.annotation)} for name, info in fields.items()
        ],
    }


def _tool_card(tool: Any, scrub: Any = None) -> dict[str, Any]:
    cost = getattr(tool, "declared_cost", None)
    return {
        "code": read_callable(getattr(tool, "fn", None), _type_name, redact=scrub),
        "version": getattr(tool, "version", None),
        "name": tool.name,
        "effect": tool.side_effect_class.value,
        "touches": sorted(tool.touches or ()),
        "asks": getattr(tool, "answered_by", None),
        "cost_per_call": getattr(cost, "per_call", None),
        "currency": getattr(cost, "currency", None),
        "description": _clip((tool.description or "").strip().split("\n")[0], 160),
    }


def _model_name(model: Any) -> str | None:
    if model is None:
        return None
    return getattr(model, "request_model", None) or type(model).__name__


def _flow_card(node: Any, graph: Any, prefix: str) -> dict[str, Any]:
    """Where a step's output can go: its edges, its cycle, its failure path, its retries."""
    loop = getattr(node, "loop", None)
    retry = getattr(node, "retry", None)
    on_error = getattr(node, "on_error", None)
    return {
        "successors": [f"{prefix}{s}" for s in graph.successors[node.node_id]],
        "closes_a_cycle": [
            f"{prefix}{target}" for source, target in graph.back_edges if source == node.node_id
        ],
        "routes": getattr(node, "route", None) is not None,
        "loop": (
            {"back_for": loop.max_iterations, "then": f"{prefix}{loop.then}"}
            if loop is not None
            else None
        ),
        "on_error": f"{prefix}{on_error}" if on_error else None,
        "retries": getattr(retry, "attempts", None) if retry is not None else None,
    }


def _limits_card(node: Any) -> dict[str, Any]:
    """What bounds one step: its budget, its answer length, and the model it calls."""
    budget = getattr(node, "budget", None)
    return {
        "model": _model_name(getattr(node, "model", None)),
        "max_output_tokens": getattr(node, "max_output_tokens", None),
        "budget": (
            budget.to_record() if budget is not None and hasattr(budget, "to_record") else None
        ),
    }


def _intent_of(node: Any) -> str | None:
    """What a step that is not built yet says it will do, in the builder's own words."""
    marker = getattr(node, "fn", None)
    if not hasattr(marker, "does"):
        marker = getattr(node, "prompt", None)
    return getattr(marker, "does", None)


def _node_code(node: Any, scrub: Any) -> dict[str, Any] | None:
    """The function this step runs, as the code says it. ``None`` for a step not built yet."""
    if getattr(node, "planned", False):
        return None
    fn = getattr(node, "fn", None)
    if fn is None:
        fn = getattr(node, "prompt", None)
    return read_callable(fn, _type_name, redact=scrub)


def _node_card(node_id: str, node: Any, graph: Any, scrub: Any = None) -> dict[str, Any]:
    """Every declared fact about one step, keyed the way the page reads it."""
    prefix = node_id[: -len(node.node_id)] if node.node_id else ""
    planned = bool(getattr(node, "planned", False))
    tools = getattr(node, "tools", []) or []
    return {
        "code": _node_code(node, scrub),
        "id": node_id,
        "prefix": prefix,
        "kind": node.node_kind,
        "kind_word": _KIND_WORDS.get(node.node_kind, node.node_kind),
        "class_name": type(node).__name__,
        "planned": planned,
        "does": _intent_of(node) if planned else None,
        "suspend_before": bool(getattr(node, "suspend_before", False)),
        "fan_out": getattr(node, "over", None),
        "concurrent_items": getattr(node, "concurrent_items", None),
        "tools": [_tool_card(t, scrub) for t in tools],
        "touches": sorted(getattr(node, "touches", ()) or ()),
        "produces": _schema_card(produced_by(node)),
        "accepts": _type_name(accepted_by(node)),
        "asks_a_person": any(getattr(t, "answered_by", None) for t in tools),
        **_flow_card(node, graph, prefix),
        **_limits_card(node),
    }


_FAILURE_CARD = {
    "name": "NodeFailure",
    "fields": [
        {"name": "node_id", "type": "str"},
        {"name": "inputs", "type": "what the failed step received"},
        {"name": "error", "type": "the error object"},
        {"name": "attempts", "type": "int"},
    ],
}


def _trace_inputs(nodes: list[dict[str, Any]]) -> None:
    """Say what each step is handed, derived from the steps whose edges reach it.

    "Whatever the step before it produced" is a non-answer wherever the graph knows better,
    and it knows better whenever a predecessor declares what it produces.
    """
    incoming: dict[str, list[dict[str, Any]]] = {n["id"]: [] for n in nodes}
    for node in nodes:
        for target in node["successors"]:
            if target in incoming:
                incoming[target].append(
                    {
                        "from": node["id"],
                        "how": "edge",
                        "carries": node["produces"],
                    }
                )
        handler = node["on_error"]
        if handler and handler in incoming:
            incoming[handler].append(
                {
                    "from": node["id"],
                    "how": "on_error",
                    "carries": _FAILURE_CARD,
                }
            )
    for node in nodes:
        sources = incoming[node["id"]]
        if not sources and node.get("reached_by") == "delegation":
            node["takes_in"] = {
                "sources": [],
                "join": False,
                "declared": node["accepts"],
                "says": "What the model asked this pipeline to do",
            }
            continue
        node["takes_in"] = {
            "sources": sources,
            "join": len(sources) > 1,
            "declared": node["accepts"],
            "says": _takes_in_words(node, sources),
        }


def _cap(text: str) -> str:
    """A sentence that starts a line, capitalised."""
    return text[:1].upper() + text[1:]


def _carried(source: dict[str, Any]) -> str:
    card = source["carries"]
    return (card or {}).get("name") or "what it produced"


def _takes_in_words(node: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    """The one line the step card shows against "Takes in"."""
    declared = node["accepts"]
    per_item = f", once per item in {node['fan_out']}" if node["fan_out"] else ""
    if not sources:
        opens = "what its pipeline is handed" if node.get("inside") else "what the run is given"
        return (f"{declared}, {opens}" if declared else _cap(opens)) + per_item
    if len(sources) == 1:
        one = sources[0]
        if one["how"] == "on_error":
            return f"A NodeFailure from {one['from']}, which is the only way it is reached"
        card = one["carries"]
        if card and card.get("name"):
            return f"{card['name']}, from {one['from']}" + per_item
        return f"What {one['from']} produced" + per_item
    parts = ", ".join(f"{s['from']} ({_carried(s)})" for s in sources)
    return f"A Join with one key per edge: {parts}" + per_item


def _sides_of(node: dict[str, Any]) -> dict[str, list[str]]:
    """The resources one step reads, writes, and touches without saying which.

    The same rule the system level uses: a paid call is undirected, since its side-effect
    class covers a read and a write alike, and so is a step's own ``touches=``.
    """
    reads, writes, touches = set(), set(), set(node["touches"])
    for tool in node["tools"]:
        for name in tool["touches"]:
            if tool["effect"] == "read_only":
                reads.add(name)
            elif tool["effect"] == "spends_money":
                touches.add(name)
            else:
                writes.add(name)
    return {"reads": sorted(reads), "writes": sorted(writes), "touches": sorted(touches)}


def _step_intent(node: dict[str, Any]) -> str | None:
    """What one step is for, in the words the project already wrote.

    A step not built yet carries the sentence its ``NotBuilt`` marker was given; a built one
    carries the first line of its function's docstring. Neither is written down twice, so
    neither can drift from the code. ``None`` where the project wrote no sentence.
    """
    if node["planned"]:
        return node["does"] or None
    said = ((node.get("code") or {}).get("says") or "").strip()
    return said or None


def _seams_of(node: dict[str, Any], sides: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Where one step leaves the straight line: it decides, asks, spends, or changes something.

    ``words`` is the seam in the builder's words and ``name`` is the store it touches, kept
    apart so the page can set a name in monospace and a word in prose. Read from the same
    declarations the drawing marks, so the two cannot disagree.
    """
    found: list[dict[str, Any]] = []
    if node["kind"] == "agent":
        found.append({"kind": "decides", "words": "Decides for itself", "name": None})
    if len(node["successors"]) > 1 and node["routes"]:
        found.append({"kind": "branches", "words": "Branches", "name": None})
    if node["loop"]:
        found.append(
            {
                "kind": "loops",
                "words": f"Loops back up to {node['loop']['back_for']}×",
                "name": None,
            }
        )
    if node["asks_a_person"]:
        found.append({"kind": "asks", "words": "Asks a person", "name": None})
    if any(t["effect"] == "spends_money" for t in node["tools"]):
        found.append({"kind": "spends", "words": "Spends money", "name": None})
    if any(t["effect"] == "irreversible" for t in node["tools"]):
        found.append({"kind": "permanent", "words": "Makes a permanent change", "name": None})
    for store in sides["writes"]:
        found.append({"kind": "writes", "words": "Writes", "name": store})
    for store in sides["touches"]:
        found.append({"kind": "touches", "words": "Touches", "name": store})
    return found


def _data_path(name: str, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Where data enters this pipeline, what each step does to it, and what leaves.

    One row per step, in graph order, so the path reads top to bottom rather than being
    reassembled from the cards. Each row also carries what the step is for and the seams it
    holds, which is what the `shape` page reads it as.
    """
    ends = {n["id"] for n in nodes if not n["successors"]}
    path = []
    for node in nodes:
        sides = _sides_of(node)
        path.append(
            {
                "id": node["id"],
                "at": f"{name}/{node['id']}",
                "kind_word": node["kind_word"],
                "intent": _step_intent(node),
                "seams": _seams_of(node, sides),
                "takes_in": node["takes_in"]["says"],
                "hands_on": (node["produces"] or {}).get("name")
                or ("not settled yet" if node["planned"] else "plain data"),
                # Two kinds of step narrow what travels: one that calls the model produces what
                # its schema describes, and one that fans out produces the outcomes.
                "narrows": bool(node["fan_out"])
                or (bool(node["produces"]) and node["kind"] != "deterministic"),
                "took_in_volume": None,
                "handed_on_volume": None,
                **sides,
                "ends": node["id"] in ends,
                "planned": node["planned"],
            }
        )
    return path


def _containers(pipeline: Any) -> list[dict[str, Any]]:
    """Every pipeline used inside this one, with the step ids it opens and closes at.

    A pipeline used as a node is reached along an edge; one reached through a model call is a
    delegate and sits off the graph, which is why each says how it is reached.
    """
    found = []
    for container_id, inner, graph, delegation in pipeline.declared_containers():
        prefix = container_id[: -len(inner.node_id)] if inner.node_id else container_id
        found.append(
            {
                "id": container_id,
                "name": container_id.rsplit(".", 1)[-1],
                "entry": f"{container_id}.{inner.graph.entry}",
                "terminal": f"{container_id}.{inner.graph.terminal}",
                "steps": len(inner.declared_nodes()),
                "reached_by": "edge" if graph is not None else "delegation",
                "successors": (
                    [f"{prefix}{s}" for s in graph.successors[inner.node_id]]
                    if graph is not None
                    else []
                ),
                "on_error": (
                    f"{prefix}{inner.on_error}"
                    if graph is not None and getattr(inner, "on_error", None)
                    else None
                ),
                "budget": inner.budget.to_record() if inner.budget else None,
                "asked_for": getattr(delegation, "description", None) if delegation else None,
            }
        )
    return found


def _point_at_the_entry(nodes: list[dict[str, Any]], entry_of: dict[str, str]) -> None:
    """An edge naming a nested pipeline names its first step instead."""
    for node in nodes:
        node["successors"] = [entry_of.get(s, s) for s in node["successors"]]
        node["closes_a_cycle"] = [entry_of.get(s, s) for s in node["closes_a_cycle"]]
        node["on_error"] = entry_of.get(node["on_error"], node["on_error"])


def _carry_the_edges_out(
    nodes: list[dict[str, Any]], containers: list[dict[str, Any]], entry_of: dict[str, str]
) -> None:
    """A nested pipeline's last step carries the edges its container declared."""
    by_id = {n["id"]: n for n in nodes}
    for container in containers:
        closing = by_id.get(container["terminal"])
        if closing is None:
            continue
        outward = [entry_of.get(s, s) for s in container["successors"]]
        closing["successors"] = list(dict.fromkeys([*closing["successors"], *outward]))
        if container["on_error"] and not closing["on_error"]:
            closing["on_error"] = entry_of.get(container["on_error"], container["on_error"])


def _entry_map(containers: list[dict[str, Any]]) -> dict[str, str]:
    """Which step an edge naming a nested pipeline actually enters, by container id."""
    return {c["id"]: c["entry"] for c in containers}


def _link_containers(nodes: list[dict[str, Any]], containers: list[dict[str, Any]]) -> None:
    """Make an edge that names a nested pipeline point at the steps inside it.

    A pipeline used as a node is one node in its parent's graph and several in the drawing,
    so an edge into it enters at its first step and its last step carries its edges out.
    Without this the nested steps are drawn as a component connected to nothing.
    """
    if not containers:
        for node in nodes:
            node["inside"] = None
            node["reached_by"] = "edge"
        return
    entry_of = {c["id"]: c["entry"] for c in containers}
    _point_at_the_entry(nodes, entry_of)
    _carry_the_edges_out(nodes, containers, entry_of)
    depth = sorted(containers, key=lambda c: -len(c["id"]))
    for node in nodes:
        held = next((c for c in depth if node["id"].startswith(c["id"] + ".")), None)
        node["inside"] = held["id"] if held else None
        node["reached_by"] = held["reached_by"] if held else "edge"


def _pipeline_card(name: str, pipeline: Any, scrub: Any = None) -> dict[str, Any]:
    scrub = scrub if scrub is not None else _redactor()
    nodes = [
        _node_card(node_id, node, graph, scrub)
        for node_id, node, graph in pipeline._declared_with_graph()
    ]
    containers = _containers(pipeline)
    _link_containers(nodes, containers)
    _trace_inputs(nodes)
    entry_of = _entry_map(containers)
    planned = [n for n in nodes if n["planned"]]
    return {
        "name": name,
        "origin": "declared",
        "fingerprint": pipeline.graph_fingerprint(),
        "budget": pipeline.budget.to_record() if pipeline.budget else None,
        "nodes": nodes,
        "containers": containers,
        "entry_of": entry_of,
        "data_path": _data_path(name, nodes),
        "status": (
            "planned"
            if planned and len(planned) == len(nodes)
            else "in progress"
            if planned
            else "built"
        ),
        "runs": None,
    }


def _empty_resource() -> dict[str, list[str]]:
    """Both sides, and why anything undirected is undirected: a paid call, or no declaration."""
    return {"readers": [], "writers": [], "unknown": [], "paid": [], "undeclared": []}


def _resources(pipelines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    held: dict[str, dict[str, list[str]]] = {}
    for pipeline in pipelines:
        for node in pipeline["nodes"]:
            where = f"{pipeline['name']}/{node['id']}"
            for name in node["touches"]:
                slot = held.setdefault(name, _empty_resource())
                slot["unknown"].append(where)
                slot["undeclared"].append(where)
            for tool in node["tools"]:
                for name in tool["touches"]:
                    slot = held.setdefault(name, _empty_resource())
                    # A paid call can be a read or a write and the class cannot say which,
                    # so it lands beside a node's own undirected touches.
                    side = (
                        "readers"
                        if tool["effect"] == "read_only"
                        else "unknown"
                        if tool["effect"] == "spends_money"
                        else "writers"
                    )
                    slot[side].append(where)
                    if side == "unknown":
                        slot["paid"].append(where)
    cards = [
        {"name": name, **{k: sorted(set(v)) for k, v in sides.items()}}
        for name, sides in sorted(held.items())
    ]
    for card in cards:
        card["through"] = _tools_touching(pipelines, card["name"])
    return cards


def _tools_touching(pipelines: list[dict[str, Any]], resource: str) -> list[dict[str, Any]]:
    """Every tool that names this resource, once each, with what its author said it does.

    A resource is a string a project chose, so the library cannot say what is in it. What it
    can say is which tools reach it and what each of them declares, which is the closest
    thing to a description of the data that exists anywhere in the code.
    """
    found: dict[str, dict[str, Any]] = {}
    for pipeline in pipelines:
        for node in pipeline["nodes"]:
            for tool in node["tools"]:
                if resource not in tool["touches"]:
                    continue
                held = found.setdefault(tool["name"], {**tool, "used_by": []})
                held["used_by"].append(f"{pipeline['name']}/{node['id']}")
    for held in found.values():
        held["used_by"] = sorted(set(held["used_by"]))
    return [found[name] for name in sorted(found)]
