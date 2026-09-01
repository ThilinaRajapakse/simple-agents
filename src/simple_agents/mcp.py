"""Tools an MCP server offers, declared as tools this library can evaluate.

Needs the optional extra::

    pip install 'simple-agents[mcp]'

A server is an object the project constructs and holds. It connects on first use, keeps the
connection, and is reaped when the process exits::

    from simple_agents import SideEffectClass, ToolRegistry
    from simple_agents.mcp import MCPServer

    tickets = MCPServer.http("https://mcp.internal/tickets")

    registry = ToolRegistry()
    registry.add_all(tickets.tools(effects={
        "tickets_search": SideEffectClass.READ_ONLY,
        "tickets_create": SideEffectClass.WRITES,
    }))

``effects`` is both the selection and the declaration: a tool the server offers that it does
not name is not registered. Calling ``tools()`` with nothing declared lists the server and
refuses, naming every tool, the hints it carries and the class those propose, so the
declaration is written once against a proposal rather than from nothing.

**A hint is what a server claims, not what it guarantees.** The MCP specification says a
client must treat ``readOnlyHint`` and its siblings as untrusted, so what this module derives
from them is a proposal and the value in ``effects`` is the declaration ``docs/tools.md`` §1.4
means.

``docs/tools.md`` §7 is the reference for what a server declaration records and how a call is
replayed.
"""

from __future__ import annotations

import atexit
import json
import threading
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from .errors import CallerFacingError, ConfigurationError, ModelFacingError
from .tools import DeclaredCost, SideEffectClass, Tool

__all__ = [
    "MCPServer",
    "MCPTool",
    "MCPHints",
    "proposed_side_effect_class",
    "MCP_CASSETTE_KIND",
    "mcp_listing_key",
    "servers_of",
]

MCP_CASSETTE_KIND = "mcp_tools"
"""The cassette entry kind a server's tool listing is stored under.

A listing is a call to something outside the run, so it is recorded and served like one. A
replay resolves every declaration from the file and reaches no server, which is what lets a
recorded evaluation run with no network (``docs/tools.md`` §7.4).
"""

_UNRESOLVED = "This tool's description has not been read from its MCP server yet."

_MISSING = (
    "{what} needs the `mcp` extra, which is not installed. It speaks the Model Context "
    "Protocol, so it depends on the `mcp` SDK.\n"
    "Install it with `pip install 'simple-agents[mcp]'`."
)


def _require(module: str, what: str) -> Any:
    try:
        import importlib

        return importlib.import_module(module)
    except ImportError as exc:
        raise ConfigurationError(_MISSING.format(what=what)) from exc


# -- the hints, and what they propose ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MCPHints:
    """What a server claims about one tool's behaviour.

    Four booleans from the tool's ``annotations``, each ``None`` where the server sent no
    value. ``present`` is false for a tool carrying no annotations at all, which is different
    from one whose annotations left every field unset::

        MCPHints(read_only=True, destructive=None, idempotent=True, open_world=False)

    The specification's defaults are ``destructive=True`` and ``open_world=True``, and they
    apply only where the server sent some annotations. A tool with none gets no proposal
    (:func:`proposed_side_effect_class`).
    """

    read_only: bool | None = None
    destructive: bool | None = None
    idempotent: bool | None = None
    open_world: bool | None = None
    present: bool = True

    @classmethod
    def from_annotations(cls, annotations: Any) -> MCPHints:
        """Read the four hints off an SDK ``ToolAnnotations``, or off the wire dictionary.

        ``None`` annotations produce ``MCPHints(present=False)``.
        """
        if annotations is None:
            return cls(present=False)
        if isinstance(annotations, Mapping):
            read = annotations.get
            return cls(
                read_only=read("readOnlyHint", read("read_only_hint")),
                destructive=read("destructiveHint", read("destructive_hint")),
                idempotent=read("idempotentHint", read("idempotent_hint")),
                open_world=read("openWorldHint", read("open_world_hint")),
            )
        return cls(
            read_only=getattr(annotations, "read_only_hint", None),
            destructive=getattr(annotations, "destructive_hint", None),
            idempotent=getattr(annotations, "idempotent_hint", None),
            open_world=getattr(annotations, "open_world_hint", None),
        )

    def to_record(self) -> dict[str, Any] | None:
        """The four hints as the manifest records them, or ``None`` where there were none."""
        if not self.present:
            return None
        return {
            "read_only": self.read_only,
            "destructive": self.destructive,
            "idempotent": self.idempotent,
            "open_world": self.open_world,
        }


