"""Adapters for the backends the library ships.

One adapter per backend, each implementing the two methods of
:class:`~simple_agents.ModelClient`. Import them from the package root::

    from simple_agents import GeminiClient, MistralClient, VLLMClient

An adapter for a backend the library does not ship is written the same way, against the
Protocol, without modifying the library. ``docs/model-clients.md`` says what an adapter owes
its caller.
"""

from __future__ import annotations

from .embeddings_local import LocalCrossEncoder, SentenceTransformerEmbeddings
from .embeddings_openai import MistralEmbeddings, OpenAIEmbeddings, OpenAIReranker
from .gemini import GeminiClient
from .mistral import MistralClient
from .vllm import VLLMClient

__all__ = [
    "GeminiClient",
    "MistralClient",
    "VLLMClient",
    "OpenAIEmbeddings",
    "MistralEmbeddings",
    "OpenAIReranker",
    "SentenceTransformerEmbeddings",
    "LocalCrossEncoder",
]
