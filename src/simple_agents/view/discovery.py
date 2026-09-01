"""Finding a project's pipelines by importing its `agent.py`, without running anything.

The convention: a factory registered with `@pipeline_factory("name")` builds one pipeline,
and importing the module is effect-free. A module-level `Pipeline` is picked up too, under
the name it is bound to, so a project that predates the convention still draws.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..product import clear_registered_product, registered_product
from ..registry import clear_registered_pipelines, registered_pipelines

AGENT_MODULE = "agent.py"


@dataclass(slots=True)
class LoadedProject:
    """What importing the project produced: pipelines by name, and what went wrong.

    ``problems`` is written for the person reading the page: each entry says what could not
    be read and why, in one sentence.
    """

    pipelines: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    imported: bool = False

    could_not_import: str | None = None
    """Why `agent.py` would not import, or ``None``. A project with no `agent.py` is
    ``None`` too: nothing was attempted, so nothing failed."""

    product: Any = None
    """The declared ``Product``, or ``None`` where the project declares none."""

    product_module: str | None = None
    """The module that declares it, which is the one whose numbers are the surface's own."""

    product_parameters: list = field(default_factory=list)
    """Every module-level number that module defines, read while it is still imported."""


def load_project(root: str | Path) -> LoadedProject:
    """Import ``<root>/agent.py`` and collect every pipeline it declares.

    ::

        loaded = load_project(".")
        loaded.pipelines            # {"recommend": <Pipeline>, ...}

    A factory that raises is reported in ``problems`` and the rest still load. A project
    with no ``agent.py`` returns with ``imported=False``, which is a project before its
    first line of code and not an error.
    """
    from ..pipeline import Pipeline

    target = Path(root).expanduser() / AGENT_MODULE
    found = LoadedProject()
    if not target.exists():
        return found

    clear_registered_pipelines()
    clear_registered_product()
    module_name = f"_simple_agents_view_{abs(hash(str(target.resolve())))}"
    spec = importlib.util.spec_from_file_location(module_name, target)
    if spec is None or spec.loader is None:
        found.problems.append(f"{AGENT_MODULE} exists but could not be loaded as a module.")
        return found
    module = importlib.util.module_from_spec(spec)
    # Registered so imports inside the module that reference it by name resolve, and removed
    # after, so two projects loaded in one process never see each other.
    sys.modules[module_name] = module
    parent = str(target.parent.resolve())
    added_path = parent not in sys.path
    if added_path:
        sys.path.insert(0, parent)
    try:
        spec.loader.exec_module(module)
        found.imported = True
    except BaseException as error:  # noqa: BLE001 - reported to the reader, never swallowed
        _would_not_import(found, error)
        return found
    finally:
        if added_path and parent in sys.path:
            sys.path.remove(parent)
        sys.modules.pop(module_name, None)

    for name, factory in registered_pipelines().items():
        try:
            built = factory()
        except BaseException as error:  # noqa: BLE001
            found.problems.append(
                f"The pipeline {name!r} could not be built "
                f"({type(error).__name__}: {error}), so it is missing from the picture."
            )
            continue
        if not isinstance(built, Pipeline):
            found.problems.append(
                f"The factory registered as {name!r} returned "
                f"{type(built).__name__} rather than a Pipeline, so it is missing from "
                f"the picture."
            )
            continue
        found.pipelines[name] = built

    _take_the_product(found)

    registered = set(found.pipelines.values())
    for name, value in vars(module).items():
        if isinstance(value, Pipeline) and value not in registered and not name.startswith("_"):
            found.pipelines.setdefault(name, value)
    # Last, because everything above reads the modules this forgets.
    _drop_the_projects_modules(target.parent.resolve())
    return found


def _would_not_import(found: LoadedProject, error: BaseException) -> None:
    """Record why `agent.py` raised, for the frame that would otherwise be blank.

    Two readers, so two forms of it. `could_not_import` is the error alone, which the empty
    drawing and the attention card put in front of the builder. `problems` is the sentence
    that says what the page did about it.
    """
    found.could_not_import = f"{type(error).__name__}: {error}"
    found.problems.append(
        f"{AGENT_MODULE} could not be imported ({found.could_not_import}), so the page shows "
        f"the run record only. Importing it must be free of effects: build clients and "
        f"pipelines inside functions."
    )


def _take_the_product(found: LoadedProject) -> None:
    """Build the declared product, and report a factory that refuses to build.

    A product that cannot be built leaves the rest of the page intact, the way a pipeline
    that cannot be built does: the picture is worth more than the one thing missing from it.
    """
    from ..records.manifest import module_constants
    from ..product import Product

    factory = registered_product()
    if factory is None:
        return
    try:
        built = factory()
    except BaseException as error:  # noqa: BLE001 - reported to the reader, never swallowed
        found.problems.append(
            f"The product could not be built ({type(error).__name__}: {error}), so the page "
            f"shows no surfaces."
        )
        return
    if not isinstance(built, Product):
        found.problems.append(
            f"The registered product factory returned {type(built).__name__} rather than a "
            f"Product, so the page shows no surfaces."
        )
        return
    found.product = built
    found.product_module = getattr(factory, "__module__", None)
    # Read here rather than by the page: the module is dropped from `sys.modules` on the way
    # out, and a number is read from the module the factory came from.
    found.product_parameters = module_constants([factory])


_RESOLVED: dict[str, str] = {}

# Where an installed package lives. A virtual environment usually sits inside the project
# directory, so being under the project root does not make a module the project's own.
_INSTALLED = ("site-packages", "dist-packages")

# The library's own directory, kept whole whatever path it was installed to.
_LIBRARY = os.path.realpath(str(Path(__file__).resolve().parent.parent)) + os.sep


def _the_projects_own(resolved: str, inside: str) -> bool:
    """Whether this file is the project's own source rather than something it installed.

    Under the project directory and outside any virtual environment. `uv` writes the
    environment to `<project>/.venv`, which puts every installed package under the project
    root, and dropping those unimports the library itself.
    """
    if not resolved.startswith(inside) or resolved.startswith(_LIBRARY):
        return False
    return not any(one in resolved.split(os.sep) for one in _INSTALLED)


def _drop_the_projects_modules(root: Path) -> None:
    """Forget every module the project imported, so loading it twice runs it twice.

    A registration is module-level code, and a module Python has already imported does not
    run again: a project whose factory lives beside `agent.py` rather than in it registered on
    the first load and on no later one. The page and the checks both load a project in one
    process, so the second reading saw a project declaring nothing.

    Only the project's own source goes. The library's own modules and every installed package
    stay imported: dropping those re-imports the library on the next call, which gives every
    exception class a second identity and empties the pipeline registry the project just
    registered into.
    """
    inside = str(root.resolve()) + os.sep
    for name, module in list(sys.modules.items()):
        where = getattr(module, "__file__", None)
        if not where:
            continue
        resolved = _RESOLVED.get(where)
        if resolved is None:
            try:
                resolved = _RESOLVED[where] = os.path.realpath(where)
            except OSError:
                continue
        if _the_projects_own(resolved, inside):
            sys.modules.pop(name, None)
