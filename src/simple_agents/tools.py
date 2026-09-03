"""The tool contract, the registry, and `finish`.

A tool must declare a side-effect class so that the agent can be evaluated. Evaluation runs k
rollouts per example, so a tool that sends an email or places an order would perform k real
actions per example. The class is recorded on every tool call and in the run manifest, and
``simple_agents.evaluation`` reads it to refuse a rollout over a tool whose effects reach
outside the run.

A tool call is served from the cassette under a key made from its name, its version, its
arguments and how many times that same call has already been made in this run. A tool whose
signature asks for a handle is re-run during replay instead, and the rule it must satisfy is
that **it may reach the outside world only through the handles it was given**.
``docs/tools.md`` covers both, and the built-in set lives in ``simple_agents.builtins``.

**Credentials go in a ``pydantic.SecretStr``**, which is redacted by its type wherever it is
recorded. Two limits: a string built from one is an ordinary string, and a cassette key hashes
one as its mask, so two calls differing only in a typed secret share a key.

An agent node terminates on an explicit ``finish`` call, validated against the node's output
schema. Model output is never inspected for signs of completion.
"""

from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Callable,
    Iterable,
    Iterator,
    Mapping,
    Sequence,
    get_args,
    get_origin,
    get_type_hints,
)

from pydantic import ValidationError as PydanticValidationError
from pydantic import create_model

from .errors import ConfigurationError, ModelFacingError
from .records.conversation import Conversation
from .memory import Memory
from .schema import json_schema_for_model

__all__ = [
    "SideEffectClass",
    "DeclaredCost",
    "Tool",
    "tool",
    "ToolRegistry",
    "ModelHandle",
    "Workspace",
    "Retrieval",
    "Reading",
    "SpendMeter",
    "Conversation",
    "Memory",
    "HostPolicy",
    "NodeInput",
    "Admission",
    "ConsultTool",
    "ANSWERED_BY",
    "FinishTool",
    "FINISH_TOOL_NAME",
    "derived_version",
]

FINISH_TOOL_NAME = "finish"


class SideEffectClass(str, Enum):
    """What a tool does to the world. Declared by the tool author, never inferred.

    ``READ_ONLY`` and ``WRITES`` confined to the run's workspace are the classes an evaluation
    may execute during a rollout. ``SPENDS_MONEY`` and ``IRREVERSIBLE`` reach outside the run,
    so k rollouts would perform k real actions.
    """

    READ_ONLY = "read_only"
    WRITES = "writes"
    SPENDS_MONEY = "spends_money"
    IRREVERSIBLE = "irreversible"

    @property
    def reaches_outside_the_run(self) -> bool:
        """Whether repeating this k times during an evaluation acts on the world k times."""
        return self in (SideEffectClass.SPENDS_MONEY, SideEffectClass.IRREVERSIBLE)


@dataclass(frozen=True, slots=True)
class DeclaredCost:
    """What one call to a tool costs and how long it takes, as declared rather than measured.

    Recorded on every ``tool_call`` and in the run manifest, so an evaluation can price k×n
    rollouts before running them::

        DeclaredCost(currency="USD", per_call=0.005, latency_ms=800)

    Required on a ``SPENDS_MONEY`` tool, where the figure is the point. ``per_call`` needs a
    ``currency`` beside it; a bare number cannot be added to anything.

    ``max_per_call`` is the most one call can cost, for a tool whose price varies with the
    request. ``max_cost`` is checked against it before the call rather than after, so the
    limit holds exactly::

        DeclaredCost(currency="USD", per_call=0.002, max_per_call=0.02)

    Without it the limit is checked against ``per_call``, and a run can exceed by whatever one
    call cost beyond that.
    """

    currency: str | None = None
    per_call: float | None = None
    latency_ms: int | None = None
    max_per_call: float | None = None

    def __post_init__(self) -> None:
        if self.per_call is not None and not self.currency:
            raise ConfigurationError(
                f"DeclaredCost(per_call={self.per_call}) was given no currency. A figure with "
                f"no unit cannot be summed across tools or compared against a budget.\n"
                f"Pass DeclaredCost(currency='USD', per_call={self.per_call})."
            )
        if self.max_per_call is not None:
            if not self.currency:
                raise ConfigurationError(
                    f"DeclaredCost(max_per_call={self.max_per_call}) was given no currency. A "
                    f"ceiling with no unit cannot be compared against a budget.\n"
                    f"Pass DeclaredCost(currency='USD', max_per_call={self.max_per_call})."
                )
            if self.per_call is not None and self.max_per_call < self.per_call:
                raise ConfigurationError(
                    f"DeclaredCost(per_call={self.per_call}, "
                    f"max_per_call={self.max_per_call}) says one call costs more than the most "
                    f"a call can cost.\n"
                    f"Raise max_per_call to the worst case, or drop it where every call costs "
                    f"the same."
                )

    @property
    def ceiling(self) -> float | None:
        """The most one call can cost: ``max_per_call`` where declared, else ``per_call``."""
        return self.max_per_call if self.max_per_call is not None else self.per_call

    def to_record(self) -> dict[str, Any]:
        """What the trajectory and the manifest store. All four keys always present."""
        return {
            "currency": self.currency,
            "per_call": self.per_call,
            "latency_ms": self.latency_ms,
            "max_per_call": self.max_per_call,
        }


