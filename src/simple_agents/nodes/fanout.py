"""A node run once per item of a sequence, and what each item produced."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Sequence
from pydantic import TypeAdapter
from ..budget import BudgetExceeded, NodeBudgetExceeded
from ..context import RunContext, error_object
from ..records.cassette import CassetteMiss
from ..errors import (
    CallerFacingError,
    ConfigurationError,
    LeftTheSlice,
    RunSuspended,
    StreamUsageMissing,
    Suspend,
)
from ..graph import RetryPolicy
from ..runtime.calls import _is_plain
from ..runtime.suspending import _Suspending
from .base import Execution


@dataclass(frozen=True, slots=True)
class ItemOutcome:
    """One item of a fan-out: either a validated output or a failure, never both.

    ``value`` holds what the schema validated. ``error`` holds why nothing was produced, in
    the shape ``docs/trajectory-format.md`` §5.2 defines. ``item`` is the input, so a caller
    can retry the failures without re-deriving them::

        retry = [outcome.item for outcome in result.failures]

    ``termination`` is why an item stopped, for a kind that decides that for itself. An item
    of an ``AgentNode`` fan-out that ran out of steps is a success carrying whatever it had::

        spun = [o.index for o in result if o.termination == "max_steps"]
    """

    index: int
    item: Any
    value: Any = None
    error: dict[str, Any] | None = None
    termination: str | None = None
    """Why this item stopped where the node kind knows: a ``finish`` call, a rejected one, or
    a budget axis. ``None`` where the item ran to the end of its own work, which is every item
    of a fan-out that makes one call."""

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass(frozen=True, slots=True)
class FanOutResult:
    """What a fan-out node returns: one outcome per input item, in input order.

    An item whose output is ``unknown`` is a **success**: the model answered, and the answer
    was that the information is not there. A failure is an item the model produced no valid
    answer for at all. Iterating the result yields its outcomes, so it stays lined up with the
    input sequence::

        result.outcomes   # one ItemOutcome per input item, in input order
        result.failures   # ItemOutcome, each carrying its input and its error
        result.ok         # True when nothing failed

        summaries = [outcome.value for outcome in result if outcome.ok]

    There is no property returning the successful values alone. Such a list is shorter than the
    input sequence whenever an item failed, so pairing it back against the inputs mispairs them
    with nothing raised.

    ``kept`` holds the input keys the node declared in ``keep=``, so a value that arrived
    beside the sequence reaches the next node instead of ending here::

        node = LLMNode(read_one, output_schema=Reading, over="pages", keep=["unreadable"])

        result.kept["unreadable"]   # what the node before this one put under that key

    It is empty on a node that declared no ``keep=``.
    """

    outcomes: tuple[ItemOutcome, ...]
    kept: dict[str, Any] = field(default_factory=dict)

    @property
    def failures(self) -> list[ItemOutcome]:
        return [o for o in self.outcomes if not o.ok]

    @property
    def ok(self) -> bool:
        return all(o.ok for o in self.outcomes)

    def __len__(self) -> int:
        return len(self.outcomes)

    def __iter__(self) -> Any:
        return iter(self.outcomes)

    def to_record(self) -> dict[str, Any]:
        """What the node record stores: one entry per input item, in input order.

        An entry carries ``value`` or ``error`` and never both, which is the split
        :class:`ItemOutcome` makes, and ``termination`` beside it where the item stopped for a
        reason its node kind knows. ``kept`` is present only where the node declared ``keep=``,
        so a record written without one is unchanged.
        """
        record: dict[str, Any] = {
            "items": [
                (
                    {"index": o.index, "value": o.value}
                    if o.ok
                    else {"index": o.index, "error": o.error}
                )
                | ({"termination": o.termination} if o.termination is not None else {})
                for o in self.outcomes
            ]
        }
        if self.kept:
            record["kept"] = dict(self.kept)
        return record


def _declare_fan_out(
    node: Any,
    *,
    over: str | None,
    keep: Sequence[str] | None,
    max_failures: int | None,
    concurrent_items: int | None,
    retry: RetryPolicy | None,
) -> None:
    """Attach the fan-out arguments any node kind may take, refusing the shapes that misread.

    ``over`` names an input key holding a sequence and makes the node run once per item. What
    that means differs by kind: one model call for an ``LLMNode``, one agent loop for an
    ``AgentNode``, one call of the function for a ``Deterministic`` node. What is checked here
    is the same for all three, so the refusals are written once and name the kind they came
    from.
    """
    kind = type(node).__name__
    example = {
        "LLMNode": "LLMNode(summarise, output_schema=Summary, over='documents')",
        "AgentNode": (
            "AgentNode(read_one, tools=[look_up], output_schema=Reading, "
            "over='documents', budget_per_item=Budget(...))"
        ),
    }.get(kind, "Deterministic(parse_one, over='documents')")

    node.over = over
    node.keep = tuple(keep) if keep is not None else ()
    node.max_failures = max_failures
    node.concurrent_items = concurrent_items

    if over is not None and not isinstance(over, str):
        raise ConfigurationError(
            f"{kind} {node.node_id!r} was given over={over!r}. `over` names the input "
            f"key holding the sequence to run over, as a string: {example}."
        )
    if max_failures is not None and over is None:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} sets max_failures without over=. A node that runs "
            f"once has one outcome and nothing to collect. Pass over= to fan out over a "
            f"sequence, or drop max_failures."
        )
    if over is not None and retry is not None and max_failures is None:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} fans out over {over!r} with "
            f"retry=RetryPolicy(attempts={retry.attempts}) and no max_failures. An item "
            f"that fails is collected rather than raised, and a retry re-executes a node "
            f"only when the node raises, so an item failure never reaches this one: the "
            f"node runs once and the failed items stay failed.\n"
            f"Pass max_failures=0 to make the first failed item raise, which re-executes "
            f"the node and re-attempts every item including the ones that succeeded. Or "
            f"drop retry= to keep collecting, and read the failures off what the node "
            f"returned."
        )
    if concurrent_items is not None and over is None:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} sets concurrent_items without over=. A node that "
            f"runs once has one piece of work, and nothing to overlap it with.\n"
            f"Pass over= to fan out over a sequence, or drop concurrent_items. To let "
            f"this node run at the same time as another node, list both in the "
            f"pipeline's concurrent_nodes."
        )
    if concurrent_items is not None and concurrent_items < 1:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} sets concurrent_items={concurrent_items}, which is "
            f"fewer than one item at a time.\n"
            f"Pass the most items that may be in flight at once, such as "
            f"concurrent_items=8, or drop it to run them one after another."
        )
    if keep is not None and over is None:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} sets keep without over=. A node that runs once "
            f"returns what it produced, and the node after it is handed that value whole, "
            f"so there is nothing for keep to rescue. Pass over= to fan out over a "
            f"sequence, or drop keep."
        )
    if isinstance(keep, str) or any(not isinstance(k, str) for k in node.keep):
        raise ConfigurationError(
            f"{kind} {node.node_id!r} was given keep={keep!r}. `keep` names input keys "
            f"to carry past the fan-out, as a sequence of strings: keep=['question']."
        )
    if over in node.keep:
        raise ConfigurationError(
            f"{kind} {node.node_id!r} names {over!r} in both over= and keep=. That key "
            f"holds the sequence being fanned out, and every item of it is already in the "
            f"result, so keeping it as well writes each one twice.\n"
            f"Read the items from the result and drop {over!r} from keep=."
        )


def _fan_out(
    node: Any,
    *,
    inputs: Any,
    run: RunContext,
    ctx: Any,
    execution: Execution,
    one: Callable[..., tuple[Any, str | None]],
    resume_state: dict[str, Any] | None = None,
    answer: Any = None,
) -> FanOutResult:
    """One run of ``one`` per item, collecting failures rather than ending the run.

    ``one`` is what a single item is: one model call for an ``LLMNode``, one agent loop for an
    ``AgentNode``, one call of the function for a ``Deterministic`` node. It receives that
    item's inputs, a context carrying its index, and the index, and returns the value and how
    the item terminated.

    An item is a success even when its value is ``unknown``: the work happened, and the answer
    was absence. An item that raised produced no answer at all, and the two are kept apart so
    an evaluation can tell a shortfall from a broken call. An item too long to send is
    collected like any other failed one.

    ``concurrent_items`` runs that many at once, bounded by the run's ceiling. Each model call
    is numbered by the item it is for and its position within that item, so an item's seed is
    the same whatever order the items ran in, and the outcomes come back in input order.

    A run stopped part-way through carries the items already done and whatever each item
    still running was holding, so a resume finishes those rather than starting them again.
    One suspension asks one question, so where several items stopped together the lowest of
    them is the one asked and answered; the rest keep their state and ask on the next pass.
    """
    node_id = execution.node_id
    items = _sequence_for(inputs, node.over, node_id)
    kept = _kept_for(inputs, node.keep, node_id)
    done: dict[int, ItemOutcome] = {}
    schema = getattr(node, "output_schema", None)

    in_flight = (resume_state or {}).get("in_flight") or {}
    asked = (resume_state or {}).get("asked")
    if resume_state is not None:
        for record in resume_state["done"]:
            done[record["index"]] = ItemOutcome(
                index=record["index"],
                item=record["item"],
                value=_item_value_in(record["value"], schema),
                error=record["error"],
                termination=record.get("termination"),
            )

    failures = _Failures(
        already=sum(1 for outcome in done.values() if not outcome.ok),
        limit=node.max_failures,
        node_id=node_id,
        total=len(items),
    )
    remaining = [(index, item) for index, item in enumerate(items) if index not in done]

    def unit(index: int, item: Any) -> ItemOutcome:
        item_inputs = {**inputs, node.over: item} if isinstance(inputs, dict) else item
        held = in_flight.get(str(index))
        try:
            # The step an item's call spends is reserved inside `_call_model`, before the
            # call, so items that overlap stop exactly on `max_steps` rather than by however
            # many were in flight when it ran out.
            value, termination = one(
                item_inputs,
                replace(ctx, item_index=index),
                index,
                held["state"] if held is not None else None,
                answer if asked == index else None,
            )
        except NodeBudgetExceeded as exc:
            # The node's own total is gone rather than the run's, so this item never ran and
            # the ones left will not either. Collected rather than raised, because a fan-out
            # returns one outcome per input item and a run that can continue should say what
            # happened to each of them. It is not counted against max_failures: the items did
            # not fail, the node ran out of what it declared.
            return ItemOutcome(index=index, item=item, error=error_object(exc, model_facing=False))
        except (*_STOPS_THE_RUN, _Suspending):
            # The run is invalid, or it is stopping. Neither is this item's failure, so
            # neither is collected as one. `_STOPS_THE_RUN` says which and why.
            raise
        except Exception as exc:
            failures.saw(exc)
            return ItemOutcome(index=index, item=item, error=error_object(exc, model_facing=False))
        return ItemOutcome(index=index, item=item, value=value, termination=termination)

    def announce(outcome: ItemOutcome) -> ItemOutcome:
        """Tell a watching caller this item is done, before the rest of the fan-out is.

        The executor announces nodes, and a fan-out hands its whole result to the next node
        when the last item finishes, so without this a caller writing each item as it lands
        has nothing to write on.

        ``item_already_done`` is how many of ``item_total`` were finished before this pass
        began, which is what a resumed fan-out announces nothing for. A display seeds itself
        from it and reaches the total, rather than ending short by whatever was resumed.
        """
        if run.progress_sink is not None:
            from ..pipeline import NodeEvent

            run.progress_sink(
                NodeEvent(
                    phase="item",
                    node_id=node_id,
                    node_kind=node.node_kind,
                    item_index=outcome.index,
                    item_total=len(items),
                    item_already_done=len(items) - len(remaining),
                    error=outcome.error,
                )
            )
        return outcome

    outcomes = run.pool.map(
        [lambda index=index, item=item: announce(unit(index, item)) for index, item in remaining],
        limit=node.concurrent_items,
        stops_on=_ends_the_run,
    )

    stopping: BaseException | None = None
    stopped_at: int | None = None
    still_holding: dict[str, Any] = {}
    for outcome, (index, item) in zip(outcomes, remaining):
        if outcome.error is not None:
            if stopping is None:
                stopping, stopped_at = outcome.error, index
            # Whatever this item was holding when it stopped, so a resume finishes it rather
            # than running it again and re-spending the calls it already made. Read off every
            # stopped item and not only the one that is asked: items that overlap can stop
            # together, and the ones not asked keep their place.
            state = getattr(outcome.error, "node_state", None)
            if state is not None:
                still_holding[str(index)] = {"item": item, "state": state}
            continue
        if outcome.started:
            done[index] = outcome.value

    if stopping is not None:
        if isinstance(stopping, Suspend) or hasattr(stopping, "node_state"):
            # The items already done travel with the stop, so the resumed run pays for the
            # ones that are left and not for these. Each value is written down against the
            # schema this node declared, which is the rule a value on an edge crosses under.
            # `asked` is which item the question on this suspension came from, so the answer
            # reaches that item and no other.
            stopping.node_state = {
                "kind": "fan_out",
                "done": [_item_record(done[index], node_id, schema) for index in sorted(done)],
                "in_flight": {**in_flight, **still_holding},
                "asked": stopped_at,
            }
        raise stopping

    collected = [done[index] for index in sorted(done)]
    _refuse_one_failure_wearing_a_tolerance(collected, node_id, len(items))
    return FanOutResult(outcomes=tuple(collected), kept=kept)


def _item_value_in(raw: Any, schema: Any) -> Any:
    """One finished item's value, rebuilt from the file a resumed run reads.

    A node with no ``output_schema`` returned plain data to cross the suspend point, so it
    comes back as it went down.
    """
    if raw is None or schema is None:
        return raw
    return TypeAdapter(schema).validate_python(raw)


def _item_record(outcome: ItemOutcome, node_id: str, schema: Any) -> dict[str, Any]:
    """One finished fan-out item, as data a resumed run rebuilds it from.

    The item itself has to be plain data: it came from the run's own input and no schema
    describes it. The value is dumped against the node's ``output_schema``, which is what
    every item validated against; a node that declares none has to have returned plain data,
    which is the rule any value crosses a suspend point under.
    """
    if not _is_plain(outcome.item):
        raise CallerFacingError(
            f"Node {node_id!r} suspended {outcome.index} item(s) into a fan-out, and the "
            f"items it runs over are {type(outcome.item).__name__}, which cannot cross a "
            f"suspend point. A resumed run rebuilds each finished item from the file, and "
            f"the inputs it fans out over carry no schema to rebuild them from.\n"
            f"Fan out over plain data: strings, numbers, or dicts and lists of those."
        )
    if outcome.value is None:
        value = None
    elif schema is None:
        if not _is_plain(outcome.value):
            raise CallerFacingError(
                f"Node {node_id!r} suspended inside a fan-out, and item {outcome.index} "
                f"produced a {type(outcome.value).__name__}, which cannot cross a suspend "
                f"point. A resumed run rebuilds each finished item's value from the file, "
                f"and this node declares no output_schema to rebuild it from.\n"
                f"Declare output_schema= on the node, or return plain data from it: a "
                f"string, a number, a boolean, or a list or dict of those."
            )
        value = outcome.value
    else:
        value = TypeAdapter(schema).dump_python(outcome.value, mode="json")
    return {
        "index": outcome.index,
        "item": outcome.item,
        "value": value,
        "error": outcome.error,
        "termination": outcome.termination,
    }


# What a fan-out item raises through rather than collecting: the run is invalid, or it is
# stopping. A miss means this is not the run that was recorded, a budget means there is
# nothing left to spend, a misconfiguration was wrong before the run started, a slice ended
# where the graph left it, and a suspension is the run going to disk. None is answered by
# running the next item.
#
# **The named subclasses, and not `CallerFacingError` itself.** The base class is also raised
# for a condition that *is* one item's: `_validated_output` raises it where a model's response
# does not match the output schema, which is the case `max_failures` exists for. Widening this
# to the base class ends a whole run on one item's bad JSON. A new caller-facing subclass that
# means the run is invalid belongs in this tuple.
# An item stopped by the node's own budget did not fail: the node ran out of what it
# declared. Named rather than caught, because the outcome carries the recorded error object
# rather than the exception, and a resumed fan-out rebuilds these from the file.
_RAN_OUT = frozenset({NodeBudgetExceeded.__name__})


_STOPS_THE_RUN: tuple[type[BaseException], ...] = (
    CassetteMiss,
    BudgetExceeded,
    ConfigurationError,
    LeftTheSlice,
    RunSuspended,
    StreamUsageMissing,
    Suspend,
)


def _ends_the_run(exc: BaseException) -> bool:
    """Whether this failure stops the work beside it rather than being collected.

    Wider than ``_STOPS_THE_RUN``. That tuple decides what an item raises instead of
    collecting; this decides what stops the items running beside it, and anything reaching
    here has already escaped the item. The failure budget's own refusal is the case: a bare
    ``CallerFacingError`` raised while collecting, after which the items not yet started do
    not start.
    """
    return isinstance(exc, (CassetteMiss, BudgetExceeded, Suspend, CallerFacingError, _Suspending))


@dataclass
class _Failures:
    """How many items of a fan-out have failed, against what the node allows.

    Shared by items that overlap, so the count is the node's rather than one thread's. Raising
    is what stops the rest: items not yet started do not start, and items already running
    finish.
    """

    already: int
    limit: int | None
    node_id: str
    total: int
    _lock: Any = field(default_factory=threading.Lock, repr=False)

    def saw(self, exc: Exception) -> None:
        with self._lock:
            self.already += 1
            failed = self.already
        if self.limit is None or failed <= self.limit:
            return
        raise CallerFacingError(
            f"Node {self.node_id!r} fanned out over {self.total} items and {failed} failed, "
            f"above max_failures={self.limit}. A failure rate this high usually means the "
            f"prompt or the schema is wrong for every item rather than for these ones. The "
            f"last failure was: {exc}\n"
            f"Raise max_failures to collect more, or set it to None to collect every failure "
            f"and decide afterwards."
        ) from exc


def _refuse_one_failure_wearing_a_tolerance(
    outcomes: list[ItemOutcome], node_id: str, total: int
) -> None:
    """Refuse a fan-out that produced nothing, where the failures were not about the items.

    A tolerance is for items that fail for their own reasons. Where every item failed and
    every failure carries the same type and the same message, the failure is not about any
    item: the prompt, the schema or the function is wrong for all of them, and collecting
    them reports a shortfall the node never measured.

    Separate from ``max_failures``, which answers how many items may fail. This answers
    whether the node worked at all, so it applies whatever the tolerance says.

    Two items at least. At one, every failure is trivially the same failure, and the rule
    would become "a one-item fan-out that failed raises".

    An item the node's own budget stopped is outside this, as it is outside ``max_failures``:
    the node reached a bound it was given rather than failing.

    Judged when the fan-out is done, since whether every item failed is knowable only then.
    A broken node still pays for every item and says so afterwards.
    """
    if total < 2 or len(outcomes) < total:
        return
    failed = [
        outcome
        for outcome in outcomes
        if not outcome.ok and (outcome.error or {}).get("type") not in _RAN_OUT
    ]
    if len(failed) != total:
        return
    kinds = {
        ((outcome.error or {}).get("type"), (outcome.error or {}).get("message"))
        for outcome in failed
    }
    if len(kinds) != 1:
        return
    kind, message = next(iter(kinds))
    raise CallerFacingError(
        f"Node {node_id!r} fanned out over {total} items and every one of them failed with "
        f"the same {kind}: {message}\n"
        f"A failure every item shares is not about the items, so the node produced nothing "
        f"and nothing downstream of it has anything to read. Fix what is wrong for all of "
        f"them, which is usually the prompt function reading the item under the wrong key, "
        f"the output schema, or the function itself. Where the items really did each fail "
        f"for their own reason, say which item in the failure so the messages differ."
    )


def _kept_for(inputs: Any, keys: Sequence[str], node_id: str) -> dict[str, Any]:
    """The input values a fan-out carries past itself, or a refusal naming what was found.

    A key that is not there is refused rather than dropped: a value that silently stops at a
    fan-out is what ``keep`` exists to prevent, and a typo would reproduce it exactly.
    """
    if not keys:
        return {}
    missing = [key for key in keys if key not in inputs]
    if missing:
        raise CallerFacingError(
            f"Node {node_id!r} keeps {', '.join(repr(k) for k in missing)} past its fan-out, "
            f"and its input has no such key. A fan-out node receives the previous node's "
            f"output, so that node must return a dict containing every key named in keep=. "
            f"Found: {sorted(inputs)}."
        )
    return {key: inputs[key] for key in keys}


def _sequence_for(inputs: Any, key: str, node_id: str) -> list[Any]:
    """The items a fan-out runs over, or a caller-facing refusal naming what was found."""
    if not isinstance(inputs, dict) or key not in inputs:
        raise ConfigurationError(
            f"Node {node_id!r} fans out over {key!r}, and its input has no such key. A "
            f"fan-out node receives the previous node's output, so that node must return a "
            f"dict containing {key!r}. Found: "
            f"{sorted(inputs) if isinstance(inputs, dict) else type(inputs).__name__}."
        )
    value = inputs[key]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ConfigurationError(
            f"Node {node_id!r} fans out over {key!r}, which holds "
            f"{type(value).__name__}. `over` needs a sequence of items to run once per; a "
            f"string is a single value. Pass a list."
        )
    return list(value)
