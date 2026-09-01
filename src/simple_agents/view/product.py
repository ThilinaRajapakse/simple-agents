"""The product as the page draws it: the surfaces, and what each one joins to.

A declared `Surface` names a pipeline, a channel or a resource by name. On its own that is a
string; joined to what the code declares it becomes the picture the `ship` page draws: which
pipeline an interaction runs, who the channel says answers and whether that is still a
stand-in (FT-31), and which store an artifact surface shows.

::

    read_product(root, loaded, pipelines)
    # {'surfaces': [...], 'parameters': [...], 'reaches_the_agent': True, 'problems': [...]}

The surface's own numbers are read from the module that declares it, the way a run's are read
from the modules its steps come from. A project that declares its product beside its surface
gets that surface's numbers; one that declares it in `agent.py` gets the agent's.
"""

from __future__ import annotations

from typing import Any

__all__ = ["read_product"]


def _channel(
    pipelines: list[dict[str, Any]],
    name: str | None,
    within: str | None = None,
) -> dict[str, Any] | None:
    """The consultation channel a surface answers through, and who it says answers.

    Matched on the tool's own name, within the pipeline the surface names where it names one:
    two pipelines can each hold a tool called ``consult``, and a surface that answers one
    pipeline's questions does not answer the other's. ``None`` where no step holds a tool of
    that name, which is a declaration naming a channel the code does not have.
    """
    if not name:
        return None
    steps: list[str] = []
    answered_by: set[str] = set()
    for pipeline in pipelines:
        if within and pipeline["name"] != within:
            continue
        for node in pipeline["nodes"]:
            for held in node["tools"]:
                if held["name"] != name:
                    continue
                steps.append(f"{pipeline['name']}/{node['id']}")
                if held["asks"]:
                    answered_by.add(str(held["asks"]))
    if not steps:
        return None
    return {"name": name, "at": sorted(set(steps)), "answered_by": sorted(answered_by)}


def _stand_in(answered_by: list[str]) -> bool:
    """Whether the channel still says a stand-in answers, by FT-31's own rule.

    `end_user` is the person the agent is for and `nobody` is a design a project can ship;
    everything else belongs to a build. Read from the check rather than restated, so the page
    and the gate cannot come to different answers.
    """
    from ..conformance.checks import SHIPPED_ANSWERERS

    return any(str(who) not in SHIPPED_ANSWERERS for who in answered_by)


def _one_surface(
    surface: Any,
    pipelines: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    """One declared surface with what it joins to, and what the join could not find."""
    named = surface.pipeline
    found = next((p for p in pipelines if p["name"] == named), None)
    channel = _channel(pipelines, surface.through, named)
    store = next((r for r in resources if r["name"] == surface.reads), None)
    missing = []
    if named and found is None:
        missing.append(f"no pipeline is registered as {named}")
    if surface.through and channel is None:
        missing.append(
            f"no step of {named} holds a tool called {surface.through}"
            if named
            else f"no step holds a tool called {surface.through}"
        )
    elif channel is not None and not channel["answered_by"]:
        missing.append(f"the tool {surface.through} asks nobody, so it is not a channel")
    if surface.reads and store is None:
        missing.append(f"no step or tool touches {surface.reads}")
    return {
        "name": surface.name,
        "kind": surface.kind,
        "kind_words": surface.kind_words,
        "does": surface.does,
        "reaches_the_agent": surface.reaches_the_agent,
        "pipeline": named if found is not None else None,
        "pipeline_named": named,
        "through": surface.through,
        "channel": channel,
        "stand_in": _stand_in(channel["answered_by"]) if channel else False,
        "reads": surface.reads if store is not None else None,
        "reads_named": surface.reads,
        "writers": sorted(store["writers"]) if store else [],
        "missing": missing,
    }


def read_product(
    root: Any,
    loaded: Any,
    pipelines: list[dict[str, Any]],
    resources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The declared product, joined to the code, or ``None`` where none is declared.

    ::

        held = read_product(root, loaded, declared, resources)
        [s["name"] for s in held["surfaces"] if s["missing"]]   # names the code does not have

    ``parameters`` is every module-level number the declaring module defines, which is the
    surface's own; a run's manifest cannot record them, since no run reaches the surface.
    ``reaches_the_agent`` is whether any interaction starts or answers a run: a product with
    none is a display over stored output, which is a real state and reported rather than
    refused.
    """
    product = getattr(loaded, "product", None)
    if product is None:
        return None
    surfaces = [_one_surface(s, pipelines, resources) for s in product.surfaces]
    return {
        "surfaces": surfaces,
        "parameters": list(getattr(loaded, "product_parameters", ()) or ()),
        "reaches_the_agent": any(s["reaches_the_agent"] for s in surfaces),
        "declared_in": getattr(loaded, "product_module", None),
    }
