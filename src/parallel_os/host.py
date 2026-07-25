"""Host API — the callable surface over the runtime backend.

Synchronous and stateless (exec/reap are addressed by container_id), so it works
straight from the CLI and over SSH from a remote orchestrator (e.g. internet-agents)
without needing the async MCP session layer wired. Spawns from the named REGISTRY.
"""
from __future__ import annotations
from typing import Any

from .orchestrator.docker_backend import DockerBackend
from .orchestrator.runtime import RuntimeSpec, RuntimeInstance
from . import runtimes

_PLACEHOLDER = RuntimeSpec(name="_", image="", mcp_entrypoint=[])  # exec/reap only need container_id


class Host:
    def __init__(self) -> None:
        self.backend = DockerBackend()

    def spawn(self, name: str, agent_id: str | None = None, ttl_sec: int | None = None) -> dict[str, Any]:
        spec = runtimes.get(name)
        if spec is None:
            raise ValueError(f"unknown runtime {name!r}. Available: {sorted(runtimes.REGISTRY)}")
        inst = self.backend.spawn(spec, agent_id=agent_id, ttl_sec=ttl_sec)
        return {"runtime": name, "container_id": inst.container_id,
                "instance_id": inst.instance_id, "ttl_sec": int(inst.ttl_remaining_sec)}

    def exec(self, container_id: str, cmd: list[str], timeout_sec: int = 60) -> dict[str, Any]:
        inst = RuntimeInstance(spec=_PLACEHOLDER, container_id=container_id)
        code, out, err = self.backend.exec(inst, cmd, timeout_sec=timeout_sec)
        return {"exit_code": code,
                "stdout": (out or b"").decode("utf-8", "replace"),
                "stderr": (err or b"").decode("utf-8", "replace")}

    def reap(self, container_id: str) -> dict[str, Any]:
        self.backend.reap(RuntimeInstance(spec=_PLACEHOLDER, container_id=container_id))
        return {"reaped": container_id}

    def list(self) -> list[dict[str, Any]]:
        import docker
        cs = docker.from_env().containers.list(filters={"label": "parallel-os.runtime"})
        return [{"container_id": c.id, "runtime": c.labels.get("parallel-os.runtime", ""),
                 "status": c.status} for c in cs]