def proposed_side_effect_class(hints: MCPHints) -> SideEffectClass | None:
    """The class a server's hints propose, or ``None`` where they propose nothing.

    ``read_only`` where the server claims the tool modifies nothing, ``writes`` where it claims
    the updates are additive, and ``irreversible`` where it claims they are destructive::

        proposed_side_effect_class(MCPHints(read_only=True))     # SideEffectClass.READ_ONLY

    A tool carrying no annotations proposes nothing, because the specification's defaults would
    read as ``irreversible`` and an evaluation refuses every tool in that class. Servers that
    publish no annotations are common, so proposing from their absence would produce a
    declaration that has to be overridden tool by tool to run anything.

    ``spends_money`` is never proposed. MCP publishes no cost hint, so that class is always the
    project's own to declare.
    """
    if not hints.present:
        return None
    if hints.read_only:
        return SideEffectClass.READ_ONLY
    # The specification's own defaults, applied only to a tool that carried some annotations.
    destructive = True if hints.destructive is None else hints.destructive
    return SideEffectClass.IRREVERSIBLE if destructive else SideEffectClass.WRITES


# -- one tool ----------------------------------------------------------------------------------


@dataclass(slots=True)
class MCPTool(Tool):
    """One tool an MCP server offers, declared by the project as an ordinary tool.

    Built by :meth:`MCPServer.tools` rather than directly. The name and the side-effect class
    come from ``effects``; the description and the input schema are read from the server, or
    from the recording on a replayed run, and until then this tool refuses to be called.

    It is a plain tool in every other way: stored in the cassette, served on a replay, and
    taking no handle. ``version`` is a digest of the name, the description and the schema, so a
    server that changes a tool invalidates the recording rather than answering differently
    under one key.
    """

    server: Any = None
    """The :class:`MCPServer` this tool is called through."""

    hints: MCPHints = field(default_factory=lambda: MCPHints(present=False))
    """What the server claimed about the tool, recorded beside what the project declared."""

    proposed: SideEffectClass | None = None
    """The class the hints proposed, or ``None``. Kept so a manifest reader can see where the
    declaration and the claim disagree."""

    resolved: bool = False
    """Whether the description and the schema have been read yet."""

    @property
    def mcp_entry(self) -> dict[str, Any]:
        """What the manifest records about this tool's server and its hints.

        ``declared`` is what the project said and ``proposed`` what the server's hints said, so
        a disagreement between the two is readable from the run (``docs/tools.md`` §7.3).
        """
        return {
            "server": getattr(self.server, "name", None),
            "hints": self.hints.to_record(),
            "proposed": self.proposed.value if self.proposed else None,
            "declared": self.side_effect_class.value,
            "agrees": self.proposed is None or self.proposed is self.side_effect_class,
        }

    def call(self, arguments: dict[str, Any], handles: dict[str, Any] | None = None) -> Any:
        """Send the call to the server and return what it answered.

        A tool the server reports as failing raises
        :class:`~simple_agents.errors.ModelFacingError`, so the model gets a turn to correct
        it. A protocol failure or an unreachable server raises
        :class:`~simple_agents.errors.CallerFacingError` and ends the run.
        """
        if not self.resolved:
            raise ConfigurationError(
                f"Tool {self.name!r} has not been read from its MCP server. A server is read "
                f"when the run starts, so this tool was called outside one.\n"
                f"Call it inside Pipeline.run, or read the server first with "
                f"server.resolve()."
            )
        return self.server.call(self.name, arguments)


# -- the server --------------------------------------------------------------------------------