@dataclass(frozen=True, slots=True)
class ModelHandle:
    """A model call made from inside a tool, recorded and replayed like any other.

    A tool whose signature asks for one is re-run during replay rather than served from the
    cassette, and the model call it makes is served instead, so the trajectory a replay writes
    matches the one the live run wrote. The parameter is filled by the library and is not
    offered to the model::

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def summarise(model: ModelHandle, text: str) -> str:
            \"\"\"Summarise a passage in two sentences.\"\"\"
            asked = Prompt.user("Summarise in two sentences:\\n{text}", text=text)
            return model.complete(asked).content or ""

    The tool may reach the outside world only through this handle. A request written directly
    in the body is invisible to the library and is made again on every replay and on every
    rollout of an evaluation.
    """

    _complete: Callable[..., Any] = field(repr=False)

    def complete(
        self,
        prompt: Any,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        """Make one model call. ``prompt`` is a `Prompt`, as a node's prompt function returns.

        Returns a ``ModelResponse``; its ``content`` is the text. The call is charged to the
        run's budget and emitted as a ``model_call`` record parented to this tool call.
        """
        return self._complete(
            prompt,
            output_schema=output_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class Workspace:
    """The run's own directory, for a tool that reads or writes files.

    A tool whose signature asks for one is re-run during replay rather than served from the
    cassette, so a replayed run writes the same files into its own fresh directory and a later
    step that reads them finds them. The parameter is filled by the library and is not offered
    to the model::

        @tool(side_effect_class=SideEffectClass.WRITES)
        def save_note(workspace: Workspace, path: str, content: str) -> str:
            \"\"\"Write a note into the run's workspace. Returns the path written.\"\"\"
            workspace.write_text(path, content)
            return path

    Paths are relative to the workspace root. One that escapes it raises
    :class:`~simple_agents.errors.ModelFacingError`, so the model is told to try another path
    rather than the run ending.
    """

    root: Path

    def resolve(self, relative: str) -> Path:
        """The absolute path for a relative one, refusing anything outside the workspace."""
        candidate = (self.root / relative).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ModelFacingError(
                f"The path {relative!r} resolves outside the run's workspace. Only paths "
                f"inside it can be read or written. Pass a path relative to the workspace "
                f"root, such as 'notes.txt' or 'drafts/summary.md'.",
                retryable=False,
            )
        return candidate

    def read_text(self, relative: str) -> str:
        """The file's contents. Raises ``ModelFacingError`` when it is not there."""
        target = self.resolve(relative)
        try:
            return target.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ModelFacingError(
                f"No file at {relative!r} in the run's workspace. Files present: "
                f"{', '.join(self.listing()) or '(none)'}.",
                retryable=False,
            ) from exc

    def write_text(self, relative: str, content: str) -> Path:
        """Write the file, creating parent directories. Returns the absolute path."""
        target = self.resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def listing(self) -> list[str]:
        """Every file in the workspace, as paths relative to its root, sorted."""
        if not self.root.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*") if p.is_file())


@dataclass(frozen=True, slots=True)
class Retrieval:
    """The recorded path for the model calls a search makes, filled by the library.

    A tool whose signature asks for one is re-run during replay rather than served from the
    cassette, and the embedding and reranking calls it makes are served instead, so the
    trajectory a replay writes matches the live run's. The parameter is not offered to the
    model::

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def find(retrieval: Retrieval, query: str) -> list[str]:
            \"\"\"Find the passages closest to a query.\"\"\"
            vector = retrieval.embed(embedder, [query])[0]
            return [doc_id for doc_id, _ in store.search(vector, top_k=5)]

    ``client`` is passed in by the caller rather than held here, because which model embeds a
    corpus is a property of the index that holds it. A call made on a client directly, without
    going through this, is charged to no budget and is made again on every replay.
    """

    _embed: Callable[..., Any] = field(repr=False)
    _rerank: Callable[..., Any] = field(repr=False)

    def embed(self, client: Any, texts: Sequence[str]) -> list[list[float]]:
        """One unit-length vector per text, in the order given.

        ``client`` is an :class:`~simple_agents.EmbeddingClient`. The call is charged to the
        run's budget and emitted as a ``model_call`` record parented to this tool call.
        """
        return self._embed(client, list(texts))

    def rerank(self, client: Any, query: str, documents: Sequence[str]) -> list[Any]:
        """``RerankScore`` per document, most relevant first.

        ``client`` is a :class:`~simple_agents.RerankClient`. Each score carries the ``index``
        of the document in the list given, so the caller keeps whatever it holds alongside
        them.
        """
        return self._rerank(client, query, list(documents))


@dataclass(frozen=True, slots=True)
class SpendMeter:
    """What a tool reports it was charged, so the run's spend is measured rather than declared.

    A tool whose signature asks for one calls :meth:`spend` after the vendor has answered, with
    what that call actually cost. The parameter is filled by the library and is not offered to
    the model::

        @tool(side_effect_class=SideEffectClass.SPENDS_MONEY, declared_cost=PAID)
        def search(meter: SpendMeter, query: str) -> list[dict]:
            \"\"\"Search the web. Costs money unless the answer is already stored.\"\"\"
            stored = cache.get(query)
            if stored is not None:
                return stored
            results = provider(query)
            meter.spend(0.005)
            return results

    A tool holding one is authoritative: what it reports is what the call cost, and reporting
    nothing means the call cost nothing. The figure reaches the ``tool_call`` record as
    ``spent`` with ``source: "measured"``, and depletes the run's ``max_cost``.

    Unlike a ``ModelHandle`` or a ``Workspace``, taking this does not stop the tool being
    served from the cassette, so a replayed call reports nothing and spends nothing.
    """

    _spend: Callable[[float, str | None, str], None] = field(repr=False)

    def spend(
        self, amount: float, *, currency: str | None = None, source: str = "measured"
    ) -> None:
        """Report what this call was charged.

        ``currency`` defaults to the tool's ``declared_cost`` currency, and is the one the run
        uses. A run's totals are one number, so a figure in a second currency is refused here
        rather than added: convert it in the tool where the vendor bills in something else.
        Called more than once in a call, the amounts add up. A negative amount and a second
        currency both raise :class:`~simple_agents.errors.ConfigurationError`.

        ``source`` is what the record says the figure is. The default says the vendor
        returned it. A tool reporting a price it was told, so that a cache hit can report
        nothing, passes ``source="declared"``::

            meter.spend(declared_cost.per_call, source="declared")
        """
        if amount < 0:
            raise ConfigurationError(
                f"SpendMeter.spend({amount}) was given a negative amount. Report what the "
                f"call was charged, or report nothing where it was charged nothing."
            )
        self._spend(float(amount), currency, source)


@dataclass(frozen=True, slots=True)
class Reading:
    """The recorded path for the model call that reads an end user's answer.

    A consultation's reader receives one and makes its call through it, so the call is charged
    to the run's budget, emitted as a ``model_call`` record parented to the consultation, and
    served from the cassette on a replay::

        def read_the_answer(reading: Reading, answer: str, options: list[str]) -> str | None:
            \"\"\"Which offered option this answer meant, or None where it meant none.\"\"\"
            asked = Prompt.user("Options: {options}\\nAnswer: {answer}",
                                options=options, answer=answer)
            response = reading.complete(client, asked)
            return response.content.strip() or None

        registry.add(consult(ask_in_chat, answered_by="end_user", read=read_the_answer))

    ``client`` is passed in by the caller rather than held here, for the same reason
    :class:`Retrieval` takes one: which model reads an end user's prose is a property of the
    reader rather than of the node that asked the question.

    Unlike the five handles a tool's signature asks for, this one is never filled from a tool
    parameter. It reaches a reader, which the library calls itself.

    A call made on the client directly, without going through this, is charged to no budget,
    recorded nowhere, and made again on every replay and every rollout of an evaluation.
    """

    _complete: Callable[..., Any] = field(repr=False)

    def complete(
        self,
        client: Any,
        prompt: Any,
        *,
        output_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> Any:
        """Make one model call. ``prompt`` is a `Prompt`, as a node's prompt function returns.

        ``client`` is a :class:`~simple_agents.ModelClient`. Returns a ``ModelResponse``; its
        ``content`` is the text.
        """
        return self._complete(
            client,
            prompt,
            output_schema=output_schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class Admission:
    """One host brought into scope during a run, and why."""

    host: str
    reason: str

    def to_record(self) -> dict[str, str]:
        return {"host": self.host, "reason": self.reason}


def _site(host: str) -> str:
    """A host reduced to the site it belongs to, by dropping a leading ``www.``.

    ``www.example.com`` and ``example.com`` are one site. Treating them as two refuses a page
    the project meant to permit, and spends an admission on a site already in scope.
    """
    host = host.lower().strip()
    return host[4:] if host.startswith("www.") else host


@dataclass
class HostPolicy:
    """The hosts a run may fetch from, and what it may spend reading them.

    Passed to ``http_fetch`` or ``read_page`` in place of ``allow_hosts``, or declared on the
    pipeline::

        policy = HostPolicy(["docs.example.com"], max_admitted=5, max_fetches=60)
        registry.add(read_page(policy=policy))

    A subdomain of a host in scope is in scope, so ``help.example.com`` is reachable under
    ``example.com``. Leading ``www.`` is ignored on both sides.

    ``max_fetches`` is a ceiling on requests that reach the network for one run, whichever
    host they go to. It is a count of requests and not a sum of money.

    **The object built here is the declaration, and each run binds its own copy**, so two
    runs served by one process count separately. The run's copy is what admits and counts:
    a tool reaches it by annotating a parameter with this type, and a ``Deterministic``
    function or a route reads it at ``ctx.fetch_policy``::

        def choose(output, ctx):
            ctx.fetch_policy.admit("brand.example", reason="named on the listing")
            return "read_the_site"

    Calling ``admit`` or ``spend_fetch`` on the declaration itself raises, naming both
    routes, because an admission made there would reach no run.

    Admissions and the fetch count are written to each run's manifest under ``fetch_policy``.
    """

    hosts: frozenset[str]
    max_admitted: int = 0
    max_fetches: int | None = None
    admitted: dict[str, Admission] = field(default_factory=dict, init=False)
    fetches: int = field(default=0, init=False)
    _bound: bool = field(default=False, init=False, repr=False, compare=False)
    _lock: Any = field(default=None, init=False, repr=False, compare=False)

    def __init__(
        self,
        hosts: Iterable[str],
        *,
        max_admitted: int = 0,
        max_fetches: int | None = None,
    ) -> None:
        configured = frozenset(_site(host) for host in hosts if str(host).strip())
        if not configured:
            raise ConfigurationError(
                "HostPolicy was built with no hosts, so every fetch is refused before it "
                "starts. Pass the hosts the agent may read, such as "
                "HostPolicy(['docs.example.com']), and max_admitted=N to let the project add "
                "more while the run proceeds."
            )
        if max_fetches is not None and max_fetches <= 0:
            raise ConfigurationError(
                f"HostPolicy(max_fetches={max_fetches}) permits no request at all. Pass the "
                f"number of requests the run may make, or max_fetches=None for no ceiling."
            )
        object.__setattr__(self, "hosts", configured)
        object.__setattr__(self, "max_admitted", int(max_admitted))
        object.__setattr__(self, "max_fetches", max_fetches)
        object.__setattr__(self, "admitted", {})
        object.__setattr__(self, "fetches", 0)
        object.__setattr__(self, "_bound", False)
        object.__setattr__(self, "_lock", None)

    # -- binding --------------------------------------------------------------------------

    def for_run(self) -> HostPolicy:
        """This declaration bound for one run: fresh admissions, a fresh count, and a lock.

        The runtime calls this once per run per declaration. Concurrent tool calls inside one
        run share the copy, which is why it carries the lock the declaration does not.
        """
        bound = HostPolicy(self.hosts, max_admitted=self.max_admitted, max_fetches=self.max_fetches)
        object.__setattr__(bound, "_bound", True)
        object.__setattr__(bound, "_lock", threading.Lock())
        return bound

    def _refuse_unbound(self, doing: str) -> None:
        if not self._bound:
            raise ConfigurationError(
                f"HostPolicy.{doing} was called on the declaration rather than on a run's "
                f"own copy, so it would reach no run. Inside a node function or a route, "
                f"call it on ctx.fetch_policy. Inside a tool, annotate a parameter with "
                f"HostPolicy and call it on that parameter; the run fills it."
            )

    # -- scope ----------------------------------------------------------------------------

    def in_scope(self, host: str) -> bool:
        """Whether this host, or a site it belongs to, is reachable::

        policy.in_scope("help.example.com")   # True, under 'example.com'
        """
        site = _site(host)
        for allowed in (*self.hosts, *tuple(self.admitted)):
            if site == allowed or site.endswith("." + allowed):
                return True
        return False

    def admit(self, host: str, *, reason: str) -> Admission:
        """Bring a host into scope for the rest of the run, and record why.

        ``reason`` is free text and is written to the manifest, so a reader of the run can see
        what the agent reached and on what grounds::

            ctx.fetch_policy.admit("brand.example", reason="named in a search result")

        A host already in scope costs nothing and returns an admission saying so. Beyond
        ``max_admitted`` this raises ``ConfigurationError`` naming what has been admitted so
        far. A project calling this from a tool catches it and re-raises the sentence the model
        should read. Called on the declaration rather than on a run's copy, it raises naming
        both routes to the copy.
        """
        self._refuse_unbound("admit")
        site = _site(host)
        if not site:
            raise ConfigurationError(
                f"HostPolicy.admit({host!r}) was given no host. Pass a bare host such as "
                f"'brand.example', taken from the URL rather than the whole URL."
            )
        with self._lock:
            if self.in_scope(site):
                return Admission(host=site, reason="already in scope")
            if site in self.admitted:
                return self.admitted[site]
            if len(self.admitted) >= self.max_admitted:
                admitted = ", ".join(sorted(self.admitted)) or "none"
                raise ConfigurationError(
                    f"This run has admitted {len(self.admitted)} of {self.max_admitted} "
                    f"hosts ({admitted}), so {site} cannot be brought into scope. Raise "
                    f"max_admitted on the policy, configure the host up front, or work with "
                    f"what is in scope."
                )
            admission = Admission(host=site, reason=reason)
            self.admitted[site] = admission
            return admission

    # -- spending -------------------------------------------------------------------------

    def spend_fetch(self) -> None:
        """Charge one request against ``max_fetches``, or raise where the ceiling is reached.

        Called by the fetch tool for a request that reaches the network. Nothing served from a
        cache is charged, because nothing was requested. Called on the declaration rather than
        on a run's copy, it raises naming both routes to the copy.
        """
        self._refuse_unbound("spend_fetch")
        with self._lock:
            if self.max_fetches is not None and self.fetches >= self.max_fetches:
                raise _CeilingReached(
                    f"This run has made its limit of {self.max_fetches} page requests. Do "
                    f"not read any more pages. Answer from what has already been read, and "
                    f"say what is still unverified."
                )
            object.__setattr__(self, "fetches", self.fetches + 1)

    def refusal_for(self, host: str) -> str:
        """What the model is told when it addresses a host out of scope."""
        reachable = ", ".join(sorted(self.hosts | set(self.admitted)))
        return (
            f"This agent may not fetch from {host!r}. Permitted hosts: {reachable}. Read a "
            f"page on one of those, or report what could not be read."
        )

    # -- what the run records ---------------------------------------------------------------

    def to_record(self) -> dict[str, Any]:
        """What the manifest stores under ``fetch_policy``::

        {"hosts": [...], "admitted": [{"host": ..., "reason": ...}],
         "max_admitted": 5, "max_fetches": 60, "fetches": 23}
        """
        return {
            "hosts": sorted(self.hosts),
            "admitted": [a.to_record() for a in self.admitted.values()],
            "max_admitted": self.max_admitted,
            "max_fetches": self.max_fetches,
            "fetches": self.fetches,
        }


class _CeilingReached(Exception):
    """The run's fetch ceiling is spent. Carries the sentence the model is shown."""


@dataclass(frozen=True, slots=True)
class NodeInput:
    """The node's own input, given to a tool the node runs.

    The other six handles name something the library owns. This one names what the node was
    handed on its edges, which is the value its ``node_execution`` record holds under
    ``inputs``. It is written as annotation metadata rather than as the parameter's type,
    because the type of the value belongs to the project::

        from typing import Annotated

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def rank(query: str, pool: Annotated[list[dict], NodeInput("pool")]) -> list[dict]:
            \"\"\"Rank the shortlist against a query. Returns the ten closest.\"\"\"
            return closest(pool, query)[:10]

    ``NodeInput("pool")`` is the value under that key, and the node's input has to be a
    mapping carrying it. ``NodeInput`` with no key is the whole input, whatever shape it has::

        def rank(query: str, given: Annotated[dict, NodeInput]) -> list[dict]: ...

    A key the input does not carry, and a key on an input that is not a mapping, raise
    ``ConfigurationError`` where the tool is called. A tool reading something that is there on
    some runs and not others takes ``NodeInput`` with no key and reads it itself.

    A tool taking one is re-run on a replay rather than served from the cassette, because the
    node's input is not in the call's key: a stored answer would be served to a rollout that
    was handed something else.
    """

    key: str | None = None


HANDLE_TYPES: tuple[type, ...] = (
    ModelHandle,
    Workspace,
    SpendMeter,
    Memory,
    Conversation,
    Retrieval,
    HostPolicy,
    NodeInput,
)
"""What the library fills in and leaves out of the schema the model is shown.

Six name something the library owns and are written as the parameter's type. `NodeInput` names
the node's own input and is written as annotation metadata, since its type is the project's.
"""

RE_EXECUTED_HANDLE_TYPES: tuple[type, ...] = (
    ModelHandle,
    Workspace,
    Memory,
    Conversation,
    Retrieval,
    NodeInput,
)
"""Handles whose tool cannot be served from the cassette and runs again during a replay.

A `ModelHandle` is here because a tool served from the cassette writes no nested `model_call`
record, so a replay would write fewer records than the live run. A `Retrieval` is here for the
same reason: it makes model calls. A `Workspace` is here because a later step reads the files,
and a `Memory`, or a `Conversation`, because a later run does. A `NodeInput` is here because the input it carries is
not in the call's key, so one rollout's answer would be served to the next. A `SpendMeter`
reaches nothing outside the run, so it is not, and neither is a `HostPolicy`: a replayed fetch
is served rather than made, so it admits nothing and spends no request.
"""


@dataclass(slots=True)
class Tool:
    """A callable the model may invoke.

    ``description`` is prompt text read by the model. It determines when and how the tool is
    called, and should state what the tool does, what its arguments mean, and the cases in
    which it should not be used.

    ``fn`` reports failure by raising. :class:`~simple_agents.errors.ModelFacingError` covers
    failures the model can react to, such as an empty result set or a 404; the loop catches it
    and passes it to the model as an observation.
    :class:`~simple_agents.errors.CallerFacingError` covers a broken dependency and ends the
    run.

    ``redact_result`` redacts what this tool returns, once, where the call is made, so the
    model, the node and the cassette are given one string and a recording of the run replays.
    Declare it on a tool whose result carries a credential the model has no use for.
    ``Redaction.at_boundary`` decides which rules apply (``docs/tools.md`` §1.6).

    Build one with the :func:`tool` decorator rather than by hand, which derives ``parameters``
    and ``handles`` from the signature.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    side_effect_class: SideEffectClass
    fn: Callable[..., Any]
    version: str | None = None
    declared_cost: DeclaredCost | None = None
    touches: str | Sequence[str] | None = None
    """The resource this tool reads or writes, by name: ``touches="catalogue"``, or several.
    The same string wherever the resource is touched, so `simple-agents view` can draw what
    flows between the pipelines that share it. Direction is read from ``side_effect_class``:
    ``READ_ONLY`` reads the resource, every other class writes it. Normalised to a tuple."""
    handles: dict[str, type] = field(default_factory=dict)
    node_inputs: dict[str, str | None] = field(default_factory=dict)
    """The key each ``NodeInput`` parameter reads, by parameter name. A parameter named here
    with ``None``, and one not named at all, both read the whole input, so a ``Tool`` built by
    hand gets that without saying anything."""
    redact_result: bool = False
    fetch_policy: Any = field(default=None, repr=False, compare=False)
    """The ``HostPolicy`` declaration this tool was built with, or ``None``. A run binds its
    own copy of the declaration and fills the tool's ``HostPolicy`` parameter with the copy;
    a tool declaring none is filled from the pipeline's ``fetch_policy=``."""
    searches: Any = field(default=None, repr=False, compare=False)
    """The ``DocumentIndex`` this tool searches, or ``None``. Set by ``document_search``. The
    manifest reads how the index ranks off it, and reads the size of the corpus off it again
    when the run ends, since a run that adds documents changes that."""
    _validator: Callable[..., Any] | None = None
    _accepts: frozenset[str] | None = None
    _derived: str | None = field(default=None, repr=False)
    """The hash of ``fn``, taken when this tool was declared. ``version`` is this where the
    author declared none, and a ``Tool`` built by hand with neither records the hash here so
    its body is traced somewhere."""

    def __post_init__(self) -> None:
        self._derived = derived_version(self.fn)
        self.touches = normalized_touches(self.touches, where=f"Tool {self.name!r}")
        if not isinstance(self.side_effect_class, SideEffectClass):
            raise ConfigurationError(
                f"Tool {self.name!r} was given side_effect_class="
                f"{self.side_effect_class!r}, which is not a SideEffectClass. A tool cannot "
                f"be registered without one, because an evaluation reads it to decide "
                f"whether the tool may execute inside a rollout (FT-19).\n"
                f"Use SideEffectClass.READ_ONLY for a tool that is safe to call repeatedly, "
                f"or WRITES, SPENDS_MONEY, or IRREVERSIBLE otherwise. A tool whose class is "
                f"unclear is not READ_ONLY."
            )
        if not self.description.strip():
            raise ConfigurationError(
                f"Tool {self.name!r} has no description. The description is prompt text the "
                f"model reads to decide when and how to call the tool, so an empty one "
                f"leads to misuse. State what the tool does, what its arguments mean, and "
                f"when it should not be called (FT-23)."
            )
        if self.declared_cost is not None and not isinstance(self.declared_cost, DeclaredCost):
            raise ConfigurationError(
                f"Tool {self.name!r} was given declared_cost="
                f"{self.declared_cost!r}, which is not a DeclaredCost. Pass "
                f"DeclaredCost(currency='USD', per_call=0.005, latency_ms=800)."
            )
        if self.side_effect_class is SideEffectClass.SPENDS_MONEY and (
            self.declared_cost is None or self.declared_cost.per_call is None
        ):
            raise ConfigurationError(
                f"Tool {self.name!r} is declared SPENDS_MONEY and declares no per-call cost. "
                f"An evaluation runs k rollouts over n examples, so the bill is k×n times "
                f"this figure and is worth knowing before the run rather than after it.\n"
                f"Pass declared_cost=DeclaredCost(currency='USD', per_call=0.005). Declare "
                f"the price the provider charges, not an average over a workload."
            )
        if self.re_executed and self.side_effect_class.reaches_outside_the_run:
            names = ", ".join(
                sorted(
                    t.__name__
                    for t in set(self.handles.values())
                    if issubclass(t, RE_EXECUTED_HANDLE_TYPES)
                )
            )
            raise ConfigurationError(
                f"Tool {self.name!r} takes a {names} and declares "
                f"side_effect_class={self.side_effect_class.name}. A tool taking a handle is "
                f"re-run during replay rather than served from the cassette, so whatever it "
                f"does happens again on every replay and on every rollout of an evaluation. "
                f"It may reach the outside world only through the handles it was given: a "
                f"model call made through a ModelHandle is served from the cassette and "
                f"costs nothing, and a request written directly in the body is not.\n"
                f"Declare READ_ONLY, or WRITES for a tool that only writes inside the run's "
                f"workspace, and move whatever spends or cannot be undone into a separate "
                f"tool that takes no handle."
            )

    @property
    def re_executed(self) -> bool:
        """Whether replay re-runs this tool rather than serving a recorded return value.

        True for a tool taking a ``ModelHandle`` or a ``Workspace``. Everything such a tool
        does through its handles is recorded and replayed individually, so the records a
        replay writes match the live run's. A ``SpendMeter`` does not put a tool here: it
        reaches nothing outside the run, and a replayed call spends nothing.
        """
        return any(issubclass(held, RE_EXECUTED_HANDLE_TYPES) for held in self.handles.values())

    def to_wire(self) -> dict[str, Any]:
        """The tool as a model backend expects to receive it."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }

    def call(self, arguments: dict[str, Any], handles: dict[str, Any] | None = None) -> Any:
        """Invoke the tool with the arguments the model supplied.

        An argument the tool does not take raises
        :class:`~simple_agents.errors.ModelFacingError`, so the loop hands the failure back for
        the model to correct rather than ending the run. This holds however the schema was
        declared. A function taking ``**kwargs`` accepts anything and is not checked, which is
        how a tool absorbs an argument and reports back that it was ignored.

        Types are validated as well when the schema was derived from the signature. A schema
        passed as ``parameters=`` describes a shape the derivation could not express, so the
        library checks the argument names against the function and leaves the types to it.

        ``handles`` is supplied by the library, one per handle parameter in the signature.
        """
        if self._accepts is not None:
            unknown = sorted(set(arguments) - self._accepts)
            if unknown:
                raise ModelFacingError(
                    f"Call to {self.name!r} passed {unknown}, which it does not take. "
                    f"It takes {sorted(self._accepts)}. Call it again using only those, and "
                    f"do not supply an argument that is not in the tool's schema."
                )
        if self._validator is not None:
            try:
                self._validator(**arguments)
            except PydanticValidationError as exc:
                raise ModelFacingError(
                    f"Call to {self.name!r} does not match its schema: "
                    f"{_first_error(exc)}. Arguments given: {sorted(arguments)}."
                ) from exc
        return self.fn(**arguments, **(handles or {}))


class ToolRegistry:
    """The tools a project makes available, by name.

    Construct one, add every tool to it, and hand it to the nodes that need them. It holds no
    global state, so two projects in one process do not share a namespace and a test does not
    depend on import order::

        registry = ToolRegistry([document_search(index), now()])
        registry.add(save_note)

        node = AgentNode(build_prompt, tools=registry, output_schema=Answer, budget=budget)

    Registration refuses a tool with no side-effect class, a duplicate name, and the reserved
    name ``finish``. An ``AgentNode`` accepts a registry or a plain list; the registry is what
    lets a project enumerate every tool it declared, including ones no node uses yet.
    """

    def __init__(self, tools: Iterable[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {}
        for item in tools:
            self.add(item)

    def add(self, tool: Tool) -> Tool:
        """Register one tool and return it, so it can be used as a statement or an expression."""
        if not isinstance(tool, Tool):
            raise ConfigurationError(
                f"ToolRegistry.add was given {type(tool).__name__}, not a Tool. Decorate the "
                f"function first: @tool(side_effect_class=SideEffectClass.READ_ONLY)."
            )
        if tool.name == FINISH_TOOL_NAME:
            raise ConfigurationError(
                f"A tool cannot be named {FINISH_TOOL_NAME!r}. The name is reserved: the "
                f"library supplies `finish` itself, validated against each node's "
                f"output_schema, so that termination is an explicit schema-checked call. "
                f"Rename the tool."
            )
        if tool.name in self._tools:
            raise ConfigurationError(
                f"This registry already holds a tool named {tool.name!r}. The model selects "
                f"tools by name, so a duplicate makes dispatch ambiguous and the trajectory "
                f"cannot say which one ran.\n"
                f"Give each tool a distinct name: @tool(side_effect_class=..., "
                f"name='search_products'). It defaults to the function's name, so two tools "
                f"built from one factory collide unless a name is passed."
            )
        self._tools[tool.name] = tool
        return tool

    def add_all(self, tools: Iterable[Tool]) -> list[Tool]:
        """Register every tool in ``tools`` and return them, for a factory that builds several::

            registry.add_all(tickets.tools(effects={"search": SideEffectClass.READ_ONLY}))

        Each is registered on the same terms :meth:`add` applies, so a duplicate name is
        refused and nothing is registered after it.
        """
        return [self.add(one) for one in tools]

    def get(self, name: str) -> Tool:
        """The tool registered under ``name``, or a refusal listing what is registered."""
        try:
            return self._tools[name]
        except KeyError:
            raise ConfigurationError(
                f"No tool named {name!r} is registered. Registered: "
                f"{', '.join(self.names()) or '(none)'}. Add it with registry.add(...)."
            ) from None

    def names(self) -> tuple[str, ...]:
        """Every registered name, in registration order."""
        return tuple(self._tools)

    def to_manifest(self) -> list[dict[str, Any]]:
        """What the run manifest records for each tool: the declarations, not the code."""
        return [
            {
                "name": t.name,
                "version": t.version,
                "side_effect_class": t.side_effect_class.value,
                "declared_cost": t.declared_cost.to_record() if t.declared_cost else None,
                "re_executed": t.re_executed,
            }
            for t in self._tools.values()
        ]

    def __iter__(self) -> Iterator[Tool]:
        return iter(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


def tool(
    *,
    side_effect_class: SideEffectClass,
    name: str | None = None,
    description: str | None = None,
    parameters: dict[str, Any] | None = None,
    version: str | None = None,
    declared_cost: DeclaredCost | None = None,
    touches: str | Sequence[str] | None = None,
    redact_result: bool = False,
) -> Callable[[Callable[..., Any]], Tool]:
    """Turn a function into a :class:`Tool`.

    ``side_effect_class`` is keyword-only and has no default, so it cannot be set by
    omission. The function's docstring becomes the model-facing description unless
    ``description`` is given::

        @tool(side_effect_class=SideEffectClass.READ_ONLY)
        def look_up(query: str) -> str:
            \"\"\"Search the indexed documents. Returns matching passages, or an
            empty string when nothing matches. Do not call this for questions about
            the current date.\"\"\"
            return index.search(query)

    The schema the model is shown is derived from the signature: each annotated parameter becomes
    a property and one without a default is required, so ``look_up`` takes a required ``query``.

    A parameter annotated with a handle type is filled by the library and left out of the
    schema the model sees. ``docs/tools.md`` §3.2 lists the seven and says which re-run.
    ``redact_result=True`` redacts the result before the model reads it, so a credential in
    one does not stop a recording replaying (``docs/tools.md`` §1.6)::

        @tool(side_effect_class=SideEffectClass.READ_ONLY, redact_result=True)
        def fetch_page(url: str) -> dict:
            \"\"\"Fetch one page from the supplier portal. Returns its body and headers.\"\"\"
            return {"headers": dict(response.headers), "body": response.text}

    ``version`` is in the cassette key. Left unset it is derived from the function's source;
    :func:`derived_version` says what that covers.

    Pass ``parameters`` to supply the schema directly, for a signature the derivation cannot
    express; the names are still checked against the function. **An argument the model invents
    is refused and handed back for correction**, so a guess costs one step rather than the run.
    ``**kwargs`` receives everything instead, which is how a tool absorbs one and says so::

        @tool(side_effect_class=SideEffectClass.READ_ONLY, parameters={
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        })
        def find_book(title: str, **extra) -> dict:
            \"\"\"Look one book up by title. Returns what the catalogue holds.\"\"\"
            found = catalogue.get(title)
            if not extra:
                return found
            return {**found, "ignored_arguments": sorted(extra)}

    Raise :class:`~simple_agents.errors.ModelFacingError` for a failure the model can act on.
    """

    def decorate(fn: Callable[..., Any]) -> Tool:
        tool_name = name or fn.__name__
        hints = _resolved_hints(fn, tool_name)
        handles, node_inputs = _handles_in_signature(fn, hints, tool_name)
        if parameters is not None:
            schema, validator = parameters, None
            _refuse_undeliverable_properties(fn, tool_name, schema, handles)
        else:
            schema, validator = _schema_from_signature(fn, tool_name, hints, handles)
        return Tool(
            name=tool_name,
            description=description or inspect.getdoc(fn) or "",
            parameters=schema,
            side_effect_class=side_effect_class,
            fn=fn,
            version=version or derived_version(fn),
            declared_cost=declared_cost,
            touches=touches,
            handles=handles,
            node_inputs=node_inputs,
            redact_result=redact_result,
            _validator=validator,
            _accepts=_accepted_names(fn, handles),
        )

    return decorate


def normalized_touches(touches: Any, *, where: str) -> tuple[str, ...]:
    """The resource names a tool or node declares, as a tuple, refusing empty names."""
    if touches is None:
        return ()
    names = (touches,) if isinstance(touches, str) else tuple(touches)
    cleaned = []
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ConfigurationError(
                f"{where} declares touches={touches!r}, which holds something other than a "
                f"non-empty name. A resource is named by a plain string, and the same string "
                f"wherever it is touched: touches='catalogue', or "
                f"touches=['catalogue', 'watch_history']."
            )
        cleaned.append(name.strip())
    return tuple(cleaned)


def derived_version(fn: Callable[..., Any]) -> str | None:
    """A version for a tool whose author declared none, hashed from the function's source.

    The version is in the cassette key, so an edited body makes a recorded call miss rather
    than serve the answer the old body gave::

        derived_version(look_up)        # 'sha256:0f3c1a9d4b22'

    ``None`` where the source cannot be read, such as a function defined in a REPL. What the
    function closed over is covered too, read when the tool is declared, so two tools one factory
    built are two tools. **What it reads from outside itself is not**, such as a file on disk or
    a table; declare ``version=`` and change it where that matters.
    """
    from .records.manifest import source_version

    found = source_version(fn)
    return found["version"] if found["source"] == "derived" else None


def _resolved_hints(fn: Callable[..., Any], tool_name: str) -> dict[str, Any]:
    """The function's annotations, resolved against the module it was defined in.

    ``include_extras`` keeps ``Annotated`` metadata. Without it, ``Field(description=...)`` and
    any constraint on a parameter are discarded before ``create_model`` sees them, so the model
    is shown a bare type and the validator enforces no bound.
    """
    try:
        return get_type_hints(fn, include_extras=True)
    except Exception as exc:  # an annotation naming something not importable at runtime
        raise ConfigurationError(
            f"Tool {tool_name!r} has annotations that cannot be resolved: {exc}. The model is "
            f"shown a schema derived from them, so they have to be resolvable at run time. "
            f"Pass parameters= with the schema written out to bypass the derivation."
        ) from exc


def _handles_in_signature(
    fn: Callable[..., Any], hints: dict[str, Any], tool_name: str
) -> tuple[dict[str, type], dict[str, str | None]]:
    """Parameters the library fills in, keyed by name, and the key each ``NodeInput`` reads.

    Six handles are the parameter's type, and ``Annotated[Workspace, ...]`` is one of them, so
    the metadata is stripped before the annotation is compared. A ``NodeInput`` is the
    metadata instead, because the type belongs to the project.
    """
    found: dict[str, type] = {}
    keys: dict[str, str | None] = {}
    for param_name in inspect.signature(fn).parameters:
        annotation = hints.get(param_name)
        marker: NodeInput | None = None
        if get_origin(annotation) is Annotated:
            arguments = get_args(annotation)
            annotation, marker = arguments[0], _node_input_in(arguments[1:])
        if marker is not None:
            found[param_name] = NodeInput
            keys[param_name] = marker.key
            continue
        if annotation is NodeInput or (
            isinstance(annotation, type) and issubclass(annotation, NodeInput)
        ):
            raise ConfigurationError(
                f"Tool {tool_name!r} annotates {param_name!r} as NodeInput. A NodeInput says "
                f"which of the node's inputs to fill this parameter with, and the parameter "
                f"keeps the type of the value, so it goes in the metadata:\n"
                f"    {param_name}: Annotated[list[dict], NodeInput('pool')]\n"
                f"Use Annotated[dict, NodeInput] for the whole input."
            )
        if isinstance(annotation, type) and issubclass(annotation, HANDLE_TYPES):
            found[param_name] = annotation
    return found, keys


def _node_input_in(metadata: tuple[Any, ...]) -> NodeInput | None:
    """The ``NodeInput`` in a parameter's ``Annotated`` metadata, or ``None``.

    Both forms are read: ``NodeInput("pool")`` names a key, and a bare ``NodeInput`` asks for
    the whole input.
    """
    for item in metadata:
        if isinstance(item, NodeInput):
            return item
        if item is NodeInput:
            return NodeInput()
    return None


def _accepted_names(fn: Callable[..., Any], handles: dict[str, type]) -> frozenset[str] | None:
    """The argument names ``fn`` accepts from the model, or ``None`` where it accepts any.

    ``None`` is a function taking ``**kwargs``, which can receive an argument nobody declared.
    Handle parameters are excluded: the library fills those, and a model supplying one by that
    name is supplying something the tool does not take from it.
    """
    signature = inspect.signature(fn)
    if any(p.kind is p.VAR_KEYWORD for p in signature.parameters.values()):
        return None
    return frozenset(name for name in signature.parameters if name not in handles)


def _refuse_undeliverable_properties(
    fn: Callable[..., Any],
    tool_name: str,
    schema: dict[str, Any],
    handles: dict[str, type],
) -> None:
    """Refuse a declared schema offering the model a property the function cannot receive.

    The model is told it may pass every property in ``parameters``. A property the function has
    no parameter for is one the model will be refused for using, which is a contradiction the
    tool's author can see and the model cannot.
    """
    accepts = _accepted_names(fn, handles)
    if accepts is None or not isinstance(schema.get("properties"), dict):
        return
    undeliverable = sorted(set(schema["properties"]) - accepts)
    if undeliverable:
        raise ConfigurationError(
            f"Tool {tool_name!r} declares parameters {undeliverable} that {tool_name!r} does "
            f"not take, so the model would be offered an argument every call using it is "
            f"refused for. Its function takes {sorted(accepts)}.\n"
            f"Add the parameters to the function, remove them from the schema, or give the "
            f"function **kwargs to absorb them and report back what it ignored."
        )


def _schema_from_signature(
    fn: Callable[..., Any],
    tool_name: str,
    hints: dict[str, Any],
    handles: dict[str, type],
) -> tuple[dict[str, Any], Callable[..., Any]]:
    """The JSON schema for a function's parameters, and a validator for calls against it."""
    signature = inspect.signature(fn)

    fields: dict[str, Any] = {}
    for param_name, param in signature.parameters.items():
        if param_name in handles:
            continue
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            raise ConfigurationError(
                f"Tool {tool_name!r} takes {'*' if param.kind is param.VAR_POSITIONAL else '**'}"
                f"{param_name}, which has no JSON schema equivalent, so the model cannot be "
                f"told what to pass. Name the arguments explicitly, or pass parameters= with "
                f"the schema written out."
            )
        if param_name not in hints:
            raise ConfigurationError(
                f"Tool {tool_name!r} has an unannotated parameter {param_name!r}. The model "
                f"is shown a schema derived from the annotations, and an unannotated "
                f"parameter would be offered with no type at all, which is how a tool gets "
                f"called with the wrong thing (FT-23).\n"
                f"Annotate it, or pass parameters= with the schema written out. A parameter "
                f"the library should fill in is annotated ModelHandle, Workspace or Memory, "
                f"or Annotated[<type>, NodeInput()] for the node's own input."
            )
        default = ... if param.default is inspect.Parameter.empty else param.default
        fields[param_name] = (hints[param_name], default)

    model = create_model(f"{tool_name}_arguments", **fields)
    schema = json_schema_for_model(model)
    schema.pop("title", None)
    return schema, model


def _first_error(exc: PydanticValidationError) -> str:
    first = exc.errors()[0]
    location = ".".join(str(p) for p in first["loc"]) or "arguments"
    return f"{location}: {first['msg']}"


class FinishTool:
    """The termination primitive.

    An ``AgentNode`` stops when the model calls ``finish`` or when a budget axis is reached.
    Both outcomes are recorded in the node record's ``termination`` field, so the reason a run
    stopped can be read from the trajectory without reconstructing the transcript.

    Arguments are validated against the node's output schema, and then by the node's
    ``finish_check`` if it has one. A malformed or rejected call is returned to the model for
    correction rather than accepted as a result.
    """

    def __init__(self, output_schema: Any) -> None:
        self.output_schema = output_schema

    def as_tool(self) -> Tool:
        schema = _json_schema_for(self.output_schema)
        return Tool(
            name=FINISH_TOOL_NAME,
            description=(
                "Call this tool with the final answer. Its arguments are the answer itself "
                "and are validated against the required schema.\n"
                "A field that accepts `unknown` takes either form, and both are answers:\n"
                '  "inseam_cm": 81\n'
                '  "inseam_cm": {"type": "unknown", "reason": "not listed on the page"}\n'
                "Send the object, not the word. A guess presented as a fact is not an answer, "
                'and neither is the string "unknown" where the object belongs.'
            ),
            parameters=schema,
            side_effect_class=SideEffectClass.READ_ONLY,
            fn=lambda **kwargs: kwargs,
        )

    def validate(self, arguments: dict[str, Any]) -> Any:
        """Validate a finish payload against the output schema.

        Raises :class:`ModelFacingError` on failure: a malformed answer is something the
        model can correct on its next step.
        """
        schema = self.output_schema
        validator = getattr(schema, "model_validate", None)
        if validator is None:
            return arguments
        try:
            return validator(arguments)
        except Exception as exc:  # pydantic ValidationError, or anything a custom type raises
            raise ModelFacingError(
                f"The arguments to `finish` did not match the required schema: {exc}. "
                f"Call `finish` again with arguments that match it. Where a value is not "
                f"available, use the schema's `unknown` variant rather than omitting the "
                f"field or supplying a guess."
            ) from exc


def _json_schema_for(output_schema: Any) -> dict[str, Any]:
    return json_schema_for_model(output_schema)


ANSWERED_BY = ("end_user", "builder", "coding_agent", "simulated", "canned", "nobody")
"""Who a consultation channel says answers the questions it carries.

Declared once, where the channel is registered, and recorded on every ``consultation`` the
channel produces and on the tool's manifest entry. ``docs/tools.md`` §4.6.2 says which to
declare.
"""


@dataclass(slots=True)
class ConsultTool(Tool):
    """A tool that asks the end user something, recorded as a ``consultation``.

    The agent loop recognises the type and writes a ``consultation`` record rather than a
    ``tool_call``, because asking a person is a different event from calling a function and
    ``docs/trajectory-format.md`` gives it its own shape. Everything else about it is an
    ordinary tool: it is offered to the model by name and served from the cassette, so a
    rollout replays the recorded answer instead of asking k times.

    Build one with :func:`simple_agents.builtins.consult` rather than directly.
    """

    read_answer: Callable[[Any, Any], Any] | None = None
    """Turns a raw answer and the offered options into the value the run sees.

    Applied wherever an answer arrives: from the channel, from a resumed run, and from the
    cassette on replay. It has to run on the replayed value too, because the answer is stored
    as the text the end user typed and which option that was is derived from it. A replay that
    skipped this step would record ``answered`` where the live run recorded ``unmatched``.

    Deriving the same value from the same text and options every time is what makes that safe,
    so a function passed here is called more than once for one answer and must not do work
    beyond matching.
    """

    reader: Callable[..., Any] | None = None
    """Reads an answer into the option it meant, through a model, where the project set one.

    Applied wherever an answer arrives, as :attr:`read_answer` is, and what separates the two
    is that this one may reach a model. Its call goes through the cassette, so a replay reads
    again at the price of a cassette hit and an edited prompt misses on that call rather than
    on the recorded answer. A run that stopped to ask reads in the process the answer arrives
    in.

    ``None`` where the project passed no ``read=``, which leaves ``chose`` to ``match=``.
    """

    answered_by: str | None = None
    """Who the registered channel says answers, one of :data:`ANSWERED_BY`."""

    reaches: str | None = None
    """Which answerer this tool asks, where a pipeline asks more than one. ``None`` where it
    asks the only one, which is what a run supplying a single channel binds to every tool."""

    permission: str | None = None
    """What the builder agreed to, on a channel declaring ``coding_agent``. ``None`` on the
    rest."""

    ask: Any = None
    """The channel this tool asks. Replaced for one call by :meth:`for_one_call`."""

    asking: Callable[[Any, dict[str, Any]], Callable[..., Any]] | None = None
    """Builds the function one call runs, given the channel and somewhere to report from."""

    provenance: dict[str, Any] | None = None
    """What produced the answer to this one call, filled in on the copy
    :meth:`for_one_call` returns. Empty where a person answered."""

    def for_one_call(self, channel: Any = None) -> ConsultTool:
        """This tool bound to the channel answering one call.

        ``channel`` replaces the registered one, which is how a run says who answers without
        the pipeline being rebuilt (``RunEnvelope(end_user=...)``). Passing ``None`` keeps the
        registered channel. A run answering more than one person passes a channel per name,
        and this tool takes the one its ``reaches`` names.

        The copy holds that call's ``provenance``, so two consultations that overlap do not
        write over each other's.
        """
        if self.asking is None:
            return self
        channel = self._channel_in(channel)
        one = replace(
            self,
            ask=channel if channel is not None else self.ask,
            answered_by=getattr(channel, "answered_by", None) or self.answered_by,
            provenance={},
        )
        one.fn = self.asking(one.ask, one.provenance)
        return one

    def _channel_in(self, channel: Any) -> Any:
        """The channel answering this tool, out of one channel or one per answerer."""
        if not isinstance(channel, Mapping):
            return channel
        if self.reaches is None:
            raise ConfigurationError(
                f"This run answers {len(channel)} people "
                f"({', '.join(sorted(map(repr, channel)))}) and the tool {self.name!r} does "
                f"not say which of them it asks, so its questions would reach whichever "
                f"answerer happened to be first.\n"
                f"Name it where the tool is registered: consult(ask, "
                f"answered_by='end_user', reaches='approver'). Where every tool asks the same "
                f"person, pass one channel rather than one per name."
            )
        if self.reaches not in channel:
            raise ConfigurationError(
                f"The tool {self.name!r} asks {self.reaches!r}, and this run answers "
                f"{', '.join(sorted(map(repr, channel)))}. Its questions have no answerer.\n"
                f"Give {self.reaches!r} an answerer, or change the name the tool declares in "
                f"consult(reaches=...)."
            )
        return channel[self.reaches]

    def resolve(self, value: Any, failed: bool) -> str:
        """How the consultation ended, for the record's ``resolution`` field.

        ``unmatched`` is an answer that was none of the offered options, which is distinct
        from a refusal to answer: the end user said something, and it is kept. ``unavailable``
        is the channel reporting that there was nobody to ask, which is distinct from
        ``declined``, where somebody was asked and said nothing, and from ``shelved``, where
        the question reached somebody and the answer has not come back yet.
        """
        if getattr(value, "shelved", False):
            return "shelved"
        if getattr(value, "no_one_to_ask", False):
            return "unavailable"
        if failed or value is None:
            return "declined"
        if getattr(value, "options", ()) and getattr(value, "chose", None) is None:
            return "unmatched"
        return "answered"
