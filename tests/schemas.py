"""Output schemas used across the tests.

A class docstring here would be sent to the model as the schema's description, so these carry
none: the recordings then differ from the ones taken before that behaviour changed only by
their cassette keys. `Total` is refused at construction and never reaches a model.
"""

from __future__ import annotations

from pydantic import BaseModel

from simple_agents import Maybe


class Answer(BaseModel):
    answer: Maybe[str]
    source: str | None = None


class Finding(BaseModel):
    retailer: Maybe[str]
    returns_policy: Maybe[str]


class Total(BaseModel):
    """No `unknown` branch anywhere. Used to prove the refusal fires."""

    label: str