# `eq=False` keeps identity equality and a usable hash: a server is a resource, two are the
# same only when they are the same object, and the at-exit set holds weak references to them.
@dataclass(eq=False)
class MCPServer:
    """A Model Context Protocol server the project's agent can call tools on.

    Construct one with :meth:`http` or :meth:`stdio`, hold it, and hand its tools to a
    registry. Constructing connects nothing: the connection opens on first use, so a pipeline
    that never reaches the tool starts no server and a replayed run reaches nothing at all::

        tickets = MCPServer.http("https://mcp.internal/tickets")
        registry.add_all(tickets.tools(effects={"tickets_search": SideEffectClass.READ_ONLY}))

    It is also a context manager, for a caller that wants the connection closed at a known
    point::

        with MCPServer.stdio("npx", ["-y", "@modelcontextprotocol/server-filesystem", "."]) as fs:
            ...

    A connection left open is closed when the process exits.
    """

    name: str
    """What the run records this server as. Defaults to the URL or the command."""

    _open: Callable[[], Any] = field(repr=False)
    _session: Any = field(default=None, init=False, repr=False)
    _listing: dict[str, tuple[str, dict[str, Any], MCPHints]] | None = field(
        default=None, init=False, repr=False
    )
    _declared: list[MCPTool] = field(default_factory=list, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    @classmethod
    def http(
        cls,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        auth: Any = None,
        timeout_s: float = 30.0,
        name: str | None = None,
    ) -> MCPServer:
        """A server reached over streamable HTTP.

        ``auth`` is an ``httpx`` authentication object, which is where the SDK's
        ``OAuthClientProvider`` goes for a server behind OAuth::

            MCPServer.http("https://mcp.internal/tickets", headers={"X-Team": "logistics"})
        """

        def opener() -> Any:
            transport = _require("mcp.client.streamable_http", "MCPServer.http")

            def connect() -> Any:
                # Headers, authentication and timeouts belong to the HTTP client the SDK
                # takes, and `create_mcp_http_client` is what applies its own defaults on top:
                # redirects followed, and a read timeout long enough for an SSE stream.
                http = transport.create_mcp_http_client(
                    headers=dict(headers) if headers else None,
                    timeout=_timeout(timeout_s),
                    auth=auth,
                )
                return transport.streamable_http_client(url, http_client=http)

            return _Session(connect)

        return cls(name=name or url, _open=opener)

    @classmethod
    def stdio(
        cls,
        command: str,
        args: Sequence[str] = (),
        *,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        name: str | None = None,
    ) -> MCPServer:
        """A server run as a child process, spoken to over its standard input and output.

        The process starts on first use and is terminated when the connection closes::

            MCPServer.stdio("npx", ["-y", "@modelcontextprotocol/server-everything", "stdio"])

        The command runs on the machine the agent runs on, with whatever that account can
        reach. It is the project's to trust.
        """

        def opener() -> Any:
            mod = _require("mcp.client.stdio", "MCPServer.stdio")
            params = _require("mcp", "MCPServer.stdio").StdioServerParameters(
                command=command, args=list(args), env=dict(env) if env else None, cwd=cwd
            )
            return _Session(lambda: mod.stdio_client(params))

        return cls(name=name or " ".join([command, *args]), _open=opener)

    # -- declaring tools ------------------------------------------------------------------

    def tools(
        self,
        effects: Mapping[str, SideEffectClass] | None = None,
        *,
        costs: Mapping[str, DeclaredCost] | None = None,
        touches: Mapping[str, str | Sequence[str]] | None = None,
    ) -> list[MCPTool]:
        """The tools this project declares from this server, one per name in ``effects``.

        ``effects`` is the selection and the declaration at once: a tool the server offers
        that it does not name is not registered, and a class it does not carry cannot be
        supplied by the server (``docs/tools.md`` §1.4)::

            tickets.tools(effects={"tickets_search": SideEffectClass.READ_ONLY})

        ``costs`` and ``touches`` are per tool and optional, and take the same values ``@tool``
        takes. A ``spends_money`` declaration needs a ``costs`` entry, as any tool does.

        Called with nothing declared, this reads the server and refuses, naming every tool it
        offers with the class its hints propose. That listing is how the declaration is
        written the first time, and it needs the server to be reachable.

        Nothing is read from the server here where ``effects`` is given. The names and the
        classes are enough to build the registry, so a project constructs its pipeline with no
        network and the descriptions arrive when the run starts (``docs/tools.md`` §7.4).
        """
        if not effects:
            raise ConfigurationError(self._proposal())
        built = []
        for tool_name, declared in effects.items():
            if not isinstance(declared, SideEffectClass):
                raise ConfigurationError(
                    f"MCPServer({self.name!r}).tools was given "
                    f"effects[{tool_name!r}]={declared!r}, which is not a SideEffectClass. A "
                    f"tool cannot be registered without one, because an evaluation reads it "
                    f"to decide whether the tool may execute inside a rollout (FT-19).\n"
                    f"Pass SideEffectClass.READ_ONLY, WRITES, SPENDS_MONEY or IRREVERSIBLE."
                )
            built.append(
                MCPTool(
                    name=tool_name,
                    description=_UNRESOLVED,
                    parameters={"type": "object", "properties": {}},
                    side_effect_class=declared,
                    fn=_refuse_direct_call,
                    version=None,
                    declared_cost=(costs or {}).get(tool_name),
                    touches=(touches or {}).get(tool_name),
                    server=self,
                )
            )
        self._declared.extend(built)
        return built

    def _proposal(self) -> str:
        """The refusal that carries one declaration line per tool the server offers."""
        listing = self.listing()
        if not listing:
            return (
                f"MCPServer({self.name!r}) offers no tools, so there is nothing to declare. "
                f"Check that the server is the one intended and that it has finished starting."
            )
        lines = []
        for tool_name, (_, _, hints) in sorted(listing.items()):
            proposed = proposed_side_effect_class(hints)
            value = f"SideEffectClass.{proposed.name}," if proposed else "...,"
            lines.append(f"        {tool_name!r}: {value}{_why(hints, proposed)}")
        body = "\n".join(lines)
        return (
            f"MCPServer({self.name!r}) offers {len(listing)} tool(s) and effects= declares "
            f"none. A tool cannot be registered without a side-effect class, because an "
            f"evaluation reads it to decide whether the tool may execute inside a rollout "
            f"(FT-19). The server's hints propose:\n\n"
            f"    effects={{\n{body}\n    }}\n\n"
            f"A hint is what the server claims, not what it guarantees. Confirm each against "
            f"what one call does, and declare only the tools this agent needs: a tool left "
            f"out is not registered. That confirmation is the brief's `tool_effects` answer."
        )

    # -- the connection -------------------------------------------------------------------

    def listing(self) -> dict[str, tuple[str, dict[str, Any], MCPHints]]:
        """Every tool the server offers, as ``name -> (description, schema, hints)``.

        Read once and kept, so repeated calls in one process reach the server once. This is
        what a live run reads; a replayed run is served :meth:`restore` instead.
        """
        with self._lock:
            if self._listing is None:
                self._listing = self._read()
            return self._listing

    def _read(self) -> dict[str, tuple[str, dict[str, Any], MCPHints]]:
        found = {}
        for tool in self._connect().list_tools():
            schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {})
            found[tool.name] = (
                tool.description or "",
                dict(schema),
                MCPHints.from_annotations(getattr(tool, "annotations", None)),
            )
        return found

    def _connect(self) -> Any:
        with self._lock:
            if self._session is None or not self._session.alive:
                self._session = self._open()
                self._session.open()
                _reap_at_exit(self)
            return self._session

    def call(self, tool_name: str, arguments: Mapping[str, Any]) -> Any:
        """Call one tool on the server and return what it answered.

        A result the server marks as an error raises
        :class:`~simple_agents.errors.ModelFacingError`. Anything else that goes wrong raises
        :class:`~simple_agents.errors.CallerFacingError`, because an infrastructure failure
        handed to a model produces an answer built on nothing (FT-22).
        """
        try:
            result = self._connect().call_tool(tool_name, dict(arguments))
        except (ModelFacingError, CallerFacingError):
            raise
        except Exception as exc:
            raise CallerFacingError(
                f"MCPServer({self.name!r}) could not be reached to call {tool_name!r}: "
                f"{type(exc).__name__}: {exc}. Check that the server is running and that this "
                f"machine can reach it."
            ) from exc
        text = _text_of(result)
        if getattr(result, "is_error", False) or getattr(result, "isError", False):
            raise ModelFacingError(text)
        structured = getattr(result, "structured_content", None)
        return structured if structured is not None else text

    def close(self) -> None:
        """Close the connection and stop the server process, where there is one."""
        with self._lock:
            session, self._session = self._session, None
            if session is not None:
                session.close()

    def __enter__(self) -> MCPServer:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- resolving declarations -----------------------------------------------------------

    def resolve(self) -> dict[str, Any]:
        """Fill every declared tool's description, schema and version from the server.

        Returns what was read, in the shape :meth:`restore` takes, so a run records it and a
        replay is served it. Also reports what the server offers that this project did not
        declare and what it declared that the server no longer offers (``docs/tools.md`` §7.3).
        """
        listing = self.listing()
        self._apply(listing)
        return {
            "server": self.name,
            "tools": {
                tool_name: {"description": text, "schema": schema, "hints": hints.to_record()}
                for tool_name, (text, schema, hints) in sorted(listing.items())
            },
        }

    def restore(self, recorded: Mapping[str, Any]) -> None:
        """Fill every declared tool from a recording rather than from the server.

        This is the replayed path. Nothing is connected and no process is started, which is
        what lets a recorded evaluation run with no network.
        """
        listing = {
            tool_name: (
                entry.get("description") or "",
                dict(entry.get("schema") or {}),
                MCPHints.from_annotations(entry.get("hints")),
            )
            for tool_name, entry in (recorded.get("tools") or {}).items()
        }
        with self._lock:
            self._listing = listing
        self._apply(listing)

    def _apply(self, listing: Mapping[str, tuple[str, dict[str, Any], MCPHints]]) -> None:
        for tool in self._declared:
            found = listing.get(tool.name)
            if found is None:
                raise ConfigurationError(
                    f"MCPServer({self.name!r}) does not offer {tool.name!r}, which effects= "
                    f"declares. It offers: {', '.join(sorted(listing)) or '(none)'}.\n"
                    f"Remove it from effects=, or check that this is the intended server."
                )
            text, schema, hints = found
            tool.description = text or _UNRESOLVED
            tool.parameters = dict(schema) or {"type": "object", "properties": {}}
            tool.hints = hints
            tool.proposed = proposed_side_effect_class(hints)
            tool.version = _declaration_version(tool.name, tool.description, tool.parameters)
            tool.resolved = True

    def drift(self, recorded: Mapping[str, Any]) -> list[dict[str, str]]:
        """How the server's tools differ from what a recording holds, one entry per difference.

        Empty where they agree. ``added`` is a tool the server now offers, ``withdrawn`` one it
        no longer does, and ``changed`` one whose description or schema moved. Only tools this
        project declared are compared for change; the rest are reported as added.
        """
        was = dict((recorded.get("tools") or {}).items())
        now = self.listing()
        found: list[dict[str, str]] = []
        for tool_name in sorted(set(now) - set(was)):
            found.append({"tool": tool_name, "difference": "added"})
        for tool_name in sorted(set(was) - set(now)):
            found.append({"tool": tool_name, "difference": "withdrawn"})
        for tool_name in sorted(set(was) & set(now)):
            text, schema, _ = now[tool_name]
            before = was[tool_name]
            if (before.get("description") or "") != text:
                found.append({"tool": tool_name, "difference": "description"})
            if dict(before.get("schema") or {}) != schema:
                found.append({"tool": tool_name, "difference": "schema"})
        return found

    def undeclared(self) -> tuple[str, ...]:
        """Tools the server offers that this project did not declare, so cannot call."""
        declared = {tool.name for tool in self._declared}
        return tuple(sorted(set(self.listing()) - declared))


