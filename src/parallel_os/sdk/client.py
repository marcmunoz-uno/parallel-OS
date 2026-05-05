"""Agent-facing SDK.

The agent's view of parallel-OS. Agents call `Runtime.spawn(name)` to get
a connection to a freshly-spawned runtime, invoke its MCP tools, and the
runtime is reaped when the context exits.

Status: scaffold. The orchestrator + MCP-over-Docker plumbing isn't yet
wired end-to-end. APIs here describe the intended shape.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any


class RuntimeProxy:
    """Live connection to a spawned runtime. Forwards MCP tool calls."""

    def __init__(self, name: str, instance_id: str) -> None:
        self.name = name
        self.instance_id = instance_id
        # TODO: hold an MCP client session here, route attribute access to it.

    @property
    def shell(self) -> "ShellProxy":
        return ShellProxy(self)

    @property
    def fs(self) -> "FsProxy":
        return FsProxy(self)

    @property
    def pkg(self) -> "PkgProxy":
        return PkgProxy(self)

    @property
    def tool(self) -> "ToolProxy":
        return ToolProxy(self)


class ShellProxy:
    def __init__(self, runtime: RuntimeProxy) -> None:
        self._runtime = runtime

    async def run(self, cmd: str, *, timeout_sec: int = 60) -> dict[str, Any]:
        # TODO: forward to MCP `shell.run` tool on the runtime
        raise NotImplementedError("MCP wiring not yet implemented")


class FsProxy:
    def __init__(self, runtime: RuntimeProxy) -> None:
        self._runtime = runtime

    async def read(self, path: str) -> bytes:
        raise NotImplementedError

    async def write(self, path: str, content: bytes) -> None:
        raise NotImplementedError


class PkgProxy:
    def __init__(self, runtime: RuntimeProxy) -> None:
        self._runtime = runtime

    async def install(self, name: str) -> dict[str, Any]:
        raise NotImplementedError


class ToolProxy:
    """Dynamic dispatcher for first-class tool wrappers (e.g. `tool.amass.enum(...)`)."""

    def __init__(self, runtime: RuntimeProxy) -> None:
        self._runtime = runtime

    def __getattr__(self, tool_name: str) -> "ToolGroup":
        return ToolGroup(self._runtime, tool_name)


class ToolGroup:
    def __init__(self, runtime: RuntimeProxy, tool_name: str) -> None:
        self._runtime = runtime
        self._tool_name = tool_name

    def __getattr__(self, verb: str) -> Any:
        async def call(**kwargs: Any) -> dict[str, Any]:
            # TODO: route via MCP, validate against tools.json manifest
            raise NotImplementedError(
                f"would call {self._tool_name}.{verb}({kwargs}) on {self._runtime.name}"
            )
        return call


class Runtime:
    """Top-level entry point for agents."""

    @classmethod
    @asynccontextmanager
    async def spawn(cls, name: str, *, ttl_sec: int = 1800):  # type: ignore[no-untyped-def]
        """Spawn a runtime and yield a live proxy. Reaps on exit."""
        # TODO: connect to host orchestrator (Unix socket or TCP), request spawn,
        # set up MCP session, yield proxy, tear down on exit.
        proxy = RuntimeProxy(name, instance_id="<unwired>")
        try:
            yield proxy
        finally:
            # TODO: tell orchestrator to reap
            pass


class Swarm:
    """Multi-runtime context manager. Spawns several runtimes in parallel."""

    @classmethod
    @asynccontextmanager
    async def spawn(cls, names: list[str], *, ttl_sec: int = 1800):  # type: ignore[no-untyped-def]
        """Spawn multiple runtimes; yields an object whose attributes are each proxy."""
        # TODO: parallel spawn via asyncio.gather, yield a SwarmHandle.
        raise NotImplementedError
        yield  # pragma: no cover
