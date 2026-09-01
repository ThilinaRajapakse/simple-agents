"""Compacting a conversation that has outgrown what one call can hold."""

from __future__ import annotations

from typing import Any

from ..records.conversation import Conversation
from ..tools import SideEffectClass, Tool, tool

__all__ = ["compact_conversation"]


def compact_conversation(
    *,
    name: str = "compact_conversation",
    version: str | None = None,
    keep_last: int = 4,
) -> Tool:
    """A tool that replaces a conversation's older messages with a summary of them.

    Declared ``WRITES``, and it makes no model call of its own: the summary is an argument, so
    whichever node produced it did so on the record, under its own budget. A tool holding a
    ``Conversation`` is re-run during a replay rather than served from the cassette, since the
    next turn reads what it wrote.

    **On an ``AgentNode``, the model calls it and writes the summary itself**, out of the
    conversation it is already holding::

        node = AgentNode(build_prompt, tools=[search, compact_conversation()],
                         output_schema=Answer, budget=Budget(...))

    **Without an ``AgentNode``, an ``LLMNode`` writes the summary and a ``Deterministic`` node
    files it**, which is two steps and one model call::

        class Summary(BaseModel):
            summary: str

        def summarise(inputs, ctx):
            older = ctx.conversation.messages()[:-6]
            return "Summarise this conversation for whoever continues it:\\n" + str(older)

        def file_it(summary, ctx):
            ctx.call_tool("compact_conversation", summary=summary.summary)
            return summary

        pipeline = Pipeline([
            LLMNode(summarise, output_schema=Summary, node_id="summarise"),
            Deterministic(file_it, node_id="compact", tools=[compact_conversation()]),
        ], budget=budget)

    ``keep_last`` is how many of the newest messages are left alone, so the turn in progress
    and the ones around it are not summarised away.

    The messages a compaction replaced stay in the file and stop being read, so what was
    dropped is still there for anything reading the conversation's records.
    """

    @tool(side_effect_class=SideEffectClass.WRITES, name=name, version=version)
    def compact(conversation: Conversation, summary: str) -> dict[str, Any]:
        """Shorten this conversation by replacing its older messages with a summary.

        Call this when the conversation has grown long enough that carrying all of it is
        wasteful. The most recent messages are kept as they are.

        `summary` is the earlier conversation written out for whoever continues it. Keep every
        fact the person stated about themselves or their request, every decision reached, and
        anything still outstanding. Leave out the searching and the tool calls.

        Returns how many messages were replaced and how many the conversation now holds.
        """
        held = conversation.messages()
        text = (summary or "").strip()
        if len(held) <= keep_last or not text:
            return {"replaced": 0, "messages": len(held)}

        replaced = len(held) - keep_last
        conversation.supersede(f"Earlier in this conversation:\n{text}", keep_last=keep_last)
        return {"replaced": replaced, "messages": len(conversation.messages())}

    return compact
