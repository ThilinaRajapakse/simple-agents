"""Naming a project's pipelines so tooling can find them without running them.

`simple-agents view` imports the project's `agent.py` and builds each registered pipeline to
draw it. Registering is one decorator on the function that builds the pipeline::

    from simple_agents import Pipeline, pipeline_factory

    @pipeline_factory("recommend")
    def recommend() -> Pipeline:
        return Pipeline([...], budget=...)

The name is the pipeline's name everywhere a person sees it, so pick the word the builder
uses. The factory is called with no arguments; one that needs configuration reads it inside
the function, from the same place the project's own entry point reads it.

**The name travels onto the pipeline the factory builds**, so every run of it records which
pipeline it was. `Pipeline.name` is where it lands, a run's manifest records it under
`pipeline`, and a results file records it in `config`. A pipeline built outside a registered
factory records `null`, and the checks that read one pipeline's runs say so.

Importing `agent.py` runs its module-level code, so keep that free of effects: build clients
and pipelines inside functions, never at import. A factory is also called at import-free
moments by the view, so building the pipeline must not call a model, write a file the project
keeps, or reach the network.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any, Callable

from .errors import ConfigurationError

if TYPE_CHECKING:  # pragma: no cover
    from .pipeline import Pipeline

__all__ = ["pipeline_factory", "registered_pipelines", "clear_registered_pipelines"]

_FACTORIES: dict[str, Callable[[], "Pipeline"]] = {}


def pipeline_factory(name: str) -> Callable[[Callable[[], Any]], Callable[[], Any]]:
    """Register the decorated zero-argument function as the builder of one named pipeline.

    ::

        @pipeline_factory("ingest")
        def ingest() -> Pipeline:
            return Pipeline([...], budget=...)

        ingest().name           # 'ingest'

    The project calls the function exactly as before. What comes back carries the registered
    name, so a run of it records which pipeline it was, and a factory returning anything other
    than a pipeline is handed back untouched.

    Registering two factories under one name is refused: the name is an identity, and two
    pipelines answering to it would make every figure shown under it ambiguous.
    """
    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError(
            "pipeline_factory was given no name. The name is how the pipeline appears "
            "everywhere a person sees it: @pipeline_factory('recommend')."
        )
    cleaned = name.strip()

    def register(factory: Callable[[], Any]) -> Callable[[], Any]:
        held = _FACTORIES.get(cleaned)
        # The registry holds the wrapper, so what is compared is the function it wraps.
        # Applying one decorator to one function twice, which a module imported under two
        # names does, registers the same pipeline rather than a second one.
        if held is not None and getattr(held, "__wrapped__", held) is not factory:
            raise ConfigurationError(
                f"pipeline_factory({cleaned!r}) is already registered to "
                f"{getattr(held, '__name__', held)!r}. One name names one pipeline; give "
                f"the second factory its own name."
            )

        @functools.wraps(factory)
        def build(*args: Any, **kwargs: Any) -> Any:
            built = factory(*args, **kwargs)
            _name_it(built, cleaned)
            return built

        _FACTORIES[cleaned] = build
        return build

    return register


def _name_it(built: Any, name: str) -> None:
    """Record the registered name on the pipeline the factory returned.

    A factory that returned something else is left alone: the view reports what it got
    (`docs/view.md` §2), and raising here would break a project the moment it registered a
    function that builds something other than a pipeline.
    """
    from .pipeline import Pipeline

    if isinstance(built, Pipeline):
        built.name = name


def registered_pipelines() -> dict[str, Callable[[], Any]]:
    """The registered factories by name, in registration order. A copy; mutating it registers nothing."""
    return dict(_FACTORIES)


def clear_registered_pipelines() -> None:
    """Empty the registry. For tests and for tooling that imports one project after another."""
    _FACTORIES.clear()
