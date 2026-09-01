"""The current time, as a tool.

A model has no clock and its training data has a date, so anything relative to "now" is
guessed unless the agent is told. This is the cheapest tool in the set and it removes a class
of date errors.

It is served from the cassette under a key that counts how many times it has been called, so
a run that read the clock twice replays both readings in turn. A replay therefore reports the
instants the recorded run saw rather than the instants of the replay, which is what makes an
evaluation of a time-sensitive agent repeatable.
"""

from __future__ import annotations

from ..tools import SideEffectClass, Tool, tool
from ..records.trajectory import utc_now

__all__ = ["now"]


def now(*, name: str = "now", version: str | None = None) -> Tool:
    """A tool returning the current time.

    registry.add(now())
    """

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def clock() -> str:
        """The current date and time, in UTC, as an ISO 8601 timestamp.

        Takes no arguments. Call this before answering anything about today, this week, or how
        long ago something happened, rather than assuming a date.
        """
        return utc_now()

    return clock
