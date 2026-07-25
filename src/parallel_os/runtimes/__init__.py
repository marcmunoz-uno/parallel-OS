"""Runtime registry — the named OS bodies an agent can spawn.

Each entry is a declarative RuntimeSpec (hardened defaults from RuntimeSpec apply:
read-only rootfs, tmpfs /tmp+/work, dropped caps, docker's default seccomp, mem/cpu
caps, TTL). These are BENIGN, pre-baked tool images — no offensive/recon runtimes
here. Add those separately, network-scoped to authorized targets only.

`mcp_entrypoint` is used as the container's keep-alive command; the host execs
tools in via `docker exec` (the in-container MCP server is a future add).
"""
from __future__ import annotations
from parallel_os.orchestrator.runtime import RuntimeSpec

_KEEPALIVE = ["sleep", "infinity"]


def _spec(name: str, image: str, **kw) -> RuntimeSpec:
    base = dict(name=name, image=image, mcp_entrypoint=_KEEPALIVE,
                network_mode="bridge", user="0:0",
                mem_limit_mb=1024, cpu_quota=1.0, default_ttl_sec=1800)
    base.update(kw)
    return RuntimeSpec(**base)


REGISTRY: dict[str, RuntimeSpec] = {
    # general-purpose Linux userland
    "ubuntu": _spec("ubuntu", "ubuntu:24.04"),
    # network/dns diagnostics toolbox (dig, curl, mtr, jq, whois, nmap, ...)
    "netshoot": _spec("netshoot", "nicolaka/netshoot:latest"),
    # document/format conversion — clearly benign "tool the base agent lacks"
    "pandoc": _spec("pandoc", "pandoc/core:latest", network_mode="none"),
}


def get(name: str) -> RuntimeSpec | None:
    return REGISTRY.get(name)
