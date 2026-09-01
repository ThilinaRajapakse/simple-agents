"""The built-in tools.

Each is a factory returning a :class:`~simple_agents.tools.Tool`, because every one of them
needs something the project holds: the documents, the search provider, the schema, the channel
to the end user. Add what the agent needs to a registry and leave out the rest::

    from simple_agents import ToolRegistry
    from simple_agents.builtins import DocumentIndex, document_search, now, workspace_write

    registry = ToolRegistry([
        document_search(DocumentIndex.from_directory("corpus/")),
        workspace_write(),
        now(),
    ])

``finish`` is not here. The library supplies it to every ``AgentNode`` from the node's own
output schema, so it is never registered.

``docs/tools.md`` covers what each one is for and what its declarations commit it to.
"""

from __future__ import annotations

from .clock import now
from .conversation import compact_conversation
from .consult import (
    DEFAULT_READING_INSTRUCTIONS,
    ConsultChannel,
    ModelAnswer,
    ModelReader,
    Reply,
    Shelved,
    Unavailable,
    ask_on_stdin,
    consult,
    on_reply,
    unattended,
)
from .extract import extract_to_schema
from .files import workspace_list, workspace_read, workspace_write
from .hostpolicy import Admission, HostPolicy
from .memory import memory_search, recall, remember
from .htmlreduce import PageLink, Reduced, reduce_html
from .urlcache import CachedValue, UrlCache
from .http import http_fetch, read_page
from .ranking import (
    Hybrid,
    Interleave,
    Lexical,
    Ranking,
    RRF,
    Semantic,
    VectorScan,
    VectorStore,
    WeightedScore,
)
from .rerank import CrossEncoderRerank, ModelRerank, Reranker
from .search import ENGLISH_STOPWORDS, DocumentIndex, Hit, document_search
from .websearch import SearchProvider, web_search

__all__ = [
    "DocumentIndex",
    "ENGLISH_STOPWORDS",
    "Hit",
    "document_search",
    "Lexical",
    "Semantic",
    "Hybrid",
    "Ranking",
    "RRF",
    "Interleave",
    "WeightedScore",
    "VectorStore",
    "VectorScan",
    "Reranker",
    "CrossEncoderRerank",
    "ModelRerank",
    "workspace_read",
    "workspace_write",
    "workspace_list",
    "compact_conversation",
    "now",
    "http_fetch",
    "HostPolicy",
    "UrlCache",
    "CachedValue",
    "Admission",
    "read_page",
    "reduce_html",
    "Reduced",
    "PageLink",
    "web_search",
    "SearchProvider",
    "extract_to_schema",
    "consult",
    "on_reply",
    "Reply",
    "ModelAnswer",
    "ModelReader",
    "DEFAULT_READING_INSTRUCTIONS",
    "Shelved",
    "Unavailable",
    "unattended",
    "ask_on_stdin",
    "ConsultChannel",
    "remember",
    "recall",
    "memory_search",
]
