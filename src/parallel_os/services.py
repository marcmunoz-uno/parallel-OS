"""Service discovery for parallel-OS.

Loads `services/MANIFEST.yaml` and gives agents a typed view of what runtimes
are available on this host. The manifest is the source of truth — service
URLs, auth paths, and job types should never be hardcoded by callers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


_ENV_REF = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


def _expand_env(value: Any) -> Any:
    """Resolve `${VAR}` and `${VAR:-default}` references inside string values."""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            var, default = m.group(1), m.group(2)
            return os.environ.get(var, default if default is not None else "")
        return _ENV_REF.sub(repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


@dataclass
class ServiceAPI:
    host: str
    port: int
    base_url: str
    auth: str
    token_file: str | None = None
    health: str | None = None
    tools_endpoint: str | None = None
    submit_endpoint: str | None = None
    poll_endpoint: str | None = None


@dataclass
class ServiceMCP:
    transport: str
    command: str | None = None
    socket: str | None = None


@dataclass
class Service:
    name: str
    role: str
    status: str
    repo: str
    description: str
    submodule_path: str | None = None
    api: ServiceAPI | None = None
    mcp: ServiceMCP | None = None
    jobs: list[str] = field(default_factory=list)
    forbidden: dict[str, Any] = field(default_factory=dict)
    agent_doc: str | None = None
    deployment_doc: str | None = None

    def read_token(self) -> str | None:
        """Read the bearer token from disk, if this service uses bearer auth."""
        if not self.api or self.api.auth != "bearer" or not self.api.token_file:
            return None
        return Path(self.api.token_file).read_text().strip()


@dataclass
class Manifest:
    version: int
    services: list[Service]

    def get(self, name: str) -> Service:
        for svc in self.services:
            if svc.name == name:
                return svc
        raise KeyError(f"no service named {name!r} in manifest")

    def by_role(self, role: str) -> list[Service]:
        return [svc for svc in self.services if svc.role == role]


def _coerce_service(raw: dict[str, Any]) -> Service:
    api_raw = raw.get("api")
    api = ServiceAPI(**api_raw) if api_raw else None
    mcp_raw = raw.get("mcp")
    mcp = ServiceMCP(**mcp_raw) if mcp_raw else None
    return Service(
        name=raw["name"],
        role=raw["role"],
        status=raw["status"],
        repo=raw["repo"],
        description=raw.get("description", "").strip(),
        submodule_path=raw.get("submodule_path"),
        api=api,
        mcp=mcp,
        jobs=list(raw.get("jobs", [])),
        forbidden=dict(raw.get("forbidden", {})),
        agent_doc=raw.get("agent_doc"),
        deployment_doc=raw.get("deployment_doc"),
    )


def load(manifest_path: str | os.PathLike[str] | None = None) -> Manifest:
    """Load the parallel-OS service manifest. Defaults to the repo's services/MANIFEST.yaml."""
    if manifest_path is None:
        repo_root = Path(__file__).resolve().parents[2]
        manifest_path = repo_root / "services" / "MANIFEST.yaml"
    raw = yaml.safe_load(Path(manifest_path).read_text())
    raw = _expand_env(raw)
    return Manifest(
        version=int(raw["version"]),
        services=[_coerce_service(s) for s in raw.get("services", [])],
    )
