"""Reading and writing files inside the run's own directory.

Both tools take a :class:`~simple_agents.tools.Workspace`, which the library fills in with
``runs/<run_id>/workspace/``. That makes them re-run during a replay rather than served from
the cassette, so a replayed run writes the same files into its own directory and a later step
that reads them finds them there.

Paths are relative to the workspace root. One that escapes it is refused as a model-facing
failure, so the model is told to try another path rather than the run ending.
"""

from __future__ import annotations

from ..tools import SideEffectClass, Tool, Workspace, tool

__all__ = ["workspace_read", "workspace_write", "workspace_list"]


def workspace_write(*, name: str = "workspace_write", version: str | None = None) -> Tool:
    """A tool that writes a file into the run's workspace.

    Declared ``WRITES``: it changes the filesystem, and every write lands inside the run's own
    directory, so k rollouts of an evaluation write k separate directories::

        registry.add(workspace_write())
    """

    @tool(side_effect_class=SideEffectClass.WRITES, name=name, version=version)
    def write(workspace: Workspace, path: str, content: str) -> str:
        """Write text to a file in the run's working directory, replacing what was there.

        The path is relative to that directory, such as 'notes.txt' or 'drafts/summary.md';
        parent directories are created. Returns the path written. Use this to keep something
        that will be needed later rather than carrying it through the conversation.
        """
        workspace.write_text(path, content)
        return path

    return write


def workspace_read(*, name: str = "workspace_read", version: str | None = None) -> Tool:
    """A tool that reads a file the run wrote earlier.

    Reading a path that is not there names the files that are, so the model can correct the
    call rather than guessing again::

        registry.add(workspace_read())
    """

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def read(workspace: Workspace, path: str) -> str:
        """Read a file previously written to the run's working directory.

        The path is relative to that directory. Fails naming the files that are present, so a
        wrong path can be corrected. Only files this run wrote are there; it starts empty.
        """
        return workspace.read_text(path)

    return read


def workspace_list(*, name: str = "workspace_list", version: str | None = None) -> Tool:
    """A tool that lists what the run has written so far.

    registry.add(workspace_list())
    """

    @tool(side_effect_class=SideEffectClass.READ_ONLY, name=name, version=version)
    def listing(workspace: Workspace) -> list[str]:
        """List the files in the run's working directory, as paths relative to its root.

        Returns an empty list before anything has been written. Takes no arguments.
        """
        return workspace.listing()

    return listing
