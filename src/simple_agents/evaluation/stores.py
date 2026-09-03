"""What each rollout of an evaluation runs against, for a pipeline that reaches a store.

A rollout executes the real code, so a pipeline whose step writes a store writes it once per
rollout. Where the pipeline also reads that store back, sending the write to the run's
workspace measures a pipeline the product does not run, and sharing one store lets each
rollout answer out of what the last one wrote.

:class:`CopyPerRollout` is what closes that: the suite copies the store for each rollout,
hands the copy's path to the pipeline in its inputs, and deletes it when the rollout ends.
:class:`Shared` is the declaration for a store no rollout writes.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..errors import ConfigurationError

__all__ = [
    "CopyPerRollout",
    "Isolation",
    "Shared",
    "copies_for",
    "refuse_a_collision",
    "refuse_an_unisolated_store",
    "remove",
    "stores_record",
]

# A resource name is any non-empty string, and it becomes part of a path here.
_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class CopyPerRollout:
    """A store copied for each rollout, so no rollout reads what another wrote.

    ``source`` is the store as the product holds it: a file, or a directory copied whole.
    ``as_input`` is the input key the copy's path arrives under, which is the same key the
    pipeline reads in production::

        suite.run(envelope=env, model=client, split="held_out", k=5,
                  stores={"catalogue": CopyPerRollout("data/shows.db", as_input="db_path")})

    The path is put into the rollout's inputs after the example set is hashed, so a copy that
    is somewhere different each run leaves ``content_hash`` and ``eval_id`` alone and two
    evaluations still compare. A node reaches it through ``ctx.run_inputs[as_input]``.

    The copy is made before the rollout starts and deleted when it ends, whether the rollout
    passed or failed. A rollout that suspended keeps its copy, since the run is waiting and
    can be continued against it. One copy is made per rollout, so a 51MB store over 23
    rollouts is 1.1GB written and removed.
    """

    source: str | os.PathLike[str]
    as_input: str

    def __post_init__(self) -> None:
        if not str(self.as_input).strip():
            raise ConfigurationError(
                f"CopyPerRollout({str(self.source)!r}) declares no as_input, so the copy has "
                f"no key to arrive under and the pipeline cannot find it.\n"
                f"Name the input key the pipeline reads the store's path from: "
                f"CopyPerRollout({str(self.source)!r}, as_input='db_path')."
            )


@dataclass(frozen=True, slots=True)
class Shared:
    """A store every rollout reaches as it is, with the reason that is safe here.

    For a store the pipeline reads and never writes, such as a corpus or a catalogue::

        stores={"embeddings": Shared("read-only; no step of this pipeline writes it")}

    ``reason`` goes into the results file, so a figure measured against a shared store says
    so beside itself.
    """

    reason: str

    def __post_init__(self) -> None:
        if not str(self.reason).strip():
            raise ConfigurationError(
                "Shared() declares no reason. A shared store is what let rollouts read each "
                "other's writes, so the reason it is safe here is recorded in the results "
                "file beside the figure it produced.\n"
                "Say what makes it safe: Shared('read-only; no step of this pipeline writes "
                "it')."
            )


Isolation = CopyPerRollout | Shared


def refuse_an_unisolated_store(pipeline: Any, stores: Mapping[str, Isolation], verb: str) -> None:
    """Refuse an evaluation over a pipeline whose steps reach a store it says nothing about.

    A node's ``touches=`` names a resource it reaches in its own code, and says nothing about
    which direction. What an evaluation does about it is a decision about the store, so it is
    answered per resource rather than by a flag over all of them.
    """
    declared: dict[str, list[str]] = {}
    for node_id, node in pipeline.declared_nodes():
        for resource in getattr(node, "touches", ()) or ():
            declared.setdefault(str(resource), []).append(str(node_id))
    missing = sorted(set(declared) - set(stores))
    if not missing:
        return
    named = ", ".join(f"{name!r} (declared by {', '.join(declared[name])})" for name in missing)
    first = missing[0]
    raise ConfigurationError(
        f"Evaluation refused to {verb}: {named} is reached by a step of this pipeline and "
        f"this evaluation says nothing about it. Rollouts run the real code, so a store they "
        f"share serves each of them what the last one wrote, and the figure that comes out "
        f"describes none of them.\n"
        f"Say what each store does here: stores={{{first!r}: "
        f"CopyPerRollout('data/store.db', as_input='store_path')}} copies it per rollout and "
        f"deletes the copy, and stores={{{first!r}: Shared('read-only; no step writes it')}} "
        f"records that sharing it is safe. `docs/evaluation.md` §6.9."
    )


def refuse_a_collision(stores: Mapping[str, Isolation]) -> None:
    """Refuse two stores that would write over each other, before any rollout runs.

    Two ``as_input`` keys the same means one copy is never reachable, and two names that file
    to the same path means one copy overwrites the other. Both would produce a figure measured
    against a store the caller did not describe.
    """
    keys: dict[str, list[str]] = {}
    files: dict[str, list[str]] = {}
    for name, isolation in sorted(stores.items()):
        if not isinstance(isolation, CopyPerRollout):
            continue
        keys.setdefault(isolation.as_input, []).append(name)
        files.setdefault(_filed_as(name, Path(isolation.source).suffix), []).append(name)
    for shared_key, names in keys.items():
        if len(names) > 1:
            raise ConfigurationError(
                f"stores= gives {' and '.join(repr(n) for n in names)} the same "
                f"as_input={shared_key!r}, so one rollout's copies would arrive under one key "
                f"and only the last would be reachable.\n"
                f"Give each store its own input key."
            )
    for filename, names in files.items():
        if len(names) > 1:
            raise ConfigurationError(
                f"stores= names {' and '.join(repr(n) for n in names)}, which both file their "
                f"copy as {filename!r} and would write over each other.\n"
                f"A copy is filed under the resource name with anything but letters, digits, "
                f"'_', '.' and '-' replaced. Rename one of the resources."
            )


def _filed_as(name: str, suffix: str) -> str:
    """The filename a store's copy takes, derived from the resource name.

    A resource name is whatever the node declared, so the copy is filed under a name derived
    from it rather than under the name itself: 'catalogue/v2' would otherwise nest a directory
    and '../x' would write outside the rollout.
    """
    return f"{_SAFE_NAME.sub('_', name).strip('_') or 'store'}{suffix}"


def copies_for(root: Path, stores: Mapping[str, Isolation]) -> tuple[dict[str, Any], list[Path]]:
    """One rollout's store copies, as inputs to add and the paths to remove afterwards.

    Each :class:`CopyPerRollout` is copied under ``root``. A :class:`Shared` store is left
    alone and adds nothing. Returns the input overlay and what the caller deletes.
    """
    overlay: dict[str, Any] = {}
    made: list[Path] = []
    for name, isolation in sorted(stores.items()):
        if not isinstance(isolation, CopyPerRollout):
            continue
        source = Path(isolation.source)
        if not source.exists():
            raise ConfigurationError(
                f"stores={{{name!r}: CopyPerRollout({str(source)!r}, ...)}} names a store that "
                f"is not there, so there is nothing to copy for this rollout.\n"
                f"Give the path the product holds the store at, relative to where the "
                f"evaluation runs or absolute."
            )
        target = root / "stores" / _filed_as(name, source.suffix)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        overlay[isolation.as_input] = str(target)
        made.append(target)
    return overlay, made


def remove(made: list[Path]) -> None:
    """Delete a rollout's copies, whatever the rollout did."""
    for target in made:
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)


def stores_record(stores: Mapping[str, Isolation]) -> dict[str, Any]:
    """What the results file records about each store this evaluation ran against."""
    record: dict[str, Any] = {}
    for name, isolation in sorted(stores.items()):
        if isinstance(isolation, CopyPerRollout):
            record[name] = {
                "isolation": "copy_per_rollout",
                "source": str(isolation.source),
                "as_input": isolation.as_input,
            }
        else:
            record[name] = {"isolation": "shared", "reason": isolation.reason}
    return record