# -- the synchronous bridge --------------------------------------------------------------------


class _Session:
    """A synchronous view of the SDK's asynchronous client session.

    One task owns the session for its whole lifetime and commands reach it on a queue, because
    the SDK's cancel scopes have to be entered and exited in the same task. Submitting each
    call as its own task raises ``Attempted to exit cancel scope in a different task`` when the
    session closes.
    """

    def __init__(self, opener: Callable[[], Any]) -> None:
        import asyncio
        from concurrent.futures import Future

        self._asyncio = asyncio
        self._Future = Future
        self._opener = opener
        self._loop = asyncio.new_event_loop()
        self._ready: Any = Future()
        self._queue: Any = None
        self._thread = threading.Thread(target=self._serve, daemon=True, name="mcp-session")
        self.alive = False

    def open(self) -> Any:
        self._thread.start()
        found = self._ready.result(120)
        self.alive = True
        return found

    def _serve(self) -> None:
        self._asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._own())
        finally:
            self._loop.close()

    async def _own(self) -> None:
        session_type = _require("mcp", "MCPServer").ClientSession
        self._queue = self._asyncio.Queue()
        try:
            async with self._opener() as streams:
                # Two values over stdio and three over streamable HTTP, whose third is a
                # session-id accessor this client does not read.
                read, write = streams[0], streams[1]
                async with session_type(read, write) as session:
                    self._ready.set_result(await session.initialize())
                    while True:
                        job, future = await self._queue.get()
                        if job is None:
                            future.set_result(None)
                            return
                        try:
                            future.set_result(await job(session))
                        except Exception as exc:  # handed back to the calling thread
                            future.set_exception(exc)
        except Exception as exc:
            if not self._ready.done():
                self._ready.set_exception(exc)

    def _submit(self, job: Any, timeout: float = 300.0) -> Any:
        if not self.alive:
            raise CallerFacingError("This MCP session is closed.")
        future = self._Future()
        self._loop.call_soon_threadsafe(self._queue.put_nowait, (job, future))
        return future.result(timeout)

    def list_tools(self) -> list[Any]:
        return list(self._submit(lambda s: s.list_tools()).tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return self._submit(lambda s: s.call_tool(name, arguments))

    def close(self) -> None:
        if not self.alive:
            return
        try:
            self._submit(None, timeout=30.0)
        except Exception:  # a session already gone is closed
            pass
        finally:
            self.alive = False
            self._thread.join(30)


# -- helpers -----------------------------------------------------------------------------------


_LIVE: weakref.WeakSet = weakref.WeakSet()
_REAPING = False


def _reap_at_exit(server: MCPServer) -> None:
    global _REAPING
    _LIVE.add(server)
    if not _REAPING:
        _REAPING = True
        atexit.register(_reap_all)


def _reap_all() -> None:
    for server in list(_LIVE):
        try:
            server.close()
        except Exception:  # nothing useful can be reported during interpreter shutdown
            pass


def _refuse_direct_call(**_: Any) -> Any:
    raise ConfigurationError(
        "An MCP tool's function is not called directly. The call goes to the server through "
        "MCPServer.call, which the tool does itself."
    )


def _declaration_version(name: str, description: str, schema: Mapping[str, Any]) -> str:
    """A digest of what the server declared, which is what the cassette key holds.

    The derived version cannot see any of this: it hashes the function and what it closed
    over, and a closure over a live connection is the same text for every tool one server
    builds. So a server that reworded a description or changed a schema would answer under the
    key of the one it replaced.
    """
    import hashlib

    payload = json.dumps(
        {"name": name, "description": description, "schema": schema},
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _why(hints: MCPHints, proposed: SideEffectClass | None) -> str:
    if proposed is None:
        return "  # no annotations: declare it"
    if hints.read_only:
        return "  # readOnlyHint: true"
    return f"  # destructiveHint: {'true' if hints.destructive is not False else 'false'}"


def _text_of(result: Any) -> str:
    """Every text block of a tool result, joined. Non-text content is named by its type."""
    pieces = []
    for block in getattr(result, "content", ()) or ():
        text = getattr(block, "text", None)
        pieces.append(text if text is not None else f"[{getattr(block, 'type', 'content')}]")
    return "\n".join(pieces)


def _timeout(seconds: float) -> Any:
    """The request timeout as the SDK's HTTP client takes it, or ``None`` for its own default.

    Its default reads for far longer than it connects, because a streamable HTTP response can
    be a server-sent event stream held open between messages.
    """
    if seconds is None:
        return None
    httpx2 = _require("httpx2", "MCPServer.http")
    return httpx2.Timeout(seconds, read=max(seconds, 300.0))


def mcp_listing_key(server_name: str) -> str:
    """The cassette key one server's tool listing is stored under.

    The server's name and nothing else. A run reads each server once, so there is no occurrence
    to count, and a project that renames a server has renamed what the manifest records too.
    """
    import hashlib

    return "mcp:" + hashlib.sha256(server_name.encode("utf-8")).hexdigest()[:16]


def servers_of(tools: Iterable[Tool]) -> list[MCPServer]:
    """Every distinct MCP server the given tools are called through, in declaration order."""
    found: list[MCPServer] = []
    for tool in tools:
        server = getattr(tool, "server", None)
        if isinstance(server, MCPServer) and not any(server is one for one in found):
            found.append(server)
    return found
