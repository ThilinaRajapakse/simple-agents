"""A whole pipeline standing where a node stands."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from ..errors import ConfigurationError, ModelFacingError
from ..schema import json_schema_for_model


@dataclass(slots=True)
class Delegation:
    """A pipeline an ``AgentNode``'s model may hand a subtask to, and how it is described.

    The model chooses what each subtask is and how many to send. A ``Pipeline`` used as a node
    covers the case where the builder fixes the decomposition; this covers the case where the
    model chooses it::

        research = Pipeline([hunt, verify], budget=Budget(...), node_id="research")

        orchestrate = AgentNode(
            plan_the_work,
            tools=[read_page],
            delegates=[Delegation(research, description=(
                "Research one question and return sourced notes. Call it once per question. "
                "Do not call it for a question the notes already answer."))],
            output_schema=Report,
            budget=Budget(max_steps=20, max_tokens=200_000, max_cost=None,
                          max_wall_clock_ms=600_000),
        )

    ``description`` is prompt text read by the model, the same as a tool's. It should say what
    the sub-pipeline does, what one subtask looks like, and when not to send one.

    The model is offered the delegation under the pipeline's ``node_id``, taking the type the
    pipeline's entry node reads. That type has to be a pydantic model, because the model fills
    it in and anything else is offered as an object with no properties.

    ``max_calls`` bounds how many subtasks one execution may send. It is required only where
    the sub-pipeline makes no model call, since a sub-pipeline that calls a model spends the
    calling node's ``max_steps`` and one that does not is bounded by no axis.
    """

    pipeline: Any
    description: str = ""
    max_calls: int | None = None
    _reads: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        from ..pipeline import Pipeline
        from ..shapes import accepted_by, type_name

        if not isinstance(self.pipeline, Pipeline):
            raise ConfigurationError(
                f"Delegation was given {type(self.pipeline).__name__}, not a Pipeline. A "
                f"delegation hands a subtask to a whole pipeline; a single function the model "
                f"may call is a tool.\n"
                f"Pass Delegation(Pipeline([...], budget=..., node_id='research'), "
                f"description='...'), or declare it on the node as tools=[the_function]."
            )
        if not self.pipeline.node_id:
            raise ConfigurationError(
                "This Delegation holds a pipeline with no node_id. The model is offered the "
                "delegation under that id, and the pipeline's nodes record under ids prefixed "
                "by it, so it has to have one.\n"
                "Pass node_id= when constructing it: Pipeline([...], budget=..., "
                "node_id='research')."
            )
        name = self.pipeline.node_id
        if not self.description.strip():
            raise ConfigurationError(
                f"Delegation of {name!r} has no description. The description is prompt text "
                f"the model reads to decide when and what to delegate, so an empty one leads "
                f"to misuse. State what the sub-pipeline does, what one subtask looks like, "
                f"and when not to send one (FT-23)."
            )
        if self.pipeline.suspend_before:
            raise ConfigurationError(
                f"The pipeline delegated as {name!r} declares suspend_before=True. That is "
                f"read by the walk of the graph a node sits in, and a delegated pipeline sits "
                f"in none, so it would never fire.\n"
                f"Drop suspend_before=True. To stop before the work the delegate does, declare "
                f"it on the first node inside that pipeline."
            )

        reads = accepted_by(self.pipeline)
        if getattr(reads, "model_json_schema", None) is None:
            entry = self.pipeline.graph.entry
            raise ConfigurationError(
                f"The pipeline delegated as {name!r} reads its input as "
                f"{type_name(reads)}, and the model has to be shown a schema it can fill in. "
                f"Anything without one is offered as an object with no properties, which is "
                f"how a delegation gets sent arguments the entry node cannot read (FT-23).\n"
                f"Annotate {entry!r}'s first parameter with a pydantic model: "
                f"def {entry}(inputs: Subtask, ctx: NodeContext) -> ...."
            )
        self._reads = reads

        if self.max_calls is not None and self.max_calls < 1:
            raise ConfigurationError(
                f"Delegation of {name!r} sets max_calls={self.max_calls}. A delegation the "
                f"model may never send is a delegation to remove rather than to bound.\n"
                f"Pass max_calls=1 or more, or leave it unset where the sub-pipeline calls a "
                f"model and max_steps bounds it."
            )
        kinds = self.pipeline.node_kinds
        if self.max_calls is None and not (kinds.get("llm") or kinds.get("agent")):
            raise ConfigurationError(
                f"The pipeline delegated as {name!r} makes no model call, and this delegation "
                f"declares no max_calls, so nothing bounds how many times the model may send a "
                f"subtask to it. max_steps counts model calls, so a sub-pipeline of "
                f"Deterministic nodes spends none of it, the same way a cycle that makes no "
                f"model call carries its own bound (FT-18).\n"
                f"Pass max_calls=: Delegation(pipeline, description=..., max_calls=4)."
            )

    @property
    def name(self) -> str:
        """What the model calls this delegation, which is the pipeline's ``node_id``."""
        return str(self.pipeline.node_id)

    def to_wire(self) -> dict[str, Any]:
        """The delegation as a model backend expects to receive it: as one more tool."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": json_schema_for_model(self._reads),
        }

    def build_inputs(self, arguments: dict[str, Any]) -> Any:
        """The value the sub-pipeline is run on, built from what the model sent.

        Raises :class:`~simple_agents.errors.ModelFacingError` where the arguments do not
        satisfy the entry node's type, so the model gets another turn to correct the subtask
        rather than the run ending.
        """
        try:
            return self._reads.model_validate(arguments)
        except Exception as exc:  # pydantic ValidationError, or anything a custom type raises
            raise ModelFacingError(
                f"The subtask sent to {self.name!r} did not match the required schema: {exc}. "
                f"Send it again with arguments that match it."
            ) from exc
