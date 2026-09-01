"""Which hosts a run may fetch from, including ones it learns about while running.

``http_fetch(allow_hosts=[...])`` fixes the reachable set when the tool is built. A project
whose agent legitimately discovers a host mid-run, such as the vendor's own site named in a
search result, has nowhere to put it, and the alternative to a policy is switching the check
off.

A policy is the same containment with a way to grow: hosts configured up front, hosts admitted
during the run against a cap, each admission carrying the reason it was made, and a ceiling on
how many requests the run may make at all.

The project decides which hosts, which caps, and who may admit. The policy is the mechanism.

The classes live in ``simple_agents.tools``, because a ``HostPolicy`` parameter on a tool is
part of the tool contract: the run fills it with that run's own copy of the declaration.
"""

from __future__ import annotations

from ..tools import Admission, HostPolicy

__all__ = ["HostPolicy", "Admission"]
