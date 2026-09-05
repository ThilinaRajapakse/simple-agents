"""What the end user meets, declared beside the pipelines.

The product is the surface the end user reaches the agent through and the artifact it keeps
for them to read. The agent runs inside it, and every project has one (`docs/product.md`).
Nothing in a run reaches it: a web handler calls `pipeline.run`, so introspection sees the
pipeline and never the thing that called it, which is the situation resources were in before a
tool declared what it touches. Declaration is the mechanism here too.

::

    from simple_agents import Product, Surface, product_factory

    @product_factory
    def product() -> Product:
        return Product(surfaces=[
            Surface("the support inbox", "starts_a_run", pipeline="triage",
                    does="a script takes each new ticket and starts a run"),
            Surface("the rota", "answers_a_waiting_run", pipeline="triage",
                    through="consult",
                    does="the person on the rota answers when the agent asks"),
            Surface("the outbox", "reads_the_artifact", reads="outbox",
                    does="the reply lands there as a draft for a person to send"),
        ], jobs=[
            Job("nightly digest", pipeline="digest",
                does="every night at 02:00, over the day's tickets"),
        ])

A `Job` is a run that starts without the end user: a schedule, a change in a store, another
job finishing. The project's own scheduler runs it and passes the job's name as
``Pipeline.run(trigger=...)``, which is what joins the runs back to the declaration.

`simple-agents view` draws it on the `ship` page, joined to the pipelines, the channels and
the stores it names. The declaration is read from the code and nothing writes it into a run
record, so it costs a project one function and no format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .errors import ConfigurationError

__all__ = [
    "Product",
    "Surface",
    "Job",
    "INTERACTION_KINDS",
    "product_factory",
    "registered_product",
    "clear_registered_product",
]

INTERACTION_KINDS: tuple[str, ...] = (
    "starts_a_run",
    "answers_a_waiting_run",
    "reads_the_artifact",
    "records_a_judgement",
)
"""The four kinds an interaction can be (`docs/product.md` §2).

A surface with no interaction of the first two kinds never reaches the agent: it is a display
over stored output, and saying so is what puts that in front of the builder.
"""

_KIND_WORDS = {
    "starts_a_run": "Starts a run",
    "answers_a_waiting_run": "Answers a waiting run",
    "reads_the_artifact": "Reads the artifact",
    "records_a_judgement": "Records a judgement",
}

# What each kind has to name for the declaration to say anything: the field, and what it is.
_REQUIRED: dict[str, tuple[str, str]] = {
    "starts_a_run": ("pipeline", "the pipeline one interaction here runs"),
    "answers_a_waiting_run": ("pipeline", "the pipeline whose run is waiting"),
    "reads_the_artifact": ("reads", "the resource the end user reads"),
}


@dataclass(frozen=True, slots=True)
class Surface:
    """One place the end user meets the agent, and what they do there.

    ``name`` is what the builder calls it, ``kind`` is one of :data:`INTERACTION_KINDS`, and
    ``does`` is the interaction in the end user's terms::

        Surface("the rota", "answers_a_waiting_run", pipeline="triage", through="consult",
                does="the person on the rota answers when the agent asks")

    ``pipeline`` is the registered name of the pipeline the interaction reaches, required for
    a surface that starts or answers a run. ``through`` names the consultation channel a
    waiting run is answered through, by the tool's own name, which is what joins the surface
    to who the channel says answers (FT-31). ``reads`` names the resource an artifact surface
    shows, which is what joins it to the store the pipelines write.

    A kind outside the four, or a kind whose required name is missing, raises
    ``ConfigurationError`` saying which field to add.
    """

    name: str
    kind: str
    does: str = ""
    pipeline: str | None = None
    through: str | None = None
    reads: str | None = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ConfigurationError(
                "A Surface was declared with no name. The name is what the builder calls it: "
                'Surface("the support inbox", "starts_a_run", pipeline="triage").'
            )
        if self.kind not in INTERACTION_KINDS:
            raise ConfigurationError(
                f"The surface {self.name!r} declares kind={self.kind!r}, and the four kinds "
                f"are {', '.join(INTERACTION_KINDS)}. Every interaction is one of them "
                f"(docs/product.md §2); a surface showing stored output is "
                f"'reads_the_artifact'."
            )
        held = _REQUIRED.get(self.kind)
        if held is not None and not getattr(self, held[0]):
            field_name, what = held
            raise ConfigurationError(
                f"The surface {self.name!r} is {self.kind!r} and names no {field_name}. "
                f"Add {field_name}=, which is {what}: "
                f'Surface({self.name!r}, {self.kind!r}, {field_name}="...").'
            )

    @property
    def kind_words(self) -> str:
        """The kind as a person reads it: ``"Answers a waiting run"``."""
        return _KIND_WORDS.get(self.kind, self.kind.replace("_", " ").capitalize())

    @property
    def reaches_the_agent(self) -> bool:
        """Whether an interaction here reaches the agent, rather than showing what it left."""
        return self.kind in ("starts_a_run", "answers_a_waiting_run")


@dataclass(frozen=True, slots=True)
class Job:
    """One run that starts without the end user: on a schedule, on a change, after another job.

    ``name`` is what the builder calls it, ``pipeline`` the registered name of the pipeline
    it runs, and ``does`` says when it runs, in the builder's words::

        Job("nightly digest", pipeline="digest", does="every night at 02:00, over the day's tickets")
        Job("rank", pipeline="rank", does="after every corpus change", after="nightly digest")

    ``after`` names another job in the same ``Product`` that this one follows. Nothing here
    runs: the project's own scheduler starts the pipeline and passes the job's name as
    ``Pipeline.run(trigger="nightly digest")``, so each run says which job started it and the
    view joins the runs to this declaration. A job with no name or no pipeline raises
    ``ConfigurationError``.
    """

    name: str
    pipeline: str
    does: str = ""
    after: str | None = None

    def __post_init__(self) -> None:
        if not str(self.name).strip():
            raise ConfigurationError(
                "A Job was declared with no name. The name is what the builder calls it, and "
                "what the scheduler passes as trigger=: "
                'Job("nightly digest", pipeline="digest", does="every night at 02:00").'
            )
        if not str(self.pipeline or "").strip():
            raise ConfigurationError(
                f"The job {self.name!r} names no pipeline. Add pipeline=, the registered name "
                f"of the pipeline it runs: "
                f'Job({self.name!r}, pipeline="digest", does="every night at 02:00").'
            )
        if self.after is not None and str(self.after).strip() == str(self.name).strip():
            raise ConfigurationError(
                f"The job {self.name!r} declares after={self.name!r}, which is itself. "
                f"after= names another job of the same Product that this one follows."
            )

    @property
    def kind_words(self) -> str:
        """The trigger as a person reads it: ``"Job · after nightly digest"`` or ``"Job"``."""
        return f"Job · after {self.after}" if self.after else "Job"


@dataclass(frozen=True, slots=True)
class Product:
    """What the end user uses: the surfaces they meet the agent through, and the jobs that
    run without them.

    ::

        Product(surfaces=[Surface("the support inbox", "starts_a_run", pipeline="triage")],
                jobs=[Job("nightly digest", pipeline="digest", does="every night at 02:00")])

    ``surfaces`` are where the end user meets the agent; ``jobs`` are the runs that start
    without them. Declared once per project through :func:`product_factory`. A product with no
    surface that reaches the agent is accepted and reported by the page, because that is a
    real state a project passes through and refusing it would refuse a project mid-build. A
    job whose ``after`` names no job of this product raises ``ConfigurationError``.
    """

    surfaces: tuple[Surface, ...] = field(default_factory=tuple)
    jobs: tuple[Job, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "surfaces", tuple(self.surfaces))
        object.__setattr__(self, "jobs", tuple(self.jobs))
        _refuse_bad_surfaces(self.surfaces)
        _refuse_bad_jobs(self.jobs)

    def job(self, name: str | None) -> "Job | None":
        """The declared job of that name, or ``None``; what a run's ``trigger`` is joined by."""
        if not name:
            return None
        return next((j for j in self.jobs if j.name == name), None)


