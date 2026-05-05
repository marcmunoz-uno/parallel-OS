"""Runtime — base abstraction for an OS execution surface.

A Runtime is a containerized OS environment with an MCP server inside that
exposes its userland tooling. The orchestrator spawns/reaps runtimes on
demand; agents talk to them through the MCP protocol.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RuntimeSpec:
    """Declarative description of a runtime image."""

    name: str                              # "kali", "ubuntu", "arch", ...
    image: str                             # OCI image reference (with tag)
    mcp_entrypoint: list[str]              # how the in-container MCP server starts
    tools_manifest_path: str = "/etc/parallel-os/tools.json"
    cap_add: list[str] = field(default_factory=list)
    cap_drop: list[str] = field(default_factory=lambda: ["ALL"])
    seccomp_profile: str = "default"       # path or named profile
    network_mode: str = "none"             # "none" | "bridge" | "host" | named net
    egress_allowlist: list[str] = field(default_factory=list)
    workdir: str = "/work"
    user: str = "65534:65534"              # nobody:nogroup by default
    env: dict[str, str] = field(default_factory=dict)
    mem_limit_mb: int = 2048
    cpu_quota: float = 2.0                 # CPU cores
    default_ttl_sec: int = 1800
    requires_gpu: bool = False


@dataclass
class RuntimeInstance:
    """A live, spawned runtime — what the orchestrator tracks per session."""

    spec: RuntimeSpec
    container_id: str
    instance_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    spawned_at: float = field(default_factory=time.time)
    expires_at: float = 0.0                # set on spawn from spec.default_ttl_sec
    agent_id: str | None = None
    status: str = "starting"               # "starting" | "ready" | "draining" | "dead"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def ttl_remaining_sec(self) -> float:
        return max(0.0, self.expires_at - time.time())

    def is_expired(self) -> bool:
        return self.ttl_remaining_sec == 0.0
