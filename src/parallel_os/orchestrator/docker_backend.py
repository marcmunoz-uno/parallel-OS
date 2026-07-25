"""Docker backend for the runtime orchestrator.

Spawns containers from RuntimeSpecs, manages lifecycle, executes MCP calls
inside them via `docker exec`. Other backends (podman, Firecracker, gVisor,
remote SSH) implement the same interface.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import structlog

from parallel_os.orchestrator.runtime import RuntimeInstance, RuntimeSpec

if TYPE_CHECKING:
    import docker
    from docker.models.containers import Container

log = structlog.get_logger()


def _seccomp_opt(profile: str) -> list[str]:
    """Map a RuntimeSpec.seccomp_profile to a docker security_opt.

    Docker only accepts `seccomp=unconfined` or `seccomp=<path-to-json>`; the
    built-in default profile is applied when NO seccomp opt is passed. So:
      "default"/""  -> []                       (docker's hardened default)
      "unconfined"  -> ["seccomp=unconfined"]
      "<path.json>" -> ["seccomp=<path.json>"]
    (Previously passed `seccomp=default`, which docker rejects — a 500 on start.)
    """
    if profile in ("", "default"):
        return []
    return [f"seccomp={profile}"]


class DockerBackend:
    """Spawn / reap / exec against a local Docker daemon."""

    def __init__(self, client: "docker.DockerClient | None" = None) -> None:
        if client is None:
            import docker
            client = docker.from_env()
        self._client = client
        self._instances: dict[str, RuntimeInstance] = {}

    def spawn(self, spec: RuntimeSpec, agent_id: str | None = None,
              ttl_sec: int | None = None) -> RuntimeInstance:
        """Create + start a container for this runtime spec."""
        ttl = ttl_sec or spec.default_ttl_sec
        container = self._client.containers.run(
            image=spec.image,
            command=spec.mcp_entrypoint,
            detach=True,
            user=spec.user,
            working_dir=spec.workdir,
            environment=spec.env,
            cap_add=spec.cap_add or None,
            cap_drop=spec.cap_drop or None,
            network_mode=spec.network_mode,
            mem_limit=f"{spec.mem_limit_mb}m",
            nano_cpus=int(spec.cpu_quota * 1_000_000_000),
            read_only=True,
            tmpfs={"/tmp": "rw,size=512m", spec.workdir: "rw,size=2g"},
            security_opt=_seccomp_opt(spec.seccomp_profile),
            remove=False,  # explicit GC; let orchestrator reap
            labels={
                "parallel-os.runtime": spec.name,
                "parallel-os.agent": agent_id or "",
                "parallel-os.spawned_at": str(int(time.time())),
            },
        )
        instance = RuntimeInstance(
            spec=spec,
            container_id=container.id,
            agent_id=agent_id,
            expires_at=time.time() + ttl,
            status="starting",
        )
        self._instances[instance.instance_id] = instance
        log.info("runtime.spawned",
                 runtime=spec.name, instance=instance.instance_id,
                 container=container.id[:12], agent=agent_id, ttl_sec=ttl)
        return instance

    def reap(self, instance: RuntimeInstance, force: bool = False) -> None:
        """Stop + remove the container for an instance."""
        try:
            container: "Container" = self._client.containers.get(instance.container_id)
            container.stop(timeout=5 if not force else 0)
            container.remove(force=True)
        except Exception as exc:
            log.warning("runtime.reap_failed",
                        instance=instance.instance_id, error=str(exc))
        instance.status = "dead"
        self._instances.pop(instance.instance_id, None)
        log.info("runtime.reaped", instance=instance.instance_id, runtime=instance.spec.name)

    def gc_expired(self) -> int:
        """Reap any instances past their TTL. Returns count reaped."""
        expired = [i for i in self._instances.values() if i.is_expired()]
        for inst in expired:
            self.reap(inst)
        return len(expired)

    def exec(self, instance: RuntimeInstance, cmd: list[str],
             stdin: bytes | None = None, timeout_sec: int = 60) -> tuple[int, bytes, bytes]:
        """Execute a command inside the runtime's container.

        Returns (exit_code, stdout, stderr). Used by the MCP request handler
        to translate tool calls into shell commands inside the runtime.
        """
        container: "Container" = self._client.containers.get(instance.container_id)
        # TODO: wire timeout via a SIGTERM watchdog; docker SDK doesn't honor it natively.
        result = container.exec_run(
            cmd=cmd,
            stdin=stdin is not None,
            stdout=True,
            stderr=True,
            demux=True,
        )
        out, err = result.output if isinstance(result.output, tuple) else (result.output, b"")
        return result.exit_code, out or b"", err or b""

    def list_active(self) -> list[RuntimeInstance]:
        return list(self._instances.values())