def _twice(names: list[str]) -> list[str]:
    return sorted({n for n in names if names.count(n) > 1})


def _refuse_bad_surfaces(surfaces: tuple[Any, ...]) -> None:
    for surface in surfaces:
        if not isinstance(surface, Surface):
            raise ConfigurationError(
                f"Product was given {type(surface).__name__} where a Surface was "
                f"expected. Each entry says what the end user does at one place: "
                f'Surface("the rota", "answers_a_waiting_run", pipeline="triage").'
            )
    twice = _twice([s.name for s in surfaces])
    if twice:
        raise ConfigurationError(
            f"Product declares {', '.join(repr(n) for n in twice)} more than once. One "
            f"name names one surface; a place the end user does two things there is two "
            f"surfaces with their own names."
        )


def _refuse_bad_jobs(jobs: tuple[Any, ...]) -> None:
    for job in jobs:
        if not isinstance(job, Job):
            raise ConfigurationError(
                f"Product was given {type(job).__name__} under jobs= where a Job was "
                f"expected. Each entry is one run that starts without the end user: "
                f'Job("nightly digest", pipeline="digest", does="every night at 02:00").'
            )
    names = [j.name for j in jobs]
    twice = _twice(names)
    if twice:
        raise ConfigurationError(
            f"Product declares the job {', '.join(repr(n) for n in twice)} more than "
            f"once. A run records the job's name as its trigger, so one name names one job."
        )
    unknown = sorted({j.after for j in jobs if j.after and j.after not in names})
    if unknown:
        raise ConfigurationError(
            f"A job declares after={', '.join(repr(n) for n in unknown)}, and the product "
            f"declares no job of that name. after= names another entry of jobs=: "
            f'Job("rank", pipeline="rank", after="nightly digest").'
        )


_PRODUCT: list[Callable[[], Any]] = []


def product_factory(factory: Callable[[], Any]) -> Callable[[], Any]:
    """Register the decorated zero-argument function as the builder of this project's product.

    ::

        @product_factory
        def product() -> Product:
            return Product(surfaces=[...])

    The function is returned unchanged. A project has one product, so registering a second is
    refused. Like a pipeline factory, it is called at import-free moments by the view, so
    building the product must not call a model, write a file the project keeps, or reach the
    network.
    """
    if not callable(factory):
        raise ConfigurationError(
            "product_factory decorates a function that builds the product, and takes no "
            "arguments of its own: @product_factory over def product() -> Product."
        )
    if _PRODUCT and _PRODUCT[0] is not factory:
        raise ConfigurationError(
            f"A product is already registered to "
            f"{getattr(_PRODUCT[0], '__name__', _PRODUCT[0])!r}. A project has one product: "
            f"the surfaces the end user meets it through are the entries of its one "
            f"Product(surfaces=[...])."
        )
    _PRODUCT[:] = [factory]
    return factory


def registered_product() -> Callable[[], Any] | None:
    """The registered factory, or ``None`` where the project declares no product."""
    return _PRODUCT[0] if _PRODUCT else None


def clear_registered_product() -> None:
    """Forget the registered product. For tests and for tooling reading one project after
    another."""
    _PRODUCT.clear()
